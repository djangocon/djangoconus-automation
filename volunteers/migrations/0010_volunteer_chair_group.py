from django.db import migrations, models

from volunteers.permissions import VOLUNTEER_CHAIR_GROUP, grant_chair_group


def create_chair_group(apps, schema_editor):
    """Seed the Volunteer Chair group so chairs can be added in the admin."""
    grant_chair_group(
        apps.get_model("auth", "Group"),
        apps.get_model("auth", "Permission"),
        apps.get_model("contenttypes", "ContentType"),
    )


def delete_chair_group(apps, schema_editor):
    """Drop the group; leave the permissions for ``create_permissions`` to manage."""
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=VOLUNTEER_CHAIR_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("volunteers", "0009_sitecontactinfo"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="VolunteerChairPermissions",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ],
            options={
                "permissions": [
                    ("view_volunteer_dashboard", "Can view and manage the volunteer dashboard"),
                    ("view_volunteer_interest", "Can view the volunteer interest report"),
                ],
                "managed": False,
                "default_permissions": (),
            },
        ),
        migrations.RunPython(create_chair_group, delete_chair_group),
    ]
