from django.contrib import admin

from .models import CalendarToken, Role, Shift, Talk, VolunteerProfile, VolunteerSignup


@admin.register(VolunteerProfile)
class VolunteerProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "updated_at"]
    search_fields = ["user__email", "contact_info"]
    autocomplete_fields = ["user"]


@admin.register(CalendarToken)
class CalendarTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "token"]
    search_fields = ["user__email"]
    readonly_fields = ["token"]


class VolunteerSignupInline(admin.TabularInline):
    model = VolunteerSignup
    extra = 0
    autocomplete_fields = ["user"]
    readonly_fields = ["created_at"]


class TalkInline(admin.TabularInline):
    model = Talk
    extra = 0
    fields = ["title", "starts_at", "ends_at", "location", "talk_url"]


@admin.register(Talk)
class TalkAdmin(admin.ModelAdmin):
    list_display = ["title", "starts_at", "ends_at", "location", "shift"]
    list_filter = ["location", "starts_at"]
    search_fields = ["title", "external_uid"]
    autocomplete_fields = ["shift"]
    date_hierarchy = "starts_at"


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "documentation_url"]
    search_fields = ["name"]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["title", "role", "starts_at", "ends_at", "capacity", "filled", "spots_left", "signups_open"]
    list_filter = ["signups_open", "role", "starts_at"]
    search_fields = ["title", "location"]
    date_hierarchy = "starts_at"
    inlines = [TalkInline, VolunteerSignupInline]


@admin.register(VolunteerSignup)
class VolunteerSignupAdmin(admin.ModelAdmin):
    list_display = ["user", "shift", "cancelled", "reminded", "created_at"]
    list_filter = ["cancelled", "reminded", "shift__role"]
    search_fields = ["user__email", "shift__title"]
    autocomplete_fields = ["user", "shift"]
