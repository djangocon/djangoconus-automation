"""The volunteer hour budget is guidance, not a gate (#139).

Ken cancelled a 2pm shift, tried to pick up a 4pm one instead, and was blocked
by the 8-hour limit — the app refused a change that left his total the same. The
budget now warns and gets out of the way, matching how shift capacity has always
behaved ("a visual guide for organizers, not a hard cap").
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup, total_volunteer_hours

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="vol", email="vol@example.com", password="pw12345!")


@pytest.fixture
def role(db):
    return Role.objects.create(name="Registration Desk")


def make_shift(role, *, offset_hours, length_hours=2):
    start = timezone.now() + datetime.timedelta(hours=offset_hours)
    return Shift.objects.create(
        role=role,
        title=f"Shift +{offset_hours}h",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=length_hours),
    )


def messages_of(response, level_tag):
    return [m.message for m in get_messages(response.wsgi_request) if m.level_tag == level_tag]


def sign_up(client, shift):
    return client.post(reverse("volunteers:signup", args=[shift.pk]), follow=True)


@pytest.mark.django_db
class TestHourBudgetIsSoft:
    def test_signup_past_the_budget_succeeds(self, client, user, role, settings):
        settings.VOLUNTEER_MAX_HOURS = 4
        for offset in (10, 20):  # 4 hours banked, already at the budget
            VolunteerSignup.objects.create(shift=make_shift(role, offset_hours=offset), user=user)
        client.force_login(user)

        over = make_shift(role, offset_hours=30)
        sign_up(client, over)

        assert VolunteerSignup.objects.filter(shift=over, user=user, cancelled=False).exists()
        assert total_volunteer_hours(user) == 6

    def test_going_over_warns_rather_than_erroring(self, client, user, role, settings):
        settings.VOLUNTEER_MAX_HOURS = 4
        for offset in (10, 20):
            VolunteerSignup.objects.create(shift=make_shift(role, offset_hours=offset), user=user)
        client.force_login(user)

        response = sign_up(client, make_shift(role, offset_hours=30))

        assert not messages_of(response, "error"), "the budget must never block a signup"
        warnings = messages_of(response, "warning")
        assert len(warnings) == 1
        assert "6.0 volunteer hours" in warnings[0]

    def test_staying_under_the_budget_says_nothing(self, client, user, role, settings):
        settings.VOLUNTEER_MAX_HOURS = 8
        client.force_login(user)

        response = sign_up(client, make_shift(role, offset_hours=10))

        assert not messages_of(response, "warning")
        assert messages_of(response, "success")

    def test_kens_case_swapping_one_shift_for_another(self, client, user, role, settings):
        """Cancel a shift, pick up a different one: the total is unchanged."""
        settings.VOLUNTEER_MAX_HOURS = 4
        booked = [make_shift(role, offset_hours=o) for o in (10, 20)]
        for shift in booked:
            VolunteerSignup.objects.create(shift=shift, user=user)
        client.force_login(user)

        client.post(reverse("volunteers:cancel", args=[booked[1].pk]), follow=True)
        assert total_volunteer_hours(user) == 2

        replacement = make_shift(role, offset_hours=24)
        response = sign_up(client, replacement)

        assert VolunteerSignup.objects.filter(shift=replacement, user=user, cancelled=False).exists()
        assert total_volunteer_hours(user) == 4
        assert not messages_of(response, "warning"), "back at the budget, not over it"


@pytest.mark.django_db
class TestOtherGatesStillHold:
    """Softening the budget must not soften the gates that mean something."""

    def test_overlapping_shifts_are_still_refused(self, client, user, role, settings):
        settings.VOLUNTEER_MAX_HOURS = 99
        first = make_shift(role, offset_hours=10, length_hours=4)
        VolunteerSignup.objects.create(shift=first, user=user)
        client.force_login(user)

        overlapping = make_shift(role, offset_hours=11)
        response = sign_up(client, overlapping)

        assert not VolunteerSignup.objects.filter(shift=overlapping, user=user, cancelled=False).exists()
        assert messages_of(response, "error")

    def test_closed_shifts_are_still_refused(self, client, user, role, settings):
        settings.VOLUNTEER_MAX_HOURS = 99
        closed = make_shift(role, offset_hours=10)
        closed.signups_open = False
        closed.save(update_fields=["signups_open"])
        client.force_login(user)

        response = sign_up(client, closed)

        assert not VolunteerSignup.objects.filter(shift=closed, user=user, cancelled=False).exists()
        assert messages_of(response, "error")
