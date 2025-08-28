import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import HttpRequest, HttpResponse, HttpResponseServerError
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .forms import BulkTicketCreationForm
from .models import TicketLink

logger = logging.getLogger(__name__)


def tickets_info(request: HttpRequest) -> HttpResponse:
    """Display ticket availability information page."""
    tickets_available = TicketLink.objects.filter(date_link_accessed__isnull=True).exists()

    context = {
        "tickets_available": tickets_available,
    }
    return render(request, "tickets/info.html", context)


@require_GET
def venueless_view(request: HttpRequest) -> HttpResponse:
    """
    Atomically claim an available ticket and redirect to its URL.

    Uses database-level locking to prevent race conditions when
    multiple users attempt to claim tickets simultaneously.
    """
    try:
        with transaction.atomic():
            ticket_link = (
                TicketLink.objects.select_for_update(skip_locked=True).filter(date_link_accessed__isnull=True).first()
            )

            if not ticket_link:
                logger.info("Ticket request failed: no tickets available")
                return HttpResponse(
                    "No available tickets. Please check back later.",
                    status=404,
                    content_type="text/plain",
                )

            ticket_link.date_link_accessed = timezone.now()
            ticket_link.save(update_fields=["date_link_accessed"])

            logger.info(f"Ticket {ticket_link.id} claimed and redirecting to: {ticket_link.link}")

        return redirect(ticket_link.link)

    except DatabaseError as e:
        logger.error(f"Database error while claiming ticket: {e}")
        return HttpResponseServerError(
            "Unable to process ticket request. Please try again.",
            content_type="text/plain",
        )
    except Exception as e:
        logger.exception(f"Unexpected error in venueless_view: {e}")
        return HttpResponseServerError(
            "An unexpected error occurred. Please contact support.",
            content_type="text/plain",
        )


@login_required
@require_http_methods(["GET", "POST"])
def create_tickets_view(request: HttpRequest) -> HttpResponse:
    """
    Bulk create ticket links from a form submission.

    GET: Display the ticket creation form
    POST: Process the form and create tickets
    """
    if request.method == "POST":
        form = BulkTicketCreationForm(request.POST)
        if form.is_valid():
            urls = form.cleaned_data["urls"]
            created_count = 0
            failed_urls = []

            for url in urls:
                try:
                    TicketLink.objects.create(link=url)
                    created_count += 1
                except Exception as e:
                    logger.error(f"Failed to create ticket for URL {url}: {e}")
                    failed_urls.append(url)

            if created_count > 0:
                messages.success(
                    request, f"Successfully created {created_count} ticket{'s' if created_count != 1 else ''}."
                )

            if failed_urls:
                messages.warning(request, f"Failed to create tickets for: {', '.join(failed_urls)}")

            return redirect("tickets_list")
    else:
        form = BulkTicketCreationForm()

    context = {
        "form": form,
    }
    return render(request, "tickets/create.html", context)


@login_required
def tickets_list_view(request: HttpRequest) -> HttpResponse:
    """
    Display all tickets with their status.

    Shows a table with all ticket links, creation dates, and access dates.
    """
    tickets = TicketLink.objects.all().order_by("-date_link_created")

    context = {
        "tickets": tickets,
        "total_count": tickets.count(),
        "available_count": tickets.filter(date_link_accessed__isnull=True).count(),
        "used_count": tickets.filter(date_link_accessed__isnull=False).count(),
    }
    return render(request, "tickets/list.html", context)
