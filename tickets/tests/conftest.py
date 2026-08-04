# tests/conftest.py

import pytest

from tickets.models import OnlineAttendee, TicketLink


@pytest.fixture
def ticket_link(db):
    return TicketLink.objects.create(link="https://example.com/ticket")


@pytest.fixture
def ticket_links(db):
    return [TicketLink.objects.create(link=f"https://example.com/ticket{i}") for i in range(1, 4)]


@pytest.fixture
def attendee(db):
    return OnlineAttendee.objects.create(
        email="online@example.com",
        name="Online Buyer",
        year=2026,
        release_title="Conference (Online)",
    )


@pytest.fixture
def queued_tasks(monkeypatch):
    """Capture async_task dispatches instead of hitting the django-q broker."""
    calls = []
    monkeypatch.setattr("tickets.services.async_task", lambda *args, **kwargs: calls.append((args, kwargs)))
    return calls


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(
        username="staffer",
        email="staffer@example.com",
        password="password",
        is_staff=True,
    )
