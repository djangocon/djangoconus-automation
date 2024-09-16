from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import TicketLink


def tickets_info(request):
    tickets_available = TicketLink.objects.filter(date_link_accessed__isnull=True).exists()
    return render(request, "tickets/info.html", {"tickets_available": tickets_available})


@require_GET
def venueless_view(request):
    try:
        with transaction.atomic():
            # Fetch the next available ticket link
            ticket_link = (
                TicketLink.objects.select_for_update(skip_locked=True).filter(date_link_accessed__isnull=True).first()
            )
            if not ticket_link:
                return HttpResponse("No available tickets.", status=404)
            # Update the access date
            ticket_link.date_link_accessed = timezone.now()
            ticket_link.save()
            # Get the link to redirect
            redirect_url = ticket_link.link
        # Redirect the user
        return redirect(redirect_url)
    except Exception:
        # Handle exceptions
        return HttpResponse("An error occurred.", status=500)
