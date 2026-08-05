import pytest

from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink
from tickets.services import (
    NoTicketsAvailable,
    assign_and_email,
    assign_link,
    claim_for_email,
)


@pytest.mark.django_db
def test_assign_link_is_idempotent(ticket_links):
    first = assign_link("attendee@example.com")
    second = assign_link("attendee@example.com")

    assert first.pk == second.pk
    assert TicketLink.objects.filter(attendee_email="attendee@example.com").count() == 1


@pytest.mark.django_db
def test_assign_link_normalizes_case(ticket_links):
    link = assign_link("MixedCase@Example.COM")
    assert link.attendee_email == "mixedcase@example.com"


@pytest.mark.django_db
def test_assign_link_raises_when_pool_is_empty(db):
    with pytest.raises(NoTicketsAvailable):
        assign_link("nobody@example.com")


@pytest.mark.django_db
def test_reissue_supersedes_the_old_link(ticket_links):
    original = assign_link("attendee@example.com")
    replacement = assign_link("attendee@example.com", reissue=True)

    original.refresh_from_db()
    assert replacement.pk != original.pk
    assert original.superseded_at is not None
    assert original.attendee_email == "attendee@example.com"  # history preserved
    assert replacement.attendee_email == "attendee@example.com"


@pytest.mark.django_db
def test_reissue_keeps_current_link_when_pool_is_empty(ticket_link):
    original = assign_link("attendee@example.com")

    with pytest.raises(NoTicketsAvailable):
        assign_link("attendee@example.com", reissue=True)

    original.refresh_from_db()
    assert original.superseded_at is None


@pytest.mark.django_db
def test_assign_link_backfills_attendee_fk(ticket_links, attendee):
    TicketLink.objects.filter(pk=ticket_links[0].pk).update(attendee_email=attendee.email)

    link = assign_link(attendee.email, attendee=attendee)

    assert link.pk == ticket_links[0].pk
    assert link.attendee_id == attendee.pk


@pytest.mark.django_db
def test_claim_for_email_reports_empty_pool(db):
    link, is_existing, error = claim_for_email("nobody@example.com")

    assert link is None
    assert is_existing is False
    assert "no tickets" in error.lower()


@pytest.mark.django_db
def test_claim_for_email_returns_existing(ticket_links):
    first, _, _ = claim_for_email("attendee@example.com")
    second, is_existing, error = claim_for_email("attendee@example.com")

    assert second.pk == first.pk
    assert is_existing is True
    assert error is None


@pytest.mark.django_db
def test_assign_and_email_logs_initial_then_resend(ticket_links, attendee, queued_tasks):
    _, first_log = assign_and_email(attendee)
    _, second_log = assign_and_email(attendee)

    assert first_log.kind == TicketEmailLog.KIND_INITIAL
    assert second_log.kind == TicketEmailLog.KIND_RESEND
    assert first_log.to_email == attendee.email
    assert len(queued_tasks) == 2


@pytest.mark.django_db
def test_assign_and_email_reissue_logs_reissue(ticket_links, attendee, queued_tasks):
    assign_and_email(attendee)
    link, log = assign_and_email(attendee, reissue=True)

    assert log.kind == TicketEmailLog.KIND_REISSUE
    assert log.ticket_link_id == link.pk


@pytest.mark.django_db
def test_attendee_email_is_normalized_on_save(db):
    attendee = OnlineAttendee.objects.create(email="  Loud@Example.COM ", year=2026)
    assert attendee.email == "loud@example.com"


@pytest.mark.django_db
def test_attendee_counters_only_include_sent(ticket_links, attendee, queued_tasks):
    _, log = assign_and_email(attendee)

    assert attendee.sent_email_count == 0
    assert attendee.last_emailed_at is None

    log.mark_sent()

    assert attendee.sent_email_count == 1
    assert attendee.last_emailed_at is not None
