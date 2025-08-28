import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import BulkTicketCreationForm, ClaimTicketForm
from .models import TicketLink

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "POST"])
def tickets_info(request: HttpRequest) -> HttpResponse:
    """
    Main ticket page with claim functionality.

    GET: Display ticket info and claim form
    POST: Process ticket claim
    """
    tickets_available = TicketLink.objects.filter(attendee_email__isnull=True).exists()
    ticket_link = None
    is_existing = False

    if request.method == "POST":
        form = ClaimTicketForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()

            # First, check if this email already has a ticket
            existing_ticket = TicketLink.objects.filter(attendee_email=email).first()

            if existing_ticket:
                # Email already has a ticket assigned
                ticket_link = existing_ticket
                is_existing = True
                logger.info(f"Existing ticket retrieved for email: {email}")
            else:
                # Try to claim a new ticket
                try:
                    with transaction.atomic():
                        # Get the next available ticket (not assigned to anyone)
                        new_ticket = (
                            TicketLink.objects.select_for_update(skip_locked=True)
                            .filter(attendee_email__isnull=True)
                            .first()
                        )

                        if new_ticket:
                            # Assign the ticket to this email
                            new_ticket.attendee_email = email
                            new_ticket.date_link_assigned = timezone.now()
                            new_ticket.save(update_fields=["attendee_email", "date_link_assigned"])

                            ticket_link = new_ticket
                            logger.info(f"New ticket {new_ticket.id} assigned to email: {email}")
                        else:
                            # No tickets available
                            messages.error(request, "Sorry, no tickets are currently available.")
                            logger.warning(f"No tickets available for email: {email}")

                except DatabaseError as e:
                    logger.error(f"Database error while claiming ticket for {email}: {e}")
                    messages.error(request, "An error occurred. Please try again.")
                except Exception as e:
                    logger.exception(f"Unexpected error while claiming ticket for {email}: {e}")
                    messages.error(request, "An unexpected error occurred. Please contact support.")
    else:
        form = ClaimTicketForm()

    context = {
        "tickets_available": tickets_available,
        "form": form,
        "ticket_link": ticket_link,
        "is_existing": is_existing,
    }
    return render(request, "tickets/info.html", context)


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


@require_http_methods(["GET", "POST"])
def claim_ticket_view(request: HttpRequest) -> HttpResponse:
    """
    Allow attendees to claim a ticket with their email or retrieve existing ticket.

    GET: Display the email form
    POST: Process the email and assign/retrieve ticket
    """
    ticket_link = None
    is_existing = False

    if request.method == "POST":
        form = ClaimTicketForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower()

            # First, check if this email already has a ticket
            existing_ticket = TicketLink.objects.filter(attendee_email=email).first()

            if existing_ticket:
                # Email already has a ticket assigned
                ticket_link = existing_ticket
                is_existing = True
                logger.info(f"Existing ticket retrieved for email: {email}")
            else:
                # Try to claim a new ticket
                try:
                    with transaction.atomic():
                        # Get the next available ticket (not assigned to anyone)
                        new_ticket = (
                            TicketLink.objects.select_for_update(skip_locked=True)
                            .filter(attendee_email__isnull=True)
                            .first()
                        )

                        if new_ticket:
                            # Assign the ticket to this email
                            new_ticket.attendee_email = email
                            new_ticket.date_link_assigned = timezone.now()
                            new_ticket.save(update_fields=["attendee_email", "date_link_assigned"])

                            ticket_link = new_ticket
                            logger.info(f"New ticket {new_ticket.id} assigned to email: {email}")
                        else:
                            # No tickets available
                            messages.error(request, "Sorry, no tickets are currently available.")
                            logger.warning(f"No tickets available for email: {email}")

                except DatabaseError as e:
                    logger.error(f"Database error while claiming ticket for {email}: {e}")
                    messages.error(request, "An error occurred. Please try again.")
                except Exception as e:
                    logger.exception(f"Unexpected error while claiming ticket for {email}: {e}")
                    messages.error(request, "An unexpected error occurred. Please contact support.")

            if ticket_link:
                # Show the ticket to the user
                context = {
                    "form": form,
                    "ticket_link": ticket_link,
                    "is_existing": is_existing,
                    "email": email,
                }
                return render(request, "tickets/claim_result.html", context)
    else:
        form = ClaimTicketForm()

    context = {
        "form": form,
    }
    return render(request, "tickets/claim.html", context)
