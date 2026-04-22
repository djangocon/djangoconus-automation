import logging
from datetime import datetime, timezone

from django.conf import settings

from titowebhooks.models import TitoEvent, TitoHistoricalEvent
from titowebhooks.tito_api import DJANGOCON_EVENT_SLUGS, get_releases

logger = logging.getLogger(__name__)

CURRENT_SLUG = DJANGOCON_EVENT_SLUGS[0]


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

        _, created = TitoHistoricalEvent.objects.update_or_create(
            slug=slug,
            defaults={
                "year": year,
                "title": f"DjangoCon US {year}",
                "account_slug": account_slug,
                "is_current": slug == CURRENT_SLUG,
                "releases": releases,
                "last_synced": datetime.now(tz=timezone.utc),
            },
        )
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
