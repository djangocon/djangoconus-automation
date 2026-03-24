from django.conf import settings
from django.db import models
from django.db.models import Avg


class Event(models.Model):
    name = models.CharField(max_length=200)
    pretalx_slug = models.SlugField(max_length=200, unique=True, help_text="Event slug used in pretalx API URLs")
    start_date = models.DateField()
    end_date = models.DateField()
    slots_25_in_person = models.PositiveIntegerField(default=0, verbose_name="25-min in-person slots")
    slots_45_in_person = models.PositiveIntegerField(default=0, verbose_name="45-min in-person slots")
    slots_25_online = models.PositiveIntegerField(default=0, verbose_name="25-min online slots")
    slots_45_online = models.PositiveIntegerField(default=0, verbose_name="45-min online slots")
    pretalx_token = models.CharField(max_length=200, blank=True, help_text="Pretalx API token for this event")

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    pretalx_id = models.CharField(max_length=100, blank=True, null=True, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Speaker(models.Model):
    name = models.CharField(max_length=200)
    pretalx_code = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Submission(models.Model):
    PRETALX_STATE_CHOICES = [
        ("submitted", "Submitted"),
        ("accepted", "Accepted"),
        ("confirmed", "Confirmed"),
        ("rejected", "Rejected"),
        ("canceled", "Canceled"),
        ("withdrawn", "Withdrawn"),
    ]

    STATE_CHOICES = [
        ("unreviewed", "Unreviewed"),
        ("accepted-in-person", "Accepted (In-Person)"),
        ("accepted-online", "Accepted (Online)"),
        ("waitlist-in-person", "Waitlist (In-Person)"),
        ("waitlist-online", "Waitlist (Online)"),
        ("rejected", "Rejected"),
    ]

    DURATION_CHOICES = [
        (25, "25 minutes"),
        (45, "45 minutes"),
    ]

    pretalx_id = models.CharField(max_length=100, db_index=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="submissions")
    speakers = models.ManyToManyField(Speaker, blank=True, related_name="submissions")
    title = models.CharField(max_length=500)
    track = models.CharField(max_length=200, blank=True)
    duration = models.PositiveIntegerField(choices=DURATION_CHOICES, null=True, blank=True)
    pretalx_state = models.CharField(
        max_length=30, choices=PRETALX_STATE_CHOICES, default="submitted", help_text="State synced from pretalx"
    )
    state = models.CharField(
        max_length=30, choices=STATE_CHOICES, default="unreviewed", help_text="Thunderdome decision"
    )
    abstract = models.TextField(blank=True)
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True, help_text="Speaker's notes to reviewers")
    internal_notes = models.TextField(blank=True, help_text="Internal organizer notes")
    tags = models.ManyToManyField(Tag, blank=True, related_name="submissions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        unique_together = [("event", "pretalx_id")]

    def __str__(self):
        return f"{self.pretalx_id}: {self.title}"

    @property
    def review_count(self):
        return self.reviews.exclude(score__isnull=True).count()

    @property
    def review_mean(self):
        result = self.reviews.exclude(score__isnull=True).aggregate(avg=Avg("score"))
        return result["avg"]

    @property
    def review_median(self):
        scores = list(self.reviews.exclude(score__isnull=True).values_list("score", flat=True).order_by("score"))
        if not scores:
            return None
        mid = len(scores) // 2
        if len(scores) % 2 == 0:
            return (scores[mid - 1] + scores[mid]) / 2
        return scores[mid]


class Review(models.Model):
    SCORE_CHOICES = [
        (0, "No"),
        (1, "Maybe"),
        (2, "Yes"),
    ]

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="thunderdome_reviews", null=True, blank=True
    )
    reviewer_name = models.CharField(max_length=200, blank=True, help_text="Reviewer name from pretalx")
    pretalx_review_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        name = self.reviewer_name or str(self.user or "Unknown")
        return f"{name} -> {self.submission.pretalx_id}: {self.score}"

    @property
    def display_name(self):
        return self.reviewer_name or str(self.user or "Unknown")
