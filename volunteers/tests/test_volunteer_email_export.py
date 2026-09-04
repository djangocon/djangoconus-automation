"""The dashboard's CSV of volunteer emails, for surveys and follow-up."""

import csv
import datetime
import io

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.permissions import grant_chair_group

User = get_user_model()

EXPORT = "volunteers:export_volunteers"


@pytest.fixture
def chair_client(client, db):
    user = User.objects.create_user(username="chair", email="chair@example.com", password="pw12345!")
    user.groups.add(grant_chair_group())
    client.force_login(user)
    return client


@pytest.fixture
def role(db):
    return Role.objects.create(name="Room Monitor")


def make_shift(role, hours=2, offset_days=-1):
    starts_at = timezone.now() + datetime.timedelta(days=offset_days)
    return Shift.objects.create(
        role=role,
        title=f"{role.name} shift",
        starts_at=starts_at,
        ends_at=starts_at + datetime.timedelta(hours=hours),
        capacity=2,
    )


def rows_of(response):
    return list(csv.DictReader(io.StringIO(response.content.decode())))


def test_export_lists_each_volunteer_once(chair_client, role):
    """Two shifts, one person — one row, with the totals summed."""
    volunteer = User.objects.create_user(
        username="ada", email="ada@example.com", first_name="Ada", last_name="Lovelace"
    )
    for _ in range(2):
        VolunteerSignup.objects.create(shift=make_shift(role), user=volunteer)

    response = chair_client.get(reverse(EXPORT))

    assert response["Content-Type"] == "text/csv"
    assert ".csv" in response["Content-Disposition"]
    rows = rows_of(response)
    assert len(rows) == 1
    assert rows[0]["Name"] == "Ada Lovelace"
    assert rows[0]["Email"] == "ada@example.com"
    assert rows[0]["Shifts"] == "2"
    assert rows[0]["Hours"] == "4.0"
    assert rows[0]["Roles"] == "Room Monitor"


def test_export_skips_cancelled_and_emailless_volunteers(chair_client, role):
    cancelled = User.objects.create_user(username="bailed", email="bailed@example.com")
    VolunteerSignup.objects.create(shift=make_shift(role), user=cancelled, cancelled=True)
    no_email = User.objects.create_user(username="anon", email="")
    VolunteerSignup.objects.create(shift=make_shift(role), user=no_email)
    kept = User.objects.create_user(username="grace", email="grace@example.com")
    VolunteerSignup.objects.create(shift=make_shift(role), user=kept)

    emails = [row["Email"] for row in rows_of(chair_client.get(reverse(EXPORT)))]

    assert emails == ["grace@example.com"]


def test_export_needs_dashboard_access(client, db, role):
    outsider = User.objects.create_user(username="nosy", email="nosy@example.com", password="pw12345!")
    client.force_login(outsider)

    assert client.get(reverse(EXPORT)).status_code == 403
