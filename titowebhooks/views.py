import base64
import csv
import hashlib
import hmac
import json
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
from titowebhooks.models import TitoHistoricalEvent, TitoTicket, TitoWebhookEvent
from titowebhooks.sales_curve import sales_curves
from volunteers.models import VolunteerSignup

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


def _historical_sprints_csv(include_online: bool) -> HttpResponse:
    rows = _extract_historical_sprints(include_online=include_online)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="sprint_tickets_historical.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Year",
            "Event",
            "Name",
            "Email",
            "Thursday",
            "Thursday Leading",
            "Thursday Joining",
            "Friday",
            "Friday Leading",
            "Friday Joining",
            "Online",
            "Ticket Date",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["year"],
                row["event_title"],
                row["name"],
                row["email"],
                "Yes" if row["thursday"] else "",
                row["thursday_leading"],
                row["thursday_joining"],
                "Yes" if row["friday"] else "",
                row["friday_leading"],
                row["friday_joining"],
                "Yes" if row["online"] else "",
                row["created_at"].isoformat() if row["created_at"] else "",
            ]
        )
    return response


@staff_member_required
def sprint_tickets_view(request: HttpRequest) -> HttpResponse:
    include_online = request.GET.get("include_online") == "1"

    if request.GET.get("scope") == "historical" and request.GET.get("format") == "csv":
        return _historical_sprints_csv(include_online=include_online)

    sprint_tickets = _extract_sprint_tickets(include_online=include_online)

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sprint_tickets.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Name",
                "Email",
                "Thursday",
                "Thursday Leading",
                "Thursday Joining",
                "Friday",
                "Friday Leading",
                "Friday Joining",
                "Online",
                "Ticket Date",
            ]
        )
        for ticket in sprint_tickets:
            writer.writerow(
                [
                    ticket["name"],
                    ticket["email"],
                    "Yes" if ticket["thursday"] else "",
                    ticket["thursday_leading"],
                    ticket["thursday_joining"],
                    "Yes" if ticket["friday"] else "",
                    ticket["friday_leading"],
                    ticket["friday_joining"],
                    "Yes" if ticket["online"] else "",
                    ticket["created_at"].isoformat() if ticket["created_at"] else "",
                ]
            )
        return response

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


def _latest_tickets_for_event(event_slug: str) -> list[dict]:
    """Most recent payload per ticket for an event, with voided tickets dropped.

    Ti.to fires a webhook per ticket for every state change, so the same ticket
    appears many times. We keep the last event per ticket slug and then drop the
    ones whose final state was a void - those were never really sold.
    """
    events = TitoWebhookEvent.objects.filter(payload__event__slug=event_slug).order_by("timestamp")

    latest_by_ticket: dict[str, TitoWebhookEvent] = {}
    for event in events:
        payload = event.payload or {}
        key = payload.get("slug") or payload.get("reference") or str(payload.get("id") or "")
        if key:
            latest_by_ticket[key] = event  # ascending order, so the last write wins

    tickets = []
    for event in latest_by_ticket.values():
        if event.trigger == "ticket.voided":
            continue
        payload = event.payload or {}
        if (payload.get("state_name") or "").lower() in {"void", "voided"}:
            continue
        tickets.append(payload)

    return tickets


def _discount_breakdown(event_slug: str) -> dict:
    """Group the current event's tickets by the discount code used.

    Face value comes from `release_price` (the list price of the release) and what
    the attendee actually paid from `price`; the gap between them is what the code
    was worth. Tickets bought without a code are reported as their own row so the
    totals still reconcile against the sales table.
    """
    groups: dict[str, dict] = {}

    for payload in _latest_tickets_for_event(event_slug):
        code = (payload.get("discount_code_used") or "").strip()
        group = groups.setdefault(
            code,
            {"code": code, "count": 0, "face_value": 0.0, "paid": 0.0, "releases": set()},
        )
        face = _money(payload.get("release_price"))
        paid = _money(payload.get("price"))
        group["count"] += 1
        group["face_value"] += face
        group["paid"] += paid
        if title := payload.get("release_title"):
            group["releases"].add(title)

    rows = []
    for group in groups.values():
        group["discount"] = group["face_value"] - group["paid"]
        group["releases"] = sorted(group["releases"])
        rows.append(group)

    # Codes first (biggest discount at the top), with the no-code row pinned last.
    rows.sort(key=lambda r: (not r["code"], -r["discount"], r["code"].lower()))

    discounted = [r for r in rows if r["code"]]
    return {
        "rows": rows,
        "has_data": bool(rows),
        "code_count": len(discounted),
        "discounted_tickets": sum(r["count"] for r in discounted),
        "total_tickets": sum(r["count"] for r in rows),
        "total_face_value": sum(r["face_value"] for r in rows),
        "total_paid": sum(r["paid"] for r in rows),
        "total_discount": sum(r["discount"] for r in rows),
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
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="volunteer_interest.csv"'
    writer = csv.writer(response)
    writer.writerow(["Name", "Email", "Company", "Ticket Reference", "Ticket Type", "Ticket Date"])
    for person in people:
        writer.writerow(
            [
                person["name"],
                person["email"],
                person["company_name"],
                person["reference"],
                person["release_title"],
                person["created_at"].isoformat() if person["created_at"] else "",
            ]
        )
    return response


@superuser_required
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
