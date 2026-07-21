"""Seed a starting set of non-session volunteer shifts for DjangoCon US 2026.

Modeled on the 2024 Volunteers sheet, adapted to 2026 dates and a single track.
Session Chair shifts are NOT seeded here — those come from the schedule ICS feed
(`manage.py import_schedule`). This covers the desk/coverage and block roles that
aren't in the schedule feed: Registration Desk, Health & Safety Check-in,
Swag Bag Stuffing, and Session Manager blocks.

Everything below is meant to be edited: adjust dates, hours, capacities, and
locations as the plan firms up, then re-run against a fresh DB or hand-tune in
the admin. Reversible — the reverse deletes exactly the shifts it created.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.db import migrations

CHICAGO = ZoneInfo("America/Chicago")

# DjangoCon US 2026 — single track. Talks Mon–Wed; setup/registration opens Sunday.
SUN = date(2026, 8, 23)
MON = date(2026, 8, 24)
TUE = date(2026, 8, 25)
WED = date(2026, 8, 26)
TALK_DAYS = [MON, TUE, WED]

MAIN_ROOM = "Sauganash Ballroom"

# Roles this migration relies on. The first four are already seeded in 0003; the
# last two are new here. update_or_create keeps descriptions current either way.
ROLE_DESCRIPTIONS = {
    "Registration Desk": "Check in attendees, hand out badges, and answer arrival questions at the registration desk.",
    "Session Manager": "Oversee the session chairs and room logistics for a morning, afternoon, or evening block.",
    "Health & Safety Check-in": "Staff the health & safety check-in desk and help attendees follow the safety plan.",
    "Swag Bag Stuffing": "Assemble attendee swag bags before the conference opens.",
}


def _dt(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CHICAGO)


def _hourly(role, location, day, start_hour, end_hour, capacity):
    """One shift per hour in [start_hour, end_hour), e.g. 8–17 -> nine 1-hour slots."""
    for hour in range(start_hour, end_hour):
        yield {
            "role": role,
            "title": f"{role} · {day:%a} {hour % 12 or 12}:00 {'AM' if hour < 12 else 'PM'}",
            "location": location,
            "starts_at": _dt(day, hour),
            "ends_at": _dt(day, hour + 1),
            "capacity": capacity,
        }


def _shift_specs():
    """The full list of (role, title, location, start, end, capacity) to seed."""
    specs = []

    # Registration Desk: Sunday afternoon pre-reg + Mon–Wed 8am–5pm hourly.
    specs += list(_hourly("Registration Desk", "Registration Desk", SUN, 14, 18, capacity=2))
    for day in TALK_DAYS:
        specs += list(_hourly("Registration Desk", "Registration Desk", day, 8, 17, capacity=2))

    # Health & Safety Check-in: mirrors registration hours, single-person desk.
    specs += list(_hourly("Health & Safety Check-in", "Health & Safety Desk", SUN, 14, 18, capacity=1))
    for day in TALK_DAYS:
        specs += list(_hourly("Health & Safety Check-in", "Health & Safety Desk", day, 8, 17, capacity=1))

    # Swag Bag Stuffing: one group session Sunday afternoon.
    specs.append(
        {
            "role": "Swag Bag Stuffing",
            "title": "Swag Bag Stuffing",
            "location": "Registration Area",
            "starts_at": _dt(SUN, 14),
            "ends_at": _dt(SUN, 16),
            "capacity": 10,
        }
    )

    # Session Manager: one block shift per part of each talk day.
    blocks = [("Morning", 8, 30, 12, 0), ("Afternoon", 13, 0, 15, 30), ("Evening", 15, 30, 17, 30)]
    for day in TALK_DAYS:
        for name, sh, sm, eh, em in blocks:
            specs.append(
                {
                    "role": "Session Manager",
                    "title": f"{name} Session Manager · {day:%a}",
                    "location": MAIN_ROOM,
                    "starts_at": _dt(day, sh, sm),
                    "ends_at": _dt(day, eh, em),
                    "capacity": 1,
                }
            )

    return specs


def seed_shifts(apps, schema_editor):
    Role = apps.get_model("volunteers", "Role")
    Shift = apps.get_model("volunteers", "Shift")

    for name, description in ROLE_DESCRIPTIONS.items():
        Role.objects.update_or_create(name=name, defaults={"description": description})

    roles = {r.name: r for r in Role.objects.all()}
    for spec in _shift_specs():
        role = roles[spec["role"]]
        Shift.objects.update_or_create(
            title=spec["title"],
            starts_at=spec["starts_at"],
            defaults={
                "role": role,
                "location": spec["location"],
                "ends_at": spec["ends_at"],
                "capacity": spec["capacity"],
                "external_uid": None,
            },
        )


def unseed_shifts(apps, schema_editor):
    Shift = apps.get_model("volunteers", "Shift")
    for spec in _shift_specs():
        Shift.objects.filter(title=spec["title"], starts_at=spec["starts_at"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("volunteers", "0005_add_external_uid_and_talk_url"),
    ]

    operations = [
        migrations.RunPython(seed_shifts, unseed_shifts),
    ]
