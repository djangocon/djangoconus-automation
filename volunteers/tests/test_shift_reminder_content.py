"""The reminder has to tell a volunteer where to go next (#133).

Rachell's ask: every volunteer should get the handbook for the role they signed
up for, and a link to where they can change their shifts. The reminder is the
one email they reliably receive, so it carries both.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import send_shift_reminders

User = get_user_model()

HANDBOOK = "https://example.com/general-handbook"
ROLE_DOC = "https://example.com/handbook#registration-desk"


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture
def site(db):
    site = Site.objects.get_current()
    site.domain = "automation.defna.org"
    site.save()
    Site.objects.clear_cache()
    return site


def make_signup(user, *, documentation_url=""):
    role = Role.objects.create(name="Registration Desk", documentation_url=documentation_url)
    start = timezone.now() + datetime.timedelta(hours=2)
    shift = Shift.objects.create(
        role=role, title="Test Shift", starts_at=start, ends_at=start + datetime.timedelta(hours=2)
    )
    return VolunteerSignup.objects.create(shift=shift, user=user)


@pytest.mark.django_db
class TestShiftReminderContent:
    def test_links_to_the_page_where_shifts_can_be_changed(self, user, site, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        make_signup(user)

        assert send_shift_reminders() == 1
        assert "https://automation.defna.org/volunteers/mine/" in mail.outbox[0].body

    def test_uses_the_roles_own_documentation_when_it_has_some(self, user, site, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        make_signup(user, documentation_url=ROLE_DOC)

        assert send_shift_reminders() == 1
        body = mail.outbox[0].body
        assert ROLE_DOC in body
        # The role-specific guide replaces the general handbook rather than
        # sitting alongside it — two links compete for the same click.
        assert HANDBOOK not in body

    def test_falls_back_to_the_general_handbook(self, user, site, settings):
        settings.VOLUNTEER_HANDBOOK_URL = HANDBOOK
        make_signup(user, documentation_url="")

        assert send_shift_reminders() == 1
        assert HANDBOOK in mail.outbox[0].body

    def test_survives_a_role_and_handbook_with_no_links_at_all(self, user, site, settings):
        settings.VOLUNTEER_HANDBOOK_URL = ""
        make_signup(user, documentation_url="")

        assert send_shift_reminders() == 1
        # No handbook anywhere, but the volunteer still gets the shifts page.
        assert "https://automation.defna.org/volunteers/mine/" in mail.outbox[0].body

    def test_contact_email_is_used_when_configured(self, user, site, settings):
        settings.VOLUNTEER_CONTACT_EMAIL = "volunteers@djangocon.us"
        make_signup(user)

        assert send_shift_reminders() == 1
        assert "volunteers@djangocon.us" in mail.outbox[0].body
