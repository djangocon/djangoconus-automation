import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import (
    CalendarToken,
    Role,
    Shift,
    VolunteerSignup,
    conflicting_shifts,
    total_volunteer_hours,
)

User = get_user_model()


def make_shift(role, *, start_offset_hours=24, length_hours=2, capacity=1, **kwargs):
    start = timezone.now() + datetime.timedelta(hours=start_offset_hours)
    return Shift.objects.create(
        role=role,
        title=kwargs.pop("title", "Test Shift"),
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=length_hours),
        capacity=capacity,
        **kwargs,
    )


@pytest.fixture
def role(db):
    return Role.objects.create(name="Registration Desk")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


def test_signup_creates_record(auth_client, user, role):
    shift = make_shift(role)
    resp = auth_client.post(reverse("volunteers:signup", args=[shift.id]))
    assert resp.status_code == 302
    assert VolunteerSignup.objects.filter(shift=shift, user=user, cancelled=False).count() == 1


def test_signup_allowed_over_capacity(auth_client, user, role):
    """Capacity is a visual guide for organizers, not a hard cap on signups."""
    shift = make_shift(role, capacity=1)
    other = User.objects.create_user(username="other", email="other@example.com", password="pw12345!")
    VolunteerSignup.objects.create(shift=shift, user=other)
    auth_client.post(reverse("volunteers:signup", args=[shift.id]))
    assert VolunteerSignup.objects.filter(shift=shift, user=user, cancelled=False).exists()


def test_signup_blocked_on_time_conflict(auth_client, user, role):
    shift_a = make_shift(role, start_offset_hours=24, length_hours=2, title="A")
    shift_b = make_shift(role, start_offset_hours=25, length_hours=2, title="B")  # overlaps A
    auth_client.post(reverse("volunteers:signup", args=[shift_a.id]))
    auth_client.post(reverse("volunteers:signup", args=[shift_b.id]))
    assert VolunteerSignup.objects.filter(user=user, cancelled=False).count() == 1
    assert conflicting_shifts(user, shift_b) == [shift_a]


def test_signup_blocked_over_hours_cap(auth_client, user, role, settings):
    settings.VOLUNTEER_MAX_HOURS = 3
    long_shift = make_shift(role, length_hours=4, title="Long")
    auth_client.post(reverse("volunteers:signup", args=[long_shift.id]))
    assert not VolunteerSignup.objects.filter(user=user, cancelled=False).exists()


def test_cancel_marks_cancelled(auth_client, user, role):
    shift = make_shift(role)
    signup = VolunteerSignup.objects.create(shift=shift, user=user)
    auth_client.post(reverse("volunteers:cancel", args=[shift.id]))
    signup.refresh_from_db()
    assert signup.cancelled is True


def test_total_volunteer_hours(user, role):
    shift = make_shift(role, length_hours=2)
    VolunteerSignup.objects.create(shift=shift, user=user)
    assert total_volunteer_hours(user) == pytest.approx(2.0)


def test_dashboard_requires_staff(auth_client, client, user):
    resp = auth_client.get(reverse("volunteers:dashboard"))
    assert resp.status_code in (302, 403)


def test_calendar_feed_returns_ics(auth_client, client, user, role):
    shift = make_shift(role, title="Reg Desk")
    VolunteerSignup.objects.create(shift=shift, user=user)
    token = CalendarToken.objects.create(user=user)

    resp = client.get(reverse("volunteers:calendar", args=[token.token]))
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/calendar")
    body = resp.content.decode()
    assert "BEGIN:VCALENDAR" in body
    assert "SUMMARY:Volunteer: Reg Desk" in body
    assert "END:VCALENDAR" in body


def test_calendar_feed_excludes_cancelled(client, user, role):
    shift = make_shift(role, title="Cancelled One")
    VolunteerSignup.objects.create(shift=shift, user=user, cancelled=True)
    token = CalendarToken.objects.create(user=user)

    resp = client.get(reverse("volunteers:calendar", args=[token.token]))
    assert "Cancelled One" not in resp.content.decode()
