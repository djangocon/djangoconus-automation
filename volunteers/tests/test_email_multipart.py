"""Volunteer emails go out as text plus an HTML alternative.

The text part stays the body rather than becoming a courtesy afterthought: a
client that refuses HTML still has to receive a usable email.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import notify_shift_uncovered, send_shift_reminders

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="vol", email="vol@example.com", password="pw12345!", first_name="Ada", last_name="Lovelace"
    )


@pytest.fixture
def site(db):
    site = Site.objects.get_current()
    site.domain = "automation.defna.org"
    site.save()
    Site.objects.clear_cache()
    return site


@pytest.fixture
def signup(user, db):
    role = Role.objects.create(name="Registration Desk", documentation_url="https://handbook.example/desk")
    start = timezone.now() + datetime.timedelta(hours=2)
    shift = Shift.objects.create(
        role=role,
        title="Registration Desk — morning",
        location="LaSalle Ballroom",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
    )
    return VolunteerSignup.objects.create(shift=shift, user=user)


def html_part(message):
    for content, mimetype in message.alternatives:
        if mimetype == "text/html":
            return content
    raise AssertionError("no text/html alternative on the message")


@pytest.mark.django_db
class TestShiftReminderMultipart:
    def test_has_both_a_text_body_and_an_html_alternative(self, signup, site):
        assert send_shift_reminders() == 1
        message = mail.outbox[0]

        assert message.content_subtype == "plain", "the text part must remain the body"
        assert "<html" in html_part(message)

    def test_both_parts_carry_the_shift_and_the_links(self, signup, site):
        assert send_shift_reminders() == 1
        message = mail.outbox[0]

        for body in (message.body, html_part(message)):
            assert "Registration Desk — morning" in body
            assert "LaSalle Ballroom" in body
            assert "https://handbook.example/desk" in body
            assert "https://automation.defna.org/volunteers/mine/" in body

    def test_html_escapes_a_hostile_shift_title(self, signup, site):
        signup.shift.title = "<script>alert(1)</script>"
        signup.shift.save(update_fields=["title"])

        assert send_shift_reminders() == 1
        html = html_part(mail.outbox[0])
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


@pytest.mark.django_db
class TestUncoveredAlertMultipart:
    @pytest.fixture
    def cancelled(self, signup):
        signup.cancelled = True
        signup.save(update_fields=["cancelled"])
        VolunteerSignup.objects.filter(pk=signup.pk).update(created_at=timezone.now() - datetime.timedelta(hours=2))
        return signup

    def test_has_both_parts(self, cancelled, site, settings):
        settings.VOLUNTEER_COORDINATOR_EMAILS = ["coordinator@example.com"]

        assert notify_shift_uncovered(cancelled.pk) is True
        message = mail.outbox[0]

        assert message.content_subtype == "plain"
        assert "<html" in html_part(message)

    def test_both_parts_name_who_cancelled_and_link_the_dashboard(self, cancelled, site, settings):
        settings.VOLUNTEER_COORDINATOR_EMAILS = ["coordinator@example.com"]

        assert notify_shift_uncovered(cancelled.pk) is True
        message = mail.outbox[0]

        for body in (message.body, html_part(message)):
            assert "Ada Lovelace" in body
            assert "https://automation.defna.org/volunteers/dashboard/" in body
