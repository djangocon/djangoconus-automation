import datetime

from django.conf import settings
from django.utils import timezone
from rich import print

from travel_safety.models import TravelRegistration

RETENTION_DAYS = 30


def enforce_retention():
    """Delete travel safety registrations 30 days after the conference ends."""
    cutoff_date = settings.CONFERENCE_END_DATE + datetime.timedelta(days=RETENTION_DAYS)
    # localdate(), not now().date(): the register page promises deletion 30 days
    # after the conference in the reader's terms, and CONFERENCE_END_DATE is a
    # plain local date. Comparing it against the UTC date fires the deletion up
    # to five hours early every evening, which is silent -- it destroys travel
    # details rather than raising. The __date lookup below is already evaluated
    # in TIME_ZONE, so this also keeps the two halves consistent.
    today = timezone.localdate()

    if today < cutoff_date:
        return

    registrations = TravelRegistration.objects.filter(created_at__date__lte=cutoff_date)
    count = registrations.count()

    if count == 0:
        return

    registrations.delete()
    print(f"[green]Deleted {count} travel registration(s). Retention policy enforced.[/green]")
