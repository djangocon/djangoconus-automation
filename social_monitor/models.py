from django.db import models


class SocialPlatform(models.Model):
    name = models.CharField(max_length=100, unique=True)
    get_mentions = models.BooleanField(default=True)
    last_seen = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Last seen timestamp for mentions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class PlatformHashTag(models.Model):
    platform = models.ForeignKey(SocialPlatform, on_delete=models.CASCADE)

    query = models.CharField(max_length=200)
    last_seen = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Last seen timestamp for the query",
    )
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('platform', 'query')

    def __str__(self):
        return f"{self.platform.name} -> #{self.query}"
