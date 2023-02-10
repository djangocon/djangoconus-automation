from django.contrib import admin

from titowebhooks.models import *


@admin.register(TitoWebhookEvent)
class TitoWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'trigger', 'processed', 'processing_failed')
    list_filter = ('trigger', 'processed', 'processing_failed')
