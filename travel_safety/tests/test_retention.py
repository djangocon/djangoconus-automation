"""The 30-days-after-the-conference deletion promise.

The register page tells attendees their travel details are deleted 30 days
after the conference ends, so this runs daily and has to hold both halves of
that promise: nothing goes early, and once the window closes nothing is left.
"""

import datetime

import pytest
from django.utils import timezone

from travel_safety.models import TravelRegistration
from travel_safety.tasks import RETENTION_DAYS, enforce_retention


@pytest.fixture
def today():
    return timezone.localdate()


def make_registration(*, created_days_ago=0, name="Ada Lovelace"):
    """A registration whose ``created_at`` is backdated past ``auto_now_add``."""
    registration = TravelRegistration.objects.create(
        name=name,
        email=f"{name.split()[0].lower()}@example.com",
        phone="+1 (555) 123-4567",
        arrival_airline="United Airlines",
        arrival_flight_number="UA1234",
        arrival_time=timezone.now(),
        arrival_airport="ORD",
        emergency_contact_name="Charles Babbage",
        emergency_contact_phone="+1 (555) 987-6543",
    )
    created_at = timezone.now() - datetime.timedelta(days=created_days_ago)
    TravelRegistration.objects.filter(pk=registration.pk).update(created_at=created_at)
    registration.refresh_from_db()
    return registration


def test_the_window_is_thirty_days():
    assert RETENTION_DAYS == 30


@pytest.mark.django_db
def test_nothing_is_deleted_while_the_conference_is_still_ahead(settings, today):
    settings.CONFERENCE_END_DATE = today + datetime.timedelta(days=8)
    make_registration()

    enforce_retention()

    assert TravelRegistration.objects.count() == 1


@pytest.mark.django_db
def test_nothing_is_deleted_the_day_before_the_window_closes(settings, today):
    settings.CONFERENCE_END_DATE = today - datetime.timedelta(days=RETENTION_DAYS - 1)
    make_registration()

    enforce_retention()

    assert TravelRegistration.objects.count() == 1


@pytest.mark.django_db
def test_registrations_are_deleted_on_the_day_the_window_closes(settings, today):
    settings.CONFERENCE_END_DATE = today - datetime.timedelta(days=RETENTION_DAYS)
    make_registration(created_days_ago=45)

    enforce_retention()

    assert TravelRegistration.objects.count() == 0


@pytest.mark.django_db
def test_registrations_are_still_deleted_after_the_window_has_passed(settings, today):
    """The job is idempotent and catches up if the cluster missed a day."""
    settings.CONFERENCE_END_DATE = today - datetime.timedelta(days=RETENTION_DAYS + 60)
    make_registration(created_days_ago=90)

    enforce_retention()

    assert TravelRegistration.objects.count() == 0


@pytest.mark.django_db
def test_every_registration_from_this_year_goes(settings, today):
    """Whenever they signed up — months early or the morning of — it all goes."""
    settings.CONFERENCE_END_DATE = today - datetime.timedelta(days=RETENTION_DAYS)
    make_registration(created_days_ago=200, name="Ada Lovelace")
    make_registration(created_days_ago=37, name="Grace Hopper")
    make_registration(created_days_ago=31, name="Alan Turing")

    enforce_retention()

    assert TravelRegistration.objects.count() == 0


@pytest.mark.django_db
def test_an_empty_table_is_a_no_op(settings, today):
    settings.CONFERENCE_END_DATE = today - datetime.timedelta(days=RETENTION_DAYS)

    enforce_retention()

    assert TravelRegistration.objects.count() == 0
