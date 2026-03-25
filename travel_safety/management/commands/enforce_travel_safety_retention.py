import datetime

import djclick as click
from django.conf import settings
from django.utils import timezone
from rich import print

from travel_safety.models import TravelRegistration

RETENTION_DAYS = 30


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting.")
def command(dry_run):
    """Delete travel safety registrations 30 days after the conference ends."""
    cutoff_date = settings.CONFERENCE_END_DATE + datetime.timedelta(days=RETENTION_DAYS)
    today = timezone.now().date()

    if today < cutoff_date:
        days_remaining = (cutoff_date - today).days
        print(
            f"[yellow]Retention period has not expired. {days_remaining} day(s) remaining (cutoff: {cutoff_date}).[/yellow]"
        )
        return

    registrations = TravelRegistration.objects.filter(created_at__date__lte=cutoff_date)
    count = registrations.count()

    if count == 0:
        print("[green]No travel registrations to delete.[/green]")
        return

    if dry_run:
        print(f"[yellow]Dry run: would delete {count} travel registration(s).[/yellow]")
        return

    registrations.delete()
    print(f"[green]Deleted {count} travel registration(s). Retention policy enforced.[/green]")
