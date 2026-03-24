from django.db import models


class List(models.Model):
    list_id = models.CharField(max_length=64)
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.list_id}: {self.name}"
