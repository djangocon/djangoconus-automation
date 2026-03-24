import httpx
from django.conf import settings
from rich import print


EMAILOCTOPUS_BASE_URL = "https://emailoctopus.com/api/2.0"


def send_to_emailoctopus(*, email: str, name: str, list_id: str):
    """Subscribe an email address to an Email Octopus list."""
    url = f"{EMAILOCTOPUS_BASE_URL}/lists/{list_id}/contacts"

    parts = name.split(" ", 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""

    payload = {
        "api_key": settings.EMAILOCTOPUS_API_KEY,
        "email_address": email,
        "fields": {
            "FirstName": first_name,
            "LastName": last_name,
        },
        "status": "SUBSCRIBED",
    }

    response = httpx.post(url, json=payload)

    match response.status_code:
        case 200 | 201:
            print(f"[green]Subscribed {email} successfully.[/green]")

        case 409:
            print(f"[yellow]Already subscribed: {email}[/yellow]")

        case _:
            print(f"[red]Error subscribing {email}: {response.status_code} {response.text}[/red]")
