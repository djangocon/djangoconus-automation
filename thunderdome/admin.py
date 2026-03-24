from django.contrib import admin, messages
from django.db.models import Avg, Count, Q
from django.utils.text import Truncator

from .models import Event, Review, Speaker, Submission, Tag

THUNDERDOME_PERMISSION = "thunderdome"


class ThunderdomeAdminMixin:
    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        return request.user.groups.filter(name=THUNDERDOME_PERMISSION).exists()

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


@admin.register(Event)
class EventAdmin(ThunderdomeAdminMixin, admin.ModelAdmin):
    list_display = ["name", "pretalx_slug", "start_date", "end_date"]
    search_fields = ["name", "pretalx_slug"]


@admin.register(Tag)
class TagAdmin(ThunderdomeAdminMixin, admin.ModelAdmin):
    list_display = ["name", "pretalx_id"]
    search_fields = ["name"]


@admin.register(Speaker)
class SpeakerAdmin(ThunderdomeAdminMixin, admin.ModelAdmin):
    list_display = ["name", "pretalx_code"]
    search_fields = ["name", "pretalx_code"]


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 1
    fields = ["reviewer_name", "user", "score", "notes"]


@admin.register(Submission)
class SubmissionAdmin(ThunderdomeAdminMixin, admin.ModelAdmin):
    list_display = [
        "pretalx_id",
        "title",
        "speaker_names",
        "track",
        "duration",
        "pretalx_state",
        "state",
        "abstract_snippet",
        "review_count_display",
        "review_mean_display",
    ]
    list_filter = ["event", "pretalx_state", "state", "duration", "tags"]
    list_editable = ["state"]
    search_fields = ["pretalx_id", "title", "speakers__name", "abstract"]
    readonly_fields = ["pretalx_id", "pretalx_state", "created_at", "updated_at"]
    filter_horizontal = ["speakers", "tags"]
    inlines = [ReviewInline]

    fieldsets = (
        (None, {"fields": ("pretalx_id", "event", "title", "track", "duration", "pretalx_state", "state")}),
        ("Speakers & Tags", {"fields": ("speakers", "tags")}),
        ("Content", {"fields": ("abstract", "description"), "classes": ("collapse",)}),
        ("Notes", {"fields": ("notes", "internal_notes"), "classes": ("collapse",)}),
        ("System", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = [
        "accept_in_person",
        "accept_online",
        "reject_submissions",
        "waitlist_in_person",
        "waitlist_online",
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _review_count=Count("reviews", filter=~Q(reviews__score__isnull=True)),
            _review_mean=Avg("reviews__score"),
        )

    @admin.display(description="Speakers")
    def speaker_names(self, obj):
        return ", ".join(s.name for s in obj.speakers.all())

    @admin.display(description="Abstract")
    def abstract_snippet(self, obj):
        return Truncator(obj.abstract).chars(100)

    @admin.display(description="Reviews", ordering="_review_count")
    def review_count_display(self, obj):
        return obj._review_count

    @admin.display(description="Mean Score", ordering="_review_mean")
    def review_mean_display(self, obj):
        if obj._review_mean is None:
            return "-"
        return f"{obj._review_mean:.1f}"

    @admin.action(description="Set state: Accepted (In-Person)")
    def accept_in_person(self, request, queryset):
        count = queryset.update(state="accepted-in-person")
        self.message_user(request, f"{count} submission(s) set to Accepted (In-Person).", messages.SUCCESS)

    @admin.action(description="Set state: Accepted (Online)")
    def accept_online(self, request, queryset):
        count = queryset.update(state="accepted-online")
        self.message_user(request, f"{count} submission(s) set to Accepted (Online).", messages.SUCCESS)

    @admin.action(description="Set state: Rejected")
    def reject_submissions(self, request, queryset):
        count = queryset.update(state="rejected")
        self.message_user(request, f"{count} submission(s) set to Rejected.", messages.SUCCESS)

    @admin.action(description="Set state: Waitlist (In-Person)")
    def waitlist_in_person(self, request, queryset):
        count = queryset.update(state="waitlist-in-person")
        self.message_user(request, f"{count} submission(s) set to Waitlist (In-Person).", messages.SUCCESS)

    @admin.action(description="Set state: Waitlist (Online)")
    def waitlist_online(self, request, queryset):
        count = queryset.update(state="waitlist-online")
        self.message_user(request, f"{count} submission(s) set to Waitlist (Online).", messages.SUCCESS)


@admin.register(Review)
class ReviewAdmin(ThunderdomeAdminMixin, admin.ModelAdmin):
    list_display = ["submission", "reviewer_display", "score", "notes_snippet", "created_at"]
    list_filter = ["score"]
    search_fields = ["submission__title", "submission__pretalx_id", "reviewer_name", "user__email"]
    raw_id_fields = ["submission"]

    @admin.display(description="Reviewer")
    def reviewer_display(self, obj):
        return obj.display_name

    @admin.display(description="Notes")
    def notes_snippet(self, obj):
        return Truncator(obj.notes).chars(80)
