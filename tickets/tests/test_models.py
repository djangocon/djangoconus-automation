import pytest
from django.utils import timezone

from tickets.models import TicketLink


@pytest.mark.django_db
def test_ticketlink_creation(ticket_link):
    assert ticket_link.id is not None
    assert ticket_link.link == "https://example.com/ticket"
    assert ticket_link.date_link_created is not None
    assert ticket_link.attendee_email is None


@pytest.mark.django_db
def test_ticketlink_assignment(ticket_link):
    assign_time = timezone.now()
    ticket_link.attendee_email = "test@example.com"
    ticket_link.date_link_assigned = assign_time
    ticket_link.save()

    updated_ticket_link = TicketLink.objects.get(id=ticket_link.id)
    assert updated_ticket_link.attendee_email == "test@example.com"
    assert updated_ticket_link.date_link_assigned == assign_time
