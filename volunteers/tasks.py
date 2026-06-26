import datetime

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from rich import print

from volunteers.models import VolunteerSignup

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
