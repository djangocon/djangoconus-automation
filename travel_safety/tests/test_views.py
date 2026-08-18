"""The public register → success flow.

The page is linked from the homepage and is open to anyone — no login — so the
two things worth pinning down are that a good submission actually lands in the
database as ``pending_arrival``, and that the success page only ever shows the
registration belonging to the person who just submitted it.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from travel_safety.models import TravelRegistration

from .test_forms import stamp, valid_data


@pytest.fixture
def register_url():
    return reverse("travel_safety:register")


@pytest.fixture
def success_url():
    return reverse("travel_safety:success")


def test_register_page_is_public(client, register_url):
    response = client.get(register_url)
    assert response.status_code == 200
    assert "DjangoCon US 2026 Travel Safety Registration" in response.content.decode()


@pytest.mark.django_db
def test_valid_submission_creates_a_pending_arrival_registration(client, register_url, success_url):
    response = client.post(register_url, data=valid_data())

    assert response.status_code == 302
    assert response.url == success_url

    registration = TravelRegistration.objects.get()
    assert registration.name == "Ada Lovelace"
    assert registration.status == "pending_arrival"
    assert registration.preferred_contact == "signal"


@pytest.mark.django_db
def test_optional_departure_details_round_trip(client, register_url):
    departure = timezone.now() + datetime.timedelta(days=12)
    client.post(
        register_url,
        data=valid_data(
            departure_time=stamp(departure),
            departure_airport="MDW",
            accommodation="Palmer House, 17 E Monroe St",
        ),
    )

    registration = TravelRegistration.objects.get()
    assert registration.departure_airport == "MDW"
    assert registration.accommodation == "Palmer House, 17 E Monroe St"


@pytest.mark.django_db
def test_invalid_submission_saves_nothing_and_redisplays_the_form(client, register_url):
    response = client.post(register_url, data=valid_data(email="not-an-email"))

    assert response.status_code == 200
    assert not TravelRegistration.objects.exists()
    assert response.context["form"].errors


@pytest.mark.django_db
def test_success_page_shows_the_registration_just_submitted(client, register_url, success_url):
    client.post(register_url, data=valid_data())

    response = client.get(success_url)

    assert response.status_code == 200
    assert response.context["registration"] == TravelRegistration.objects.get()


@pytest.mark.django_db
def test_success_page_forgets_the_registration_after_showing_it_once(client, register_url, success_url):
    """A shared or bookmarked success URL must not leak the previous submission."""
    client.post(register_url, data=valid_data())
    client.get(success_url)

    response = client.get(success_url)

    assert response.status_code == 200
    assert "registration" not in response.context


@pytest.mark.django_db
def test_success_page_is_reachable_without_a_submission(client, success_url):
    response = client.get(success_url)

    assert response.status_code == 200
    assert "registration" not in response.context
