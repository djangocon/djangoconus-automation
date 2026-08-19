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


def get_event(account_slug, event_slug, api_token):
    """Fetch a single event, mainly for its start date."""
    url = f"{TITO_API_BASE}/{account_slug}/{event_slug}"
    try:
        response = requests.get(url, headers=_headers(api_token), timeout=10)
        response.raise_for_status()
        return response.json().get("event")
    except Exception as exc:
        logger.warning("Failed to fetch tito event %s: %s", event_slug, exc)
        return None


def get_tickets(account_slug, event_slug, api_token, max_pages=200):
    """Fetch every ticket for an event, walking Ti.to's pagination.

    Returns None if the first page fails so callers can tell "no access" apart
    from "no tickets". A failure partway through returns what we got so far
    rather than throwing the whole event away.
    """
    url = f"{TITO_API_BASE}/{account_slug}/{event_slug}/tickets"
    tickets = []

    for page in range(1, max_pages + 1):
        try:
            response = requests.get(
                url,
                headers=_headers(api_token),
                params={"page": page, "per_page": 100},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Failed to fetch tito tickets page %s for %s: %s", page, event_slug, exc)
            return tickets or None

        batch = data.get("tickets") or []
        tickets.extend(batch)

        next_page = (data.get("meta") or {}).get("next_page")
        if not batch or not next_page:
            break
    else:
        logger.warning("Hit the %s page cap fetching tickets for %s", max_pages, event_slug)

    return tickets


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


# Ti.to hides "past" codes from the default listing, so we ask for every state by
# name. A code that expired mid-season is still worth counting - JULYSAVE10 went
# past and took a good chunk of the year's discounts with it.
DISCOUNT_CODE_STATES = ["current", "past", "upcoming", "used", "unused"]


def get_discount_codes(account_slug, event_slug, api_token, max_pages=50):
    """Fetch every discount code for an event, walking Ti.to's pagination.

    Same contract as get_tickets: None if the first page fails, so callers can
    tell "no access" apart from "no codes".
    """
    url = f"{TITO_API_BASE}/{account_slug}/{event_slug}/discount_codes"
    codes = []

    for page in range(1, max_pages + 1):
        try:
            response = requests.get(
                url,
                headers=_headers(api_token),
                params={"page": page, "per_page": 100, "search[states][]": DISCOUNT_CODE_STATES},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Failed to fetch tito discount codes page %s for %s: %s", page, event_slug, exc)
            return codes or None

        batch = data.get("discount_codes") or []
        codes.extend(batch)

        next_page = (data.get("meta") or {}).get("next_page")
        if not batch or not next_page:
            break
    else:
        logger.warning("Hit the %s page cap fetching discount codes for %s", max_pages, event_slug)

    return codes
