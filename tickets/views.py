import logging
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from titowebhooks.reports import normalized_csv

from .forms import AssignByEmailForm, BulkTicketCreationForm, ClaimTicketForm
from .models import OnlineAttendee, TicketEmailLog, TicketLink
from .services import NoTicketsAvailable, assign_and_email, assign_link, claim_for_email
from .sync import DEFAULT_YEAR

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
            ticket_link, is_existing, error = claim_for_email(form.cleaned_data["email"])
            if error:
                messages.error(request, error)
    else:
        form = ClaimTicketForm()

    venueless_url = settings.VENUELESS_URL
    context = {
        "tickets_available": tickets_available,
        "form": form,
        "ticket_link": ticket_link,
        "is_existing": is_existing,
        "venueless_url": venueless_url,
        # The button reads as a domain rather than a full URL, so drop the scheme.
        "venueless_label": urlparse(venueless_url).netloc if venueless_url else "",
    }
    return render(request, "tickets/info.html", context)


@staff_member_required
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


@staff_member_required
def tickets_list_view(request: HttpRequest) -> HttpResponse:
    """
    Display all tickets with their status.

    Shows a table with all ticket links, creation dates, and access dates.
    """
    tickets = TicketLink.objects.all().order_by("-date_link_created")

    context = {
        "tickets": tickets,
        "total_count": tickets.count(),
        "available_count": tickets.filter(attendee_email__isnull=True).count(),
        "used_count": tickets.filter(attendee_email__isnull=False).count(),
    }
    return render(request, "tickets/list.html", context)


@require_http_methods(["GET", "POST"])
def claim_ticket_view(request: HttpRequest) -> HttpResponse:
    """
    Allow attendees to claim a ticket with their email or retrieve existing ticket.

    GET: Display the email form
    POST: Process the email and assign/retrieve ticket
    """
    if request.method == "POST":
        form = ClaimTicketForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            ticket_link, is_existing, error = claim_for_email(email)

            if error:
                messages.error(request, error)
            else:
                context = {
                    "form": form,
                    "ticket_link": ticket_link,
                    "is_existing": is_existing,
                    "email": email.strip().lower(),
                }
                return render(request, "tickets/claim_result.html", context)
    else:
        form = ClaimTicketForm()

    context = {
        "form": form,
    }
    return render(request, "tickets/claim.html", context)


def _attendee_queryset(year: int, status: str):
    """Roster for ``year``, narrowed by the dashboard's status filter."""
    queryset = OnlineAttendee.objects.filter(year=year)

    if status == "unassigned":
        return [a for a in queryset if not a.has_ticket]
    if status == "assigned":
        return [a for a in queryset if a.has_ticket]
    if status == "not_emailed":
        return [a for a in queryset if a.sent_email_count == 0]
    if status == "emailed":
        return [a for a in queryset if a.sent_email_count > 0]
    return list(queryset)


def _handle_assign_by_email(request: HttpRequest, year: int) -> bool:
    """Staff pasted an address into the box. Returns True if it was handled."""
    form = AssignByEmailForm(request.POST)
    if not form.is_valid():
        for error in form.errors.values():
            messages.error(request, "; ".join(error))
        return True

    email = form.cleaned_data["email"]
    attendee, created = OnlineAttendee.objects.get_or_create(
        year=year,
        email=email,
        defaults={
            "name": form.cleaned_data.get("name", ""),
            "source": OnlineAttendee.SOURCE_MANUAL,
        },
    )
    if not created and form.cleaned_data.get("name") and not attendee.name:
        attendee.name = form.cleaned_data["name"]
        attendee.save(update_fields=["name"])

    try:
        if form.cleaned_data.get("send_email"):
            assign_and_email(attendee, sent_by=request.user)
            messages.success(request, f"Assigned a ticket link to {email} and queued their email.")
        else:
            assign_link(email, attendee=attendee)
            messages.success(request, f"Assigned a ticket link to {email} (no email sent).")
    except NoTicketsAvailable:
        messages.error(request, "No unassigned ticket links are left. Add more links before assigning.")

    return True


def _handle_bulk_action(request: HttpRequest, action: str) -> None:
    """Apply ``action`` to every attendee id checked in the table."""
    ids = request.POST.getlist("attendee_ids")
    if not ids:
        messages.warning(request, "No attendees were selected.")
        return

    attendees = OnlineAttendee.objects.filter(pk__in=ids)
    reissue = action == "reissue"
    succeeded = 0
    out_of_links = False

    for attendee in attendees:
        # "email" only re-sends to people who already hold a link; it is the
        # safe bulk action for a nudge that shouldn't consume the pool.
        if action == "email" and not attendee.has_ticket:
            continue
        try:
            assign_and_email(attendee, reissue=reissue, sent_by=request.user)
            succeeded += 1
        except NoTicketsAvailable:
            out_of_links = True
            break
        except Exception:
            logger.exception("Failed to process %s for attendee %s", action, attendee.pk)

    if succeeded:
        messages.success(request, f"Queued {succeeded} email{'s' if succeeded != 1 else ''}.")
    if out_of_links:
        messages.error(request, "Ran out of unassigned ticket links partway through. Add more links and retry.")
    if not succeeded and not out_of_links:
        messages.warning(request, "Nothing to do for the selected attendees.")


def _attendees_csv(attendees, year: int) -> HttpResponse:
    return normalized_csv(
        f"online_attendees_{year}.csv",
        ["Ticket Link", "Emails Sent", "Last Emailed"],
        [
            {
                "Name": attendee.name,
                "Email": attendee.email,
                "Ticket Type": attendee.release_title,
                "Ticket Date": attendee.purchased_at,
                "Ticket Link": attendee.active_ticket_link.link if attendee.active_ticket_link else "",
                "Emails Sent": attendee.sent_email_count,
                "Last Emailed": attendee.last_emailed_at,
            }
            for attendee in attendees
        ],
    )


@staff_member_required
@require_http_methods(["GET", "POST"])
def online_attendees_view(request: HttpRequest) -> HttpResponse:
    """Who bought an online ticket, who has a link, and who has been emailed.

    Also the place staff assign links: one at a time by pasting an address, or
    in bulk from the table's checkboxes.
    """
    try:
        year = int(request.GET.get("year") or DEFAULT_YEAR)
    except ValueError:
        year = DEFAULT_YEAR

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "assign_by_email":
            _handle_assign_by_email(request, year)
        elif action in {"assign_and_email", "email", "reissue"}:
            _handle_bulk_action(request, action)
        else:
            messages.error(request, "Unknown action.")
        return redirect(f"{request.path}?year={year}&status={request.GET.get('status', 'all')}")

    status = request.GET.get("status", "all")
    attendees = _attendee_queryset(year, status)

    if request.GET.get("format") == "csv":
        return _attendees_csv(attendees, year)

    all_attendees = OnlineAttendee.objects.filter(year=year)
    assigned_count = sum(1 for a in all_attendees if a.has_ticket)
    emailed_count = sum(1 for a in all_attendees if a.sent_email_count)

    context = {
        "attendees": attendees,
        "year": year,
        "status": status,
        "assign_form": AssignByEmailForm(),
        "filters": [
            ("all", "All"),
            ("unassigned", "No link yet"),
            ("assigned", "Has a link"),
            ("not_emailed", "Never emailed"),
            ("emailed", "Emailed"),
        ],
        "total_count": len(all_attendees),
        "assigned_count": assigned_count,
        "unassigned_count": len(all_attendees) - assigned_count,
        "emailed_count": emailed_count,
        "available_links": TicketLink.objects.filter(attendee_email__isnull=True, superseded_at__isnull=True).count(),
        "failed_emails": TicketEmailLog.objects.filter(status=TicketEmailLog.STATUS_FAILED).count(),
    }
    return render(request, "tickets/attendees.html", context)


@staff_member_required
def ticket_emails_view(request: HttpRequest) -> HttpResponse:
    """Audit trail of every ticket-link email we've queued."""
    logs = TicketEmailLog.objects.select_related("attendee", "ticket_link", "sent_by")

    status = request.GET.get("status")
    if status in {TicketEmailLog.STATUS_QUEUED, TicketEmailLog.STATUS_SENT, TicketEmailLog.STATUS_FAILED}:
        logs = logs.filter(status=status)

    context = {
        "logs": logs[:500],
        "status": status or "all",
        "sent_count": TicketEmailLog.objects.filter(status=TicketEmailLog.STATUS_SENT).count(),
        "queued_count": TicketEmailLog.objects.filter(status=TicketEmailLog.STATUS_QUEUED).count(),
        "failed_count": TicketEmailLog.objects.filter(status=TicketEmailLog.STATUS_FAILED).count(),
    }
    return render(request, "tickets/emails.html", context)
