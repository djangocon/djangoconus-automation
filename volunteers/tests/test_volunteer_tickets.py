"""Spotting volunteers who don't hold a ticket."""

import csv
import datetime
import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from titowebhooks.models import TitoWebhookEvent
from titowebhooks.views import EVENT_SLUG
from volunteers.attendance import ticket_index, ticket_status
from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.permissions import grant_chair_group

User = get_user_model()


@pytest.fixture
def chair_client(client, db):
    chair = User.objects.create_user(username="chair", email="chair@example.com")
    chair.groups.add(grant_chair_group())
    client.force_login(chair)
    return client


@pytest.fixture
def shift(db):
    role = Role.objects.create(name="Room Monitor")
    starts_at = timezone.now() + datetime.timedelta(days=1)
    return Shift.objects.create(
        role=role, title="Room Monitor", starts_at=starts_at, ends_at=starts_at + datetime.timedelta(hours=2)
    )


def ticket(email, release="Individual", trigger="ticket.completed"):
    return TitoWebhookEvent.objects.create(
        trigger=trigger,
        timestamp=timezone.now(),
        payload={
            "email": email,
            "name": "A Volunteer",
            "release_title": release,
            "event": {"slug": EVENT_SLUG},
        },
    )


def volunteer(shift, email, **kwargs):
    user = User.objects.create_user(username=email.split("@")[0], email=email, **kwargs)
    VolunteerSignup.objects.create(shift=shift, user=user)
    return user


def test_ticket_index_marks_online_tickets(db):
    ticket("online@example.com", release="Individual- Online")
    ticket("inperson@example.com", release="Individual")

    index = ticket_index()

    assert index["online@example.com"]["online"] is True
    assert index["inperson@example.com"]["online"] is False


def test_ticket_status_defaults_to_no_ticket(db):
    user = User.objects.create_user(username="nobody", email="nobody@example.com")

    assert ticket_status(user, ticket_index())["has_ticket"] is False


def test_a_voided_ticket_reads_as_no_ticket(db):
    """A refunded ticket shouldn't make someone look covered."""
    ticket("refunded@example.com")
    ticket("refunded@example.com", trigger="ticket.voided")
    user = User.objects.create_user(username="refunded", email="refunded@example.com")

    assert ticket_status(user, ticket_index())["has_ticket"] is False


def test_volunteers_page_flags_someone_without_a_ticket(chair_client, shift):
    ticket("has@example.com")
    volunteer(shift, "has@example.com")
    volunteer(shift, "missing@example.com")

    body = chair_client.get(reverse("volunteers:volunteers_list")).content.decode()

    assert "1 volunteer with no ticket" in body
    assert "missing@example.com" in body


def test_volunteers_page_is_quiet_when_everyone_has_a_ticket(chair_client, shift):
    ticket("has@example.com")
    volunteer(shift, "has@example.com")

    body = chair_client.get(reverse("volunteers:volunteers_list")).content.decode()

    assert "no ticket" not in body


def test_export_carries_ticket_columns(chair_client, shift):
    ticket("online@example.com", release="Individual- Online")
    volunteer(shift, "online@example.com")
    volunteer(shift, "missing@example.com")

    response = chair_client.get(reverse("volunteers:export_volunteers"))
    rows = {r["Email"]: r for r in csv.DictReader(io.StringIO(response.content.decode()))}

    assert rows["online@example.com"]["Attending"] == "Online"
    assert rows["online@example.com"]["Has Ticket"] == "Yes"
    assert rows["missing@example.com"]["Has Ticket"] == ""
    # No ticket means we can't claim either mode.
    assert rows["missing@example.com"]["Attending"] == ""
