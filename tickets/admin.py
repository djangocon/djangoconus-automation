from django.contrib import admin

from .models import TicketLink


@admin.register(TicketLink)
class TicketLinkAdmin(admin.ModelAdmin):
    list_display = (
        "link",
        "attendee_email",
        "date_link_created",
        "date_link_assigned",
        "date_link_accessed",
        "is_accessed",
    )
    list_filter = ("date_link_created", "date_link_assigned", "date_link_accessed")
    search_fields = ("link", "attendee_email")
    readonly_fields = ("date_link_created", "date_link_accessed", "date_link_assigned")
    ordering = ("-date_link_created",)

    @admin.display(
        description="Accessed",
        boolean=True,
    )
    def is_accessed(self, obj):
        return obj.date_link_accessed is not None

    def get_readonly_fields(self, request, obj=None):
        if obj:  # When editing an existing object
            return self.readonly_fields + ("link",)
        return self.readonly_fields
