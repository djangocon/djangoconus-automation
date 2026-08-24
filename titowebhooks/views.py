import base64
import hashlib
import hmac
import json
import logging
import re
from datetime import datetime, timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_q.tasks import async_task
from rich import print

from emailoctopus.models import Campaign
from tickets.sync import record_webhook_attendee
from titowebhooks.models import TitoDiscountCode, TitoHistoricalEvent, TitoTicket, TitoWebhookEvent
from titowebhooks.reports import (
    matches_speaker,
    matches_sponsor,
    normalized_csv,
    ticket_holders,
)
from titowebhooks.sales_curve import sales_curves
from volunteers.models import VolunteerSignup
from volunteers.permissions import volunteer_interest_required

logger = logging.getLogger(__name__)

superuser_required = user_passes_test(lambda u: u.is_active and u.is_superuser)

LEADER_QUESTION_ID = 1216404
JOINER_QUESTION_ID = 1216405
EVENT_SLUG = "djangocon-us-2026"

# Ti.to stores question answers twice: an "answers" list keyed by question id, and a
# "responses" object keyed by the question slug. The slug is truncated by Ti.to, hence
# the cut-off "-th". Querying "responses" lets Postgres do the filtering for us.
VOLUNTEER_QUESTION_SLUG = "are-you-interested-in-volunteering-at-th"
VOLUNTEER_RESPONSE_LOOKUP = f"payload__responses__{VOLUNTEER_QUESTION_SLUG}"
VOLUNTEER_YES = "Yes!"

# How many conference years the "Download Historical" export reaches back, counting
# from the most recent year present in the data (e.g. 3 -> current + two prior years).
HISTORICAL_YEARS = 3


def verify_tito_signature(payload_body: bytes, signature: str, security_token: str) -> bool:
    computed = (
        base64.b64encode(
            hmac.new(
                security_token.encode(),
                payload_body,
                hashlib.sha256,
            ).digest()
        )
        .decode()
        .strip()
    )
    return hmac.compare_digest(computed, signature)


@csrf_exempt
def tito_webhook(request):
    body = request.body
    signature = request.headers.get("tito-signature", "")

    if settings.TITO_SECURITY_TOKEN:
        if not signature or not verify_tito_signature(body, signature, settings.TITO_SECURITY_TOKEN):
            return HttpResponseForbidden("Invalid signature")

    payload = json.loads(body.decode())
    TitoWebhookEvent.objects.create(
        payload=payload,
        payload_text=body.decode(),
        trigger=request.headers.get("x-webhook-name"),
        tito_webhook_endpoint_id=request.headers.get("x-webhook-endpoint-id"),
        tito_signature=signature,
    )

    # Land online buyers on the roster right away so staff aren't waiting on the
    # nightly sync to see a purchase they were just told about.
    if request.headers.get("x-webhook-name") == "ticket.completed":
        try:
            attendee = record_webhook_attendee(payload)
        except Exception:
            logger.exception("Failed to record online attendee from webhook payload")
        else:
            # Send their link straight away rather than waiting for someone to
            # run a batch. Handed to the worker so a slow send or an empty pool
            # cannot fail the webhook and start Ti.to retrying it. Non-online
            # purchases come back as None and are left alone.
            if attendee is not None:
                async_task("tickets.tasks.email_new_online_attendee", attendee.pk)

    try:
        if settings.EMAILOCTOPUS_API_KEY:
            campaigns = Campaign.objects.filter(default=True)
            for campaign in campaigns:
                async_task(
                    "emailoctopus.utils.send_to_emailoctopus",
                    email=payload["email"],
                    name=f"{payload['first_name']} {payload['last_name']}",
                    list_id=campaign.list_id,
                )

    except Exception as e:
        print(f"[red]{e}: {payload=}[/red]")

    return HttpResponse("ok")


def _get_answer(answers, question_id):
    for answer in answers:
        if answer.get("question", {}).get("id") == question_id:
            return answer.get("humanized_response", "")
    return ""


def _parse_created_at(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _is_online_release(release_title: str) -> bool:
    return "online" in release_title.lower()


def _event_year(payload: dict) -> int | None:
    """Best-effort conference year for a webhook payload.

    Prefers the year embedded in the event slug (e.g. ``djangocon-us-2023``),
    then falls back to the event start/end dates, then the ticket created_at.
    """
    event = payload.get("event", {}) or {}
    for source in (event.get("slug", ""), event.get("end_date", ""), event.get("start_date", "")):
        match = re.search(r"(20\d{2})", source or "")
        if match:
            return int(match.group(1))
    created_at = _parse_created_at(payload.get("created_at", ""))
    return created_at.year if created_at else None


def _extract_historical_sprints(
    include_online: bool = False, years: int | None = HISTORICAL_YEARS, current_year: int | None = None
):
    """One row per person per conference year, across all events in the webhook log.

    Used by the "Download Historical" export so the sprints team can see who has
    attended in-person sprints over the last few years. Online sprints are excluded
    unless ``include_online`` is set.

    ``years`` limits the result to conference years on or after ``current_year - years``
    (``None`` keeps every year). The window is anchored to the calendar year, not to the
    most recent year present in the data, so it stays stable even if a year's webhooks are
    incomplete. ``current_year`` defaults to today's year and exists mainly for testing.
    """
    events = TitoWebhookEvent.objects.filter(trigger="ticket.completed")
    # Collect per email+year+release, keeping most recent.
    by_email_year_release = {}

    for event in events:
        payload = event.payload
        if not payload:
            continue

        release_title = payload.get("release_title", "")
        if "Sprint" not in release_title:
            continue

        is_online = _is_online_release(release_title)
        if is_online and not include_online:
            continue

        year = _event_year(payload)
        if year is None:
            continue

        answers = payload.get("answers", [])
        email = (payload.get("email") or "").strip().lower()
        created_at = _parse_created_at(payload.get("created_at", "")) or datetime.min.replace(tzinfo=timezone.utc)
        event_data = payload.get("event", {}) or {}
        event_title = event_data.get("title", "") or event_data.get("slug", "")

        key = (email, year, release_title)
        if key not in by_email_year_release or created_at > by_email_year_release[key]["created_at"]:
            by_email_year_release[key] = {
                "name": payload.get("name", ""),
                "email": email,
                "year": year,
                "event_title": event_title,
                "release_title": release_title,
                "is_online": is_online,
                "leading": _get_answer(answers, LEADER_QUESTION_ID),
                "joining": _get_answer(answers, JOINER_QUESTION_ID),
                "created_at": created_at,
            }

    # Limit to conference years within the last ``years`` calendar years of the current
    # year (e.g. 2026 with years=3 -> 2023 and newer). Anchoring to the calendar year
    # rather than the newest year in the data keeps the window stable when a year's
    # webhook coverage is incomplete.
    if years:
        if current_year is None:
            current_year = datetime.now(timezone.utc).year
        cutoff = current_year - years
        by_email_year_release = {k: v for k, v in by_email_year_release.items() if v["year"] >= cutoff}

    # Consolidate to one row per person per year.
    people = {}
    for ticket in by_email_year_release.values():
        person_key = (ticket["email"], ticket["year"])
        if person_key not in people:
            people[person_key] = {
                "name": ticket["name"],
                "email": ticket["email"],
                "year": ticket["year"],
                "event_title": ticket["event_title"],
                "thursday": False,
                "thursday_leading": "",
                "thursday_joining": "",
                "friday": False,
                "friday_leading": "",
                "friday_joining": "",
                "online": False,
                "created_at": ticket["created_at"],
            }

        person = people[person_key]
        if ticket["created_at"] > person["created_at"]:
            person["created_at"] = ticket["created_at"]
            person["name"] = ticket["name"]

        if ticket["is_online"]:
            person["online"] = True

        if "Thursday" in ticket["release_title"]:
            person["thursday"] = True
            person["thursday_leading"] = ticket["leading"]
            person["thursday_joining"] = ticket["joining"]
        elif "Friday" in ticket["release_title"]:
            person["friday"] = True
            person["friday_leading"] = ticket["leading"]
            person["friday_joining"] = ticket["joining"]

    return sorted(people.values(), key=lambda t: (-t["year"], (t["name"] or "").lower()))


def _extract_sprint_tickets(include_online: bool = False):
    events = TitoWebhookEvent.objects.filter(trigger="ticket.completed")
    # Collect per email+release, keeping most recent
    by_email_release = {}

    for event in events:
        payload = event.payload
        if not payload:
            continue

        event_slug = payload.get("event", {}).get("slug", "")
        if event_slug != EVENT_SLUG:
            continue

        release_title = payload.get("release_title", "")
        if "Sprint" not in release_title:
            continue

        is_online = _is_online_release(release_title)
        if is_online and not include_online:
            continue

        answers = payload.get("answers", [])
        email = (payload.get("email") or "").strip().lower()
        created_at = _parse_created_at(payload.get("created_at", "")) or datetime.min.replace(tzinfo=timezone.utc)

        key = (email, release_title)
        if key not in by_email_release or created_at > by_email_release[key]["created_at"]:
            by_email_release[key] = {
                "name": payload.get("name", ""),
                "email": email,
                "release_title": release_title,
                "is_online": is_online,
                "leading": _get_answer(answers, LEADER_QUESTION_ID),
                "joining": _get_answer(answers, JOINER_QUESTION_ID),
                "created_at": created_at,
            }

    # Consolidate to one row per person
    people = {}
    for ticket in by_email_release.values():
        email = ticket["email"]
        if email not in people:
            people[email] = {
                "name": ticket["name"],
                "email": email,
                "thursday": False,
                "thursday_leading": "",
                "thursday_joining": "",
                "friday": False,
                "friday_leading": "",
                "friday_joining": "",
                "online": False,
                "created_at": ticket["created_at"],
            }

        if ticket["created_at"] > people[email]["created_at"]:
            people[email]["created_at"] = ticket["created_at"]
            people[email]["name"] = ticket["name"]

        if ticket["is_online"]:
            people[email]["online"] = True

        if "Thursday" in ticket["release_title"]:
            people[email]["thursday"] = True
            people[email]["thursday_leading"] = ticket["leading"]
            people[email]["thursday_joining"] = ticket["joining"]
        elif "Friday" in ticket["release_title"]:
            people[email]["friday"] = True
            people[email]["friday_leading"] = ticket["leading"]
            people[email]["friday_joining"] = ticket["joining"]

    return sorted(people.values(), key=lambda t: t["created_at"], reverse=True)


SPRINT_EXTRA_COLUMNS = [
    "Thursday",
    "Thursday Leading",
    "Thursday Joining",
    "Friday",
    "Friday Leading",
    "Friday Joining",
    "Online",
]


def _sprint_row(row: dict) -> dict:
    """A sprint person in the shared column shape.

    The sprint reports never carried a ticket type of their own — the release
    title was decomposed into Thursday/Friday/Online flags and then discarded.
    Rebuilding it from those flags keeps the core columns honest.
    """
    days = [day for day, present in (("Thursday", row["thursday"]), ("Friday", row["friday"])) if present]
    kind = "Online Sprint" if row["online"] else "Sprint"
    ticket_type = f"{kind} — {' & '.join(days)}" if days else kind
    return {
        "Name": row["name"],
        "Email": row["email"],
        "Ticket Type": ticket_type,
        "Ticket Date": row["created_at"],
        "Thursday": bool(row["thursday"]),
        "Thursday Leading": row["thursday_leading"],
        "Thursday Joining": row["thursday_joining"],
        "Friday": bool(row["friday"]),
        "Friday Leading": row["friday_leading"],
        "Friday Joining": row["friday_joining"],
        "Online": bool(row["online"]),
    }


def _historical_sprints_csv(include_online: bool) -> HttpResponse:
    rows = _extract_historical_sprints(include_online=include_online)
    people = []
    for row in rows:
        person = _sprint_row(row)
        # Year and Event are what makes this report historical, but they go after
        # the core columns so "column 0 is the name" holds here too.
        person["Year"] = row["year"]
        person["Event"] = row["event_title"]
        people.append(person)
    return normalized_csv(
        "sprint_tickets_historical.csv",
        SPRINT_EXTRA_COLUMNS + ["Year", "Event"],
        people,
    )


@staff_member_required
def sprint_tickets_view(request: HttpRequest) -> HttpResponse:
    include_online = request.GET.get("include_online") == "1"

    if request.GET.get("scope") == "historical" and request.GET.get("format") == "csv":
        return _historical_sprints_csv(include_online=include_online)

    sprint_tickets = _extract_sprint_tickets(include_online=include_online)

    if request.GET.get("format") == "csv":
        return normalized_csv(
            "sprint_tickets.csv",
            SPRINT_EXTRA_COLUMNS,
            [_sprint_row(ticket) for ticket in sprint_tickets],
        )

    leaders_count = sum(1 for t in sprint_tickets if t["thursday_leading"] == "Yes" or t["friday_leading"] == "Yes")
    joiners_count = sum(1 for t in sprint_tickets if t["thursday_joining"] == "Yes" or t["friday_joining"] == "Yes")
    thursday_count = sum(1 for t in sprint_tickets if t["thursday"])
    friday_count = sum(1 for t in sprint_tickets if t["friday"])
    online_count = sum(1 for t in sprint_tickets if t["online"])

    context = {
        "sprint_tickets": sprint_tickets,
        "total_count": len(sprint_tickets),
        "leaders_count": leaders_count,
        "joiners_count": joiners_count,
        "thursday_count": thursday_count,
        "friday_count": friday_count,
        "online_count": online_count,
        "include_online": include_online,
        "historical_years": HISTORICAL_YEARS,
    }
    return render(request, "titowebhooks/sprint_tickets.html", context)


def _money(value) -> float:
    """Ti.to sends money as strings ("100.0"); missing/garbage becomes 0.0."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _release_prices(event_slug: str) -> dict[int, float]:
    """List price per release id, from the event's synced release list.

    The /tickets API leaves release_price off the ticket itself, so this is the
    only place face value can come from for API-sourced rows. Comp and sponsor
    releases carry a null price - they map to 0.0, which is why those rows show
    no face value rather than a made-up one.
    """
    event = TitoHistoricalEvent.objects.filter(slug=event_slug).first()
    prices = {}
    for release in (event.releases if event else None) or []:
        if release_id := release.get("id"):
            prices[release_id] = _money(release.get("price"))
    return prices


def _discount_breakdown(event_slug: str) -> dict:
    """What each discount code was redeemed for, and how much of it is left.

    Two sources, joined on the code, because neither one can answer the question
    alone. Ticket rows say what was *used*: how many tickets, at what face value,
    for what the attendee actually paid. TitoDiscountCode says what was *issued*:
    the cap Ti.to put on the code and how much of that cap is spent. A code
    nobody has redeemed appears only in the second, with a zero-ticket row, which
    is the whole point - "unused" and "never issued" look identical otherwise.

    The two ticket counts can legitimately disagree. Ti.to's quantity_used counts
    redemptions against the cap, which is not the same as tickets carrying the
    code - an organizer issuing tickets straight off a release can produce one
    without the other. Both numbers are reported rather than reconciled.
    """
    prices = _release_prices(event_slug)
    groups: dict[str, dict] = {}

    def group_for(code: str) -> dict:
        return groups.setdefault(
            code.lower(),
            {"code": code, "count": 0, "face_value": 0.0, "paid": 0.0, "releases": set(), "record": None},
        )

    for ticket in TitoTicket.objects.filter(event_slug=event_slug, voided=False).iterator():
        group = group_for(ticket.discount_code.strip())
        # Webhook-sourced rows carry the price on the ticket; API rows need the lookup.
        face = ticket.release_price or prices.get(ticket.release_id, 0.0)
        group["count"] += 1
        group["face_value"] += face
        group["paid"] += ticket.price
        if ticket.release_title:
            group["releases"].add(ticket.release_title)

    codes = list(TitoDiscountCode.objects.filter(event_slug=event_slug))
    for record in codes:
        group = group_for(record.code)
        group["code"] = record.code  # Ti.to's casing wins over whatever the ticket recorded
        group["record"] = record

    rows = []
    for group in groups.values():
        record = group.pop("record")
        group["discount"] = group["face_value"] - group["paid"]
        group["releases"] = sorted(group["releases"])
        group["known"] = record is not None
        group["issued"] = record.quantity if record else None
        group["redeemed"] = record.quantity_used if record else None
        group["remaining"] = record.remaining if record else None
        group["unlimited"] = record.unlimited if record else False
        group["used_up"] = record.used_up if record else False
        group["state"] = record.state if record else ""
        group["share_url"] = record.share_url if record else ""
        group["label"] = record.discount_label if record else ""
        # Ti.to's own count is the one that decides "has this been used at all",
        # so a code redeemed outside our ticket data still reads as used.
        group["unused"] = bool(group["code"]) and group["count"] == 0 and not (record.quantity_used if record else 0)
        rows.append(group)

    # Redeemed codes first (biggest discount at the top), then the issued-but-unused
    # ones alphabetically, with the no-code row pinned last.
    rows.sort(key=lambda r: (not r["code"], r["unused"], -r["discount"], r["code"].lower()))

    discounted = [r for r in rows if r["code"]]
    capped = [r for r in rows if r["issued"] is not None]
    return {
        "rows": rows,
        "has_data": bool(rows),
        "code_count": len(discounted),
        "discounted_tickets": sum(r["count"] for r in discounted),
        "total_tickets": sum(r["count"] for r in rows),
        "total_face_value": sum(r["face_value"] for r in rows),
        "total_paid": sum(r["paid"] for r in rows),
        "total_discount": sum(r["discount"] for r in rows),
        # Availability side: only meaningful once discount codes have been synced.
        "has_code_data": bool(codes),
        "issued_code_count": len(codes),
        "unused_code_count": sum(1 for r in rows if r["unused"]),
        "uncapped_code_count": sum(1 for r in rows if r["known"] and r["unlimited"]),
        "total_issued": sum(r["issued"] for r in capped),
        "total_redeemed": sum(r["redeemed"] or 0 for r in rows if r["known"]),
        "total_remaining": sum(r["remaining"] for r in capped),
    }


def _annotate_event_totals(events: list[TitoHistoricalEvent]) -> None:
    """Hang revenue and discount totals off each event, in place.

    Revenue is what attendees actually paid, summed from the ticket rows. Discounts
    are the gap between that and Raised, so the three figures reconcile on sight:
    Raised minus Discounts is Revenue.

    Years with no per-ticket detail get None rather than a zero, since "nothing
    synced" and "nothing given away" look identical at a glance and only one of them
    is good news.
    """
    revenue_by_year: dict[int, float] = {}
    counts: dict[int, int] = {}

    for year, price in TitoTicket.objects.filter(voided=False).values_list("year", "price"):
        revenue_by_year[year] = revenue_by_year.get(year, 0.0) + (price or 0.0)
        counts[year] = counts.get(year, 0) + 1

    for event in events:
        revenue = revenue_by_year.get(event.year)
        event.has_ticket_detail = revenue is not None

        if revenue is None:
            event.revenue_total = None
            event.discount_total = None
            event.ticket_detail_count = 0
            event.totals_partial = False
            event.face_value_understated = False
            continue

        event.revenue_total = revenue
        event.ticket_detail_count = counts[event.year]
        # Raised only counts releases that have a list price set. Comps and sponsor
        # allocations sell for real money against no list price, so a year can take in
        # more than its face value - which is not a discount, negative or otherwise.
        event.discount_total = max(event.total_revenue - revenue, 0.0)
        event.face_value_understated = revenue > event.total_revenue
        event.totals_partial = counts[event.year] < (event.total_sold or 0)


@superuser_required
def tito_sales_dashboard_view(request: HttpRequest) -> HttpResponse:
    events = list(TitoHistoricalEvent.objects.all())  # ordered by -year via Meta
    never_synced = not events
    _annotate_event_totals(events)

    context = {
        "events": events,
        "never_synced": never_synced,
        "discounts": _discount_breakdown(EVENT_SLUG),
        "curves": sales_curves(include_optional=request.GET.get("show") == "all"),
    }
    return render(request, "titowebhooks/sales_dashboard.html", context)


@superuser_required
@require_POST
def tito_sync_view(request: HttpRequest) -> HttpResponse:
    async_task("titowebhooks.sync.sync_tito_events")
    messages.success(request, "Tito sync queued. Refresh in a moment to see updated data.")
    return redirect("tito_sales_dashboard")


@superuser_required
@require_POST
def tito_sync_tickets_view(request: HttpRequest) -> HttpResponse:
    """Queue the per-ticket sync that feeds the days-out curves.

    Backfilling from webhooks first means the charts fill in immediately for the
    years we already have on hand, even if the API sync is slow or lacks access
    to the older events.
    """
    async_task("titowebhooks.sync.backfill_tickets_from_webhooks")
    async_task("titowebhooks.sync.sync_tito_tickets")
    messages.success(request, "Ticket history sync queued. This one walks every ticket, so give it a minute.")
    return redirect("tito_sales_dashboard")


def _extract_volunteer_interest() -> list[dict]:
    """Attendees who answered "Yes!" to the volunteering question on their ticket.

    Ti.to fires several webhooks per ticket (completed, updated, voided...), so the
    same person shows up many times. We keep only the most recent event per email
    address, then drop anyone whose latest event voided their ticket - they should
    not land on an outreach list.
    """
    events = TitoWebhookEvent.objects.filter(**{VOLUNTEER_RESPONSE_LOOKUP: VOLUNTEER_YES}).order_by("timestamp")

    latest_by_email: dict[str, TitoWebhookEvent] = {}
    for event in events:
        email = ((event.payload or {}).get("email") or "").strip().lower()
        if email:
            latest_by_email[email] = event  # ascending order, so the last write wins

    people = []
    for email, event in latest_by_email.items():
        if event.trigger == "ticket.voided":
            continue
        payload = event.payload or {}
        people.append(
            {
                "name": payload.get("name") or "",
                "email": email,
                "company_name": payload.get("company_name") or "",
                "reference": payload.get("reference") or "",
                "release_title": (payload.get("release") or {}).get("title") or "",
                "created_at": _parse_created_at(payload.get("created_at")),
                "trigger": event.trigger,
            }
        )

    return sorted(people, key=lambda p: p["name"].lower())


def _volunteer_interest_csv(people: list[dict]) -> HttpResponse:
    return normalized_csv(
        "volunteer_interest.csv",
        ["Company", "Ticket Reference"],
        [
            {
                "Name": person["name"],
                "Email": person["email"],
                "Ticket Type": person["release_title"],
                "Ticket Date": person["created_at"],
                "Company": person["company_name"],
                "Ticket Reference": person["reference"],
            }
            for person in people
        ],
    )


@volunteer_interest_required
def volunteer_interest_view(request: HttpRequest) -> HttpResponse:
    people = _extract_volunteer_interest()

    if request.GET.get("format") == "csv":
        return _volunteer_interest_csv(people)

    signed_up_emails = set(
        VolunteerSignup.objects.filter(cancelled=False).exclude(user__email="").values_list("user__email", flat=True)
    )
    signed_up_emails = {email.strip().lower() for email in signed_up_emails}

    for person in people:
        person["has_signed_up"] = person["email"] in signed_up_emails

    context = {
        "people": people,
        "total_count": len(people),
        "signed_up_count": sum(1 for p in people if p["has_signed_up"]),
        "not_signed_up_count": sum(1 for p in people if not p["has_signed_up"]),
    }
    return render(request, "titowebhooks/volunteer_interest.html", context)


@staff_member_required
def speakers_report_view(request: HttpRequest) -> HttpResponse:
    """Speaker ticket holders, as a CSV download."""
    people = ticket_holders(matches_speaker, event_slug=EVENT_SLUG)
    return normalized_csv("speakers.csv", ["Company", "Ticket Reference", "Online"], people)


@staff_member_required
def sponsors_report_view(request: HttpRequest) -> HttpResponse:
    """Sponsor ticket holders, as a CSV download."""
    people = ticket_holders(matches_sponsor, event_slug=EVENT_SLUG)
    return normalized_csv("sponsors.csv", ["Company", "Ticket Reference", "Online"], people)
