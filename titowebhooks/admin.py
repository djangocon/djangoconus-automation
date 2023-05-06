from django.conf import settings
from django.contrib import admin
from django_q.tasks import async_task

from titowebhooks.models import TitoWebhookEvent


@admin.action(description="Send Event to Sendy")
def send_to_sendy_action(modeladmin, request, queryset):
    for event in queryset:
        async_task(
            "titowebhooks.utils.send_to_sendy",
            email=event.payload["email"],
            name=f"{event.payload['first_name']} {event.payload['last_name']}",
            campaign_id=settings.SENDY_CAMPAIGN_ID,
        )


@admin.register(TitoWebhookEvent)
class TitoWebhookEventAdmin(admin.ModelAdmin):
    actions = [send_to_sendy_action]
    list_display = ("timestamp", "trigger", "processed", "processing_failed")
    list_filter = ("trigger", "processed", "processing_failed")
    readonly_fields = [
        "trigger",
        "tito_webhook_endpoint_id",
        "tito_signature",
        "payload",
        "payload_text",
    ]
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "trigger",
                    "tito_webhook_endpoint_id",
                    "tito_signature",
                    "processed",
                    "processing_failed",
                ],
            },
        ),
        (
            "Payload information",
            {
                "classes": ["collapse"],
                "fields": [
                    "payload",
                    "payload_text",
                ],
            },
        ),
    ]
