from django.contrib import admin

from .models import CalendarToken, Role, Shift, VolunteerSignup


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


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]
    search_fields = ["name"]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ["title", "role", "starts_at", "ends_at", "capacity", "filled", "spots_left", "signups_open"]
    list_filter = ["signups_open", "role", "starts_at"]
    search_fields = ["title", "location"]
    date_hierarchy = "starts_at"
    inlines = [VolunteerSignupInline]


@admin.register(VolunteerSignup)
class VolunteerSignupAdmin(admin.ModelAdmin):
    list_display = ["user", "shift", "cancelled", "reminded", "created_at"]
    list_filter = ["cancelled", "reminded", "shift__role"]
    search_fields = ["user__email", "shift__title"]
    autocomplete_fields = ["user", "shift"]
