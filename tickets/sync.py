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

from tickets.models import OnlineAttendee
from titowebhooks.models import TitoTicket, TitoWebhookEvent

logger = logging.getLogger(__name__)

DEFAULT_YEAR = 2026


def is_online_release(release_title: str) -> bool:
    return "online" in (release_title or "").lower()


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
    tickets = TitoTicket.objects.filter(year=year, voided=False).exclude(email="")
    for ticket in tickets:
        if not is_online_release(ticket.release_title):
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
    for event in TitoWebhookEvent.objects.filter(trigger="ticket.completed").iterator():
        payload = event.payload
        if not payload:
            continue

        event_slug = (payload.get("event") or {}).get("slug", "")
        if _year_from_slug(event_slug) != year:
            continue

        release_title = payload.get("release_title") or ""
        if not is_online_release(release_title):
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

    release_title = payload.get("release_title") or ""
    if not is_online_release(release_title):
        return None

    email = (payload.get("email") or "").strip().lower()
    if not email:
        return None

    year = _year_from_slug((payload.get("event") or {}).get("slug", ""))
    if year is None:
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
