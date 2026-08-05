import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from tickets.models import TicketEmailLog

logger = logging.getLogger(__name__)

SUBJECTS = {
    TicketEmailLog.KIND_INITIAL: "Your DjangoCon US online conference link",
    TicketEmailLog.KIND_RESEND: "Your DjangoCon US online conference link (resent)",
    TicketEmailLog.KIND_REISSUE: "Your new DjangoCon US online conference link",
}


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

    context = {
        "attendee": log.attendee,
        "name": (log.attendee.name if log.attendee else "") or "",
        "ticket_link": log.ticket_link.link,
        "kind": log.kind,
        "is_reissue": log.kind == TicketEmailLog.KIND_REISSUE,
        "is_resend": log.kind == TicketEmailLog.KIND_RESEND,
        "year": log.attendee.year if log.attendee else None,
        "support_email": settings.DEFAULT_FROM_EMAIL,
    }

    subject = SUBJECTS.get(log.kind, SUBJECTS[TicketEmailLog.KIND_INITIAL])
    text_body = render_to_string("tickets/email/ticket_link.txt", context)
    html_body = render_to_string("tickets/email/ticket_link.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[log.to_email],
    )
    message.attach_alternative(html_body, "text/html")

    # Persist before sending; mark_sent/mark_failed only touch their own fields.
    log.subject = subject
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
