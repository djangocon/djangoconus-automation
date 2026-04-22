import logging

import requests

logger = logging.getLogger(__name__)

TITO_API_BASE = "https://api.tito.io/v3"

# Known DjangoCon US events, latest first.
DJANGOCON_EVENT_SLUGS = [
    "djangocon-us-2026",
    "djangocon-us-2025",
    "djangocon-us-2024",
    "djangocon-us-2023",
    "djangocon-us-2022",
    "djangocon-us-2021",
    "djangocon-us-2020",
    "djangocon-us-2019",
]


def _headers(api_token):
    return {
        "Authorization": f"Token token={api_token}",
        "Accept": "application/json",
    }


def get_releases(account_slug, event_slug, api_token):
    """Fetch all ticket releases for an event."""
    url = f"{TITO_API_BASE}/{account_slug}/{event_slug}/releases"
    try:
        response = requests.get(url, headers=_headers(api_token), timeout=10)
        response.raise_for_status()
        return response.json().get("releases", [])
    except Exception as exc:
        logger.warning("Failed to fetch tito releases for %s: %s", event_slug, exc)
        return None


def get_activities(account_slug, event_slug, api_token):
    """Fetch all activities for an event."""
    url = f"{TITO_API_BASE}/{account_slug}/{event_slug}/activities"
    try:
        response = requests.get(url, headers=_headers(api_token), timeout=10)
        response.raise_for_status()
        return response.json().get("activities", [])
    except Exception as exc:
        logger.warning("Failed to fetch tito activities for %s: %s", event_slug, exc)
        return None
