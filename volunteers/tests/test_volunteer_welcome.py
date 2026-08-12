"""Welcome someone to the volunteer team the first time they sign up (#133).

A welcome for the person, not a receipt for the shift: it goes out once, on the
signup that made them a volunteer. Signing up for a fifth shift shouldn't
produce a fifth welcome, and cancelling everything then starting again
shouldn't produce a second one either.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import send_volunteer_welcome

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
class TestWelcomeContent:
    def test_it_sends_both_parts(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user)

        assert send_volunteer_welcome(signup.pk) is True
        message = mail.outbox[0]

        assert message.to == [user.email]
        assert message.subject == "Welcome to the DjangoCon US volunteer team"
        assert message.content_subtype == "plain", "the text part must remain the body"
        assert "<html" in html_part(message)

    def test_both_parts_carry_the_shift_the_guide_and_the_link(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user)

        assert send_volunteer_welcome(signup.pk) is True
        message = mail.outbox[0]

        for body in (message.body, html_part(message)):
            assert "Registration Desk — morning" in body
            assert "LaSalle Ballroom" in body
            assert ROLE_DOC in body
            assert "https://automation.defna.org/volunteers/mine/" in body

    def test_it_falls_back_to_the_general_handbook(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(documentation_url=""), user=user)

        assert send_volunteer_welcome(signup.pk) is True
        assert HANDBOOK in mail.outbox[0].body


@pytest.mark.django_db
class TestWhenItSends:
    def test_signing_up_queues_the_welcome_task(self, client, user, monkeypatch):
        """The view hands the send to the worker rather than doing it inline."""
        queued = []
        monkeypatch.setattr("volunteers.views.async_task", lambda name, *args: queued.append((name, args)))
        shift = make_shift()
        client.force_login(user)

        client.post(reverse("volunteers:signup", args=[shift.pk]))

        signup = VolunteerSignup.objects.get(shift=shift, user=user)
        assert ("volunteers.tasks.send_volunteer_welcome", (signup.pk,)) in queued

    def test_only_the_first_signup_is_welcomed(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        first = VolunteerSignup.objects.create(shift=make_shift(), user=user)
        other_shift = make_shift(role_name="Session Chair", documentation_url="https://handbook.example/chair")
        second = VolunteerSignup.objects.create(shift=other_shift, user=user)

        assert send_volunteer_welcome(first.pk) is True
        assert send_volunteer_welcome(second.pk) is False, "a second shift is not a second welcome"

        assert len(mail.outbox) == 1
        assert ROLE_DOC in mail.outbox[0].body

    def test_cancelling_everything_and_starting_again_does_not_re_welcome(self, user, settings):
        """``welcomed`` is a mark on the signup, not a count of live signups."""
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        first = VolunteerSignup.objects.create(shift=make_shift(), user=user)
        assert send_volunteer_welcome(first.pk) is True

        first.cancelled = True
        first.save(update_fields=["cancelled"])
        again = VolunteerSignup.objects.create(shift=make_shift(role_name="Room Monitor"), user=user)

        assert send_volunteer_welcome(again.pk) is False
        assert len(mail.outbox) == 1

    def test_another_volunteer_still_gets_their_own_welcome(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        mine = VolunteerSignup.objects.create(shift=make_shift(), user=user)
        assert send_volunteer_welcome(mine.pk) is True

        someone_else = User.objects.create_user(username="other", email="other@example.com", password="pw12345!")
        theirs = VolunteerSignup.objects.create(shift=make_shift(role_name="Room Monitor"), user=someone_else)

        assert send_volunteer_welcome(theirs.pk) is True
        assert [m.to for m in mail.outbox] == [[user.email], ["other@example.com"]]

    def test_a_cancelled_signup_is_not_welcomed(self, user):
        """Signed up and changed their mind before the worker got to it."""
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user, cancelled=True)

        assert send_volunteer_welcome(signup.pk) is False
        assert mail.outbox == []

    def test_a_missing_signup_does_not_explode(self, db):
        assert send_volunteer_welcome(999999) is False
        assert mail.outbox == []

    def test_a_user_with_no_address_is_skipped(self, db):
        addressless = User.objects.create_user(username="noemail", email="", password="pw12345!")
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=addressless)

        assert send_volunteer_welcome(signup.pk) is False
        assert mail.outbox == []

    def test_a_broken_mail_server_does_not_raise(self, user, monkeypatch):
        """The signup already happened; the email must not be able to undo it."""

        def explode(**kwargs):
            raise OSError("smtp is down")

        monkeypatch.setattr("volunteers.tasks.send_rich_email", explode)
        signup = VolunteerSignup.objects.create(shift=make_shift(), user=user)

        assert send_volunteer_welcome(signup.pk) is False


@pytest.mark.django_db
class TestHandbookLinks:
    def test_the_handbook_is_not_offered_twice(self, user, settings):
        """Some roles point their guide straight at the handbook."""
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(documentation_url=HANDBOOK), user=user)

        assert send_volunteer_welcome(signup.pk) is True
        message = mail.outbox[0]

        assert message.body.count(HANDBOOK) == 1
        assert html_part(message).count(HANDBOOK) == 1

    def test_a_role_guide_and_the_handbook_both_appear_when_they_differ(self, user, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        signup = VolunteerSignup.objects.create(shift=make_shift(documentation_url=ROLE_DOC), user=user)

        assert send_volunteer_welcome(signup.pk) is True
        for body in (mail.outbox[0].body, html_part(mail.outbox[0])):
            assert ROLE_DOC in body
            assert HANDBOOK in body
