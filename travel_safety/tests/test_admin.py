"""The organizer-facing changelist.

The status badge sat in this admin unused from the app's first commit until
2026 — defined, never added to ``list_display``, so it rendered nowhere. These
tests assert it actually reaches the page, and that wiring it in didn't cost
the inline status dropdown organizers use to work the list during check-in.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from travel_safety.admin import STATUS_COLORS
from travel_safety.models import TravelRegistration

User = get_user_model()


@pytest.fixture
def changelist_url():
    return reverse("admin:travel_safety_travelregistration_changelist")


@pytest.fixture
def staff_client(client, db):
    user = User.objects.create_superuser(username="organizer", email="organizer@example.com", password="pw12345!")
    client.force_login(user)
    return client


def make_registration(*, status="pending_arrival", name="Ada Lovelace"):
    return TravelRegistration.objects.create(
        name=name,
        email="ada@example.com",
        phone="+1 (555) 123-4567",
        arrival_airline="United Airlines",
        arrival_flight_number="UA1234",
        arrival_time=timezone.now(),
        arrival_airport="ORD",
        emergency_contact_name="Charles Babbage",
        emergency_contact_phone="+1 (555) 987-6543",
        status=status,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("status,color", sorted(STATUS_COLORS.items()))
def test_every_status_renders_its_badge_colour(staff_client, changelist_url, status, color):
    make_registration(status=status)

    content = staff_client.get(changelist_url).content.decode()

    assert f"background-color: {color}" in content


@pytest.mark.django_db
def test_badge_shows_the_human_readable_status(staff_client, changelist_url):
    make_registration(status="emergency_contact_notified")

    content = staff_client.get(changelist_url).content.decode()

    assert "Emergency Contact Notified" in content


@pytest.mark.django_db
def test_status_is_still_editable_from_the_list(staff_client, changelist_url):
    """The badge is display-only, so the list_editable dropdown has to survive alongside it."""
    registration = make_registration()

    content = staff_client.get(changelist_url).content.decode()

    assert 'name="form-0-status"' in content
    assert f'value="{registration.pk}"' in content


@pytest.mark.django_db
def test_every_status_choice_has_a_colour():
    """A new status added to the model without a colour would silently render grey."""
    assert set(STATUS_COLORS) == {value for value, _ in TravelRegistration.STATUS_CHOICES}
