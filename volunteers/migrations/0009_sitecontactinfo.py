from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("volunteers", "0008_volunteerprofile"),
    ]

    operations = [
        migrations.DeleteModel(name="VolunteerProfile"),
        migrations.CreateModel(
            name="SiteContactInfo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "contact_info",
                    models.TextField(
                        blank=True,
                        help_text="Markdown. How volunteers can reach the coordinators — email, Slack, etc.",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Volunteer contact info",
                "verbose_name_plural": "Volunteer contact info",
            },
        ),
    ]
