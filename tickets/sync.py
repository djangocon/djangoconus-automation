"""Build the online-attendee roster from the two Ti.to feeds we already store.

``TitoTicket`` rows come from the nightly API sync and are complete for the
season; ``TitoWebhookEvent`` payloads land instantly but only exist for
purchases made after the webhook endpoint was wired up. Neither alone is both
current and complete, so this reconciles them into ``OnlineAttendee``.
"""

import logging
from datetime import datetime
from datetime import timezone as dt_timezone

from django.utils import timezone

from tickets.models import OnlineAttendee, TicketRelease
from titowebhooks.models import TitoTicket, TitoWebhookEvent

logger = logging.getLogger(__name__)

DEFAULT_YEAR = 2026


# Seeded onto newly discovered releases so a fresh database is not a blank
# slate. Staff edits are never overwritten --- see ``sync_ticket_releases``.
DEFAULT_ELIGIBLE_TITLES = {
    "online- individual",
    "online- corporate",
    "one day individual (in-person)",
    "one day corporate (in-person)",
}


def sync_ticket_releases(year: int = DEFAULT_YEAR) -> dict:
    """Discover the year's ticket types from sold tickets.

    Only ever creates. An existing row's ``grants_venueless_access`` is left
    alone, because it represents somebody's deliberate choice in the admin and
    a re-sync should not undo it.
    """
    seen: dict[str, int | None] = {}
    for release_id, title in TitoTicket.objects.filter(year=year).values_list("release_id", "release_title").distinct():
        if not title:
            continue
        seen.setdefault(title, release_id)

    # Webhooks are read too, for the same reason the roster reads both feeds: a
    # type first sold after the last API sync exists only in a payload, and
    # leaving it undiscovered would silently deny those buyers a link.
    for event in TitoWebhookEvent.objects.filter(trigger="ticket.completed").iterator():
        payload = event.payload or {}
        if _year_from_slug((payload.get("event") or {}).get("slug", "")) != year:
            continue
        title = payload.get("release_title") or ""
        if title:
            seen.setdefault(title, payload.get("release_id"))

    now = timezone.now()
    created = 0
    for title, release_id in seen.items():
        release, was_created = TicketRelease.objects.get_or_create(
            title=title,
            defaults={
                "release_id": release_id,
                "grants_venueless_access": title.strip().lower() in DEFAULT_ELIGIBLE_TITLES,
            },
        )
        if was_created:
            created += 1

        # Only ever moves forward, so re-syncing an old season cannot make a
        # still-current ticket type look stale.
        release.last_seen_year = max(release.last_seen_year or 0, year)
        release.release_id = release.release_id or release_id
        release.last_synced = now
        release.save(update_fields=["last_seen_year", "release_id", "last_synced"])
    logger.info("Synced ticket releases for %s: %s created, %s total", year, created, len(seen))
    return {"year": year, "created": created, "total": len(seen)}


def eligible_release_titles() -> set[str]:
    """Lowercased titles of every ticket type that earns a Venueless link."""
    return {
        title.strip().lower()
        for title in TicketRelease.objects.filter(grants_venueless_access=True).values_list("title", flat=True)
    }


def is_online_release(release_title: str) -> bool:
    """Whether ``release_title`` earns a Venueless link."""
    return (release_title or "").strip().lower() in eligible_release_titles()


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _year_from_slug(event_slug: str) -> int | None:
    tail = (event_slug or "").rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() and len(tail) == 4 else None


def _candidates_from_tito_tickets(year: int) -> dict[str, dict]:
    """Online buyers as recorded by the Ti.to API sync."""
    candidates = {}
    eligible = eligible_release_titles()
    tickets = TitoTicket.objects.filter(year=year, voided=False).exclude(email="")
    for ticket in tickets:
        if (ticket.release_title or "").strip().lower() not in eligible:
            continue
        candidates[ticket.email.strip().lower()] = {
            "name": ticket.name or "",
            "release_title": ticket.release_title or "",
            "purchased_at": ticket.created_at,
            "source": OnlineAttendee.SOURCE_TITO_API,
        }
    return candidates


def _candidates_from_webhooks(year: int) -> dict[str, dict]:
    """Online buyers seen on ``ticket.completed`` webhooks."""
    candidates = {}
    eligible = eligible_release_titles()
    for event in TitoWebhookEvent.objects.filter(trigger="ticket.completed").iterator():
        payload = event.payload
        if not payload:
            continue

        event_slug = (payload.get("event") or {}).get("slug", "")
        if _year_from_slug(event_slug) != year:
            continue

        release_title = payload.get("release_title") or ""
        if release_title.strip().lower() not in eligible:
            continue

        email = (payload.get("email") or "").strip().lower()
        if not email:
            continue

        purchased_at = _parse_dt(payload.get("created_at"))
        existing = candidates.get(email)
        # Someone can hold several online tickets; keep the most recent purchase
        # so the roster shows the freshest name and release.
        if existing and existing["purchased_at"] and purchased_at and purchased_at <= existing["purchased_at"]:
            continue

        candidates[email] = {
            "name": payload.get("name") or "",
            "release_title": release_title,
            "purchased_at": purchased_at,
            "source": OnlineAttendee.SOURCE_WEBHOOK,
        }
    return candidates


def sync_online_attendees(year: int = DEFAULT_YEAR) -> dict:
    """Upsert ``OnlineAttendee`` rows for ``year``. Returns a counts summary."""
    # Pick up ticket types added since the last run; new ones arrive switched
    # off unless they match a seeded title, so this can never widen the roster
    # behind somebody's back.
    sync_ticket_releases(year=year)

    # Webhooks are applied second so their fresher name/release wins a tie.
    merged = _candidates_from_tito_tickets(year)
    for email, data in _candidates_from_webhooks(year).items():
        merged[email] = data

    now = timezone.now()
    created = updated = 0

    for email, data in merged.items():
        _, was_created = OnlineAttendee.objects.update_or_create(
            year=year,
            email=email,
            defaults={**data, "last_synced": now},
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("Synced online attendees for %s: %s created, %s updated", year, created, updated)
    return {"year": year, "created": created, "updated": updated, "total": len(merged)}


def record_webhook_attendee(payload: dict) -> OnlineAttendee | None:
    """Upsert a single attendee straight off a ``ticket.completed`` payload.

    Lets a purchase show up in the dashboard immediately instead of waiting for
    the next full sync. Returns None when the payload is not an online ticket.
    """
    if not payload:
        return None

    # The roster row is keyed by year, so an unparseable slug has nowhere to go.
    year = _year_from_slug((payload.get("event") or {}).get("slug", ""))
    if year is None:
        return None

    release_title = payload.get("release_title") or ""
    if not is_online_release(release_title):
        return None

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return None

    attendee, _ = OnlineAttendee.objects.update_or_create(
        year=year,
        email=email,
        defaults={
            "name": payload.get("name") or "",
            "release_title": release_title,
            "purchased_at": _parse_dt(payload.get("created_at")) or datetime.now(tz=dt_timezone.utc),
            "source": OnlineAttendee.SOURCE_WEBHOOK,
            "last_synced": timezone.now(),
        },
    )
    return attendee
