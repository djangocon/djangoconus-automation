from django.contrib import admin

from .models import OnlineAttendee, TicketEmailLog, TicketLink, TicketRelease


@admin.register(TicketLink)
class TicketLinkAdmin(admin.ModelAdmin):
    list_display = (
        "link",
        "attendee_email",
        "date_link_created",
        "date_link_assigned",
        "is_assigned",
        "superseded_at",
    )
    list_filter = ("date_link_created", "date_link_assigned", "superseded_at")
    search_fields = ("link", "attendee_email")
    readonly_fields = ("date_link_created", "date_link_assigned")
    raw_id_fields = ("attendee",)
    ordering = ("-date_link_created",)

    @admin.display(
        description="Assigned",
        boolean=True,
    )
    def is_assigned(self, obj):
        return obj.attendee_email is not None

    def get_readonly_fields(self, request, obj=None):
        if obj:  # When editing an existing object
            return self.readonly_fields + ("link",)
        return self.readonly_fields


@admin.register(OnlineAttendee)
class OnlineAttendeeAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "year", "release_title", "purchased_at", "source", "has_ticket")
    list_filter = ("year", "source", "release_title")
    search_fields = ("email", "name")
    readonly_fields = ("date_created", "last_synced")
    ordering = ("-year", "email")

    @admin.display(description="Has link", boolean=True)
    def has_ticket(self, obj):
        return obj.has_ticket


@admin.register(TicketEmailLog)
class TicketEmailLogAdmin(admin.ModelAdmin):
    list_display = ("to_email", "kind", "status", "date_queued", "date_sent", "sent_by")
    list_filter = ("status", "kind", "date_queued")
    search_fields = ("to_email", "subject", "error")
    readonly_fields = ("date_queued", "date_sent")
    raw_id_fields = ("attendee", "ticket_link", "sent_by")
    ordering = ("-date_queued",)


@admin.register(TicketRelease)
class TicketReleaseAdmin(admin.ModelAdmin):
    list_display = ("title", "year", "grants_venueless_access", "release_id", "last_synced")
    # Editable straight from the list: toggling these is the reason the model
    # exists, and making staff open each row to flip one checkbox is friction.
    list_editable = ("grants_venueless_access",)
    list_filter = ("year", "grants_venueless_access")
    search_fields = ("title",)
    readonly_fields = ("date_created", "last_synced")
    ordering = ("-year", "title")
