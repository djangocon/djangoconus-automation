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
from titowebhooks.models import TitoHistoricalEvent, TitoWebhookEvent

superuser_required = user_passes_test(lambda u: u.is_active and u.is_superuser)

LEADER_QUESTION_ID = 1216404
JOINER_QUESTION_ID = 1216405
EVENT_SLUG = "djangocon-us-2026"

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


def _extract_historical_sprints(include_online: bool = False, years: int | None = HISTORICAL_YEARS):
    """One row per person per conference year, across all events in the webhook log.

    Used by the "Download Historical" export so the sprints team can see who has
    attended in-person sprints over the last few years. Online sprints are excluded
    unless ``include_online`` is set. ``years`` limits the result to the most recent
    N conference years present in the data (``None`` keeps every year).
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

    # Limit to the most recent N conference years present in the data.
    if years and by_email_year_release:
        max_year = max(t["year"] for t in by_email_year_release.values())
        cutoff = max_year - years + 1
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


@superuser_required
def tito_sales_dashboard_view(request: HttpRequest) -> HttpResponse:
    events = TitoHistoricalEvent.objects.all()  # ordered by -year via Meta
    never_synced = not events.exists()

    context = {
        "events": events,
        "never_synced": never_synced,
    }
    return render(request, "titowebhooks/sales_dashboard.html", context)


@superuser_required
@require_POST
def tito_sync_view(request: HttpRequest) -> HttpResponse:
    async_task("titowebhooks.sync.sync_tito_events")
    messages.success(request, "Tito sync queued. Refresh in a moment to see updated data.")
    return redirect("tito_sales_dashboard")
