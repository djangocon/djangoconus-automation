import base64
import csv
import hashlib
import hmac
import json

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django_q.tasks import async_task
from rich import print

from emailoctopus.models import List
from titowebhooks.models import TitoWebhookEvent

LEADER_QUESTION_ID = 1216404
JOINER_QUESTION_ID = 1216405
EVENT_SLUG = "djangocon-us-2026"


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
            eo_lists = List.objects.filter(default=True)
            for eo_list in eo_lists:
                async_task(
                    "emailoctopus.utils.send_to_emailoctopus",
                    email=payload["email"],
                    name=f"{payload['first_name']} {payload['last_name']}",
                    list_id=eo_list.list_id,
                )

    except Exception as e:
        print(f"[red]{e}: {payload=}[/red]")

    return HttpResponse("ok")


def _get_answer(answers, question_id):
    for answer in answers:
        if answer.get("question", {}).get("id") == question_id:
            return answer.get("humanized_response", "")
    return ""


def _extract_sprint_tickets():
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

        answers = payload.get("answers", [])
        email = payload.get("email", "")
        created_at = payload.get("created_at", "")

        key = (email, release_title)
        if key not in by_email_release or created_at > by_email_release[key]["created_at"]:
            by_email_release[key] = {
                "name": payload.get("name", ""),
                "email": email,
                "release_title": release_title,
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
                "created_at": ticket["created_at"],
            }

        if ticket["created_at"] > people[email]["created_at"]:
            people[email]["created_at"] = ticket["created_at"]
            people[email]["name"] = ticket["name"]

        if "Thursday" in ticket["release_title"]:
            people[email]["thursday"] = True
            people[email]["thursday_leading"] = ticket["leading"]
            people[email]["thursday_joining"] = ticket["joining"]
        elif "Friday" in ticket["release_title"]:
            people[email]["friday"] = True
            people[email]["friday_leading"] = ticket["leading"]
            people[email]["friday_joining"] = ticket["joining"]

    return sorted(people.values(), key=lambda t: t["created_at"], reverse=True)


@staff_member_required
def sprint_tickets_view(request: HttpRequest) -> HttpResponse:
    sprint_tickets = _extract_sprint_tickets()

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
                    ticket["created_at"],
                ]
            )
        return response

    leaders_count = sum(1 for t in sprint_tickets if t["thursday_leading"] == "Yes" or t["friday_leading"] == "Yes")
    joiners_count = sum(1 for t in sprint_tickets if t["thursday_joining"] == "Yes" or t["friday_joining"] == "Yes")
    thursday_count = sum(1 for t in sprint_tickets if t["thursday"])
    friday_count = sum(1 for t in sprint_tickets if t["friday"])

    context = {
        "sprint_tickets": sprint_tickets,
        "total_count": len(sprint_tickets),
        "leaders_count": leaders_count,
        "joiners_count": joiners_count,
        "thursday_count": thursday_count,
        "friday_count": friday_count,
    }
    return render(request, "titowebhooks/sprint_tickets.html", context)
