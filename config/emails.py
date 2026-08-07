"""A registry of every email the app sends, so staff can preview them.

Adding an email? Add an ``EmailPreview`` here too. ``test_email_previews.py``
walks the repo for email templates and fails if one isn't registered, so this
list can't quietly fall behind the code.

Sample context is deliberately fabricated — previews never touch the database,
so no attendee's name or ticket link can leak into a preview page.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Callable

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    text_body: str
    html_body: str | None


@dataclass(frozen=True)
class EmailPreview:
    """One email we send.

    Either ``allauth_prefix`` (allauth builds the whole message, including the
    subject, from its own templates) or ``subject`` + ``text_template`` (we
    build it ourselves) must be given.
    """

    slug: str
    label: str
    description: str
    trigger: str
    context: Callable[[], dict]
    subject: str = ""
    text_template: str | None = None
    html_template: str | None = None
    allauth_prefix: str | None = None
    recipient: str = "The attendee or volunteer"
    templates: tuple[str, ...] = field(default_factory=tuple)

    def render(self, request=None) -> RenderedEmail:
        if self.allauth_prefix:
            return self._render_allauth(request)

        context = self.context()
        html = render_to_string(self.html_template, context) if self.html_template else None
        return RenderedEmail(
            subject=self.subject,
            text_body=render_to_string(self.text_template, context),
            html_body=html,
        )

    def _render_allauth(self, request) -> RenderedEmail:
        """Build the message through allauth itself.

        Going through the adapter rather than rendering templates directly means
        the preview shows exactly what ships — including the subject prefix
        behaviour that ACCOUNT_EMAIL_SUBJECT_PREFIX controls.
        """
        from allauth.account.adapter import get_adapter

        context = self.context()
        if request is not None:
            context.setdefault("request", request)

        message = get_adapter().render_mail(self.allauth_prefix, "preview@example.com", context)
        html_body = None
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                html_body = content
        return RenderedEmail(subject=message.subject, text_body=message.body, html_body=html_body)

    @property
    def all_templates(self) -> tuple[str, ...]:
        """Every template this email owns, for the registry-coverage test."""
        explicit = [t for t in (self.text_template, self.html_template) if t]
        return tuple(explicit) + self.templates


def _sample_shift():
    # localtime, not now(): the templates render in local time, so building this in
    # UTC makes a 9am sample shift display as the middle of the night.
    start = timezone.localtime(timezone.now()).replace(hour=9, minute=0, second=0, microsecond=0)
    start += datetime.timedelta(days=1)
    return SimpleNamespace(
        title="Registration Desk — morning",
        role=SimpleNamespace(
            name="Registration Desk",
            # The real handbook: a preview is easier to judge when the links go
            # where the actual email's links go.
            documentation_url=settings.VOLUNTEER_HANDBOOK_URL,
        ),
        location="Convention Center, Lobby B",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=2),
    )


def _shift_reminder_context():
    shift = _sample_shift()
    return {
        "shift": shift,
        "signup": SimpleNamespace(shift=shift),
        "my_shifts_url": "https://automation.defna.org/volunteers/mine/",
        "role_documentation_url": shift.role.documentation_url,
        "handbook_url": settings.VOLUNTEER_HANDBOOK_URL,
        "contact_email": settings.VOLUNTEER_CONTACT_EMAIL,
    }


def _sample_user():
    return SimpleNamespace(
        email="volunteer@example.com",
        get_full_name=lambda: "Ada Lovelace",
    )


def _shift_uncovered_context():
    return {
        "shift": _sample_shift(),
        "user": _sample_user(),
        "dashboard_url": "https://automation.defna.org/volunteers/dashboard/",
        "contact_email": settings.VOLUNTEER_CONTACT_EMAIL,
    }


def _ticket_context(**overrides):
    context = {
        "attendee": None,
        "name": "Ada Lovelace",
        "ticket_link": "https://automation.defna.org/online/ticket/sample-preview-link",
        "kind": "initial",
        "is_reissue": False,
        "is_resend": False,
        "year": timezone.now().year,
        "support_email": settings.DEFAULT_FROM_EMAIL,
    }
    context.update(overrides)
    return context


EMAIL_PREVIEWS: list[EmailPreview] = [
    EmailPreview(
        slug="login-code",
        label="Sign-in code",
        description="The passwordless sign-in code. This is how nearly everyone logs in.",
        trigger="Requesting a sign-in code at /accounts/login/code/",
        recipient="Anyone signing in",
        allauth_prefix="account/email/login_code",
        context=lambda: {"code": "123456"},
        templates=("account/email/login_code_message.txt",),
    ),
    EmailPreview(
        slug="password-reset",
        label="Password reset",
        description="Sent when someone asks to reset a password. Uses allauth's default body on our branded base.",
        trigger="Submitting the form at /accounts/password/reset/",
        recipient="Anyone resetting a password",
        allauth_prefix="account/email/password_reset_key",
        context=lambda: {
            "password_reset_url": "https://automation.defna.org/accounts/password/reset/key/sample-preview-key/",
            "username": "ada",
        },
    ),
    EmailPreview(
        slug="ticket-link-initial",
        label="Ticket link — initial",
        description="The online conference link, sent once a ticket is bought.",
        trigger="tickets.services queues it; sent by tickets.tasks.send_ticket_link_email",
        recipient="Online attendee",
        subject="Your DjangoCon US online conference link",
        text_template="tickets/email/ticket_link.txt",
        html_template="tickets/email/ticket_link.html",
        context=_ticket_context,
    ),
    EmailPreview(
        slug="ticket-link-resend",
        label="Ticket link — resent",
        description="The same link again, when an attendee asks for it a second time.",
        trigger="Resending from the ticket admin",
        recipient="Online attendee",
        subject="Your DjangoCon US online conference link (resent)",
        text_template="tickets/email/ticket_link.txt",
        html_template="tickets/email/ticket_link.html",
        context=lambda: _ticket_context(kind="resend", is_resend=True),
    ),
    EmailPreview(
        slug="ticket-link-reissue",
        label="Ticket link — reissued",
        description="A brand new link that invalidates the previous one.",
        trigger="Reissuing from the ticket admin",
        recipient="Online attendee",
        subject="Your new DjangoCon US online conference link",
        text_template="tickets/email/ticket_link.txt",
        html_template="tickets/email/ticket_link.html",
        context=lambda: _ticket_context(kind="reissue", is_reissue=True),
    ),
    EmailPreview(
        slug="shift-reminder",
        label="Volunteer shift reminder",
        description=(
            "Reminder sent to a volunteer 24 hours before their shift. Carries the role's own "
            "handbook link and a link to manage their shifts."
        ),
        trigger="Hourly schedule → volunteers.tasks.send_shift_reminders",
        recipient="Volunteer with an upcoming shift",
        subject="Reminder: your DjangoCon US volunteer shift “Registration Desk — morning”",
        text_template="volunteers/email/shift_reminder.txt",
        html_template="volunteers/email/shift_reminder.html",
        context=_shift_reminder_context,
    ),
    EmailPreview(
        slug="shift-uncovered",
        label="Uncovered shift alert",
        description="Alerts the coordinators when a near-term shift loses its last volunteer.",
        trigger="Cancelling a signup → volunteers.tasks.notify_shift_uncovered",
        recipient="VOLUNTEER_COORDINATOR_EMAILS",
        subject="DjangoCon US volunteer needed: “Registration Desk — morning” just lost its only volunteer",
        text_template="volunteers/email/shift_uncovered.txt",
        html_template="volunteers/email/shift_uncovered.html",
        context=_shift_uncovered_context,
    ),
]


def get_preview(slug: str) -> EmailPreview | None:
    return next((preview for preview in EMAIL_PREVIEWS if preview.slug == slug), None)
