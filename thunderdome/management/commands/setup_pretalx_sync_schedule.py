import djclick as click
from django_q.models import Schedule
from rich import print

from thunderdome.models import Event


@click.command()
def command():
    """Set up a daily scheduled task to sync all events from pretalx."""
    events = Event.objects.exclude(pretalx_token="")
    if not events.exists():
        print("[red]No events with pretalx tokens configured.[/red]")
        return

    for event in events:
        name = f"pretalx-sync-{event.pretalx_slug}"
        schedule, created = Schedule.objects.update_or_create(
            name=name,
            defaults={
                "func": "thunderdome.sync.sync_event",
                "args": f'"{event.pretalx_slug}"',
                "schedule_type": Schedule.DAILY,
            },
        )
        action = "Created" if created else "Updated"
        print(f"[green]{action} daily sync schedule for {event.name} ({name})[/green]")
