import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from tickets.emails import build_ticket_email
from tickets.models import TicketEmailLog

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
