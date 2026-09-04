from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_q.tasks import async_task

from titowebhooks.reports import normalized_csv

from .attendance import ticket_index, ticket_status
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
from .names import display_name, fill_missing_name
from .permissions import dashboard_required, volunteer_chairs
from .schedule_plan import build_diff


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
        "my_name": request.user.get_full_name().strip(),
        "my_hours": total_volunteer_hours(request.user),
        "max_hours": max_volunteer_hours(),
        "calendar_url": request.build_absolute_uri(reverse("volunteers:calendar", args=[token.token])),
        "handbook_url": volunteer_handbook_url(),
        "contact_info": SiteContactInfo.get_solo().contact_info,
        "chairs": volunteer_chairs(),
        "volunteer_contact_email": volunteer_contact_email(),
    }
    return render(request, "volunteers/my_shifts.html", context)


@login_required
@require_POST
def update_name_view(request):
    """Let a volunteer set the name the coordinators see.

    Ti.to covers most people, but someone who volunteered without buying a
    ticket has no ticket to read a name off — this is how they say who they are.
    """
    name = " ".join(request.POST.get("name", "").split())
    first, _, last = name.partition(" ")
    request.user.first_name, request.user.last_name = first, last
    request.user.save(update_fields=["first_name", "last_name"])
    if name:
        messages.success(request, f"Thanks — the coordinators will see you as “{name}.”")
    else:
        messages.info(request, "Your name was cleared.")
    return redirect("volunteers:my_shifts")


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

    # Accounts made from a magic link carry no name, so the roster could only
    # show an email address (#168). Their ticket already knows what they're
    # called — fill it in here rather than asking them again.
    fill_missing_name(request.user)

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

    # Names, not addresses: most accounts are made from a magic link and carry
    # no name, so this cell used to read as a list of raw emails and chairs
    # couldn't tell who had signed up (#168). display_name falls back to the
    # email for anyone still unnamed.
    rosters = defaultdict(list)
    for signup in (
        VolunteerSignup.objects.filter(cancelled=False)
        .select_related("user", "shift")
        .order_by("shift__starts_at", "created_at")
    ):
        rosters[signup.shift_id].append(display_name(signup.user))

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


def _volunteer_name(person):
    user = person["user"]
    return (user.get_full_name() or user.get_username() or getattr(user, "email", "") or "").lower()


def volunteer_roster():
    """Everyone with an active sign-up, with their shift count, hours and roles.

    One entry per person, name-sorted — the shape both the roster page and the
    email export read from. Each entry also carries their Ti.to ticket status,
    so a volunteer with no ticket can be spotted before they turn up (#169).
    """
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
    index = ticket_index()
    for person in volunteers:
        person["roles"] = ", ".join(sorted(person["roles"]))
        person["ticket"] = ticket_status(person["user"], index)
    volunteers.sort(key=_volunteer_name)
    return volunteers


@dashboard_required
def volunteers_list_view(request):
    """Roster of everyone signed up, with how many shifts/hours each has taken."""
    sort = request.GET.get("sort", "name")
    if sort not in VOLUNTEER_SORTS:
        sort = "name"

    volunteers = volunteer_roster()
    if sort == "hours":
        volunteers.sort(key=lambda p: (-p["hours"], _volunteer_name(p)))
    elif sort == "shifts":
        volunteers.sort(key=lambda p: (-p["shifts"], _volunteer_name(p)))

    context = {
        "page_title": "Volunteers",
        "volunteers": volunteers,
        "sort": sort,
        "sorts": [("name", "Name"), ("hours", "Hours"), ("shifts", "Shifts")],
        "total_volunteers": len(volunteers),
        "total_hours": sum(p["hours"] for p in volunteers),
        "without_ticket": [p for p in volunteers if not p["ticket"]["has_ticket"]],
    }
    return render(request, "volunteers/volunteers_list.html", context)


@dashboard_required
def export_volunteers_view(request):
    """CSV of every volunteer's email, for surveys and follow-up.

    One row per person, not per sign-up: a volunteer who took six shifts is one
    row, so the file can be pasted straight into a mail tool without sending
    them six copies. Anyone whose account has no email is skipped — there's
    nothing to follow up to.
    """
    rows = []
    seen = set()
    for person in volunteer_roster():
        user = person["user"]
        email = (getattr(user, "email", "") or "").strip()
        if not email or email.lower() in seen:
            continue
        seen.add(email.lower())
        rows.append(
            {
                "Name": user.get_full_name() or user.get_username(),
                "Email": email,
                "Ticket Type": person["ticket"]["ticket_type"],
                "Shifts": person["shifts"],
                "Hours": round(person["hours"], 2),
                "Roles": person["roles"],
                # Blank, not "In person", when there's no ticket to say either way.
                "Attending": ("Online" if person["ticket"]["online"] else "In person")
                if person["ticket"]["has_ticket"]
                else "",
                "Has Ticket": person["ticket"]["has_ticket"],
            }
        )

    filename = f"volunteer_emails_{timezone.localdate():%Y-%m-%d}.csv"
    return normalized_csv(filename, ["Shifts", "Hours", "Roles", "Attending", "Has Ticket"], rows)


@dashboard_required
def schedule_changes_view(request):
    """What the conference feed says that the app doesn't, and vice versa.

    Read-only on purpose. A bulk import matches talks by the feed's UID, and
    that UID encodes the start time and title — so a renamed talk looks new and
    the import creates a second shift beside a coordinator's merged block. This
    screen shows the differences and links each one into the admin, so the two
    or three things that actually moved get fixed by hand.
    """
    try:
        events, skipped = fetch_events()
    except Exception as exc:  # a dead feed shouldn't 500 the dashboard
        messages.error(request, f"Couldn't read the conference schedule: {exc}")
        return redirect("volunteers:dashboard")

    diff = build_diff(events, skipped=skipped)
    return render(
        request,
        "volunteers/schedule_changes.html",
        {"page_title": "Schedule changes", "diff": diff},
    )
