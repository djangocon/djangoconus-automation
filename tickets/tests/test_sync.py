import datetime

import pytest

from tickets.models import OnlineAttendee, TicketRelease
from tickets.sync import record_webhook_attendee, sync_online_attendees, sync_ticket_releases
from titowebhooks.models import TitoTicket, TitoWebhookEvent


def _webhook(email, release_title="Online- Individual", slug="djangocon-us-2026", name="Web Hooked"):
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
        release_title="Online- Individual",
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
        release_title="Online- Individual",
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
        release_title="Online- Individual",
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
    TicketRelease.objects.create(year=2026, title="Online- Individual", grants_venueless_access=True)

    attendee = record_webhook_attendee(
        {
            "email": "Instant@Example.com",
            "name": "Instant Buyer",
            "release_title": "Online- Individual",
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


@pytest.mark.django_db
def test_sync_ticket_releases_seeds_only_the_eligible_titles(db):
    for title in ["Online- Individual", "Online Sprint - Thursday (August 27)", "Corporate (In-person)"]:
        TitoTicket.objects.create(
            ticket_slug=f"t-{title}",
            event_slug="djangocon-us-2026",
            year=2026,
            email=f"{title}@example.com",
            name="Buyer",
            release_title=title,
        )

    result = sync_ticket_releases(year=2026)

    assert result["total"] == 3
    eligible = set(
        TicketRelease.objects.filter(year=2026, grants_venueless_access=True).values_list("title", flat=True)
    )
    # Sprints contain "online" but are not a Venueless ticket; the old
    # substring rule swept them in.
    assert eligible == {"Online- Individual"}


@pytest.mark.django_db
def test_sync_ticket_releases_leaves_staff_edits_alone(db):
    TitoTicket.objects.create(
        ticket_slug="t1",
        event_slug="djangocon-us-2026",
        year=2026,
        email="buyer@example.com",
        name="Buyer",
        release_title="Corporate (In-person)",
    )
    sync_ticket_releases(year=2026)
    release = TicketRelease.objects.get(year=2026, title="Corporate (In-person)")
    release.grants_venueless_access = True
    release.save()

    sync_ticket_releases(year=2026)

    release.refresh_from_db()
    assert release.grants_venueless_access is True


@pytest.mark.django_db
def test_one_day_tickets_are_eligible_despite_being_in_person(db):
    TitoTicket.objects.create(
        ticket_slug="t1",
        event_slug="djangocon-us-2026",
        year=2026,
        email="oneday@example.com",
        name="One Day Buyer",
        release_title="One Day Individual (In-person)",
    )

    sync_online_attendees(year=2026)

    assert OnlineAttendee.objects.filter(year=2026, email="oneday@example.com").exists()
