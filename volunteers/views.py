from collections import defaultdict
from io import StringIO

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from .ical import build_calendar
from .management.commands.import_schedule import fetch_events
from .models import (
    CalendarToken,
    Role,
    Shift,
    SiteContactInfo,
    VolunteerSignup,
    conflicting_shifts,
    merge_shifts,
    split_shift,
    total_volunteer_hours,
)
from .permissions import dashboard_required, volunteer_chairs
from .schedule_plan import build_plan


def max_volunteer_hours():
    return getattr(settings, "VOLUNTEER_MAX_HOURS", 8)


def volunteer_handbook_url():
    return getattr(settings, "VOLUNTEER_HANDBOOK_URL", "")


def volunteer_contact_email():
    return getattr(settings, "VOLUNTEER_CONTACT_EMAIL", "")


def _return_url(request):
    """Where to send the user back to after signing up or cancelling.

    Honors a ``next`` field (so filters on the sign-up list are preserved and you
    can keep signing up), but only if it's a safe same-site URL. Falls back to the
    unfiltered sign-up list.
    """
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return reverse("volunteers:shifts")


def shift_list_view(request):
    """Upcoming shifts anyone can browse; signing up or cancelling still requires login."""
    all_shifts = Shift.objects.filter(ends_at__gte=timezone.now()).select_related("role")

    roles = list(Role.objects.order_by("name").values_list("name", flat=True))

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
        my_upcoming = (
            VolunteerSignup.objects.filter(user=request.user, cancelled=False, shift__ends_at__gte=timezone.now())
            .select_related("shift", "shift__role")
            .order_by("shift__starts_at")[:3]
        )
    else:
        my_shift_ids = set()
        my_hours = 0
        my_upcoming = []

    days = defaultdict(list)
    for shift in shifts:
        days[shift.starts_at.date()].append(shift)

    context = {
        "page_title": "Volunteer Sign-up",
        "days": sorted(days.items()),
        "my_shift_ids": my_shift_ids,
        "my_upcoming": my_upcoming,
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
        "contact_info": SiteContactInfo.get_solo().contact_info,
        "chairs": volunteer_chairs(),
        "volunteer_contact_email": volunteer_contact_email(),
    }
    return render(request, "volunteers/my_shifts.html", context)


@dashboard_required
@require_POST
def update_contact_view(request):
    """Save the site-wide volunteer coordinator contact info (chairs and staff)."""
    contact = SiteContactInfo.get_solo()
    contact.contact_info = request.POST.get("contact_info", "").strip()
    contact.save(update_fields=["contact_info", "updated_at"])
    messages.success(request, "Volunteer contact info was saved.")
    return redirect(_return_url(request) if request.POST.get("next") else "volunteers:dashboard")


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
    return_url = _return_url(request)

    ok, reason = shift.can_sign_up()
    if not ok:
        messages.error(request, reason)
        return redirect(return_url)

    if VolunteerSignup.objects.filter(shift=shift, user=request.user, cancelled=False).exists():
        messages.info(request, "You're already signed up for this shift.")
        return redirect(return_url)

    conflicts = conflicting_shifts(request.user, shift)
    if conflicts:
        names = ", ".join(c.title for c in conflicts)
        messages.error(request, f"This overlaps a shift you're already on: {names}.")
        return redirect(return_url)

    hours_before = total_volunteer_hours(request.user)

    # Reuse a cancelled row if one exists, otherwise create a fresh signup.
    signup, created = VolunteerSignup.objects.get_or_create(shift=shift, user=request.user)
    if not created:
        signup.cancelled = False
        signup.reminded = False
        # Treat re-signing up as a fresh signup so the uncovered-shift alert's
        # quick-change-of-mind buffer measures from now, not the original signup.
        signup.created_at = timezone.now()
        signup.save(update_fields=["cancelled", "reminded", "created_at"])

    # First-signup welcome, on the worker: a mail server having a bad day must
    # not break a signup (#133). The task decides whether this is their first.
    async_task("volunteers.tasks.send_volunteer_welcome", signup.pk)

    messages.success(request, f"You're signed up for “{shift.title}.” Thank you!")

    # The hour budget is guidance, never a gate — same as capacity. Blocking it
    # stranded people who cancelled one shift and couldn't pick up another (#139),
    # so say something and get out of the way.
    #
    # Only on the signup that crosses the line: someone who has already been told
    # doesn't need it again every time they add a shift.
    hours_after = total_volunteer_hours(request.user)
    if hours_before <= max_volunteer_hours() < hours_after:
        messages.warning(
            request,
            f"Heads up: you're now at {hours_after:.1f} volunteer hours, past the "
            f"{max_volunteer_hours()} we suggest. That's allowed and we're grateful — "
            "just don't sign up for so much that you miss the conference.",
        )

    return redirect(return_url)


@login_required
@require_POST
def cancel_view(request, pk):
    """Cancel the signed-in attendee's signup for a shift."""
    signup = get_object_or_404(VolunteerSignup, shift_id=pk, user=request.user, cancelled=False)
    signup.cancelled = True
    signup.save(update_fields=["cancelled"])
    async_task("volunteers.tasks.notify_shift_uncovered", signup.pk)
    messages.success(request, f"You've been removed from “{signup.shift.title}.”")
    return redirect(_return_url(request))


@dashboard_required
def dashboard_view(request):
    """Coordinator view: coverage per shift plus a roster of who's signed up.

    Filterable by conference day, role, location, and whether to include shifts
    that have already ended, so the chair/co-chair can see coverage for a given
    day or just what still needs attention.
    """
    all_shifts = Shift.objects.select_related("role")
    roles = list(Role.objects.order_by("name").values_list("name", flat=True))
    locations = sorted({s.location for s in all_shifts if s.location})
    dates = sorted({s.starts_at.date() for s in all_shifts})

    role_filter = request.GET.get("role", "")
    location_filter = request.GET.get("location", "")
    date_filter = request.GET.get("date", "")
    selected_date = parse_date(date_filter) if date_filter else None
    show_past = request.GET.get("show_past") == "1"
    open_only = request.GET.get("open_only") == "1"

    shifts = all_shifts.annotate(filled_count=Count("signups", filter=Q(signups__cancelled=False))).order_by(
        "starts_at", "title"
    )
    if role_filter:
        shifts = shifts.filter(role__name=role_filter)
    if location_filter:
        shifts = shifts.filter(location=location_filter)
    if selected_date:
        # An explicit day is shown in full, even if it's already in the past.
        shifts = shifts.filter(starts_at__date=selected_date)
    elif not show_past:
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

    shifts = list(shifts)
    for shift in shifts:
        shift.roster = rosters.get(shift.id, [])

    days = defaultdict(list)
    for shift in shifts:
        days[shift.starts_at.date()].append(shift)

    total_capacity = sum(s.capacity for s in shifts)
    total_filled = sum(s.filled_count for s in shifts)
    coverage = (total_filled / total_capacity * 100) if total_capacity else 0

    context = {
        "page_title": "Volunteer Dashboard",
        "shifts": shifts,
        "days": sorted(days.items()),
        "rosters": rosters,
        "total_capacity": total_capacity,
        "total_filled": total_filled,
        "total_open": max(total_capacity - total_filled, 0),
        "coverage": coverage,
        "roles": roles,
        "locations": locations,
        "dates": dates,
        "role_filter": role_filter,
        "location_filter": location_filter,
        "date_filter": date_filter,
        "selected_date": selected_date,
        "show_past": show_past,
        "open_only": open_only,
        "contact_info": SiteContactInfo.get_solo().contact_info,
    }
    return render(request, "volunteers/dashboard.html", context)


@dashboard_required
@require_POST
def merge_shifts_view(request):
    """Merge the selected schedule shifts into one sign-up block."""
    ids = request.POST.getlist("shift")
    shifts = list(Shift.objects.filter(id__in=ids))
    _, error = merge_shifts(shifts)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, "Merged into one block.")
    return redirect(_return_url(request) if request.POST.get("next") else "volunteers:dashboard")


@dashboard_required
@require_POST
def delete_shift_view(request, pk):
    """Delete a shift (and its sign-ups). Its talks are detached, not deleted."""
    shift = get_object_or_404(Shift, pk=pk)
    title = shift.title
    shift.delete()
    messages.success(request, f"Deleted “{title}.”")
    return redirect(_return_url(request) if request.POST.get("next") else "volunteers:dashboard")


@dashboard_required
@require_POST
def split_shift_view(request, pk):
    """Split a block back into one shift per talk."""
    shift = get_object_or_404(Shift, pk=pk)
    _, error = split_shift(shift)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, "Split back into per-talk shifts.")
    return redirect(_return_url(request) if request.POST.get("next") else "volunteers:dashboard")


VOLUNTEER_SORTS = {"name", "hours", "shifts"}


@dashboard_required
def volunteers_list_view(request):
    """Roster of everyone signed up, with how many shifts/hours each has taken."""
    sort = request.GET.get("sort", "name")
    if sort not in VOLUNTEER_SORTS:
        sort = "name"

    people = {}
    for signup in (
        VolunteerSignup.objects.filter(cancelled=False)
        .select_related("user", "shift", "shift__role")
        .order_by("shift__starts_at")
    ):
        person = people.setdefault(signup.user_id, {"user": signup.user, "shifts": 0, "hours": 0.0, "roles": set()})
        person["shifts"] += 1
        person["hours"] += signup.shift.duration_hours
        person["roles"].add(signup.shift.role.name)

    volunteers = list(people.values())
    for person in volunteers:
        person["roles"] = ", ".join(sorted(person["roles"]))

    def _name(person):
        user = person["user"]
        return (user.get_full_name() or user.get_username() or getattr(user, "email", "") or "").lower()

    if sort == "hours":
        volunteers.sort(key=lambda p: (-p["hours"], _name(p)))
    elif sort == "shifts":
        volunteers.sort(key=lambda p: (-p["shifts"], _name(p)))
    else:
        volunteers.sort(key=_name)

    context = {
        "page_title": "Volunteers",
        "volunteers": volunteers,
        "sort": sort,
        "sorts": [("name", "Name"), ("hours", "Hours"), ("shifts", "Shifts")],
        "total_volunteers": len(volunteers),
        "total_hours": sum(p["hours"] for p in volunteers),
    }
    return render(request, "volunteers/volunteers_list.html", context)


@dashboard_required
def sync_preview_view(request):
    """Show what a schedule sync would change, before anything is written.

    The importer matches talks by the feed's UID, and that UID encodes the start
    time and title — so an upstream retitle looks like a brand-new talk and gets
    its own shift alongside the block a coordinator already merged it into. This
    screen surfaces those collisions so a person decides, rather than finding out
    afterwards.
    """
    try:
        events, skipped = fetch_events()
    except Exception as exc:  # a dead feed shouldn't 500 the dashboard
        messages.error(request, f"Couldn't read the conference schedule: {exc}")
        return redirect("volunteers:dashboard")

    plan = build_plan(events, skipped=skipped)
    return render(
        request,
        "volunteers/sync_preview.html",
        {"page_title": "Preview schedule sync", "plan": plan},
    )


@dashboard_required
@require_POST
def sync_schedule_view(request):
    """Apply the schedule sync. Only reachable by confirming on the preview screen.

    Shifts are matched by their schedule UID, so existing slots (and any sign-ups
    on them) are updated in place rather than duplicated — but a UID that churned
    upstream looks like a new talk, which is what the preview screen warns about.
    """
    if request.POST.get("confirm") != "1":
        # Nothing should reach the importer without someone having seen the plan.
        return redirect("volunteers:sync_preview")

    out = StringIO()
    try:
        call_command("import_schedule", stdout=out, no_color=True)
    except Exception as exc:  # surface the failure to the coordinator, don't 500
        messages.error(request, f"Schedule sync failed: {exc}")
        return redirect("volunteers:dashboard")

    summary = out.getvalue().strip().splitlines()
    messages.success(request, summary[-1] if summary else "Schedule synced.")
    return redirect("volunteers:dashboard")
