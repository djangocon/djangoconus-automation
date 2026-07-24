"""Introduce the Talk model and move talk data off Shift.

A Shift becomes purely the volunteer sign-up unit; each scheduled talk lives in
its own Talk row (keyed by the ICS UID) and points at the Shift that covers it.
Existing schedule-imported Shifts (those with an external_uid) each get one Talk;
their sign-ups stay put on the Shift.
"""

import django.db.models.deletion
from django.db import migrations, models


def shifts_to_talks(apps, schema_editor):
    Shift = apps.get_model("volunteers", "Shift")
    Talk = apps.get_model("volunteers", "Talk")
    for shift in Shift.objects.exclude(external_uid__isnull=True):
        Talk.objects.create(
            shift=shift,
            external_uid=shift.external_uid,
            title=shift.title,
            description=shift.description,
            talk_url=shift.talk_url,
            location=shift.location,
            starts_at=shift.starts_at,
            ends_at=shift.ends_at,
        )


def talks_to_shifts(apps, schema_editor):
    Talk = apps.get_model("volunteers", "Talk")
    for talk in Talk.objects.exclude(shift__isnull=True):
        shift = talk.shift
        shift.external_uid = talk.external_uid
        shift.talk_url = talk.talk_url
        shift.save(update_fields=["external_uid", "talk_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("volunteers", "0006_seed_2026_shifts"),
    ]

    operations = [
        migrations.CreateModel(
            name="Talk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "external_uid",
                    models.CharField(
                        blank=True,
                        help_text="UID from the schedule ICS feed, for idempotent syncing.",
                        max_length=255,
                        null=True,
                        unique=True,
                    ),
                ),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True)),
                (
                    "talk_url",
                    models.URLField(blank=True, help_text="Link to the talk on the conference website."),
                ),
                ("location", models.CharField(blank=True, max_length=200)),
                ("starts_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                (
                    "shift",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="talks",
                        to="volunteers.shift",
                    ),
                ),
            ],
            options={"ordering": ["starts_at", "title"]},
        ),
        migrations.RunPython(shifts_to_talks, talks_to_shifts),
        migrations.RemoveField(model_name="shift", name="external_uid"),
        migrations.RemoveField(model_name="shift", name="talk_url"),
    ]
