from django.db import models


class TicketLink(models.Model):
    link = models.URLField()
    date_link_accessed = models.DateTimeField(null=True, blank=True)
    date_link_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.link
