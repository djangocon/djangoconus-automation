from django.db import migrations, models

# name -> role-specific documentation URL (provided by the volunteer chairs).
ROLE_DOCS = {
    "Registration Desk": "https://docs.djangocon.us/volunteer_team/registration/",
    "Session Chair": "https://docs.djangocon.us/volunteer_team/session_emcee/",
    "Session Manager": "https://docs.djangocon.us/volunteer_team/session_manager/",
    "Online Moderator": (
        "https://docs.google.com/document/d/1OjwaufQv2jvXTQf4apjFkjqu9Cznj8QtW1o4URZ-Kdc/"
        "edit?tab=t.0#heading=h.iokuakmruk4m"
    ),
}


def set_role_docs(apps, schema_editor):
    Role = apps.get_model("volunteers", "Role")
    for name, url in ROLE_DOCS.items():
        Role.objects.filter(name=name).update(documentation_url=url)


def clear_role_docs(apps, schema_editor):
    Role = apps.get_model("volunteers", "Role")
    Role.objects.filter(name__in=ROLE_DOCS).update(documentation_url="")


class Migration(migrations.Migration):
    dependencies = [
        ("volunteers", "0003_seed_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="documentation_url",
            field=models.URLField(
                blank=True, help_text="Link to this role's volunteer documentation, shown to volunteers."
            ),
        ),
        migrations.RunPython(set_role_docs, clear_role_docs),
    ]
