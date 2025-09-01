import os
import typer

from apiron import Endpoint
from apiron import JsonEndpoint
from apiron import Service
from rich import print


class Sendy(Service):
    domain = "https://emails.djangocon.us/"

    lists = JsonEndpoint(
        path="/api/lists/get-lists.php",
        default_method="POST",
    )

    subscribe = Endpoint(
        path="/subscribe",
        default_method="POST",
    )


def main():
    response = Sendy.lists(
        data={
            "api_key": os.getenv("SENDY_API_KEY"),
            "brand_id": 1,
            "include_hidden": "no",
        }
    )
    print(f"{response=}")

    response = Sendy.subscribe(
        data={
            "api_key": os.getenv("SENDY_API_KEY"),
            "boolean": "true",
            "email": "jeff@defana.org",
            "list": os.getenv("SENDY_CAMPAIGN_ID"),
            "name": "Jeff Triplett",
        }
    )
    print(f"{response=}")


if __name__ == "__main__":
    typer.run(main)
