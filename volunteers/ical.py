"""Minimal RFC 5545 (iCalendar) generation for volunteer shift feeds.

Hand-rolled to avoid adding an iCal dependency. Produces a VCALENDAR with one
VEVENT per active signup, with all datetimes emitted in UTC.
"""

from datetime import timezone as dt_timezone

from django.utils import timezone


def _ics_escape(text):
    if not text:
        return ""
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _utc(dt):
    return timezone.localtime(dt, dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_calendar(signups, host="djangocon.us"):
    """Return an iCalendar document (str) for an iterable of VolunteerSignup."""
    now = _utc(timezone.now())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DjangoCon US//Volunteers//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:DjangoCon US Volunteer Shifts",
    ]
    for signup in signups:
        shift = signup.shift
        summary = f"Volunteer: {shift.title}"
        description = f"Role: {shift.role.name}"
        if shift.description:
            description += f"\n{shift.description}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:volunteer-signup-{signup.pk}@{host}",
            f"DTSTAMP:{now}",
            f"DTSTART:{_utc(shift.starts_at)}",
            f"DTEND:{_utc(shift.ends_at)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(description)}",
        ]
        if shift.location:
            lines.append(f"LOCATION:{_ics_escape(shift.location)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    # iCal lines are CRLF-terminated.
    return "\r\n".join(lines) + "\r\n"
