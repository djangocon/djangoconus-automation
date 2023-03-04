import json

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from titowebhooks.models import TitoWebhookEvent


@csrf_exempt
def tito_webhook(request):
    TitoWebhookEvent.objects.create(
        payload=json.loads(request.body.decode()),
        payload_text=request.body.decode(),
        trigger=request.META.get("HTTP_X_WEBHOOK_NAME"),
        tito_webhook_endpoint_id=request.META.get("HTTP_X_WEBHOOK_ENDPOINT_ID"),
        tito_signature=request.META.get("HTTP_TITO_SIGNATURE"),
    )

    return HttpResponse("ok")
