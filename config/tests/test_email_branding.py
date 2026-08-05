"""Every email we send must be branded DjangoCon US, in the subject and the body.

Before this, allauth's account emails inherited their branding from
``Site.name``, which in production is the bare hostname — so the main sign-in
email arrived as "[automation.defna.org] Sign-In Code" and opened with "Hello
from automation.defna.org!". These tests pin the fix by driving the real flows
and asserting the site name never reaches a subject or body again.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from tickets.tasks import SUBJECTS
from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import notify_shift_uncovered, send_shift_reminders

User = get_user_model()

BRAND = "DjangoCon US"


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Allauth throttles the login-code and password-reset views per IP."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture
def hostile_site(db):
    """Give the Site the bare hostname production actually uses.

    If any template still leans on ``Site.name``, these tests fail loudly
    instead of passing on a dev database that happens to say "example.com".
    """
    site = Site.objects.get_current()
    site.name = "automation.defna.org"
    site.domain = "automation.defna.org"
    site.save()
    Site.objects.clear_cache()
    return site


def assert_branded(message, *, allow_domain_in_body=False):
    """Subject and body must name DjangoCon US and must not leak the site name."""
    assert BRAND in message.subject, f"subject not branded: {message.subject!r}"
    assert "automation.defna.org" not in message.subject, f"site name leaked into subject: {message.subject!r}"
    assert BRAND in message.body, f"body not branded: {message.body!r}"
    if not allow_domain_in_body:
        assert "automation.defna.org" not in message.body
    assert "Hello from" not in message.body, "allauth's unbranded greeting is still being used"


@pytest.mark.django_db
class TestAccountEmailBranding:
    def test_login_code_email_is_branded(self, client, user, hostile_site):
        client.post(reverse("account_request_login_code"), {"email": user.email})
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        # The sign-in link legitimately contains the domain; the branding must not.
        assert_branded(message, allow_domain_in_body=True)
        assert message.subject == "Your DjangoCon US sign-in code"

    def test_password_reset_email_is_branded(self, client, user, hostile_site):
        client.post(reverse("account_reset_password"), {"email": user.email})
        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert_branded(message, allow_domain_in_body=True)
        assert message.subject == "Reset your DjangoCon US password"

    def test_no_subject_carries_a_bracketed_hostname_prefix(self, client, user, hostile_site):
        client.post(reverse("account_request_login_code"), {"email": user.email})
        assert not mail.outbox[0].subject.startswith("["), "allauth's [site] subject prefix is back"


@pytest.mark.django_db
class TestVolunteerEmailBranding:
    @pytest.fixture
    def shift(self, db):
        role = Role.objects.create(name="Registration Desk")
        start = timezone.now() + datetime.timedelta(hours=2)
        return Shift.objects.create(
            role=role, title="Test Shift", starts_at=start, ends_at=start + datetime.timedelta(hours=2)
        )

    def test_shift_reminder_is_branded(self, user, shift, hostile_site):
        VolunteerSignup.objects.create(shift=shift, user=user)
        assert send_shift_reminders() == 1
        assert_branded(mail.outbox[0])

    def test_uncovered_alert_is_branded(self, user, shift, hostile_site, settings):
        settings.VOLUNTEER_COORDINATOR_EMAILS = ["coordinator@example.com"]
        signup = VolunteerSignup.objects.create(shift=shift, user=user, cancelled=True)
        VolunteerSignup.objects.filter(pk=signup.pk).update(
            created_at=timezone.now() - datetime.timedelta(minutes=120)
        )
        assert notify_shift_uncovered(signup.pk) is True
        assert_branded(mail.outbox[0])


@pytest.mark.django_db
class TestTicketEmailBranding:
    def test_every_ticket_subject_is_branded(self):
        for kind, subject in SUBJECTS.items():
            assert BRAND in subject, f"{kind} subject not branded: {subject!r}"

    @pytest.mark.parametrize("template", ["tickets/email/ticket_link.txt", "tickets/email/ticket_link.html"])
    def test_ticket_bodies_are_branded(self, template):
        body = render_to_string(
            template,
            {
                "name": "Ada",
                "ticket_link": "https://example.com/t/abc",
                "year": 2026,
                "support_email": "hello@mail.defna.org",
            },
        )
        assert BRAND in body
