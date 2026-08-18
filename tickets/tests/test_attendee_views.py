import pytest

from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink


@pytest.fixture
def staff_client(tp, staff_user):
    tp.client.force_login(staff_user)
    return tp


@pytest.mark.django_db
def test_dashboard_requires_staff(tp):
    response = tp.get("online_attendees")
    assert response.status_code == 302


@pytest.mark.django_db
def test_dashboard_shows_counts(staff_client, ticket_links, attendee):
    response = staff_client.get("online_attendees")

    assert response.status_code == 200
    assert response.context["total_count"] == 1
    assert response.context["assigned_count"] == 0
    assert response.context["unassigned_count"] == 1
    assert response.context["available_links"] == 3


@pytest.mark.django_db
def test_filter_narrows_to_attendees_without_a_link(staff_client, ticket_links, attendee):
    OnlineAttendee.objects.create(email="haslink@example.com", year=2026)
    TicketLink.objects.filter(pk=ticket_links[0].pk).update(attendee_email="haslink@example.com")

    response = staff_client.get("online_attendees", data={"status": "unassigned"})

    emails = [a.email for a in response.context["attendees"]]
    assert emails == [attendee.email]


@pytest.mark.django_db
def test_assign_by_pasted_email_creates_a_manual_attendee(staff_client, ticket_links, queued_tasks):
    response = staff_client.post(
        "online_attendees",
        data={"action": "assign_by_email", "email": "Pasted@Example.com", "send_email": "on"},
    )

    assert response.status_code == 302
    attendee = OnlineAttendee.objects.get(email="pasted@example.com")
    assert attendee.source == OnlineAttendee.SOURCE_MANUAL
    assert attendee.has_ticket
    assert TicketEmailLog.objects.filter(to_email="pasted@example.com").count() == 1
    assert len(queued_tasks) == 1


@pytest.mark.django_db
def test_assign_by_pasted_email_can_skip_the_email(staff_client, ticket_links, queued_tasks):
    staff_client.post(
        "online_attendees",
        data={"action": "assign_by_email", "email": "quiet@example.com"},
    )

    assert OnlineAttendee.objects.get(email="quiet@example.com").has_ticket
    assert TicketEmailLog.objects.count() == 0
    assert queued_tasks == []


@pytest.mark.django_db
def test_assign_by_email_reports_an_empty_pool(staff_client, db):
    response = staff_client.post(
        "online_attendees",
        data={"action": "assign_by_email", "email": "unlucky@example.com", "send_email": "on"},
    )

    messages = [str(m) for m in response.wsgi_request._messages]
    assert any("No unassigned ticket links" in m for m in messages)


@pytest.mark.django_db
def test_bulk_assign_and_email(staff_client, ticket_links, attendee, queued_tasks):
    other = OnlineAttendee.objects.create(email="second@example.com", year=2026)

    staff_client.post(
        "online_attendees",
        data={"action": "assign_and_email", "attendee_ids": [attendee.pk, other.pk]},
    )

    assert attendee.has_ticket
    assert other.has_ticket
    assert TicketEmailLog.objects.count() == 2
    assert len(queued_tasks) == 2


@pytest.mark.django_db
def test_bulk_resend_skips_people_without_a_link(staff_client, ticket_links, attendee, queued_tasks):
    linkless = OnlineAttendee.objects.create(email="nolink@example.com", year=2026)
    staff_client.post("online_attendees", data={"action": "assign_and_email", "attendee_ids": [attendee.pk]})
    queued_tasks.clear()

    staff_client.post(
        "online_attendees",
        data={"action": "email", "attendee_ids": [attendee.pk, linkless.pk]},
    )

    assert len(queued_tasks) == 1
    assert not linkless.has_ticket
    assert TicketEmailLog.objects.filter(kind=TicketEmailLog.KIND_RESEND).count() == 1


@pytest.mark.django_db
def test_bulk_reissue_supersedes_old_links(staff_client, ticket_links, attendee, queued_tasks):
    staff_client.post("online_attendees", data={"action": "assign_and_email", "attendee_ids": [attendee.pk]})
    original = attendee.active_ticket_link

    staff_client.post("online_attendees", data={"action": "reissue", "attendee_ids": [attendee.pk]})

    original.refresh_from_db()
    assert original.superseded_at is not None
    assert attendee.active_ticket_link.pk != original.pk
    assert TicketEmailLog.objects.filter(kind=TicketEmailLog.KIND_REISSUE).count() == 1


@pytest.mark.django_db
def test_csv_export_lists_attendees(staff_client, ticket_links, attendee):
    response = staff_client.get("online_attendees", data={"format": "csv"})

    assert response["Content-Type"] == "text/csv"
    body = response.content.decode()
    assert "online@example.com" in body
    assert "Online Buyer" in body


@pytest.mark.django_db
def test_email_log_view_filters_by_status(staff_client, ticket_links, attendee, queued_tasks):
    staff_client.post("online_attendees", data={"action": "assign_and_email", "attendee_ids": [attendee.pk]})
    TicketEmailLog.objects.update(status=TicketEmailLog.STATUS_FAILED, error="nope")

    response = staff_client.get("ticket_emails", data={"status": "failed"})

    assert response.status_code == 200
    assert response.context["failed_count"] == 1
    assert len(response.context["logs"]) == 1


@pytest.mark.django_db
def test_row_assign_button_ties_a_link_without_emailing(staff_client, ticket_links, attendee, queued_tasks):
    response = staff_client.post(
        "online_attendees",
        data={"assign_attendee_id": attendee.pk},
        follow=True,
    )

    assert response.status_code == 200
    attendee.refresh_from_db()
    assert attendee.has_ticket
    # Assigning is deliberately silent; emailing is its own step.
    assert queued_tasks == []
    assert TicketEmailLog.objects.count() == 0


@pytest.mark.django_db
def test_row_assign_button_is_idempotent(staff_client, ticket_links, attendee):
    staff_client.post("online_attendees", data={"assign_attendee_id": attendee.pk})
    first = attendee.active_ticket_link

    staff_client.post("online_attendees", data={"assign_attendee_id": attendee.pk})

    assert attendee.active_ticket_link.pk == first.pk
    assert TicketLink.objects.filter(attendee_email__isnull=True).count() == len(ticket_links) - 1


@pytest.mark.django_db
def test_row_assign_button_reports_an_empty_pool(staff_client, attendee):
    response = staff_client.post("online_attendees", data={"assign_attendee_id": attendee.pk}, follow=True)

    assert not attendee.has_ticket
    assert any("No unassigned ticket links" in str(m) for m in response.context["messages"])


@pytest.mark.django_db
def test_row_assign_button_survives_a_bogus_id(staff_client, ticket_links):
    response = staff_client.post("online_attendees", data={"assign_attendee_id": "not-a-pk"}, follow=True)

    assert response.status_code == 200
    assert any("no longer exists" in str(m) for m in response.context["messages"])


@pytest.mark.django_db
def test_bulk_assign_sends_no_email(staff_client, ticket_links, attendee, queued_tasks):
    response = staff_client.post(
        "online_attendees",
        data={"action": "assign", "attendee_ids": [attendee.pk]},
        follow=True,
    )

    assert response.status_code == 200
    attendee.refresh_from_db()
    assert attendee.has_ticket
    assert queued_tasks == []
    assert TicketEmailLog.objects.count() == 0


@pytest.mark.django_db
def test_bulk_assign_reports_an_empty_pool(staff_client, attendee):
    response = staff_client.post(
        "online_attendees",
        data={"action": "assign", "attendee_ids": [attendee.pk]},
        follow=True,
    )

    assert not attendee.has_ticket
    assert any("Ran out of unassigned ticket links" in str(m) for m in response.context["messages"])
