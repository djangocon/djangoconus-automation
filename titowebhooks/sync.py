import logging
from datetime import datetime, timezone

from django.conf import settings

from titowebhooks.models import TitoEvent, TitoHistoricalEvent, TitoTicket, TitoWebhookEvent
from titowebhooks.tito_api import DJANGOCON_EVENT_SLUGS, get_activities, get_event, get_releases, get_tickets

logger = logging.getLogger(__name__)

CURRENT_SLUG = DJANGOCON_EVENT_SLUGS[0]

VOID_STATES = {"void", "voided"}


def _parse_dt(value):
    """Ti.to timestamps are ISO strings, sometimes with a trailing Z."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _parse_date(value):
    parsed = _parse_dt(value)
    return parsed.date() if parsed else None


def _year_for_slug(event_slug: str, fallback: int | None = None) -> int | None:
    """Conference year from a slug like "djangocon-us-2026".

    Deliberately not the purchase year - tickets for a September conference are
    mostly bought the year before, and bucketing those under the wrong season
    would scramble every curve.
    """
    tail = (event_slug or "").rsplit("-", 1)[-1]
    if tail.isdigit() and len(tail) == 4:
        return int(tail)
    return fallback


def _money(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ticket_fields(payload: dict, event_slug: str, year: int, source: str) -> dict | None:
    """Flatten a Ti.to ticket (API object or webhook payload) into model fields."""
    ticket_slug = payload.get("slug") or payload.get("reference") or str(payload.get("id") or "")
    if not ticket_slug:
        return None

    release = payload.get("release") or {}
    # Webhooks send "state_name"; the /tickets API sends "state" plus a "void" boolean.
    state_name = (payload.get("state_name") or payload.get("state") or "").lower()
    voided = bool(payload.get("void")) or state_name in VOID_STATES

    # Ti.to sends the buyer's address on the ticket once it is claimed; on the
    # /tickets API it can also arrive nested under "assignee". Unclaimed tickets
    # legitimately have no address at all, so blank is normal, not an error.
    assignee = payload.get("assignee") or {}
    email = (payload.get("email") or assignee.get("email") or "").strip().lower()
    name = (
        payload.get("name")
        or assignee.get("name")
        or " ".join(filter(None, [payload.get("first_name"), payload.get("last_name")])).strip()
    )

    return {
        "ticket_slug": ticket_slug,
        "event_slug": event_slug,
        "year": year,
        "reference": (payload.get("reference") or "")[:64],
        "email": email[:254],
        "name": (name or "")[:256],
        "release_title": (payload.get("release_title") or release.get("title") or "")[:256],
        "release_id": payload.get("release_id") or release.get("id"),
        "release_price": _money(payload.get("release_price")),
        "price": _money(payload.get("price")),
        "discount_code": (payload.get("discount_code_used") or "").strip()[:128],
        "state_name": state_name[:64],
        "voided": voided,
        "created_at": _parse_dt(payload.get("created_at")),
        "source": source,
        "last_synced": datetime.now(tz=timezone.utc),
    }


def _get_credentials():
    tito_event = TitoEvent.objects.filter(api_token__gt="").first()
    account_slug = (tito_event.account_slug if tito_event else None) or settings.TITO_ACCOUNT_SLUG
    api_token = (tito_event.api_token if tito_event else None) or settings.TITO_API_TOKEN
    return account_slug, api_token


def sync_tito_events():
    """Fetch releases for all known DjangoCon US events and store in TitoHistoricalEvent."""
    account_slug, api_token = _get_credentials()

    if not api_token or not account_slug:
        logger.error("No Tito API token or account slug configured.")
        return {"error": "No Tito API credentials configured."}

    created_count = 0
    updated_count = 0
    failed_slugs = []

    for slug in DJANGOCON_EVENT_SLUGS:
        year = int(slug.split("-")[-1])
        releases = get_releases(account_slug, slug, api_token)

        if releases is None:
            logger.warning("Failed to fetch releases for %s", slug)
            failed_slugs.append(slug)
            continue

        activities = get_activities(account_slug, slug, api_token) or []

        defaults = {
            "year": year,
            "title": f"DjangoCon US {year}",
            "account_slug": account_slug,
            "is_current": slug == CURRENT_SLUG,
            "releases": releases,
            "activities": activities,
            "last_synced": datetime.now(tz=timezone.utc),
        }

        # Only overwrite the start date when Ti.to actually gives us one, so a hand-entered
        # date survives a sync against an event that has no date set.
        start_date = _parse_date((get_event(account_slug, slug, api_token) or {}).get("start_date"))
        if start_date:
            defaults["start_date"] = start_date

        _, created = TitoHistoricalEvent.objects.update_or_create(slug=slug, defaults=defaults)
        if created:
            created_count += 1
        else:
            updated_count += 1

    summary = {
        "created": created_count,
        "updated": updated_count,
        "failed": failed_slugs,
    }
    logger.info("Tito event sync complete: %s", summary)
    return summary


def _upsert_tickets(rows: list[dict]) -> tuple[int, int]:
    """Insert or update TitoTicket rows keyed on ticket_slug. Returns (created, updated)."""
    created = updated = 0
    for fields in rows:
        ticket_slug = fields.pop("ticket_slug")
        _, was_created = TitoTicket.objects.update_or_create(ticket_slug=ticket_slug, defaults=fields)
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated


def sync_tito_tickets(slugs=None):
    """Pull per-ticket detail for each event so we can chart sales over time.

    This is the slow sync - it walks every ticket for every year - so it lives
    apart from sync_tito_events and is queued separately.
    """
    account_slug, api_token = _get_credentials()

    if not api_token or not account_slug:
        logger.error("No Tito API token or account slug configured.")
        return {"error": "No Tito API credentials configured."}

    created_count = 0
    updated_count = 0
    failed_slugs = []
    per_event = {}

    for slug in slugs or DJANGOCON_EVENT_SLUGS:
        year = _year_for_slug(slug)
        tickets = get_tickets(account_slug, slug, api_token)

        if tickets is None:
            logger.warning("Failed to fetch tickets for %s", slug)
            failed_slugs.append(slug)
            continue

        rows = [_ticket_fields(t, slug, year, TitoTicket.SOURCE_API) for t in tickets]
        created, updated = _upsert_tickets([r for r in rows if r])
        created_count += created
        updated_count += updated
        per_event[slug] = created + updated

    summary = {
        "created": created_count,
        "updated": updated_count,
        "failed": failed_slugs,
        "per_event": per_event,
    }
    logger.info("Tito ticket sync complete: %s", summary)
    return summary


def backfill_tickets_from_webhooks():
    """Seed TitoTicket from webhook payloads we already have on hand.

    Useful before (or without) an API sync: the webhook history covers whichever
    years had the webhook wired up. API rows win, so we never clobber a synced
    ticket with a possibly-staler webhook copy.
    """
    api_slugs = set(TitoTicket.objects.filter(source=TitoTicket.SOURCE_API).values_list("ticket_slug", flat=True))

    latest_by_ticket: dict[str, dict] = {}
    for event in TitoWebhookEvent.objects.order_by("timestamp").iterator():
        payload = event.payload or {}
        slug = (payload.get("event") or {}).get("slug")
        created_at = _parse_dt(payload.get("created_at"))
        if not slug or not created_at:
            continue

        year = _year_for_slug(slug)
        if not year:
            continue

        fields = _ticket_fields(payload, slug, year, TitoTicket.SOURCE_WEBHOOK)
        if not fields or fields["ticket_slug"] in api_slugs:
            continue
        if event.trigger == "ticket.voided":
            fields["voided"] = True
        latest_by_ticket[fields["ticket_slug"]] = fields  # ascending, so the last write wins

    created, updated = _upsert_tickets(list(latest_by_ticket.values()))
    summary = {"created": created, "updated": updated}
    logger.info("Tito webhook backfill complete: %s", summary)
    return summary
