import datetime

import djclick as click
from django.utils import timezone
from rich import print

from thunderdome.models import Event
from travel_safety.models import TravelRegistration

RETENTION_DAYS = 30


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting.")
def command(dry_run):
    """Delete travel safety registrations 30 days after the conference ends."""
    latest_event = Event.objects.order_by("-end_date").first()

    if not latest_event:
        print("[yellow]No events found. Nothing to do.[/yellow]")
        return

    cutoff_date = latest_event.end_date + datetime.timedelta(days=RETENTION_DAYS)
    today = timezone.now().date()

    if today < cutoff_date:
        days_remaining = (cutoff_date - today).days
        print(f"[yellow]Retention period has not expired. {days_remaining} day(s) remaining (cutoff: {cutoff_date}).[/yellow]")
        return

    registrations = TravelRegistration.objects.all()
    count = registrations.count()

    if count == 0:
        print("[green]No travel registrations to delete.[/green]")
        return

    if dry_run:
        print(f"[yellow]Dry run: would delete {count} travel registration(s).[/yellow]")
        return

    registrations.delete()
    print(f"[green]Deleted {count} travel registration(s). Retention policy enforced.[/green]")
