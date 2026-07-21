from collections import defaultdict
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .ical import build_calendar
from .models import (
    CalendarToken,
    Shift,
    VolunteerSignup,
    conflicting_shifts,
    total_volunteer_hours,
)


def max_volunteer_hours():
    return getattr(settings, "VOLUNTEER_MAX_HOURS", 8)


def volunteer_handbook_url():
    return getattr(settings, "VOLUNTEER_HANDBOOK_URL", "")


def shift_list_view(request):
    """Upcoming shifts anyone can browse; signing up or cancelling still requires login."""
    all_shifts = Shift.objects.filter(ends_at__gte=timezone.now()).select_related("role")

    roles = sorted({s.role.name for s in all_shifts})

    role_filter = request.GET.get("role", "")
    needs_help = request.GET.get("needs_help") == "1"

    shifts = all_shifts.annotate(filled_count=Count("signups", filter=Q(signups__cancelled=False))).order_by(
        "starts_at", "title"
    )
    if role_filter:
        shifts = shifts.filter(role__name=role_filter)
    if needs_help:
        shifts = shifts.filter(filled_count=0)

    if request.user.is_authenticated:
        my_shift_ids = set(
            VolunteerSignup.objects.filter(user=request.user, cancelled=False).values_list("shift_id", flat=True)
        )
        my_hours = total_volunteer_hours(request.user)
    else:
        my_shift_ids = set()
        my_hours = 0

    days = defaultdict(list)
    for shift in shifts:
        days[shift.starts_at.date()].append(shift)

    context = {
        "page_title": "Volunteer Sign-up",
        "days": sorted(days.items()),
        "my_shift_ids": my_shift_ids,
        "my_hours": my_hours,
        "max_hours": max_volunteer_hours(),
        "roles": roles,
        "role_filter": role_filter,
        "needs_help": needs_help,
        "handbook_url": volunteer_handbook_url(),
    }
    return render(request, "volunteers/shift_list.html", context)


@login_required
def my_shifts_view(request):
    """The signed-in attendee's own shifts."""
    signups = (
        VolunteerSignup.objects.filter(user=request.user, cancelled=False)
        .select_related("shift", "shift__role")
        .order_by("shift__starts_at")
    )
    token, _ = CalendarToken.objects.get_or_create(user=request.user)
    context = {
        "page_title": "My Volunteer Shifts",
        "signups": signups,
        "my_hours": total_volunteer_hours(request.user),
        "max_hours": max_volunteer_hours(),
        "calendar_url": request.build_absolute_uri(reverse("volunteers:calendar", args=[token.token])),
        "handbook_url": volunteer_handbook_url(),
    }
    return render(request, "volunteers/my_shifts.html", context)


def calendar_feed(request, token):
    """Per-volunteer iCal feed, reached by unguessable token (no login)."""
    calendar_token = get_object_or_404(CalendarToken, token=token)
    signups = (
        VolunteerSignup.objects.filter(user=calendar_token.user, cancelled=False)
        .select_related("shift", "shift__role")
        .order_by("shift__starts_at")
    )
    ics = build_calendar(signups, host=request.get_host())
    return HttpResponse(ics, content_type="text/calendar; charset=utf-8")


@login_required
@require_POST
def signup_view(request, pk):
    """Claim a shift, enforcing conflicts and the per-person hours cap.

    Capacity is a visual guide for organizers, not a hard cap.
    """
    shift = get_object_or_404(Shift.objects.select_related("role"), pk=pk)

    ok, reason = shift.can_sign_up()
    if not ok:
        messages.error(request, reason)
        return redirect("volunteers:shifts")

    if VolunteerSignup.objects.filter(shift=shift, user=request.user, cancelled=False).exists():
        messages.info(request, "You're already signed up for this shift.")
        return redirect("volunteers:shifts")

    conflicts = conflicting_shifts(request.user, shift)
    if conflicts:
        names = ", ".join(c.title for c in conflicts)
        messages.error(request, f"This overlaps a shift you're already on: {names}.")
        return redirect("volunteers:shifts")

    projected = total_volunteer_hours(request.user) + shift.duration_hours
    if projected > max_volunteer_hours():
        messages.error(
            request,
            f"That would put you at {projected:.1f} volunteer hours; the limit is {max_volunteer_hours()}.",
        )
        return redirect("volunteers:shifts")

    # Reuse a cancelled row if one exists, otherwise create a fresh signup.
    signup, created = VolunteerSignup.objects.get_or_create(shift=shift, user=request.user)
    if not created:
        signup.cancelled = False
        signup.reminded = False
        signup.save(update_fields=["cancelled", "reminded"])

    messages.success(request, f"You're signed up for “{shift.title}.” Thank you!")
    return redirect("volunteers:shifts")


@login_required
@require_POST
def cancel_view(request, pk):
    """Cancel the signed-in attendee's signup for a shift."""
    signup = get_object_or_404(VolunteerSignup, shift_id=pk, user=request.user, cancelled=False)
    signup.cancelled = True
    signup.save(update_fields=["cancelled"])
    messages.success(request, f"You've been removed from “{signup.shift.title}.”")
    next_url = request.POST.get("next") or "volunteers:shifts"
    return redirect(next_url)


@staff_member_required
def dashboard_view(request):
    """Coordinator view: coverage per shift plus a roster of who's signed up.

    Filterable by role, location, and whether to include shifts that have already
    ended, so the chair/co-chair can see just what still needs attention.
    """
    all_shifts = Shift.objects.select_related("role")
    roles = sorted({s.role.name for s in all_shifts})
    locations = sorted({s.location for s in all_shifts if s.location})

    role_filter = request.GET.get("role", "")
    location_filter = request.GET.get("location", "")
    show_past = request.GET.get("show_past") == "1"
    open_only = request.GET.get("open_only") == "1"

    shifts = all_shifts.annotate(filled_count=Count("signups", filter=Q(signups__cancelled=False))).order_by(
        "starts_at", "title"
    )
    if role_filter:
        shifts = shifts.filter(role__name=role_filter)
    if location_filter:
        shifts = shifts.filter(location=location_filter)
    if not show_past:
        shifts = shifts.filter(ends_at__gte=timezone.now())
    if open_only:
        shifts = shifts.filter(filled_count__lt=1)

    rosters = defaultdict(list)
    for signup in (
        VolunteerSignup.objects.filter(cancelled=False)
        .select_related("user", "shift")
        .order_by("shift__starts_at", "created_at")
    ):
        rosters[signup.shift_id].append(signup.user)

    for shift in shifts:
        shift.roster = rosters.get(shift.id, [])

    total_capacity = sum(s.capacity for s in shifts)
    total_filled = sum(s.filled_count for s in shifts)
    coverage = (total_filled / total_capacity * 100) if total_capacity else 0

    context = {
        "page_title": "Volunteer Dashboard",
        "shifts": shifts,
        "rosters": rosters,
        "total_capacity": total_capacity,
        "total_filled": total_filled,
        "total_open": max(total_capacity - total_filled, 0),
        "coverage": coverage,
        "roles": roles,
        "locations": locations,
        "role_filter": role_filter,
        "location_filter": location_filter,
        "show_past": show_past,
        "open_only": open_only,
    }
    return render(request, "volunteers/dashboard.html", context)


@staff_member_required
@require_POST
def sync_schedule_view(request):
    """Re-import shifts from the conference schedule ICS feed.

    Idempotent: shifts are matched by their schedule UID, so existing slots
    (and any signups on them) are updated in place rather than duplicated.

    With ``dry_run`` set, reports what would be created/updated without writing.
    """
    dry_run = request.POST.get("dry_run") == "1"
    out = StringIO()
    try:
        call_command("import_schedule", dry_run=dry_run, stdout=out)
    except Exception as exc:  # surface the failure to the coordinator, don't 500
        messages.error(request, f"Schedule sync failed: {exc}")
        return redirect("volunteers:dashboard")

    summary = out.getvalue().strip().splitlines()
    result = summary[-1] if summary else "Schedule synced."
    if dry_run:
        messages.info(request, f"Dry run — no changes made. {result}")
    else:
        messages.success(request, result)
    return redirect("volunteers:dashboard")
