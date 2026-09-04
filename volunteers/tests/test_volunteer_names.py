"""Putting a name to a volunteer: from their ticket, or typed in by hand."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from titowebhooks.models import TitoWebhookEvent
from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.names import display_name, fill_missing_name
from volunteers.permissions import grant_chair_group

User = get_user_model()


@pytest.fixture
def role(db):
    return Role.objects.create(name="Session Chair")


@pytest.fixture
def shift(role):
    starts_at = timezone.now() + datetime.timedelta(days=1)
    return Shift.objects.create(
        role=role, title="Session Chair · Thu", starts_at=starts_at, ends_at=starts_at + datetime.timedelta(hours=2)
    )


def ticket_for(email, first, last, trigger="ticket.completed"):
    return TitoWebhookEvent.objects.create(
        trigger=trigger,
        timestamp=timezone.now(),
        payload={"email": email, "first_name": first, "last_name": last, "name": f"{first} {last}"},
    )


def test_display_name_prefers_the_real_name(db):
    user = User.objects.create_user(username="ada", email="ada@example.com", first_name="Ada", last_name="Lovelace")
    assert display_name(user) == "Ada Lovelace"


def test_display_name_falls_back_to_email_not_username(db):
    """The username is derived from the address, so it loses information."""
    user = User.objects.create_user(username="ada", email="ada@example.com")
    assert display_name(user) == "ada@example.com"


def test_fill_missing_name_reads_the_ticket(db):
    ticket_for("ada@example.com", "Ada", "Lovelace")
    user = User.objects.create_user(username="ada", email="ada@example.com")

    assert fill_missing_name(user) is True

    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Ada", "Lovelace")


def test_fill_missing_name_matches_case_insensitively(db):
    ticket_for("Ada@Example.COM", "Ada", "Lovelace")
    user = User.objects.create_user(username="ada", email="ada@example.com")

    assert fill_missing_name(user) is True


def test_fill_missing_name_never_overwrites_an_existing_name(db):
    """Someone who corrected their name keeps it."""
    ticket_for("ada@example.com", "Augusta", "Byron")
    user = User.objects.create_user(username="ada", email="ada@example.com", first_name="Ada")

    assert fill_missing_name(user) is False

    user.refresh_from_db()
    assert user.first_name == "Ada"


def test_fill_missing_name_is_a_no_op_without_a_ticket(db):
    user = User.objects.create_user(username="nobody", email="nobody@example.com")

    assert fill_missing_name(user) is False


def test_signing_up_fills_the_name_from_the_ticket(client, shift):
    ticket_for("ada@example.com", "Ada", "Lovelace")
    user = User.objects.create_user(username="ada", email="ada@example.com")
    client.force_login(user)

    client.post(reverse("volunteers:signup", args=[shift.pk]))

    user.refresh_from_db()
    assert user.get_full_name() == "Ada Lovelace"


def test_volunteer_can_set_their_own_name(client, db):
    user = User.objects.create_user(username="nobody", email="nobody@example.com")
    client.force_login(user)

    client.post(reverse("volunteers:update_name"), {"name": "  Grace   Hopper "})

    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Grace", "Hopper")


def test_a_one_word_name_is_kept(client, db):
    user = User.objects.create_user(username="prince", email="prince@example.com")
    client.force_login(user)

    client.post(reverse("volunteers:update_name"), {"name": "Prince"})

    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Prince", "")


def test_dashboard_roster_shows_names(client, shift):
    chair = User.objects.create_user(username="chair", email="chair@example.com")
    chair.groups.add(grant_chair_group())
    volunteer = User.objects.create_user(
        username="ada", email="ada@example.com", first_name="Ada", last_name="Lovelace"
    )
    VolunteerSignup.objects.create(shift=shift, user=volunteer)
    client.force_login(chair)

    body = client.get(reverse("volunteers:dashboard")).content.decode()

    assert "Ada Lovelace" in body


def test_dashboard_roster_falls_back_to_email(client, shift):
    chair = User.objects.create_user(username="chair", email="chair@example.com")
    chair.groups.add(grant_chair_group())
    volunteer = User.objects.create_user(username="anon", email="anon@example.com")
    VolunteerSignup.objects.create(shift=shift, user=volunteer)
    client.force_login(chair)

    body = client.get(reverse("volunteers:dashboard")).content.decode()

    assert "anon@example.com" in body
