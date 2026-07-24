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
    merge_shifts,
    split_shift,
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
    from volunteers.models import Talk

    shift = make_shift(role, title="A Talk")
    Talk.objects.create(
        shift=shift,
        external_uid="a-talk@x",
        title="A Talk",
        talk_url="https://2026.djangocon.us/talks/a-talk/",
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
    )
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
    staff = User.objects.create_user(
        username="staffer2", email="staff2@example.com", password="pw12345!", is_staff=True
    )
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
    staff = User.objects.create_user(
        username="staffer3", email="staff3@example.com", password="pw12345!", is_staff=True
    )
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


def test_signup_preserves_filters_via_next(auth_client, user, role):
    shift = make_shift(role)
    filtered = reverse("volunteers:shifts") + "?needs_help=1"
    resp = auth_client.post(reverse("volunteers:signup", args=[shift.id]), {"next": filtered})
    assert resp.status_code == 302
    assert resp.url == filtered


def test_signup_rejects_offsite_next(auth_client, user, role):
    shift = make_shift(role)
    resp = auth_client.post(reverse("volunteers:signup", args=[shift.id]), {"next": "https://evil.example.com/"})
    assert resp.status_code == 302
    assert resp.url == reverse("volunteers:shifts")


def test_cancel_preserves_filters_via_next(auth_client, user, role):
    shift = make_shift(role)
    VolunteerSignup.objects.create(shift=shift, user=user)
    filtered = reverse("volunteers:shifts") + "?needs_help=1"
    resp = auth_client.post(reverse("volunteers:cancel", args=[shift.id]), {"next": filtered})
    assert resp.status_code == 302
    assert resp.url == filtered


def _staff(auth_client, username):
    User = get_user_model()
    staff = User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pw12345!", is_staff=True
    )
    auth_client.force_login(staff)
    return staff


def test_dashboard_date_filter(auth_client, role):
    _staff(auth_client, "dstaff")
    make_shift(role, title="Day One", start_offset_hours=24)
    make_shift(role, title="Day Two", start_offset_hours=24 + 48)

    d1 = (timezone.now() + datetime.timedelta(hours=24)).date().isoformat()
    resp = auth_client.get(reverse("volunteers:dashboard"), {"date": d1})
    body = resp.content.decode()
    assert "Day One" in body
    assert "Day Two" not in body


def test_volunteers_list_shows_hours(auth_client, user, role):
    _staff(auth_client, "vstaff")
    shift = make_shift(role, length_hours=3, title="Long Shift")
    VolunteerSignup.objects.create(shift=shift, user=user)

    resp = auth_client.get(reverse("volunteers:volunteers_list"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert user.email in body
    assert "3.0" in body


def test_volunteers_list_requires_staff(auth_client):
    resp = auth_client.get(reverse("volunteers:volunteers_list"))
    assert resp.status_code in (302, 403)


def test_volunteers_list_sort_by_hours(auth_client, role):
    User = get_user_model()
    _staff(auth_client, "sortstaff")
    big = User.objects.create_user(username="big", email="big@example.com", password="pw12345!")
    small = User.objects.create_user(username="small", email="small@example.com", password="pw12345!")
    VolunteerSignup.objects.create(shift=make_shift(role, length_hours=4, title="Big"), user=big)
    VolunteerSignup.objects.create(
        shift=make_shift(role, length_hours=1, title="Small", start_offset_hours=48), user=small
    )

    resp = auth_client.get(reverse("volunteers:volunteers_list"), {"sort": "hours"})
    body = resp.content.decode()
    assert body.index("big@example.com") < body.index("small@example.com")


def _talk_shift(role, title, start_offset_hours, length_hours=1, location="Room A"):
    from volunteers.models import Talk

    shift = make_shift(
        role, title=title, start_offset_hours=start_offset_hours, length_hours=length_hours, location=location
    )
    Talk.objects.create(
        shift=shift,
        external_uid=f"{title}@x",
        title=title,
        location=location,
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
    )
    return shift


def test_merge_shifts_combines_talks(auth_client, role):
    _staff(auth_client, "mstaff")
    a = _talk_shift(role, "Talk A", 24)
    b = _talk_shift(role, "Talk B", 25)
    resp = auth_client.post(reverse("volunteers:merge_shifts"), {"shift": [a.id, b.id]})
    assert resp.status_code == 302
    a.refresh_from_db()
    assert a.talks.count() == 2
    assert not Shift.objects.filter(id=b.id).exists()
    assert a.is_block


def test_merge_rejects_different_rooms(auth_client, role):
    _staff(auth_client, "mstaff2")
    a = _talk_shift(role, "Talk A", 24, location="Room A")
    b = _talk_shift(role, "Talk B", 25, location="Room B")
    auth_client.post(reverse("volunteers:merge_shifts"), {"shift": [a.id, b.id]})
    assert Shift.objects.filter(id=b.id).exists()  # not merged


def test_split_block_restores_per_talk_shifts(auth_client, user, role):
    _staff(auth_client, "sstaff")
    a = _talk_shift(role, "Talk A", 24)
    b = _talk_shift(role, "Talk B", 25)
    merge_shifts([a, b])
    VolunteerSignup.objects.create(shift=a, user=user)

    resp = auth_client.post(reverse("volunteers:split_shift", args=[a.id]))
    assert resp.status_code == 302
    a.refresh_from_db()
    assert a.talks.count() == 1
    # a new shift now covers the second talk, and the volunteer rides along
    assert Shift.objects.filter(talks__title="Talk B").exists()
    other = Shift.objects.get(talks__title="Talk B")
    assert VolunteerSignup.objects.filter(shift=other, user=user, cancelled=False).exists()


def test_merge_desk_shifts_without_talks(auth_client, role):
    _staff(auth_client, "deskstaff")
    # Two back-to-back Registration Desk hourly slots (no talks).
    a = make_shift(role, title="Reg 8am", start_offset_hours=24, length_hours=1, location="Lobby")
    b = make_shift(role, title="Reg 9am", start_offset_hours=25, length_hours=1, location="Lobby")
    resp = auth_client.post(reverse("volunteers:merge_shifts"), {"shift": [a.id, b.id]})
    assert resp.status_code == 302
    a.refresh_from_db()
    assert a.is_block  # became a 2-slot block
    assert a.talks.count() == 2
    assert not Shift.objects.filter(id=b.id).exists()
    # ...and it can be split back apart.
    split_shift(a)
    a.refresh_from_db()
    assert a.talks.count() == 1
    assert Shift.objects.filter(role=role, location="Lobby").count() == 2


def test_merge_rejects_different_roles(auth_client, role):
    _staff(auth_client, "rolestaff")
    other_role = Role.objects.create(name="Setup Crew")
    a = make_shift(role, title="A", start_offset_hours=24, length_hours=1, location="Lobby")
    b = make_shift(other_role, title="B", start_offset_hours=25, length_hours=1, location="Lobby")
    auth_client.post(reverse("volunteers:merge_shifts"), {"shift": [a.id, b.id]})
    assert Shift.objects.filter(id=b.id).exists()  # not merged


def test_update_contact_info_requires_staff(auth_client):
    # A plain volunteer can't edit the site-wide contact info.
    resp = auth_client.post(reverse("volunteers:update_contact"), {"contact_info": "hax"})
    assert resp.status_code in (302, 403)
    from volunteers.models import SiteContactInfo

    assert SiteContactInfo.objects.first() is None or SiteContactInfo.objects.first().contact_info != "hax"


def test_staff_updates_site_contact_info(auth_client):
    _staff(auth_client, "coordinator")
    resp = auth_client.post(reverse("volunteers:update_contact"), {"contact_info": "**Slack:** #volunteers"})
    assert resp.status_code == 302
    from volunteers.models import SiteContactInfo

    assert SiteContactInfo.get_solo().contact_info == "**Slack:** #volunteers"


def test_my_shifts_shows_contact_info_readonly(auth_client, user):
    from volunteers.models import SiteContactInfo

    SiteContactInfo.objects.create(contact_info="reach the chairs on **Slack**")
    resp = auth_client.get(reverse("volunteers:my_shifts"))
    body = resp.content.decode()
    assert "reach the chairs on **Slack**" in body
    # ...but no edit form for a plain volunteer.
    assert 'action="/volunteers/mine/contact/"' not in body


def test_delete_shift_from_dashboard(auth_client, role):
    _staff(auth_client, "delstaff")
    shift = make_shift(role, title="Doomed")
    resp = auth_client.post(reverse("volunteers:delete_shift", args=[shift.id]))
    assert resp.status_code == 302
    assert not Shift.objects.filter(id=shift.id).exists()
