import datetime
import logging

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from rich import print

from volunteers.models import VolunteerSignup

logger = logging.getLogger(__name__)

# How far ahead of a shift we send the reminder.
REMINDER_WINDOW_HOURS = 24


def absolute_url(url_name: str) -> str:
    """Build a full URL for an email.

    Tasks run on the worker with no request to hang ``build_absolute_uri`` off,
    so the host comes from the Site and the scheme from allauth's setting.
    """
    protocol = getattr(settings, "ACCOUNT_DEFAULT_HTTP_PROTOCOL", "https")
    return f"{protocol}://{Site.objects.get_current().domain}{reverse(url_name)}"


def send_rich_email(*, subject: str, template_base: str, context: dict, recipients: list[str]) -> None:
    """Send a text email with an HTML alternative.

    ``template_base`` names the pair without its extension, e.g.
    ``volunteers/email/shift_reminder`` for ``.txt`` plus ``.html``. Text is the
    body and HTML the alternative, so a client that refuses HTML still gets a
    readable email.
    """
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"{template_base}.txt", context),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=recipients,
    )
    message.attach_alternative(render_to_string(f"{template_base}.html", context), "text/html")
    message.send(fail_silently=False)


def shift_email_context(signup) -> dict:
    """What both volunteer-facing emails need to say.

    The confirmation and the reminder show the same shift, the same role guide
    and the same "change your shifts" link — so they build that context here
    rather than drifting apart.
    """
    return {
        "signup": signup,
        "shift": signup.shift,
        "my_shifts_url": absolute_url("volunteers:my_shifts"),
        # The role's own guide when it has one; the general handbook is the
        # fallback so the email is never left without a link.
        "role_documentation_url": signup.shift.role.documentation_url,
        "handbook_url": settings.VOLUNTEER_HANDBOOK_URL,
        "contact_email": settings.VOLUNTEER_CONTACT_EMAIL,
    }


def send_volunteer_welcome(signup_id):
    """Welcome someone to the volunteer team the first time they sign up (#133).

    A welcome, not a per-shift receipt: it goes out once, on the signup that
    made them a volunteer, and carries the guide for that role, the handbook and
    the link to manage their shifts.

    Dispatched with async_task from the signup view, so a mail server having a
    bad day can never break a signup. ``welcomed`` is set on the user's signups
    rather than counted, so cancelling everything and starting again doesn't
    trigger a second welcome.
    """
    signup = VolunteerSignup.objects.select_related("user", "shift", "shift__role").filter(pk=signup_id).first()
    if signup is None:
        logger.warning("VolunteerSignup %s disappeared before the welcome could be sent", signup_id)
        return False
    if signup.cancelled:
        # Signed up and cancelled again before the worker got to it.
        return False

    email = signup.user.email
    if not email:
        return False

    if VolunteerSignup.objects.filter(user=signup.user, welcomed=True).exists():
        return False

    try:
        send_rich_email(
            subject="Welcome to the DjangoCon US volunteer team",
            template_base="volunteers/email/volunteer_welcome",
            context=shift_email_context(signup),
            recipients=[email],
        )
    except Exception:
        logger.exception("Failed to send volunteer welcome for signup %s", signup_id)
        return False

    signup.welcomed = True
    signup.save(update_fields=["welcomed"])
    return True


def send_shift_reminders():
    """Email volunteers whose shift starts within the next 24 hours.

    Scheduled via Q_SCHEDULES. Each signup is reminded at most once (tracked by
    ``VolunteerSignup.reminded``).
    """
    now = timezone.now()
    window_end = now + datetime.timedelta(hours=REMINDER_WINDOW_HOURS)

    signups = VolunteerSignup.objects.filter(
        cancelled=False,
        reminded=False,
        shift__starts_at__gte=now,
        shift__starts_at__lte=window_end,
    ).select_related("user", "shift", "shift__role")

    sent = 0
    for signup in signups:
        email = signup.user.email
        if not email:
            continue

        send_rich_email(
            subject=f"Reminder: your DjangoCon US volunteer shift “{signup.shift.title}”",
            template_base="volunteers/email/shift_reminder",
            context=shift_email_context(signup),
            recipients=[email],
        )
        signup.reminded = True
        signup.save(update_fields=["reminded"])
        sent += 1

    print(f"[green]Sent {sent} volunteer shift reminder(s).[/green]")
    return sent


def notify_shift_uncovered(signup_id):
    """Alert the coordinators when a near-term shift just lost its last volunteer.

    Dispatched via django-q2's async_task from the cancel view, with the
    cancelled signup's pk. Skips quietly when: no coordinator emails are
    configured, the shift still has active signups, it starts outside the alert
    window (or already started), or the volunteer signed up and cancelled within
    the buffer — a quick change of mind isn't worth an email. Returns True when
    an alert was sent.
    """
    recipients = settings.VOLUNTEER_COORDINATOR_EMAILS
    if not recipients:
        return False
    cancelled_signup = VolunteerSignup.objects.select_related("shift", "shift__role", "user").get(pk=signup_id)
    shift = cancelled_signup.shift
    if shift.active_signups.exists():
        return False

    now = timezone.now()
    window_end = now + datetime.timedelta(hours=settings.VOLUNTEER_UNCOVERED_ALERT_WINDOW_HOURS)
    if not (now <= shift.starts_at <= window_end):
        return False

    buffer = datetime.timedelta(minutes=settings.VOLUNTEER_UNCOVERED_ALERT_BUFFER_MINUTES)
    if now - cancelled_signup.created_at < buffer:
        return False

    try:
        send_rich_email(
            subject=f"DjangoCon US volunteer needed: “{shift.title}” just lost its only volunteer",
            template_base="volunteers/email/shift_uncovered",
            context={
                "shift": shift,
                "user": cancelled_signup.user,
                "dashboard_url": absolute_url("volunteers:dashboard"),
                "contact_email": settings.VOLUNTEER_CONTACT_EMAIL,
            },
            recipients=recipients,
        )
    except Exception:
        # Never let a broken mail server break the volunteer's cancel action.
        logger.exception("Failed to send uncovered-shift alert for shift %s", shift.pk)
        return False
    return True
