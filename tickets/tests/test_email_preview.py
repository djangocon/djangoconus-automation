import pytest
from django.utils import timezone

from tickets.emails import PLACEHOLDER_LINK
from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink
from tickets.tasks import send_ticket_link_email


@pytest.fixture
def staff_client(tp, staff_user):
    tp.client.force_login(staff_user)
    return tp


@pytest.fixture
def attendee_with_link(attendee, ticket_link):
    ticket_link.attendee = attendee
    ticket_link.attendee_email = attendee.email
    ticket_link.date_link_assigned = timezone.now()
    ticket_link.save()
    return attendee


@pytest.mark.django_db
def test_preview_requires_staff(tp, attendee):
    response = tp.get("attendee_email_preview", attendee.pk)
    assert response.status_code == 302


@pytest.mark.django_db
def test_preview_renders_the_attendees_own_link(staff_client, attendee_with_link, ticket_link):
    response = staff_client.get("attendee_email_preview", attendee_with_link.pk)

    assert response.status_code == 200
    assert ticket_link.link in response.content.decode()
    assert response.context["link_is_placeholder"] is False


@pytest.mark.django_db
def test_preview_defaults_to_the_send_that_would_happen(staff_client, attendee_with_link):
    """Someone holding a link would get a resend; someone without, an initial."""
    with_link = staff_client.get("attendee_email_preview", attendee_with_link.pk)
    assert with_link.context["kind"] == TicketEmailLog.KIND_RESEND

    fresh = OnlineAttendee.objects.create(email="nolink@example.com", year=2026)
    without_link = staff_client.get("attendee_email_preview", fresh.pk)
    assert without_link.context["kind"] == TicketEmailLog.KIND_INITIAL


@pytest.mark.django_db
def test_preview_without_a_link_shows_a_placeholder(staff_client, attendee):
    response = staff_client.get("attendee_email_preview", attendee.pk)

    assert response.context["link_is_placeholder"] is True
    assert PLACEHOLDER_LINK in response.content.decode()


@pytest.mark.django_db
def test_preview_honours_the_requested_kind(staff_client, attendee_with_link):
    response = staff_client.get("attendee_email_preview", attendee_with_link.pk, data={"kind": "reissue"})

    assert response.context["kind"] == TicketEmailLog.KIND_REISSUE
    assert response.context["is_reissue"] is True
    assert "NEW link" in response.context["rendered"].text_body


@pytest.mark.django_db
def test_preview_ignores_a_bogus_kind(staff_client, attendee_with_link):
    response = staff_client.get("attendee_email_preview", attendee_with_link.pk, data={"kind": "nonsense"})

    assert response.status_code == 200
    assert response.context["kind"] == TicketEmailLog.KIND_RESEND


@pytest.mark.django_db
def test_preview_part_html_serves_the_html_body_alone(staff_client, attendee_with_link, ticket_link):
    response = staff_client.get("attendee_email_preview", attendee_with_link.pk, data={"part": "html"})

    body = response.content.decode()
    assert response.status_code == 200
    assert ticket_link.link in body
    # The chrome of the preview page must not be in the standalone body.
    assert "Send history" not in body


@pytest.mark.django_db
def test_preview_lists_the_send_history(staff_client, attendee_with_link, ticket_link):
    log = TicketEmailLog.objects.create(
        attendee=attendee_with_link,
        ticket_link=ticket_link,
        to_email=attendee_with_link.email,
        kind=TicketEmailLog.KIND_INITIAL,
    )
    log.mark_sent()

    response = staff_client.get("attendee_email_preview", attendee_with_link.pk)

    assert list(response.context["logs"]) == [log]
    assert response.context["attendee"].sent_email_count == 1


@pytest.mark.django_db
def test_preview_matches_what_the_worker_sends(staff_client, attendee_with_link, ticket_link, mailoutbox):
    """The preview and the real send render from one builder, so they agree."""
    log = TicketEmailLog.objects.create(
        attendee=attendee_with_link,
        ticket_link=ticket_link,
        to_email=attendee_with_link.email,
        kind=TicketEmailLog.KIND_RESEND,
    )
    send_ticket_link_email(log.pk)

    response = staff_client.get("attendee_email_preview", attendee_with_link.pk, data={"kind": "resend"})

    sent = mailoutbox[-1]
    assert response.context["rendered"].subject == sent.subject
    assert response.context["rendered"].text_body == sent.body


@pytest.mark.django_db
def test_ticket_list_counts_emails_per_link(staff_client, attendee_with_link, ticket_link):
    for _ in range(2):
        log = TicketEmailLog.objects.create(
            attendee=attendee_with_link,
            ticket_link=ticket_link,
            to_email=attendee_with_link.email,
        )
        log.mark_sent()
    TicketEmailLog.objects.create(
        attendee=attendee_with_link,
        ticket_link=ticket_link,
        to_email=attendee_with_link.email,
        status=TicketEmailLog.STATUS_FAILED,
    )

    response = staff_client.get("tickets_list")

    row = next(t for t in response.context["tickets"] if t.pk == ticket_link.pk)
    assert row.emails_sent == 2
    assert row.emails_failed == 1
    assert row.last_emailed_at is not None
    assert response.context["emailed_count"] == 1


@pytest.mark.django_db
def test_ticket_list_resolves_a_preview_target_without_the_fk(staff_client, attendee, ticket_link):
    """Links claimed on the public page carry an address but no FK."""
    ticket_link.attendee_email = attendee.email
    ticket_link.save(update_fields=["attendee_email"])

    response = staff_client.get("tickets_list")

    row = next(t for t in response.context["tickets"] if t.pk == ticket_link.pk)
    assert row.preview_attendee == attendee


@pytest.mark.django_db
def test_ticket_list_has_no_preview_target_for_an_unassigned_link(staff_client, ticket_link):
    response = staff_client.get("tickets_list")

    row = next(t for t in response.context["tickets"] if t.pk == ticket_link.pk)
    assert row.preview_attendee is None


@pytest.mark.django_db
def test_ticket_list_marks_superseded_links(staff_client, attendee_with_link, ticket_link):
    ticket_link.supersede()

    response = staff_client.get("tickets_list")

    assert "Superseded" in response.content.decode()
    assert TicketLink.objects.filter(pk=ticket_link.pk, superseded_at__isnull=False).exists()
