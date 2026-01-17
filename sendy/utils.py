from apiron import Endpoint, JsonEndpoint, Service
from django.conf import settings
from rich import print


class Sendy(Service):
    domain = settings.SENDY_ENDPOINT_URL

    brands = JsonEndpoint(
        path="/api/brands/get-brands.php",
        default_method="POST",
    )
    lists = JsonEndpoint(
        path="/api/lists/get-lists.php",
        default_method="POST",
    )
    subscribe = Endpoint(
        path="/subscribe",
        default_method="POST",
    )


def send_to_sendy(*, email: str, name: str, campaign_id: str):
    response = Sendy.subscribe(
        data={
            "api_key": settings.SENDY_API_KEY,
            "boolean": "true",
            "list": campaign_id,
            "email": email,
            "name": name,
        }
    )

    match response:
        case "1":
            print("Subscribed successfully.")

        case "Already subscribed.":
            print("The email address is already subscribed.")

        case _:
            print("Error:", response)
