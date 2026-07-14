import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


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
