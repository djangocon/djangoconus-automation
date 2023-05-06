from django.conf import settings
from rich import print
from sendy.api import SendyAPI


def send_to_sendy(*, email: str, name: str, campaign_id: str):
    api = SendyAPI(
        host="https://emails.djangocon.us/sendy/",
        api_key=settings.SENDY_API_KEY,
    )

    response = api.subscribe(
        list=campaign_id,
        email=email,
        name=name,
    )

    match response:
        case "1":
            print("Subscribed successfully.")

        case "Already subscribed.":
            print("The email address is already subscribed.")

        case _:
            print("Error:", response)
