"""The "I'm available if you need me" offer."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, StandbyOffer, VolunteerSignup, standby_for, total_volunteer_hours
from volunteers.permissions import grant_chair_group

User = get_user_model()


@pytest.fixture
def shift(db):
    role = Role.objects.create(name="Room Monitor")
    starts_at = timezone.now() + datetime.timedelta(days=1)
    return Shift.objects.create(
        role=role, title="Room Monitor", starts_at=starts_at, ends_at=starts_at + datetime.timedelta(hours=2)
    )


def offer(user, shift, before=1, after=1, **kwargs):
    return StandbyOffer.objects.create(
        user=user,
        starts_at=shift.starts_at - datetime.timedelta(hours=before),
        ends_at=shift.ends_at + datetime.timedelta(hours=after),
        **kwargs,
    )


def test_an_offer_spanning_the_shift_counts(shift):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    offer(user, shift)

    assert [o.user for o in standby_for(shift)] == [user]


def test_a_partial_overlap_does_not_count(shift):
    """Free for ten minutes of a two-hour shift is not who you call."""
    user = User.objects.create_user(username="ada", email="ada@example.com")
    StandbyOffer.objects.create(
        user=user,
        starts_at=shift.starts_at,
        ends_at=shift.starts_at + datetime.timedelta(minutes=10),
    )

    assert standby_for(shift) == []


def test_someone_already_on_the_shift_is_not_listed(shift):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    offer(user, shift)
    VolunteerSignup.objects.create(shift=shift, user=user)

    assert standby_for(shift) == []


def test_an_offer_is_not_a_signup(shift):
    """It fills no capacity and counts toward no hours."""
    user = User.objects.create_user(username="ada", email="ada@example.com")
    offer(user, shift)

    assert shift.filled == 0
    assert total_volunteer_hours(user) == 0


def test_a_volunteer_can_add_and_remove_availability(client, shift):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    client.force_login(user)
    starts = shift.starts_at.strftime("%Y-%m-%dT%H:%M")
    ends = shift.ends_at.strftime("%Y-%m-%dT%H:%M")

    client.post(reverse("volunteers:add_standby"), {"starts_at": starts, "ends_at": ends, "note": "anything but AV"})
    assert StandbyOffer.objects.filter(user=user).count() == 1

    client.post(reverse("volunteers:delete_standby", args=[StandbyOffer.objects.get(user=user).pk]))
    assert StandbyOffer.objects.filter(user=user).count() == 0


def test_backwards_times_are_rejected(client, shift):
    user = User.objects.create_user(username="ada", email="ada@example.com")
    client.force_login(user)

    client.post(
        reverse("volunteers:add_standby"),
        {"starts_at": shift.ends_at.strftime("%Y-%m-%dT%H:%M"), "ends_at": shift.starts_at.strftime("%Y-%m-%dT%H:%M")},
    )

    assert StandbyOffer.objects.count() == 0


def test_you_cannot_delete_someone_elses_offer(client, shift):
    owner = User.objects.create_user(username="ada", email="ada@example.com")
    theirs = offer(owner, shift)
    intruder = User.objects.create_user(username="eve", email="eve@example.com")
    client.force_login(intruder)

    assert client.post(reverse("volunteers:delete_standby", args=[theirs.pk])).status_code == 404
    assert StandbyOffer.objects.filter(pk=theirs.pk).exists()


def test_dashboard_offers_a_name_for_an_empty_shift(client, shift):
    chair = User.objects.create_user(username="chair", email="chair@example.com")
    chair.groups.add(grant_chair_group())
    volunteer = User.objects.create_user(username="ada", email="ada@example.com", first_name="Ada", last_name="L")
    offer(volunteer, shift, note="anything but AV")
    client.force_login(chair)

    body = client.get(reverse("volunteers:dashboard")).content.decode()

    assert "Could cover:" in body
    assert "Ada L" in body
    assert "anything but AV" in body


def test_dashboard_stays_quiet_for_a_covered_shift(client, shift):
    chair = User.objects.create_user(username="chair", email="chair@example.com")
    chair.groups.add(grant_chair_group())
    volunteer = User.objects.create_user(username="ada", email="ada@example.com")
    offer(volunteer, shift)
    VolunteerSignup.objects.create(
        shift=shift, user=User.objects.create_user(username="bob", email="bob@example.com")
    )
    client.force_login(chair)

    body = client.get(reverse("volunteers:dashboard")).content.decode()

    assert "Could cover:" not in body
