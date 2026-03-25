import datetime

from django.conf import settings
from django.utils import timezone
from rich import print

from travel_safety.models import TravelRegistration

RETENTION_DAYS = 30


def enforce_retention():
    """Delete travel safety registrations 30 days after the conference ends."""
    cutoff_date = settings.CONFERENCE_END_DATE + datetime.timedelta(days=RETENTION_DAYS)
    today = timezone.now().date()

    if today < cutoff_date:
        return

    registrations = TravelRegistration.objects.filter(created_at__date__lte=cutoff_date)
    count = registrations.count()

    if count == 0:
        return

    registrations.delete()
    print(f"[green]Deleted {count} travel registration(s). Retention policy enforced.[/green]")
