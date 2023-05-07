import djclick as click

from rich import print
from django.conf import settings

from sendy.models import Brand
from sendy.utils import Sendy


@click.command()
def command():
    response = Sendy.brands(
        data={
            "api_key": settings.SENDY_API_KEY,
        }
    )

    for item in response:
        brand, created = Brand.objects.update_or_create(
            brand_id=response[item]["id"],
            defaults={
                "name": response[item]["name"],
            }
        )
        if created:
            print(f"creating {brand.name}")
