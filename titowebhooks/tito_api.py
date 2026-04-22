import logging

import requests

logger = logging.getLogger(__name__)

TITO_API_BASE = "https://api.tito.io/v3"


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
        logger.warning("Failed to fetch tito releases: %s", exc)
        return None


def get_activities(account_slug, event_slug, api_token):
    """Fetch all activities for an event."""
    url = f"{TITO_API_BASE}/{account_slug}/{event_slug}/activities"
    try:
        response = requests.get(url, headers=_headers(api_token), timeout=10)
        response.raise_for_status()
        return response.json().get("activities", [])
    except Exception as exc:
        logger.warning("Failed to fetch tito activities: %s", exc)
        return None
