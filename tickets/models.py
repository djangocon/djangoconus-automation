from django.conf import settings
from django.db import models
from django.utils import timezone


class OnlineAttendee(models.Model):
    """Someone who bought an online ticket for a given conference year.

    Ti.to is the system of record for who bought what, but it is reached two
    different ways: a nightly API sync (complete, but only as fresh as the last
    run) and webhooks (instant, but only for purchases made since the endpoint
    went live). Rather than make every view reconcile those two, both feed this
    table. Staff can also add someone by hand when support has to step in.
    """

    SOURCE_TITO_API = "tito_api"
    SOURCE_WEBHOOK = "webhook"
    SOURCE_MANUAL = "manual"
    SOURCE_CHOICES = [
        (SOURCE_TITO_API, "Ti.to API"),
        (SOURCE_WEBHOOK, "Webhook"),
        (SOURCE_MANUAL, "Added by staff"),
    ]

    email = models.EmailField(db_index=True)
    name = models.CharField(max_length=256, blank=True)
    year = models.PositiveIntegerField(db_index=True)
    release_title = models.CharField(max_length=256, blank=True)
    purchased_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_TITO_API)
    last_synced = models.DateTimeField(null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-year", "name", "email"]
        constraints = [
            models.UniqueConstraint(fields=["year", "email"], name="unique_attendee_per_year"),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>" if self.name else self.email

    def save(self, *args, **kwargs):
        # Ti.to and hand-typed addresses disagree on case constantly; normalizing
        # here is what makes the (year, email) constraint actually mean anything.
        self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    @property
    def active_ticket_link(self):
        """The link this attendee should be using, or None if they have none.

        Matched on the address rather than the FK: links claimed through the
        public page (or before this roster existed) carry an ``attendee_email``
        with no FK, and treating those people as unassigned would hand them a
        second link. ``unique_active_attendee_email`` guarantees at most one.
        """
        return TicketLink.objects.filter(attendee_email=self.email, superseded_at__isnull=True).first()

    @property
    def has_ticket(self) -> bool:
        return self.active_ticket_link is not None

    @property
    def last_emailed_at(self):
        log = self.email_logs.filter(status=TicketEmailLog.STATUS_SENT).order_by("-date_sent").first()
        return log.date_sent if log else None

    @property
    def sent_email_count(self) -> int:
        return self.email_logs.filter(status=TicketEmailLog.STATUS_SENT).count()


class TicketLink(models.Model):
    link = models.URLField()
    attendee_email = models.EmailField(null=True, blank=True, db_index=True)
    attendee = models.ForeignKey(
        OnlineAttendee,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_links",
    )
    date_link_created = models.DateTimeField(auto_now_add=True)
    date_link_assigned = models.DateTimeField(null=True, blank=True)
    superseded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when a replacement link is issued; the old link stays for the audit trail.",
    )

    class Meta:
        constraints = [
            # One *live* link per address. Superseded rows are excluded so a
            # reissue doesn't have to destroy the record of the previous link.
            models.UniqueConstraint(
                fields=["attendee_email"],
                condition=models.Q(attendee_email__isnull=False, superseded_at__isnull=True),
                name="unique_active_attendee_email",
            )
        ]

    def __str__(self):
        if self.attendee_email:
            return f"{self.link} - {self.attendee_email}"
        return self.link

    @property
    def is_assigned(self) -> bool:
        return self.attendee_email is not None

    def supersede(self):
        self.superseded_at = timezone.now()
        self.save(update_fields=["superseded_at"])


class TicketEmailLog(models.Model):
    """One record per ticket-link email we tried to send.

    Written up front with ``queued`` so a send that dies in the worker is still
    visible in the dashboard instead of vanishing.
    """

    KIND_INITIAL = "initial"
    KIND_RESEND = "resend"
    KIND_REISSUE = "reissue"
    KIND_CHOICES = [
        (KIND_INITIAL, "Initial send"),
        (KIND_RESEND, "Resend of same link"),
        (KIND_REISSUE, "New link issued"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    attendee = models.ForeignKey(
        OnlineAttendee,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_logs",
    )
    ticket_link = models.ForeignKey(
        TicketLink,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="email_logs",
    )
    to_email = models.EmailField(db_index=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, default=KIND_INITIAL)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    subject = models.CharField(max_length=512, blank=True)
    error = models.TextField(blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ticket_emails_sent",
    )
    date_queued = models.DateTimeField(auto_now_add=True)
    date_sent = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date_queued"]
        indexes = [models.Index(fields=["to_email", "-date_queued"])]

    def __str__(self):
        return f"{self.get_kind_display()} to {self.to_email} ({self.status})"

    def mark_sent(self):
        self.status = self.STATUS_SENT
        self.date_sent = timezone.now()
        self.save(update_fields=["status", "date_sent"])

    def mark_failed(self, error: str):
        self.status = self.STATUS_FAILED
        self.error = error
        self.save(update_fields=["status", "error"])
