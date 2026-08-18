"""Validation on the public travel safety form.

The form is the only place attendee data is checked — there is no API and the
admin bypasses it entirely — so the rules that matter to organizers live here:
a reachable phone number, an arrival we can actually check in against, and a
departure that comes after the arrival rather than before it.
"""

import datetime

import pytest
from django.utils import timezone

from travel_safety.forms import TravelRegistrationForm


def stamp(dt):
    """Format for the datetime-local input, which the form reads as US/Chicago."""
    return timezone.localtime(dt).strftime("%Y-%m-%dT%H:%M")


def valid_data(**overrides):
    """The minimum an attendee has to supply, with everything optional left off."""
    arrival = timezone.now() + datetime.timedelta(days=7)
    data = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone": "+1 (555) 123-4567",
        "preferred_contact": "signal",
        "arrival_airline": "United Airlines",
        "arrival_flight_number": "UA1234",
        "arrival_time": stamp(arrival),
        "arrival_airport": "ORD",
        "emergency_contact_name": "Charles Babbage",
        "emergency_contact_phone": "+1 (555) 987-6543",
    }
    data.update(overrides)
    return data


def test_minimum_required_fields_are_enough():
    form = TravelRegistrationForm(data=valid_data())
    assert form.is_valid(), form.errors


def test_optional_flight_and_freeform_fields_are_accepted():
    departure = timezone.now() + datetime.timedelta(days=12)
    form = TravelRegistrationForm(
        data=valid_data(
            departure_airline="Delta",
            departure_flight_number="DL567",
            departure_time=stamp(departure),
            departure_airport="MDW",
            departure_destination="London Heathrow",
            accommodation="Palmer House, 17 E Monroe St",
            emergency_contact_relationship="Colleague",
            user_notes="Landing late, may sleep through the first check-in.",
        )
    )
    assert form.is_valid(), form.errors


@pytest.mark.parametrize("missing", ["name", "email", "phone", "arrival_flight_number", "emergency_contact_name"])
def test_required_fields_are_enforced(missing):
    form = TravelRegistrationForm(data=valid_data(**{missing: ""}))
    assert not form.is_valid()
    assert missing in form.errors


def test_arrival_in_the_past_is_rejected():
    past = timezone.now() - datetime.timedelta(hours=1)
    form = TravelRegistrationForm(data=valid_data(arrival_time=stamp(past)))
    assert not form.is_valid()
    assert "arrival_time" in form.errors


@pytest.mark.parametrize("field", ["phone", "emergency_contact_phone"])
def test_phone_numbers_need_at_least_ten_digits(field):
    form = TravelRegistrationForm(data=valid_data(**{field: "555-1234"}))
    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.parametrize("field", ["phone", "emergency_contact_phone"])
def test_formatting_characters_do_not_count_toward_the_digit_minimum(field):
    """A number like +1 (555) 123-4567 is ten digits once the punctuation is stripped."""
    form = TravelRegistrationForm(data=valid_data(**{field: "+1 (555) 123-4567"}))
    assert form.is_valid(), form.errors


def test_departure_before_arrival_is_rejected():
    arrival = timezone.now() + datetime.timedelta(days=7)
    form = TravelRegistrationForm(
        data=valid_data(
            arrival_time=stamp(arrival),
            departure_time=stamp(arrival - datetime.timedelta(days=1)),
        )
    )
    assert not form.is_valid()
    assert "departure_time" in form.errors
    assert "arrival_time" in form.errors


def test_departure_at_the_same_moment_as_arrival_is_rejected():
    arrival = timezone.now() + datetime.timedelta(days=7)
    at = stamp(arrival)
    form = TravelRegistrationForm(data=valid_data(arrival_time=at, departure_time=at))
    assert not form.is_valid()
    assert "departure_time" in form.errors


def test_departure_details_without_a_departure_time_are_still_valid():
    """Attendees often know the airline before they've booked the return leg."""
    form = TravelRegistrationForm(data=valid_data(departure_airline="Delta", departure_airport="ORD"))
    assert form.is_valid(), form.errors
