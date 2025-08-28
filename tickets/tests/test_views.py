# tests/test_views.py

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from tickets.models import TicketLink
from tickets.views import venueless_view


@pytest.mark.django_db
def test_venueless_view_redirects_to_ticket_link(tp, ticket_links):
    response = tp.get("venueless_view")
    assert response.status_code == 302
    redirected_url = response["Location"]
    assert redirected_url in [tl.link for tl in ticket_links]
    accessed_links = TicketLink.objects.filter(date_link_accessed__isnull=False)
    assert accessed_links.count() == 1
    assert accessed_links.first().link == redirected_url


@pytest.mark.django_db
def test_venueless_view_no_tickets_left(tp):
    TicketLink.objects.all().update(date_link_accessed=timezone.now())
    response = tp.get("venueless_view")
    assert response.status_code == 404
    assert b"No available tickets." in response.content


@pytest.mark.django_db
def test_venueless_view_concurrent_access(tp, ticket_links):
    factory = RequestFactory()
    request = factory.get(reverse("venueless_view"))

    response1 = venueless_view(request)
    assert response1.status_code == 302
    first_link = response1["Location"]

    response2 = venueless_view(request)
    assert response2.status_code == 302
    second_link = response2["Location"]

    assert first_link != second_link

    accessed_links = TicketLink.objects.filter(date_link_accessed__isnull=False)
    assert accessed_links.count() == 2


@pytest.mark.django_db
def test_venueless_view_error_handling(tp, monkeypatch):
    def mock_get(*args, **kwargs):
        raise Exception("Forced exception")

    monkeypatch.setattr(TicketLink.objects, "select_for_update", mock_get)
    response = tp.get("venueless_view")
    assert response.status_code == 500
    assert b"An unexpected error occurred" in response.content


# New tests for tickets_info view


@pytest.mark.django_db
def test_tickets_info_view_with_available_tickets(tp, ticket_links):
    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "tickets_available" in response.context
    assert response.context["tickets_available"] is True
    assert b"Access Venueless" in response.content


@pytest.mark.django_db
def test_tickets_info_view_with_no_available_tickets(tp):
    TicketLink.objects.all().update(date_link_accessed=timezone.now())
    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "tickets_available" in response.context
    assert response.context["tickets_available"] is False
    assert b"no available tickets" in response.content


@pytest.mark.django_db
def test_tickets_info_view_template_used(tp):
    response = tp.get("tickets_info")
    assert response.status_code == 200
    tp.assertTemplateUsed(response, "tickets/info.html")


@pytest.mark.django_db
def test_tickets_info_view_context_data(tp, ticket_links):
    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "tickets_available" in response.context
    assert response.context["tickets_available"] is True

    TicketLink.objects.all().update(date_link_accessed=timezone.now())
    response = tp.get("tickets_info")
    assert response.status_code == 200
    assert "tickets_available" in response.context
    assert response.context["tickets_available"] is False
