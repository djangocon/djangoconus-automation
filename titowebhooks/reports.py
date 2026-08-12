"""One shape for every CSV report we hand out.

The reports grew up separately and drifted: the ticket type was called
``Release`` in one and ``Ticket Type`` in another and was missing entirely from
a third, the purchase date was ``Purchased`` or ``Ticket Date`` depending on
where you looked, and the historical export led with two extra columns so
"column 0 is the name" was true of some files and not others.

Every report now starts with the same four columns, in the same order. Anything
a particular report knows beyond that is appended after them, so a consumer can
rely on the prefix without the reports losing what makes them useful.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone

from django.http import HttpResponse

from titowebhooks.models import TitoWebhookEvent

# The stable prefix. Do not reorder — spreadsheets and scripts key off it.
CORE_COLUMNS = ["Name", "Email", "Ticket Type", "Ticket Date"]


def normalized_csv(filename: str, extra_columns: list[str], rows: list[dict]) -> HttpResponse:
    """Write a report as CSV: the core columns, then whatever else it carries.

    Each row is a dict of ``{"Name": ..., "Ticket Date": ...}``. A column with
    no value in a given row is written blank rather than shifting the columns.
    """
    columns = CORE_COLUMNS + extra_columns
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([format_cell(row.get(column, "")) for column in columns])
    return response


def format_cell(value) -> str:
    """Dates as ISO 8601, booleans as Yes/blank, everything else as-is."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else ""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def release_title(payload: dict) -> str:
    """Ti.to puts the release title in one of two places depending on the hook."""
    title = payload.get("release_title")
    if title:
        return title
    return (payload.get("release") or {}).get("title") or ""


def parse_created_at(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def ticket_holders(match, *, event_slug: str) -> list[dict]:
    """Everyone holding a ticket whose release title satisfies ``match``.

    Ti.to fires several webhooks per ticket (completed, updated, voided...), so
    the same person appears many times. Keep the most recent event per email,
    then drop anyone whose latest event voided their ticket — a refunded sponsor
    should not land on a sponsor mailing list.
    """
    events = TitoWebhookEvent.objects.order_by("timestamp")

    latest_by_email: dict[str, TitoWebhookEvent] = {}
    for event in events:
        payload = event.payload or {}
        if (payload.get("event") or {}).get("slug", "") != event_slug:
            continue
        if not match(release_title(payload)):
            continue
        email = (payload.get("email") or "").strip().lower()
        if email:
            latest_by_email[email] = event

    people = []
    for email, event in latest_by_email.items():
        if event.trigger == "ticket.voided":
            continue
        payload = event.payload or {}
        title = release_title(payload)
        people.append(
            {
                "Name": payload.get("name") or "",
                "Email": email,
                "Ticket Type": title,
                "Ticket Date": parse_created_at(payload.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
                "Company": payload.get("company_name") or "",
                "Ticket Reference": payload.get("reference") or "",
                "Online": "online" in title.lower(),
            }
        )

    return sorted(people, key=lambda person: (person["Name"] or "").lower())


def matches_speaker(title: str) -> bool:
    """Speaker tickets, including any future "Speaker- Online" variant."""
    return "speaker" in title.lower()


def matches_sponsor(title: str) -> bool:
    """Sponsor tickets — currently "Sponsor" and "Sponsor- Online"."""
    return "sponsor" in title.lower()
