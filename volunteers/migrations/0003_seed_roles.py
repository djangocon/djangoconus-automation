from django.db import migrations

# (group, name, description) — the group is just for readable grouping; it maps to
# the three sign-up sheets the roles were pulled from. Only name/description are stored.
ROLES = [
    (
        "Registration",
        "Registration Desk",
        "Check in attendees, hand out badges, and answer arrival questions at the registration desk.",
    ),
    (
        "Sessions",
        "Session Chair",
        "Introduce speakers, keep time, and run audience Q&A for talks in a session room.",
    ),
    (
        "Sessions",
        "Session Manager",
        "Oversee the session chairs and room logistics for a morning, afternoon, or evening block.",
    ),
    (
        "Online Volunteers",
        "Online Moderator",
        "Moderate the online stream for a room — relay remote Q&A and keep the virtual audience engaged.",
    ),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model("volunteers", "Role")
    for _group, name, description in ROLES:
        Role.objects.update_or_create(name=name, defaults={"description": description})


def unseed_roles(apps, schema_editor):
    Role = apps.get_model("volunteers", "Role")
    Role.objects.filter(name__in=[name for _group, name, _description in ROLES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("volunteers", "0002_calendartoken"),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
