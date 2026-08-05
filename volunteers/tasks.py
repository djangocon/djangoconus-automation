import datetime
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from rich import print

from volunteers.models import VolunteerSignup

logger = logging.getLogger(__name__)

# How far ahead of a shift we send the reminder.
REMINDER_WINDOW_HOURS = 24


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

        body = render_to_string("volunteers/email/shift_reminder.txt", {"signup": signup, "shift": signup.shift})
        send_mail(
            subject=f"Reminder: your DjangoCon US volunteer shift “{signup.shift.title}”",
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=False,
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

    body = render_to_string(
        "volunteers/email/shift_uncovered.txt",
        {"shift": shift, "user": cancelled_signup.user},
    )
    try:
        send_mail(
            subject=f"DjangoCon US volunteer needed: “{shift.title}” just lost its only volunteer",
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        # Never let a broken mail server break the volunteer's cancel action.
        logger.exception("Failed to send uncovered-shift alert for shift %s", shift.pk)
        return False
    return True
