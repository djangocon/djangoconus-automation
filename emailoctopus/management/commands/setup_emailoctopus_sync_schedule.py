import djclick as click
from django_q.models import Schedule
from rich import print


@click.command()
def command():
    """Set up a daily scheduled task to sync Email Octopus campaigns."""
    name = "emailoctopus-sync-campaigns"
    schedule, created = Schedule.objects.update_or_create(
        name=name,
        defaults={
            "func": "emailoctopus.utils.sync_campaigns",
            "schedule_type": Schedule.DAILY,
        },
    )
    action = "Created" if created else "Updated"
    print(f"[green]{action} daily sync schedule ({name})[/green]")
