import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup

User = get_user_model()

COORDINATORS = ["rachell@example.com", "monica@example.com"]


@pytest.fixture
def role(db):
    return Role.objects.create(name="Registration Desk")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def coordinator_emails(settings):
    settings.VOLUNTEER_COORDINATOR_EMAILS = COORDINATORS


def make_shift(role, *, start_offset_hours=24, length_hours=2):
    start = timezone.now() + datetime.timedelta(hours=start_offset_hours)
    return Shift.objects.create(
        role=role,
        title="Test Shift",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=length_hours),
    )


def make_aged_signup(shift, user, *, age_minutes=120):
    signup = VolunteerSignup.objects.create(shift=shift, user=user)
    VolunteerSignup.objects.filter(pk=signup.pk).update(
        created_at=timezone.now() - datetime.timedelta(minutes=age_minutes)
    )
    return signup


def cancel(client, shift):
    return client.post(reverse("volunteers:cancel", args=[shift.id]))


def test_alert_sent_when_last_volunteer_cancels_near_shift(auth_client, user, role):
    shift = make_shift(role, start_offset_hours=24)
    make_aged_signup(shift, user)

    cancel(auth_client, shift)
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.recipients() == COORDINATORS
    assert "lost its only volunteer" in message.subject
    assert "Test Shift" in message.body


def test_no_alert_when_signup_and_cancel_within_buffer(auth_client, user, role):
    shift = make_shift(role, start_offset_hours=24)
    make_aged_signup(shift, user, age_minutes=10)

    cancel(auth_client, shift)
    assert len(mail.outbox) == 0


def test_no_alert_when_shift_is_far_out(auth_client, user, role):
    shift = make_shift(role, start_offset_hours=72)
    make_aged_signup(shift, user)

    cancel(auth_client, shift)
    assert len(mail.outbox) == 0


def test_no_alert_when_shift_still_covered(auth_client, user, role):
    shift = make_shift(role, start_offset_hours=24)
    make_aged_signup(shift, user)
    other = User.objects.create_user(username="other", email="other@example.com", password="pw12345!")
    VolunteerSignup.objects.create(shift=shift, user=other)

    cancel(auth_client, shift)
    assert len(mail.outbox) == 0


def test_no_alert_when_no_coordinators_configured(auth_client, user, role, settings):
    settings.VOLUNTEER_COORDINATOR_EMAILS = []
    shift = make_shift(role, start_offset_hours=24)
    make_aged_signup(shift, user)

    cancel(auth_client, shift)
    assert len(mail.outbox) == 0


def test_re_signup_resets_the_buffer(auth_client, user, role):
    """Signing up again after a cancel starts a fresh buffer window, so an old
    original signup date can't sneak an alert past the debounce."""
    shift = make_shift(role, start_offset_hours=24)
    make_aged_signup(shift, user, age_minutes=600)

    cancel(auth_client, shift)
    mail.outbox.clear()
    auth_client.post(reverse("volunteers:signup", args=[shift.id]))
    cancel(auth_client, shift)
    assert len(mail.outbox) == 0
