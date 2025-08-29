from django.db import models


class TicketLink(models.Model):
    link = models.URLField()
    attendee_email = models.EmailField(null=True, blank=True, db_index=True)
    date_link_created = models.DateTimeField(auto_now_add=True)
    date_link_assigned = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attendee_email"],
                condition=models.Q(attendee_email__isnull=False),
                name="unique_attendee_email",
            )
        ]

    def __str__(self):
        if self.attendee_email:
            return f"{self.link} - {self.attendee_email}"
        return self.link
