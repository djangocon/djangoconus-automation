import datetime
import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

# How large a gap between consecutive talks may be and still count as "adjacent"
# for merging into one block (talks in a room are usually back-to-back).
MERGE_MAX_GAP = datetime.timedelta(minutes=30)


class Role(models.Model):
    """A kind of volunteer job, e.g. Registration Desk, Room Monitor, Setup."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    documentation_url = models.URLField(
        blank=True, help_text="Link to this role's volunteer documentation, shown to volunteers."
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Shift(models.Model):
    """A single block of volunteer work that attendees can sign up for.

    Replaces the full symposion Session/Slot/SessionRoleConfig stack: a shift
    carries its own start/end times and a capacity instead of leaning on a
    separate conference schedule.
    """

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="shifts")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=1, help_text="How many volunteers are needed.")
    signups_open = models.BooleanField(default=True, help_text="Uncheck to close signups for this shift.")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "title"]

    def __str__(self):
        return f"{self.title} ({self.starts_at:%a %b %d %H:%M})"

    @property
    def display_title(self):
        """The title, or blank when it only repeats the role name.

        Shift titles are conventionally "<Role> · <Day> <time>", and the card
        prints the role, the time and the day right underneath — so showing both
        stutters ("In-person sprints welcomer · Thu 9:00 AM" above "In-person
        sprints welcomer · 9:00 AM–11:00 AM"). Titles that say something the
        role name doesn't, like "Morning Session Manager", still show.
        """
        title = self.title.strip()
        if title.casefold().startswith(self.role.name.casefold()):
            return ""
        return title

    @property
    def covered_talks(self):
        return self.talks.order_by("starts_at", "title")

    @property
    def covers_talks(self):
        return self.talks.exists()

    @property
    def is_block(self):
        """True when this shift covers more than one talk (a merged block)."""
        return self.talks.count() > 1

    def recompute_span(self, save=True):
        """Set start/end (and a summary title) from the talks this shift covers.

        No-op for shifts that don't cover talks (e.g. desk/manager shifts, which
        carry their own times).
        """
        talks = list(self.talks.order_by("starts_at", "ends_at"))
        if not talks:
            return
        self.starts_at = talks[0].starts_at
        self.ends_at = max(t.ends_at for t in talks)
        if len(talks) == 1:
            self.title = talks[0].title
        else:
            self.title = f"{self.role.name} · {len(talks)} slots"

        # Rooms get renamed and sessions get moved after the schedule is first
        # imported, so the shift has to follow its talks — otherwise the card
        # keeps sending volunteers to where the session used to be. Only when
        # the feed actually names a room: a blank LOCATION shouldn't wipe one an
        # organizer set by hand.
        rooms = list(dict.fromkeys(talk.location for talk in talks if talk.location))
        if rooms:
            self.location = " / ".join(rooms)

        if save:
            self.save(update_fields=["starts_at", "ends_at", "title", "location"])

    @property
    def active_signups(self):
        return self.signups.filter(cancelled=False)

    @property
    def filled(self):
        return self.active_signups.count()

    @property
    def spots_left(self):
        return max(self.capacity - self.filled, 0)

    @property
    def is_full(self):
        return self.spots_left == 0

    @property
    def is_past(self):
        return self.ends_at < timezone.now()

    @property
    def duration_hours(self):
        return (self.ends_at - self.starts_at).total_seconds() / 3600

    def can_sign_up(self):
        """Return (ok, reason) for whether *anyone* may currently sign up.

        Capacity is a visual guide for organizers, not a hard cap — a full shift
        doesn't block further signups.
        """
        if not self.signups_open:
            return False, "Signups are closed for this shift."
        if self.is_past:
            return False, "This shift has already ended."
        return True, ""

    def overlaps(self, other):
        return self.starts_at < other.ends_at and other.starts_at < self.ends_at


class Talk(models.Model):
    """A single scheduled talk/session from the conference schedule feed.

    Talks are pure schedule data, imported by UID from the ICS feed. A Shift is
    the volunteer sign-up unit and covers one or more consecutive talks; merging
    just re-points several talks at one Shift while each talk keeps its own data.
    """

    shift = models.ForeignKey("Shift", on_delete=models.SET_NULL, null=True, blank=True, related_name="talks")
    external_uid = models.CharField(
        max_length=255,
        blank=True,
        unique=True,
        null=True,
        help_text="UID from the schedule ICS feed, for idempotent syncing.",
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    talk_url = models.URLField(blank=True, help_text="Link to the talk on the conference website.")
    location = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    class Meta:
        ordering = ["starts_at", "title"]

    def __str__(self):
        return self.title


class VolunteerSignup(models.Model):
    """One attendee claiming one shift. Signing up == confirmed."""

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="signups")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volunteer_signups")
    cancelled = models.BooleanField(default=False)
    reminded = models.BooleanField(default=False, help_text="A reminder email has been sent for this signup.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["shift__starts_at"]
        constraints = [
            models.UniqueConstraint(fields=["shift", "user"], name="unique_volunteer_per_shift"),
        ]

    def __str__(self):
        return f"{self.user} → {self.shift}"


class SiteContactInfo(models.Model):
    """Site-wide 'who to contact' note for volunteers (a singleton).

    Coordinators edit this on the dashboard — the volunteer chairs' email, Slack,
    etc. — as Markdown, and every volunteer sees it (read-only) on their page.
    """

    contact_info = models.TextField(
        blank=True,
        help_text="Markdown. How volunteers can reach the coordinators — email, Slack, etc.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Volunteer contact info"
        verbose_name_plural = "Volunteer contact info"

    def __str__(self):
        return "Volunteer coordinator contact info"

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj


class CalendarToken(models.Model):
    """A stable, unguessable token so a volunteer can subscribe to their shifts.

    Calendar clients can't authenticate, so the iCal feed is reached by this
    per-user token instead of a login.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="volunteer_calendar_token"
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    def __str__(self):
        return f"calendar token for {self.user}"


class VolunteerChairPermissions(models.Model):
    """Permission-only model: no table, no rows — just a home for the chair permissions.

    The coordinator tooling isn't owned by any one model (the dashboard spans
    shifts, signups, and contact info; the interest report reads Tito data), so
    the permissions hang here instead of being bolted onto an unrelated model.
    Granted via the "Volunteer Chair" group seeded in migration 0010.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_volunteer_dashboard", "Can view and manage the volunteer dashboard"),
            ("view_volunteer_interest", "Can view the volunteer interest report"),
        ]


def total_volunteer_hours(user):
    """Total hours a user is currently signed up for (excludes cancelled)."""
    hours = 0.0
    signups = VolunteerSignup.objects.filter(user=user, cancelled=False).select_related("shift")
    for signup in signups:
        hours += signup.shift.duration_hours
    return hours


def conflicting_shifts(user, shift):
    """Active shifts the user is signed up for that overlap ``shift`` in time."""
    candidates = (
        VolunteerSignup.objects.filter(user=user, cancelled=False)
        .exclude(shift=shift)
        .filter(shift__starts_at__lt=shift.ends_at, shift__ends_at__gt=shift.starts_at)
        .select_related("shift")
    )
    return [s.shift for s in candidates]


@transaction.atomic
def merge_shifts(shifts):
    """Merge several consecutive shifts into one block. Returns (shift, error).

    Works for any shifts of the same role in the same room that run back-to-back
    (no gap over MERGE_MAX_GAP) — scheduled talks or desk/coverage slots. The
    earliest becomes the block; each shift is first recorded as a segment so the
    block can be split apart again, then the others' segments and sign-ups move
    onto the target and they're deleted.
    """
    if len(shifts) < 2:
        return None, "Pick at least two shifts to merge."

    shifts = sorted(shifts, key=lambda s: s.starts_at)
    if len({s.role_id for s in shifts}) > 1:
        return None, "Shifts must have the same role to merge."
    if len({s.location for s in shifts}) > 1:
        return None, "Shifts must be in the same room to merge."
    for prev, nxt in zip(shifts, shifts[1:], strict=False):
        if nxt.starts_at > prev.ends_at + MERGE_MAX_GAP:
            return None, "Shifts must be consecutive (no long gaps) to merge into a block."

    # Record each shift as a segment (talks already do this) so a later split can
    # reconstruct the individual slots.
    for shift in shifts:
        if not shift.talks.exists():
            Talk.objects.create(
                shift=shift,
                title=shift.title,
                description=shift.description,
                location=shift.location,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
            )

    target, others = shifts[0], shifts[1:]
    for other in others:
        other.talks.update(shift=target)
        for signup in list(other.signups.all()):
            if VolunteerSignup.objects.filter(shift=target, user_id=signup.user_id).exists():
                signup.delete()  # already signed up on the target; drop the duplicate
            else:
                signup.shift = target
                signup.save(update_fields=["shift"])
        other.delete()

    target.recompute_span()
    return target, None


@transaction.atomic
def split_shift(shift):
    """Split a block back into one shift per talk. Returns (shift, error).

    Each talk gets its own single-talk shift; the block's volunteers are copied
    onto every resulting shift (they'd signed up to cover the whole block).
    """
    talks = list(shift.talks.order_by("starts_at", "ends_at"))
    if len(talks) < 2:
        return None, "This shift only covers one talk; there's nothing to split."

    active_users = list(shift.signups.filter(cancelled=False).values_list("user_id", flat=True))
    for talk in talks[1:]:
        new_shift = Shift.objects.create(
            role=shift.role,
            title=talk.title,
            description=talk.description,
            location=talk.location,
            starts_at=talk.starts_at,
            ends_at=talk.ends_at,
            capacity=shift.capacity,
            signups_open=shift.signups_open,
        )
        talk.shift = new_shift
        talk.save(update_fields=["shift"])
        for user_id in active_users:
            VolunteerSignup.objects.create(shift=new_shift, user_id=user_id)
        new_shift.recompute_span()

    shift.recompute_span()
    return shift, None
