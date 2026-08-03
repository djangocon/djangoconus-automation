from django.db import models


class TitoHistoricalEvent(models.Model):
    slug = models.SlugField(max_length=128, unique=True)
    year = models.PositiveIntegerField(db_index=True)
    title = models.CharField(max_length=256)
    account_slug = models.CharField(max_length=64, default="defna")
    is_current = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True, help_text="First day of the conference; anchors days-out math")
    goal = models.PositiveIntegerField(null=True, blank=True, help_text="Sales goal for this year")
    releases = models.JSONField(null=True, blank=True)
    activities = models.JSONField(null=True, blank=True)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return self.title

    @property
    def total_sold(self):
        if not self.releases:
            return 0
        return sum(r.get("tickets_count") or 0 for r in self.releases)

    @property
    def total_capacity(self):
        if not self.releases:
            return 0
        return sum(r.get("quantity") or 0 for r in self.releases)

    @staticmethod
    def _release_revenue(release: dict) -> float:
        try:
            price = float(release.get("price") or 0)
        except (TypeError, ValueError):
            return 0.0
        sold = release.get("tickets_count") or 0
        return price * sold

    @property
    def total_revenue(self) -> float:
        if not self.releases:
            return 0.0
        return sum(self._release_revenue(r) for r in self.releases)

    @property
    def percent_of_goal(self):
        if not self.goal:
            return None
        return round(self.total_sold / self.goal * 100, 1)

    def _activity_for_release(self, title: str, activity_names: list[str]) -> str | None:
        """Return the best-matching activity name for a release title, or None."""
        t = title.lower()
        # Priority order: specific keywords first so Sprint (In Person) goes to Sprints, not In-person.
        priority = [
            ("sprint", "Sprints"),
            ("tutorial", "Tutorials"),
            ("online", "Online Conference"),
            ("(in-person)", "In-person Conference"),
            ("(in person)", "In-person Conference"),
            ("in-person", "In-person Conference"),
        ]
        for keyword, default_name in priority:
            if keyword in t:
                # Prefer the matching activity name from the stored list if present.
                for name in activity_names:
                    if default_name.lower() in name.lower() or name.lower() in default_name.lower():
                        return name
                return default_name
        return None

    @property
    def releases_by_activity(self) -> list[dict]:
        """Group releases under their activity heading, unmatched go in 'Other' at the end."""
        if not self.releases:
            return []

        activity_names = [a.get("name", "") for a in (self.activities or [])]
        buckets: dict[str, list] = {name: [] for name in activity_names}
        other: list = []

        for release in self.releases:
            activity = self._activity_for_release(release.get("title", ""), activity_names)
            if activity and activity in buckets:
                buckets[activity].append(release)
            elif activity:
                # Matched a default name not in the stored activity list — add bucket.
                buckets.setdefault(activity, []).append(release)
            else:
                other.append(release)

        def _make_group(name, releases):
            enriched = [{**r, "revenue": self._release_revenue(r)} for r in releases]
            return {
                "name": name,
                "releases": enriched,
                "total_sold": sum(r.get("tickets_count") or 0 for r in releases),
                "total_capacity": sum(r.get("quantity") or 0 for r in releases),
                "total_revenue": sum(r["revenue"] for r in enriched),
            }

        groups = [_make_group(name, releases) for name, releases in buckets.items() if releases]
        if other:
            groups.append(_make_group("Other", other))
        return groups


class TitoTicket(models.Model):
    """One sold ticket, flattened out of the Ti.to API or a webhook payload.

    The historical event rows only hold point-in-time totals, so they can't say
    what sales looked like partway through a season. These rows keep the purchase
    date and the real price paid, which is what the days-out curves are built from.
    """

    SOURCE_API = "api"
    SOURCE_WEBHOOK = "webhook"
    SOURCE_CHOICES = [(SOURCE_API, "Ti.to API"), (SOURCE_WEBHOOK, "Webhook")]

    event_slug = models.SlugField(max_length=128, db_index=True)
    year = models.PositiveIntegerField(db_index=True)
    ticket_slug = models.CharField(max_length=128, unique=True)
    reference = models.CharField(max_length=64, blank=True)
    release_title = models.CharField(max_length=256, blank=True)
    release_price = models.FloatField(default=0.0, help_text="List price of the release")
    price = models.FloatField(default=0.0, help_text="What the attendee actually paid")
    discount_code = models.CharField(max_length=128, blank=True)
    state_name = models.CharField(max_length=64, blank=True)
    voided = models.BooleanField(default=False)
    created_at = models.DateTimeField(null=True, blank=True, db_index=True)
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_API)
    last_synced = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-year", "created_at"]
        indexes = [models.Index(fields=["year", "created_at"])]

    def __str__(self):
        return f"{self.reference or self.ticket_slug} ({self.year})"

    @property
    def discount(self) -> float:
        return self.release_price - self.price


class TitoWebhookEvent(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    trigger = models.CharField(max_length=256, blank=True)
    tito_webhook_endpoint_id = models.PositiveIntegerField(null=True, blank=True)
    tito_signature = models.CharField(max_length=512, null=False, blank=True, default="")
    payload = models.JSONField(null=True, blank=True)
    payload_text = models.TextField(null=False, blank=True, default="")
    processed = models.BooleanField(default=False)
    processing_failed = models.BooleanField(default=False)


class TitoEvent(models.Model):
    name = models.CharField(max_length=256)
    account_slug = models.CharField(max_length=64)
    event_slug = models.CharField(max_length=128)
    api_token = models.CharField(max_length=128)
    webhook_endpoint = models.CharField(max_length=256)
    tito_webhook_id = models.PositiveIntegerField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    sales_start_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.name


class TitoWebhookSetupLog(models.Model):
    event = models.ForeignKey(TitoEvent, on_delete=models.PROTECT)
    timestamp = models.DateTimeField(auto_now_add=True)
    payload_text = models.TextField(null=False, blank=True, default="")
    response_text = models.TextField(null=False, blank=True, default="")
