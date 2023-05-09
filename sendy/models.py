from django.db import models


class Brand(models.Model):
    brand_id = models.CharField(max_length=32)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.brand_id}: {self.name}"


class List(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)
    list_id = models.CharField(max_length=32)
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    default = models.BooleanField(default=False)
    # hidden = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.list_id}: {self.name}"
