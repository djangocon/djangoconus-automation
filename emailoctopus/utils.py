import httpx
from django.conf import settings
from rich import print

EMAILOCTOPUS_BASE_URL = "https://emailoctopus.com/api/2.0"


def _get_headers():
    return {
        "Authorization": f"Bearer {settings.EMAILOCTOPUS_API_KEY}",
    }


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


def fetch_lists():
    """Fetch all lists from Email Octopus API."""
    url = f"{EMAILOCTOPUS_BASE_URL}/lists"
    all_lists = []

    params = {"api_key": settings.EMAILOCTOPUS_API_KEY, "limit": 100}

    while url:
        response = httpx.get(url, params=params)

        if response.status_code != 200:
            print(f"[red]Error fetching lists: {response.status_code} {response.text}[/red]")
            break

        data = response.json()
        all_lists.extend(data.get("data", []))

        paging = data.get("paging", {})
        next_page = paging.get("next")
        if next_page:
            params["starting_after"] = next_page
        else:
            break

    return all_lists


def sync_campaigns():
    """Sync campaigns from Email Octopus into the local database."""
    from emailoctopus.models import Campaign

    remote_lists = fetch_lists()

    if not remote_lists:
        print("[yellow]No campaigns found in Email Octopus.[/yellow]")
        return

    synced = 0
    created = 0

    for remote_list in remote_lists:
        _, was_created = Campaign.objects.update_or_create(
            list_id=remote_list["id"],
            defaults={"name": remote_list["name"]},
        )
        if was_created:
            created += 1
        synced += 1

    print(f"[green]Synced {synced} campaign(s) ({created} new).[/green]")
