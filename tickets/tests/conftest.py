# tests/conftest.py

import pytest

from tickets.models import TicketLink


@pytest.fixture
def ticket_link(db):
    return TicketLink.objects.create(link="https://example.com/ticket")


@pytest.fixture
def ticket_links(db):
    return [TicketLink.objects.create(link=f"https://example.com/ticket{i}") for i in range(1, 4)]
