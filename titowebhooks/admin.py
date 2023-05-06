from django.conf import settings
from django.contrib import admin
from rich import print

from titowebhooks.models import TitoWebhookEvent
from titowebhooks.utils import send_to_sendy


@admin.action(description="Send Event to Sendy")
def send_to_sendy_action(modeladmin, request, queryset):
    # queryset.update(status="p")
    for event in queryset:
        try:
            send_to_sendy(
                email=event.payload["email"],
                name=f"{event.payload['first_name']} {event.payload['last_name']}",
                campaign_id=settings.SENDY_CAMPAIGN_ID,
            )
        except Exception as e:
            print(f"[red]{e}[/red]")


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
