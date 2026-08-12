"""Confirm a shift the moment someone takes it (#133).

Rachell's ask: tell volunteers where to change their shifts and give them the
handbook for the role they signed up for. The reminder does that the day before
(#134); this does it at signup, which is when people are actually deciding
whether they understood what they volunteered for.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import send_signup_confirmation

User = get_user_model()

ROLE_DOC = "https://handbook.example/registration-desk"
HANDBOOK = "https://handbook.example/general"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture(autouse=True)
def site(db):
    site = Site.objects.get_current()
    site.domain = "automation.defna.org"
    site.save()
    Site.objects.clear_cache()
    return site


def make_shift(*, documentation_url=ROLE_DOC, role_name="Registration Desk"):
    role = Role.objects.create(name=role_name, documentation_url=documentation_url)
    start = timezone.now() + datetime.timedelta(days=2)
    return Shift.objects.create(
        role=role,
        title="Registration Desk — morning",
        location="LaSalle Ballroom",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
    )


def html_part(message):
    for content, mimetype in message.alternatives:
        if mimetype == "text/html":
            return content
    raise AssertionError("no text/html alternative on the message")


@pytest.mark.django_db
class TestConfirmationContent:
    def test_it_sends_both_parts(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user)

        assert send_signup_confirmation(signup.pk) is True
        message = mail.outbox[0]

        assert message.to == [user.email]
        assert "DjangoCon US" in message.subject
        assert message.content_subtype == "plain", "the text part must remain the body"
        assert "<html" in html_part(message)

    def test_both_parts_carry_the_shift_the_guide_and_the_link(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user)

        assert send_signup_confirmation(signup.pk) is True
        message = mail.outbox[0]

        for body in (message.body, html_part(message)):
            assert "Registration Desk — morning" in body
            assert "LaSalle Ballroom" in body
            assert ROLE_DOC in body
            assert "https://automation.defna.org/volunteers/mine/" in body

    def test_it_falls_back_to_the_general_handbook(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(documentation_url=""), user=user)

        assert send_signup_confirmation(signup.pk) is True
        assert HANDBOOK in mail.outbox[0].body


@pytest.mark.django_db
class TestWhenItSends:
    def test_signing_up_queues_a_confirmation(self, client, user, monkeypatch):
        """The view hands the send to the worker rather than doing it inline."""
        queued = []
        monkeypatch.setattr("volunteers.views.async_task", lambda name, *args: queued.append((name, args)))
        shift = make_shift()
        client.force_login(user)

        client.post(reverse("volunteers:signup", args=[shift.pk]))

        signup = VolunteerSignup.objects.get(shift=shift, user=user)
        assert ("volunteers.tasks.send_signup_confirmation", (signup.pk,)) in queued

    def test_a_second_shift_in_a_different_role_is_also_confirmed(self, user, settings):
        """The role guide is the point, so each role has to send its own."""
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        first = VolunteerSignup.objects.create(shift=make_shift(), user=user)
        other_shift = make_shift(role_name="Session Chair", documentation_url="https://handbook.example/chair")
        second = VolunteerSignup.objects.create(shift=other_shift, user=user)

        assert send_signup_confirmation(first.pk) is True
        assert send_signup_confirmation(second.pk) is True

        assert len(mail.outbox) == 2
        assert ROLE_DOC in mail.outbox[0].body
        assert "https://handbook.example/chair" in mail.outbox[1].body

    def test_a_cancelled_signup_is_not_confirmed(self, user):
        """Signed up and changed their mind before the worker got to it."""
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user, cancelled=True)

        assert send_signup_confirmation(signup.pk) is False
        assert mail.outbox == []

    def test_a_missing_signup_does_not_explode(self, db):
        assert send_signup_confirmation(999999) is False
        assert mail.outbox == []

    def test_a_user_with_no_address_is_skipped(self, db):
        addressless = User.objects.create_user(username="noemail", email="", password="pw12345!")
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=addressless)

        assert send_signup_confirmation(signup.pk) is False
        assert mail.outbox == []

    def test_a_broken_mail_server_does_not_raise(self, user, monkeypatch):
        """The signup already happened; the email must not be able to undo it."""

        def explode(**kwargs):
            raise OSError("smtp is down")

        monkeypatch.setattr("volunteers.tasks.send_rich_email", explode)
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user)

        assert send_signup_confirmation(signup.pk) is False
