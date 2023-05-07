import djclick as click
from django.conf import settings
from rich import print

from sendy.models import Brand, List
from sendy.utils import Sendy


@click.command()
def command():
    brands = Brand.objects.all()
    for brand in brands:
        response = Sendy.lists(
            data={
                "api_key": settings.SENDY_API_KEY,
                "brand_id": brand.brand_id,
            }
        )

        for item in response:
            sendy_list, created = List.objects.update_or_create(
                brand=brand,
                list_id=response[item]["id"],
                defaults={
                    "name": response[item]["name"],
                },
            )
            if created:
                print(f"creating {sendy_list.name}")
