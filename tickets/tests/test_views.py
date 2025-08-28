# tests/test_views.py

import pytest

from tickets.models import TicketLink


@pytest.mark.django_db
def test_tickets_info_view_get_form(tp):
    """Test that tickets info view shows the claim form when no POST data"""
    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "form" in response.context
    assert response.context["ticket_link"] is None


@pytest.mark.django_db
def test_tickets_info_view_claim_ticket(tp, ticket_links):
    """Test claiming a ticket through tickets info view"""
    response = tp.post("tickets_info", data={"email": "test@example.com"})
    assert response.status_code == 200

    assert "ticket_link" in response.context
    assert response.context["ticket_link"] is not None
    assert response.context["is_existing"] is False

    # Verify ticket was assigned
    assigned_ticket = TicketLink.objects.filter(attendee_email="test@example.com").first()
    assert assigned_ticket is not None


@pytest.mark.django_db
def test_tickets_info_view_retrieve_existing_ticket(tp, ticket_links):
    """Test retrieving an existing ticket"""
    # Assign a ticket first
    ticket = ticket_links[0]
    ticket.attendee_email = "existing@example.com"
    ticket.save()

    response = tp.post("tickets_info", data={"email": "existing@example.com"})
    assert response.status_code == 200
    assert response.context["ticket_link"] == ticket
    assert response.context["is_existing"] is True


@pytest.mark.django_db
def test_tickets_info_view_with_available_tickets(tp, ticket_links):
    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "tickets_available" in response.context
    assert response.context["tickets_available"] is True
    assert b"Get My Ticket" in response.content


@pytest.mark.django_db
def test_tickets_info_view_with_no_available_tickets(tp):
    # Assign all existing tickets to emails (making none available for new claims)
    for ticket in TicketLink.objects.all():
        ticket.attendee_email = "assigned@example.com"
        ticket.save()

    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "tickets_available" in response.context
    assert response.context["tickets_available"] is False
    assert b"No Tickets Available" in response.content
