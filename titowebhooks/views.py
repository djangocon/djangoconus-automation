import base64
import hashlib
import hmac
import json

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django_q.tasks import async_task
from rich import print

from sendy.models import List
from titowebhooks.models import TitoWebhookEvent


def verify_tito_signature(payload_body: bytes, signature: str, security_token: str) -> bool:
    computed = base64.b64encode(
        hmac.new(
            security_token.encode(),
            payload_body,
            hashlib.sha256,
        ).digest()
    ).decode().strip()
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
