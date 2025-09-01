import os
import typer

from rich import print
from sendy.api import SendyAPI


SENDY_API_KEY = os.getenv("SENDY_API_KEY", "")
SENDY_CAMPAIGN_ID = os.getenv("SENDY_CAMPAIGN_ID", "Pe7M5ioDDHeTMDcVU1A6ag")


def main():
    email = "example2@example.com"
    name = "John Doe"

    api = SendyAPI(
        host="https://emails.djangocon.us/",
        api_key=SENDY_API_KEY,
    )

    response = api.subscribe(
        list=SENDY_CAMPAIGN_ID,
        email=email,
        name=name,
    )

    print(f"{response=}")
    match response:
        case "1":
            print("Subscribed successfully.")

        case "Already subscribed.":
            print("The email address is already subscribed.")

        case _:
            print("Error:", response)


if __name__ == "__main__":
    typer.run(main)
