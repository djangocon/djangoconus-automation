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
    # Cron expressions are evaluated against django.utils.timezone.localtime(),
    # so they run in TIME_ZONE (America/Chicago) and follow DST on their own.
    "CRON": Schedule.CRON,
}


class UnknownScheduleType(click.ClickException):
    pass


def _resolve_type(name, config):
    """Map a Q_SCHEDULES entry's schedule_type, refusing anything unrecognised.

    This used to be ``SCHEDULE_TYPE_MAP.get(..., Schedule.DAILY)``, which turned
    a typo — or a type this map simply didn't know, as CRON was — into a daily
    job firing at whatever time the command happened to run. The digest sat at
    16:57 for days because of it. Better to fail the deploy than to schedule
    something silently wrong.
    """
    raw = config["schedule_type"]
    if raw not in SCHEDULE_TYPE_MAP:
        known = ", ".join(sorted(SCHEDULE_TYPE_MAP))
        raise UnknownScheduleType(f"{name}: unknown schedule_type {raw!r}. Known types: {known}.")

    schedule_type = SCHEDULE_TYPE_MAP[raw]
    if schedule_type == Schedule.CRON and not config.get("cron"):
        raise UnknownScheduleType(f"{name}: schedule_type CRON needs a 'cron' expression.")
    return schedule_type


def _ensure_schedule(*, name, func, schedule_type, args=None, cron=None):
    """Create a schedule if it doesn't exist. Never updates or deletes existing schedules."""
    defaults = {
        "func": func,
        "schedule_type": schedule_type,
        **({"args": args} if args else {}),
        **({"cron": cron} if cron else {}),
    }
    schedule, created = Schedule.objects.get_or_create(name=name, defaults=defaults)
    if created:
        print(f"[green]Created {name} ({func})[/green]")
    else:
        # Worth saying out loud: a schedule whose settings changed keeps its old
        # row, so correcting one means editing it directly.
        drifted = schedule.schedule_type != schedule_type or (cron and schedule.cron != cron)
        if drifted:
            print(
                f"[red]Exists {name} but does NOT match settings "
                f"(is {schedule.schedule_type}/{schedule.cron!r}, "
                f"settings say {schedule_type}/{cron!r}) — edit the row to change it[/red]"
            )
        else:
            print(f"[yellow]Exists {name} ({schedule.func}) — skipping[/yellow]")


@click.command()
def command():
    """Ensure all scheduled tasks exist. Never modifies or deletes existing schedules."""
    # Sync schedules defined in settings.Q_SCHEDULES
    for name, config in getattr(settings, "Q_SCHEDULES", {}).items():
        _ensure_schedule(
            name=name,
            func=config["func"],
            schedule_type=_resolve_type(name, config),
            args=config.get("args"),
            cron=config.get("cron"),
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
