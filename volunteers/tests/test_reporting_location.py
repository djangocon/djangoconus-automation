"""Where a volunteer goes to start a shift."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone

from volunteers.ical import build_calendar
from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import send_volunteer_welcome

User = get_user_model()


@pytest.fixture
def role(db):
    return Role.objects.create(name="Session Chair", reporting_location="Organizers' room")


def make_shift(role, **kwargs):
    starts_at = timezone.now() + datetime.timedelta(days=1)
    return Shift.objects.create(
        role=role,
        title="Session Chair · Thu",
        location="Ballroom A",
        starts_at=starts_at,
        ends_at=starts_at + datetime.timedelta(hours=2),
        **kwargs,
    )


def test_shift_inherits_the_roles_reporting_location(role):
    assert make_shift(role).where_to_report == "Organizers' room"


def test_a_shift_can_override_the_role(role):
    shift = make_shift(role, reporting_location="Registration desk")

    assert shift.where_to_report == "Registration desk"


def test_no_reporting_location_anywhere_is_blank(db):
    role = Role.objects.create(name="Setup")

    assert make_shift(role).where_to_report == ""


def test_reporting_location_is_kept_apart_from_the_room(role):
    """recompute_span() rewrites `location` from the feed; report-to must survive."""
    shift = make_shift(role, reporting_location="Registration desk")
    shift.talks.create(title="A talk", location="Ballroom B", starts_at=shift.starts_at, ends_at=shift.ends_at)

    shift.recompute_span()
    shift.refresh_from_db()

    assert shift.location == "Ballroom B"
    assert shift.where_to_report == "Registration desk"


def test_the_calendar_feed_says_where_to_report(role):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    signup = VolunteerSignup.objects.create(shift=make_shift(role), user=user)

    ics = build_calendar([signup], host="example.com")

    assert "Report to: Organizers' room" in ics.replace("\r\n ", "")


def test_the_welcome_email_says_where_to_report(role):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    signup = VolunteerSignup.objects.create(shift=make_shift(role), user=user)

    send_volunteer_welcome(signup.pk)

    body = mail.outbox[0].body + "".join(part for part, _ in mail.outbox[0].alternatives)
    assert "Organizers' room" in body


def test_plain_text_emails_do_not_html_escape(role):
    """Plain text has no markup to protect, so escaping only mangles real text."""
    user = User.objects.create_user(username="ada", email="ada@example.com")
    signup = VolunteerSignup.objects.create(shift=make_shift(role), user=user)

    send_volunteer_welcome(signup.pk)

    assert "&#x27;" not in mail.outbox[0].body
