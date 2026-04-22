import djclick as click
from django.conf import settings
from django_q.models import Schedule
from rich import print

from thunderdome.models import Event

SCHEDULE_TYPE_MAP = {
    "MINUTES": Schedule.MINUTES,
    "HOURLY": Schedule.HOURLY,
    "DAILY": Schedule.DAILY,
    "WEEKLY": Schedule.WEEKLY,
    "MONTHLY": Schedule.MONTHLY,
    "QUARTERLY": Schedule.QUARTERLY,
    "YEARLY": Schedule.YEARLY,
}


def _ensure_schedule(*, name, func, schedule_type, args=None):
    """Create a schedule if it doesn't exist. Never updates or deletes existing schedules."""
    schedule, created = Schedule.objects.get_or_create(
        name=name,
        defaults={
            "func": func,
            "schedule_type": schedule_type,
            **({"args": args} if args else {}),
        },
    )
    if created:
        print(f"[green]Created {name} ({func})[/green]")
    else:
        print(f"[yellow]Exists {name} ({schedule.func}) — skipping[/yellow]")


@click.command()
def command():
    """Ensure all scheduled tasks exist. Never modifies or deletes existing schedules."""
    # Sync schedules defined in settings.Q_SCHEDULES
    for name, config in getattr(settings, "Q_SCHEDULES", {}).items():
        schedule_type = SCHEDULE_TYPE_MAP.get(config["schedule_type"], Schedule.DAILY)
        _ensure_schedule(
            name=name,
            func=config["func"],
            schedule_type=schedule_type,
            args=config.get("args"),
        )

    # Sync pretalx event schedules from the database
    events = Event.objects.exclude(pretalx_token="")
    for event in events:
        _ensure_schedule(
            name=f"pretalx-sync-{event.pretalx_slug}",
            func="thunderdome.sync.sync_event",
            schedule_type=Schedule.DAILY,
            args=f'"{event.pretalx_slug}"',
        )

    # Sync Tito historical ticket sales daily
    _ensure_schedule(
        name="tito-events-sync",
        func="titowebhooks.sync.sync_tito_events",
        schedule_type=Schedule.DAILY,
    )
