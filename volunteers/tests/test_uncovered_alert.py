import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import notify_shift_uncovered

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


def make_cancelled_signup(shift, user, *, age_minutes=120):
    """A signup that existed for ``age_minutes`` and has just been cancelled."""
    signup = VolunteerSignup.objects.create(shift=shift, user=user, cancelled=True)
    VolunteerSignup.objects.filter(pk=signup.pk).update(
        created_at=timezone.now() - datetime.timedelta(minutes=age_minutes)
    )
    return signup


def test_alert_sent_when_last_volunteer_cancels_near_shift(user, role):
    shift = make_shift(role, start_offset_hours=24)
    signup = make_cancelled_signup(shift, user)

    assert notify_shift_uncovered(signup.pk) is True
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.recipients() == COORDINATORS
    assert "lost its only volunteer" in message.subject
    assert "Test Shift" in message.body


def test_no_alert_when_signup_and_cancel_within_buffer(user, role):
    shift = make_shift(role, start_offset_hours=24)
    signup = make_cancelled_signup(shift, user, age_minutes=10)

    assert notify_shift_uncovered(signup.pk) is False
    assert len(mail.outbox) == 0


def test_no_alert_when_shift_is_far_out(user, role):
    shift = make_shift(role, start_offset_hours=72)
    signup = make_cancelled_signup(shift, user)

    assert notify_shift_uncovered(signup.pk) is False
    assert len(mail.outbox) == 0


def test_no_alert_when_shift_still_covered(user, role):
    shift = make_shift(role, start_offset_hours=24)
    signup = make_cancelled_signup(shift, user)
    other = User.objects.create_user(username="other", email="other@example.com", password="pw12345!")
    VolunteerSignup.objects.create(shift=shift, user=other)

    assert notify_shift_uncovered(signup.pk) is False
    assert len(mail.outbox) == 0


def test_no_alert_when_no_coordinators_configured(user, role, settings):
    settings.VOLUNTEER_COORDINATOR_EMAILS = []
    shift = make_shift(role, start_offset_hours=24)
    signup = make_cancelled_signup(shift, user)

    assert notify_shift_uncovered(signup.pk) is False
    assert len(mail.outbox) == 0


@patch("volunteers.views.async_task")
def test_cancel_view_dispatches_alert_task(mock_async_task, auth_client, user, role):
    shift = make_shift(role, start_offset_hours=24)
    signup = VolunteerSignup.objects.create(shift=shift, user=user)

    auth_client.post(reverse("volunteers:cancel", args=[shift.id]))
    mock_async_task.assert_called_once_with("volunteers.tasks.notify_shift_uncovered", signup.pk)


@patch("volunteers.views.async_task")
def test_re_signup_resets_the_buffer(mock_async_task, auth_client, user, role):
    """Signing up again after a cancel starts a fresh buffer window, so an old
    original signup date can't sneak an alert past the debounce."""
    shift = make_shift(role, start_offset_hours=24)
    signup = VolunteerSignup.objects.create(shift=shift, user=user)
    VolunteerSignup.objects.filter(pk=signup.pk).update(created_at=timezone.now() - datetime.timedelta(hours=10))

    auth_client.post(reverse("volunteers:cancel", args=[shift.id]))
    auth_client.post(reverse("volunteers:signup", args=[shift.id]))
    auth_client.post(reverse("volunteers:cancel", args=[shift.id]))

    assert notify_shift_uncovered(signup.pk) is False
    assert len(mail.outbox) == 0
