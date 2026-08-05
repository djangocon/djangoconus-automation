import datetime

import pytest

from tickets.models import OnlineAttendee
from tickets.sync import record_webhook_attendee, sync_online_attendees
from titowebhooks.models import TitoTicket, TitoWebhookEvent


def _webhook(email, release_title="Conference (Online)", slug="djangocon-us-2026", name="Web Hooked"):
    return TitoWebhookEvent.objects.create(
        trigger="ticket.completed",
        payload={
            "email": email,
            "name": name,
            "release_title": release_title,
            "created_at": "2026-03-01T10:00:00Z",
            "event": {"slug": slug},
        },
    )


@pytest.mark.django_db
def test_sync_picks_up_online_tickets_from_the_api(db):
    TitoTicket.objects.create(
        ticket_slug="t1",
        event_slug="djangocon-us-2026",
        year=2026,
        email="api@example.com",
        name="API Buyer",
        release_title="Conference (Online)",
        created_at=datetime.datetime(2026, 2, 1, tzinfo=datetime.timezone.utc),
    )

    result = sync_online_attendees(2026)

    assert result["created"] == 1
    attendee = OnlineAttendee.objects.get(email="api@example.com")
    assert attendee.source == OnlineAttendee.SOURCE_TITO_API
    assert attendee.name == "API Buyer"


@pytest.mark.django_db
def test_sync_ignores_in_person_and_voided_tickets(db):
    TitoTicket.objects.create(
        ticket_slug="t1",
        event_slug="djangocon-us-2026",
        year=2026,
        email="inperson@example.com",
        release_title="Conference (In-person)",
    )
    TitoTicket.objects.create(
        ticket_slug="t2",
        event_slug="djangocon-us-2026",
        year=2026,
        email="voided@example.com",
        release_title="Conference (Online)",
        voided=True,
    )

    sync_online_attendees(2026)

    assert OnlineAttendee.objects.count() == 0


@pytest.mark.django_db
def test_sync_merges_both_sources(db):
    TitoTicket.objects.create(
        ticket_slug="t1",
        event_slug="djangocon-us-2026",
        year=2026,
        email="api@example.com",
        release_title="Conference (Online)",
    )
    _webhook("hook@example.com")

    sync_online_attendees(2026)

    assert set(OnlineAttendee.objects.values_list("email", flat=True)) == {
        "api@example.com",
        "hook@example.com",
    }


@pytest.mark.django_db
def test_sync_is_rerunnable(db):
    _webhook("hook@example.com")

    sync_online_attendees(2026)
    second = sync_online_attendees(2026)

    assert second["created"] == 0
    assert second["updated"] == 1
    assert OnlineAttendee.objects.count() == 1


@pytest.mark.django_db
def test_sync_skips_other_years(db):
    _webhook("old@example.com", slug="djangocon-us-2025")

    sync_online_attendees(2026)

    assert OnlineAttendee.objects.count() == 0


@pytest.mark.django_db
def test_record_webhook_attendee_creates_immediately(db):
    attendee = record_webhook_attendee(
        {
            "email": "Instant@Example.com",
            "name": "Instant Buyer",
            "release_title": "Conference (Online)",
            "created_at": "2026-03-01T10:00:00Z",
            "event": {"slug": "djangocon-us-2026"},
        }
    )

    assert attendee is not None
    assert attendee.email == "instant@example.com"
    assert attendee.year == 2026


@pytest.mark.django_db
def test_record_webhook_attendee_ignores_in_person(db):
    assert (
        record_webhook_attendee(
            {
                "email": "inperson@example.com",
                "release_title": "Conference (In-person)",
                "event": {"slug": "djangocon-us-2026"},
            }
        )
        is None
    )
