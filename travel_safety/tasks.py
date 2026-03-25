import datetime

from django.utils import timezone
from rich import print

from thunderdome.models import Event
from travel_safety.models import TravelRegistration

RETENTION_DAYS = 30


def enforce_retention():
    """Delete travel safety registrations 30 days after the conference ends."""
    latest_event = Event.objects.order_by("-end_date").first()

    if not latest_event:
        return

    cutoff_date = latest_event.end_date + datetime.timedelta(days=RETENTION_DAYS)
    today = timezone.now().date()

    if today < cutoff_date:
        return

    registrations = TravelRegistration.objects.all()
    count = registrations.count()

    if count == 0:
        return

    registrations.delete()
    print(f"[green]Deleted {count} travel registration(s). Retention policy enforced.[/green]")
