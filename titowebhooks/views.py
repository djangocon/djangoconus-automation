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

from sendy.models import List
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
        if settings.SENDY_ENDPOINT_URL and settings.SENDY_API_KEY:
            sendy_lists = List.objects.filter(default=True)
            for sendy_list in sendy_lists:
                async_task(
                    "sendy.utils.send_to_sendy",
                    email=payload["email"],
                    name=f"{payload['first_name']} {payload['last_name']}",
                    campaign_id=sendy_list.list_id,
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
    sprint_tickets = []
    seen_emails = {}

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

        # Keep the most recent ticket per email+release combo
        key = (email, release_title)
        ticket_data = {
            "name": payload.get("name", ""),
            "email": email,
            "release_title": release_title,
            "leading": _get_answer(answers, LEADER_QUESTION_ID),
            "joining": _get_answer(answers, JOINER_QUESTION_ID),
            "created_at": payload.get("created_at", ""),
        }

        if key not in seen_emails or ticket_data["created_at"] > seen_emails[key]["created_at"]:
            seen_emails[key] = ticket_data

    sprint_tickets = sorted(seen_emails.values(), key=lambda t: t["created_at"], reverse=True)
    return sprint_tickets


@staff_member_required
def sprint_tickets_view(request: HttpRequest) -> HttpResponse:
    sprint_tickets = _extract_sprint_tickets()

    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sprint_tickets.csv"'
        writer = csv.writer(response)
        writer.writerow(["Name", "Email", "Sprint Day", "Leading", "Joining", "Ticket Date"])
        for ticket in sprint_tickets:
            writer.writerow(
                [
                    ticket["name"],
                    ticket["email"],
                    ticket["release_title"],
                    ticket["leading"],
                    ticket["joining"],
                    ticket["created_at"],
                ]
            )
        return response

    leaders_count = sum(1 for t in sprint_tickets if t["leading"] == "Yes")
    joiners_count = sum(1 for t in sprint_tickets if t["joining"] == "Yes")
    thursday_count = sum(1 for t in sprint_tickets if "Thursday" in t["release_title"])
    friday_count = sum(1 for t in sprint_tickets if "Friday" in t["release_title"])

    context = {
        "sprint_tickets": sprint_tickets,
        "total_count": len(sprint_tickets),
        "leaders_count": leaders_count,
        "joiners_count": joiners_count,
        "thursday_count": thursday_count,
        "friday_count": friday_count,
    }
    return render(request, "titowebhooks/sprint_tickets.html", context)
