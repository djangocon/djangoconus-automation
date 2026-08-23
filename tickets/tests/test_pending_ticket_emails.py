"""The unattended batch send behind the scheduled Sunday-morning run."""

from unittest.mock import patch

import pytest

from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink
from tickets.tasks import send_pending_ticket_emails

YEAR = 2026


@pytest.fixture(autouse=True)
def no_worker():
    """Never hand anything to django-q from a test."""
    with patch("tickets.services.async_task") as task:
        yield task


def make_attendee(email, year=YEAR, name="Ada Lovelace"):
    return OnlineAttendee.objects.create(name=name, email=email, year=year)


def make_links(count):
    return [TicketLink.objects.create(link=f"https://ti.to/example/{i}") for i in range(count)]


def log_for(email):
    return TicketEmailLog.objects.filter(to_email=email)


@pytest.mark.django_db
def test_emails_everyone_who_has_never_been_emailed():
    make_links(3)
    make_attendee("a@example.com")
    make_attendee("b@example.com")

    summary = send_pending_ticket_emails()

    assert summary["queued"] == 2
    assert summary["skipped"] == 0
    assert TicketEmailLog.objects.count() == 2


@pytest.mark.django_db
def test_assigns_a_link_to_anyone_who_still_lacks_one():
    """Someone who buys between scheduling and firing has no link yet."""
    make_links(1)
    attendee = make_attendee("late@example.com")
    assert attendee.active_ticket_link is None

    send_pending_ticket_emails()

    assert attendee.active_ticket_link is not None


@pytest.mark.django_db
def test_running_twice_does_not_email_anyone_twice():
    """The guard that makes this safe to schedule, retry, or re-run."""
    make_links(3)
    make_attendee("a@example.com")

    first = send_pending_ticket_emails()
    second = send_pending_ticket_emails()

    assert first["queued"] == 1
    assert second["queued"] == 0
    assert second["skipped"] == 1
    assert log_for("a@example.com").count() == 1


@pytest.mark.django_db
def test_a_still_queued_email_counts_as_already_sent():
    """A slow worker must not become a reason to send a second copy."""
    make_links(3)
    attendee = make_attendee("a@example.com")
    TicketEmailLog.objects.create(attendee=attendee, to_email=attendee.email, status=TicketEmailLog.STATUS_QUEUED)

    summary = send_pending_ticket_emails()

    assert summary["queued"] == 0
    assert summary["skipped"] == 1


@pytest.mark.django_db
def test_a_previous_failure_is_retried():
    """A transient SMTP problem should not exclude someone forever."""
    make_links(3)
    attendee = make_attendee("a@example.com")
    TicketEmailLog.objects.create(attendee=attendee, to_email=attendee.email, status=TicketEmailLog.STATUS_FAILED)

    summary = send_pending_ticket_emails()

    assert summary["queued"] == 1


@pytest.mark.django_db
def test_only_the_requested_year_is_emailed():
    make_links(3)
    make_attendee("now@example.com", year=2026)
    make_attendee("then@example.com", year=2025)

    summary = send_pending_ticket_emails(year=2026)

    assert summary["queued"] == 1
    assert not log_for("then@example.com").exists()


@pytest.mark.django_db
def test_running_out_of_links_stops_the_batch():
    """Better to stop with a loud log than to quietly mail a subset."""
    make_links(1)
    make_attendee("a@example.com")
    make_attendee("b@example.com")

    summary = send_pending_ticket_emails()

    assert summary["queued"] == 1
    assert summary["out_of_links"] is True
    assert TicketEmailLog.objects.count() == 1


@pytest.mark.django_db
def test_one_bad_attendee_does_not_sink_the_batch():
    make_links(3)
    make_attendee("bad@example.com")
    make_attendee("good@example.com")

    with patch("tickets.tasks.assign_and_email", side_effect=[RuntimeError("boom"), None]):
        summary = send_pending_ticket_emails()

    assert summary["failed"] == 1
    assert summary["queued"] == 1


@pytest.mark.django_db
def test_limit_caps_how_many_go_out():
    make_links(5)
    for i in range(4):
        make_attendee(f"a{i}@example.com")

    summary = send_pending_ticket_emails(limit=2)

    assert summary["queued"] == 2


@pytest.mark.django_db
def test_nothing_to_do_is_not_an_error():
    summary = send_pending_ticket_emails()

    assert summary["queued"] == 0
    assert summary["out_of_links"] is False


@pytest.mark.django_db
def test_the_email_is_an_initial_send():
    make_links(1)
    make_attendee("a@example.com")

    send_pending_ticket_emails()

    assert log_for("a@example.com").get().kind == TicketEmailLog.KIND_INITIAL
