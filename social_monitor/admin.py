from django.contrib import admin

from .models import PlatformHashTag, SocialPlatform


@admin.register(SocialPlatform)
class SocialPlatformAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "last_seen",
        "get_mentions",
    )


@admin.register(PlatformHashTag)
class PlatformHashTagAdmin(admin.ModelAdmin):
    list_display = (
        "platform",
        "query",
        "last_seen",
        "is_active",
    )
