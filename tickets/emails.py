"""Building the ticket-link email, in one place.

The worker sends this email and staff preview it from the attendee dashboard.
Those were two renderings of the same templates, so they lived one edit apart
from disagreeing --- a preview that quietly stops matching what ships is worse
than no preview at all. Both call ``build_ticket_email`` instead.
"""

from dataclasses import dataclass

from django.conf import settings
from django.template.loader import render_to_string

from tickets.models import OnlineAttendee, TicketEmailLog

SUBJECTS = {
    TicketEmailLog.KIND_INITIAL: "Your DjangoCon US online conference link",
    TicketEmailLog.KIND_RESEND: "Your DjangoCon US online conference link (resent)",
    TicketEmailLog.KIND_REISSUE: "Your new DjangoCon US online conference link",
}

TEXT_TEMPLATE = "tickets/email/ticket_link.txt"
HTML_TEMPLATE = "tickets/email/ticket_link.html"

# Stands in for the real thing when previewing an email to someone who has no
# link yet. Obviously fake on sight, so nobody mistakes a preview for a ticket.
PLACEHOLDER_LINK = "https://ti.to/example/a-link-is-pulled-from-the-pool-when-you-send"


@dataclass(frozen=True)
class RenderedTicketEmail:
    subject: str
    text_body: str
    html_body: str


def build_ticket_email(
    *,
    attendee: OnlineAttendee | None,
    link_url: str,
    kind: str = TicketEmailLog.KIND_INITIAL,
) -> RenderedTicketEmail:
    """Render the ticket-link email exactly as it goes out."""
    context = {
        "attendee": attendee,
        "name": (attendee.name if attendee else "") or "",
        "ticket_link": link_url,
        "kind": kind,
        "is_reissue": kind == TicketEmailLog.KIND_REISSUE,
        "is_resend": kind == TicketEmailLog.KIND_RESEND,
        "year": attendee.year if attendee else None,
        "support_email": settings.DEFAULT_FROM_EMAIL,
    }

    return RenderedTicketEmail(
        subject=SUBJECTS.get(kind, SUBJECTS[TicketEmailLog.KIND_INITIAL]),
        text_body=render_to_string(TEXT_TEMPLATE, context),
        html_body=render_to_string(HTML_TEMPLATE, context),
    )
