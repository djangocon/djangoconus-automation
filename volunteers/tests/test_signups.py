import datetime
from unittest import mock

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


def test_shift_list_visible_to_anonymous(client, role):
    make_shift(role, title="Reg Desk")
    resp = client.get(reverse("volunteers:shifts"))
    assert resp.status_code == 200
    assert "Reg Desk" in resp.content.decode()


def test_shift_list_shows_role_documentation(client, role):
    role.documentation_url = "https://docs.example.com/reg-desk/"
    role.save()
    make_shift(role, title="Reg Desk")
    resp = client.get(reverse("volunteers:shifts"))
    assert "https://docs.example.com/reg-desk/" in resp.content.decode()


def test_shift_list_shows_talk_url(client, role):
    make_shift(role, title="A Talk", talk_url="https://2026.djangocon.us/talks/a-talk/")
    resp = client.get(reverse("volunteers:shifts"))
    assert "https://2026.djangocon.us/talks/a-talk/" in resp.content.decode()


def test_my_shifts_shows_role_documentation(auth_client, user, role):
    role.documentation_url = "https://docs.example.com/reg-desk/"
    role.save()
    shift = make_shift(role, title="Reg Desk")
    VolunteerSignup.objects.create(shift=shift, user=user)
    resp = auth_client.get(reverse("volunteers:my_shifts"))
    assert "https://docs.example.com/reg-desk/" in resp.content.decode()


def test_shift_list_filters_by_role(client, role):
    other_role = Role.objects.create(name="Room Monitor")
    make_shift(role, title="Reg Desk Shift")
    make_shift(other_role, title="Room Monitor Shift")

    resp = client.get(reverse("volunteers:shifts"), {"role": role.name})
    body = resp.content.decode()
    assert "Reg Desk Shift" in body
    assert "Room Monitor Shift" not in body


def test_shift_list_needs_help_filter(client, role):
    open_shift = make_shift(role, title="Needs Help", capacity=2)
    staffed_shift = make_shift(role, title="Already Staffed", capacity=2, start_offset_hours=48)
    other = User.objects.create_user(username="other", email="other@example.com", password="pw12345!")
    VolunteerSignup.objects.create(shift=staffed_shift, user=other)

    resp = client.get(reverse("volunteers:shifts"), {"needs_help": "1"})
    body = resp.content.decode()
    assert "Needs Help" in body
    assert "Already Staffed" not in body
    assert open_shift.id != staffed_shift.id


def test_dashboard_filters_by_role_and_location(auth_client, role):
    staff = User.objects.create_user(username="staffer", email="staff@example.com", password="pw12345!", is_staff=True)
    auth_client.force_login(staff)

    other_role = Role.objects.create(name="Setup Crew")
    make_shift(role, title="Front Desk", location="Lobby")
    make_shift(other_role, title="Setup Shift", location="Ballroom")

    resp = auth_client.get(reverse("volunteers:dashboard"), {"role": role.name})
    body = resp.content.decode()
    assert "Front Desk" in body
    assert "Setup Shift" not in body

    resp = auth_client.get(reverse("volunteers:dashboard"), {"location": "Ballroom"})
    body = resp.content.decode()
    assert "Setup Shift" in body
    assert "Front Desk" not in body


def test_dashboard_hides_past_shifts_by_default(auth_client, role):
    staff = User.objects.create_user(username="staffer2", email="staff2@example.com", password="pw12345!", is_staff=True)
    auth_client.force_login(staff)

    make_shift(role, title="Past Shift", start_offset_hours=-4, length_hours=1)
    make_shift(role, title="Future Shift", start_offset_hours=24)

    resp = auth_client.get(reverse("volunteers:dashboard"))
    body = resp.content.decode()
    assert "Future Shift" in body
    assert "Past Shift" not in body

    resp = auth_client.get(reverse("volunteers:dashboard"), {"show_past": "1"})
    body = resp.content.decode()
    assert "Past Shift" in body


def test_dashboard_open_only_filter(auth_client, role):
    staff = User.objects.create_user(username="staffer3", email="staff3@example.com", password="pw12345!", is_staff=True)
    auth_client.force_login(staff)

    make_shift(role, title="Needs Volunteers", capacity=2)
    staffed = make_shift(role, title="Fully Covered", capacity=2, start_offset_hours=48)
    other = User.objects.create_user(username="other2", email="other2@example.com", password="pw12345!")
    VolunteerSignup.objects.create(shift=staffed, user=other)

    resp = auth_client.get(reverse("volunteers:dashboard"), {"open_only": "1"})
    body = resp.content.decode()
    assert "Needs Volunteers" in body
    assert "Fully Covered" not in body


def test_sync_schedule_requires_staff(auth_client):
    resp = auth_client.post(reverse("volunteers:sync_schedule"))
    assert resp.status_code in (302, 403)


def test_sync_schedule_runs_import(auth_client):
    staff = User.objects.create_user(username="synner", email="sync@example.com", password="pw12345!", is_staff=True)
    auth_client.force_login(staff)

    with mock.patch("volunteers.views.call_command") as mock_call:
        resp = auth_client.post(reverse("volunteers:sync_schedule"))

    assert resp.status_code == 302
    mock_call.assert_called_once()
    assert mock_call.call_args.kwargs.get("dry_run") is False


def test_sync_schedule_dry_run(auth_client):
    staff = User.objects.create_user(username="synner2", email="sync2@example.com", password="pw12345!", is_staff=True)
    auth_client.force_login(staff)

    with mock.patch("volunteers.views.call_command") as mock_call:
        resp = auth_client.post(reverse("volunteers:sync_schedule"), {"dry_run": "1"})

    assert resp.status_code == 302
    assert mock_call.call_args.kwargs.get("dry_run") is True
