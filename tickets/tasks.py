import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from tickets.emails import build_ticket_email
from tickets.models import OnlineAttendee, TicketEmailLog
from tickets.services import NoTicketsAvailable, assign_and_email
from tickets.sync import DEFAULT_YEAR

logger = logging.getLogger(__name__)


def send_ticket_link_email(log_id: int) -> bool:
    """Send one ticket-link email and record the outcome on its log row.

    Dispatched with django-q2's async_task from ``tickets.services``. Failures
    are swallowed after being written to the log — a bad address shouldn't kill
    the rest of a bulk send.
    """
    log = TicketEmailLog.objects.select_related("attendee", "ticket_link").filter(pk=log_id).first()
    if log is None:
        logger.error("TicketEmailLog %s disappeared before it could be sent", log_id)
        return False

    if log.status == TicketEmailLog.STATUS_SENT:
        # A retried task shouldn't mail somebody twice.
        logger.info("TicketEmailLog %s already sent; skipping", log_id)
        return False

    if log.ticket_link is None:
        log.mark_failed("Ticket link was removed before the email could be sent.")
        return False

    email = build_ticket_email(attendee=log.attendee, link_url=log.ticket_link.link, kind=log.kind)

    message = EmailMultiAlternatives(
        subject=email.subject,
        body=email.text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[log.to_email],
    )
    message.attach_alternative(email.html_body, "text/html")

    # Persist before sending; mark_sent/mark_failed only touch their own fields.
    log.subject = email.subject
    log.save(update_fields=["subject"])

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("Failed to send ticket link email %s to %s", log_id, log.to_email)
        log.mark_failed(str(exc)[:2000])
        return False

    log.mark_sent()
    logger.info("Sent %s ticket link email to %s", log.kind, log.to_email)
    return True


def send_pending_ticket_emails(year: int = DEFAULT_YEAR, limit: int | None = None) -> dict:
    """Email every online attendee for ``year`` who has not been emailed yet.

    Built to be run unattended on a schedule, so the guard against sending twice
    is the whole design. Anyone with an existing log row --- sent, or still
    queued in the worker --- is skipped, which means a second run (a retry, an
    accidental double-fire, a rerun after a partial batch) mails only the people
    the first run never reached. Failed rows are deliberately *not* skipped, so
    a transient SMTP problem gets another go.

    Links are assigned as needed rather than assumed, since anyone who buys
    between scheduling this and it firing will have no link yet. Running out of
    links stops the batch instead of silently mailing a subset --- the people
    left over are exactly the ones a human needs to know about.
    """
    already_emailed = set(
        TicketEmailLog.objects.filter(
            status__in=[TicketEmailLog.STATUS_SENT, TicketEmailLog.STATUS_QUEUED],
        ).values_list("to_email", flat=True)
    )

    queued = 0
    skipped = 0
    failed = 0
    out_of_links = False

    for attendee in OnlineAttendee.objects.filter(year=year).order_by("pk"):
        if attendee.email.lower() in already_emailed:
            skipped += 1
            continue

        if limit is not None and queued >= limit:
            break

        try:
            assign_and_email(attendee)
        except NoTicketsAvailable:
            out_of_links = True
            logger.error("Ran out of ticket links while emailing %s; stopping the batch", attendee.email)
            break
        except Exception:
            failed += 1
            logger.exception("Failed to queue ticket email for %s", attendee.email)
        else:
            queued += 1
            already_emailed.add(attendee.email.lower())

    summary = {
        "year": year,
        "queued": queued,
        "skipped": skipped,
        "failed": failed,
        "out_of_links": out_of_links,
    }
    logger.info("Pending ticket email run complete: %s", summary)
    return summary
