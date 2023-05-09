import json

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django_q.tasks import async_task
from rich import print

from sendy.models import List
from titowebhooks.models import TitoWebhookEvent


@csrf_exempt
def tito_webhook(request):
    payload = json.loads(request.body.decode())
    TitoWebhookEvent.objects.create(
        payload=payload,
        payload_text=request.body.decode(),
        trigger=request.META.get("HTTP_X_WEBHOOK_NAME"),
        tito_webhook_endpoint_id=request.META.get("HTTP_X_WEBHOOK_ENDPOINT_ID"),
        tito_signature=request.META.get("HTTP_TITO_SIGNATURE"),
    )

    try:
        if settings.SENDY_ENDPONT_URL and settings.SENDY_API_KEY:
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
