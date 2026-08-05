"""Ticket assignment and email dispatch.

Views call in here rather than reimplementing the claim dance; it used to be
copy-pasted between two views and drifting.
"""

import logging

from django.db import DatabaseError, transaction
from django.utils import timezone
from django_q.tasks import async_task

from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink

logger = logging.getLogger(__name__)


class NoTicketsAvailable(Exception):
    """Raised when the pool of unassigned ticket links is empty."""


def active_link_for_email(email: str) -> TicketLink | None:
    return TicketLink.objects.filter(attendee_email=email, superseded_at__isnull=True).first()


def assign_link(email: str, *, attendee: OnlineAttendee | None = None, reissue: bool = False) -> TicketLink:
    """Give ``email`` a ticket link, returning the one they should be using.

    Without ``reissue`` an address that already holds a live link gets that same
    link back, so a double-submitted form can't burn two links. With ``reissue``
    the current link is superseded and a fresh one is pulled from the pool.

    Raises ``NoTicketsAvailable`` when the pool is dry.
    """
    email = email.strip().lower()

    with transaction.atomic():
        existing = active_link_for_email(email)
        if existing and not reissue:
            # Backfill the FK for links claimed before the roster existed.
            if attendee and existing.attendee_id != attendee.pk:
                existing.attendee = attendee
                existing.save(update_fields=["attendee"])
            return existing

        # skip_locked lets concurrent claims grab different rows instead of
        # queueing; pk ordering makes "next available" deterministic.
        new_link = (
            TicketLink.objects.select_for_update(skip_locked=True)
            .filter(attendee_email__isnull=True, superseded_at__isnull=True)
            .order_by("pk")
            .first()
        )
        if new_link is None:
            raise NoTicketsAvailable(f"No unassigned ticket links remain (requested for {email})")

        # Supersede only after we know a replacement exists, so a failed reissue
        # never leaves someone with no link at all.
        if existing:
            existing.supersede()

        new_link.attendee_email = email
        new_link.attendee = attendee
        new_link.date_link_assigned = timezone.now()
        new_link.save(update_fields=["attendee_email", "attendee", "date_link_assigned"])

    logger.info("Assigned ticket link %s to %s (reissue=%s)", new_link.pk, email, reissue)
    return new_link


def claim_for_email(email: str) -> tuple[TicketLink | None, bool, str | None]:
    """Public self-service claim.

    Returns ``(link, is_existing, error_message)`` so the view can render a
    message without owning any of the assignment rules.
    """
    email = email.strip().lower()

    existing = active_link_for_email(email)
    if existing:
        logger.info("Existing ticket retrieved for email: %s", email)
        return existing, True, None

    attendee = OnlineAttendee.objects.filter(email=email).order_by("-year").first()
    try:
        return assign_link(email, attendee=attendee), False, None
    except NoTicketsAvailable:
        logger.warning("No tickets available for email: %s", email)
        return None, False, "Sorry, no tickets are currently available."
    except DatabaseError:
        logger.exception("Database error while claiming ticket for %s", email)
        return None, False, "An error occurred. Please try again."


def queue_ticket_email(
    attendee: OnlineAttendee,
    link: TicketLink,
    *,
    kind: str = TicketEmailLog.KIND_INITIAL,
    sent_by=None,
) -> TicketEmailLog:
    """Write the log row, then hand the send to the worker.

    The row is created before dispatch so a send that never runs still shows up
    as ``queued`` in the dashboard rather than disappearing.
    """
    log = TicketEmailLog.objects.create(
        attendee=attendee,
        ticket_link=link,
        to_email=attendee.email,
        kind=kind,
        sent_by=sent_by if (sent_by and sent_by.is_authenticated) else None,
    )
    async_task("tickets.tasks.send_ticket_link_email", log.pk)
    return log


def assign_and_email(
    attendee: OnlineAttendee,
    *,
    reissue: bool = False,
    sent_by=None,
) -> tuple[TicketLink, TicketEmailLog]:
    """Ensure the attendee holds a link and email it to them."""
    had_link = attendee.has_ticket
    link = assign_link(attendee.email, attendee=attendee, reissue=reissue)

    if reissue:
        kind = TicketEmailLog.KIND_REISSUE
    elif had_link:
        kind = TicketEmailLog.KIND_RESEND
    else:
        kind = TicketEmailLog.KIND_INITIAL

    return link, queue_ticket_email(attendee, link, kind=kind, sent_by=sent_by)
