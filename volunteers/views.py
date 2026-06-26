from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Shift,
    VolunteerSignup,
    conflicting_shifts,
    total_volunteer_hours,
)


def max_volunteer_hours():
    return getattr(settings, "VOLUNTEER_MAX_HOURS", 8)


@login_required
def shift_list_view(request):
    """Upcoming shifts an attendee can browse and sign up for, grouped by day."""
    shifts = (
        Shift.objects.filter(ends_at__gte=timezone.now())
        .select_related("role")
        .annotate(filled_count=Count("signups", filter=Q(signups__cancelled=False)))
        .order_by("starts_at", "title")
    )

    my_shift_ids = set(
        VolunteerSignup.objects.filter(user=request.user, cancelled=False).values_list("shift_id", flat=True)
    )

    days = defaultdict(list)
    for shift in shifts:
        days[shift.starts_at.date()].append(shift)

    context = {
        "page_title": "Volunteer Sign-up",
        "days": sorted(days.items()),
        "my_shift_ids": my_shift_ids,
        "my_hours": total_volunteer_hours(request.user),
        "max_hours": max_volunteer_hours(),
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
    context = {
        "page_title": "My Volunteer Shifts",
        "signups": signups,
        "my_hours": total_volunteer_hours(request.user),
        "max_hours": max_volunteer_hours(),
    }
    return render(request, "volunteers/my_shifts.html", context)


@login_required
@require_POST
def signup_view(request, pk):
    """Claim a shift, enforcing capacity, conflicts, and the per-person hours cap."""
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
    """Coordinator view: coverage per shift plus a roster of who's signed up."""
    shifts = (
        Shift.objects.select_related("role")
        .annotate(filled_count=Count("signups", filter=Q(signups__cancelled=False)))
        .order_by("starts_at", "title")
    )

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
    }
    return render(request, "volunteers/dashboard.html", context)
