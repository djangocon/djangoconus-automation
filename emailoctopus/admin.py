from django.contrib import admin

from emailoctopus.models import Campaign


@admin.action(description="Set active to False")
def set_active_to_false(modeladmin, request, queryset):
    queryset.update(active=False)


@admin.action(description="Set active to True")
def set_active_to_true(modeladmin, request, queryset):
    queryset.update(active=True)


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    actions = [set_active_to_true, set_active_to_false]
    list_display = ["list_id", "name", "active", "default"]
    list_filter = ["default", "active"]
    ordering = ["-default", "-pk"]
