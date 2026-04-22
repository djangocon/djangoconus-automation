from django.db import models


class TitoHistoricalEvent(models.Model):
    slug = models.SlugField(max_length=128, unique=True)
    year = models.PositiveIntegerField(db_index=True)
    title = models.CharField(max_length=256)
    account_slug = models.CharField(max_length=64, default="defna")
    is_current = models.BooleanField(default=False)
    goal = models.PositiveIntegerField(null=True, blank=True, help_text="Sales goal for this year")
    releases = models.JSONField(null=True, blank=True)
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

    @property
    def percent_of_goal(self):
        if not self.goal:
            return None
        return round(self.total_sold / self.goal * 100, 1)


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
