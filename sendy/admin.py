from django.contrib import admin

from sendy.models import Brand
from sendy.models import List


@admin.action(description="Set active to False")
def set_active_to_false(modeladmin, request, queryset):
    queryset.update(active=False)


@admin.action(description="Set active to True")
def set_active_to_true(modeladmin, request, queryset):
    queryset.update(active=True)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["brand_id", "name"]


@admin.register(List)
class ListAdmin(admin.ModelAdmin):
    actions = [set_active_to_true, set_active_to_false]
    list_display = ["list_id", "name", "active", "default"]
    list_filter = ["default", "active"]
    ordering = ["-default", "-pk"]
