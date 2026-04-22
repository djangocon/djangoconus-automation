from django.contrib import admin
from django_q.tasks import async_task
from rich import print

from emailoctopus.models import Campaign
from titowebhooks.models import TitoHistoricalEvent, TitoWebhookEvent


@admin.action(description="Send Event to Email Octopus")
def send_to_emailoctopus_action(modeladmin, request, queryset):
    campaigns = Campaign.objects.filter(default=True)
    for campaign in campaigns:
        for event in queryset:
            try:
                async_task(
                    "emailoctopus.utils.send_to_emailoctopus",
                    email=event.payload["email"],
                    name=f"{event.payload['first_name']} {event.payload['last_name']}",
                    list_id=campaign.list_id,
                )

            except Exception as e:
                print(f"[red]{event=}: {e}[/red]")


@admin.register(TitoHistoricalEvent)
class TitoHistoricalEventAdmin(admin.ModelAdmin):
    list_display = ["title", "year", "is_current", "goal", "total_sold", "percent_of_goal", "last_synced"]
    list_filter = ["is_current"]
    readonly_fields = ["slug", "year", "title", "account_slug", "releases", "last_synced"]
    fields = ["slug", "year", "title", "account_slug", "is_current", "goal", "releases", "last_synced"]
    ordering = ["-year"]

    @admin.display(description="Sold")
    def total_sold(self, obj):
        return obj.total_sold

    @admin.display(description="% of Goal")
    def percent_of_goal(self, obj):
        pct = obj.percent_of_goal
        return f"{pct}%" if pct is not None else "—"


@admin.register(TitoWebhookEvent)
class TitoWebhookEventAdmin(admin.ModelAdmin):
    actions = [send_to_emailoctopus_action]
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
