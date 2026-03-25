import djclick as click
from django_q.models import Schedule
from rich import print


@click.command()
def command():
    """Set up a daily scheduled task to enforce travel safety data retention."""
    name = "travel-safety-retention-policy"
    schedule, created = Schedule.objects.update_or_create(
        name=name,
        defaults={
            "func": "travel_safety.tasks.enforce_retention",
            "schedule_type": Schedule.DAILY,
        },
    )
    action = "Created" if created else "Updated"
    print(f"[green]{action} daily retention schedule ({name})[/green]")
