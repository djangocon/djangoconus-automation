"""The morning "what you're on for today" digest.

Jeff's constraint, and the reason most of these tests exist: no pressure. It
goes to people who have a shift today and to nobody else — a daily email to a
volunteer with nothing scheduled is nagging, not a reminder. Open shifts get a
one-line count, never a list of what still needs filling.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core import mail
from django.utils import timezone

from volunteers.models import Role, Shift, VolunteerSignup
from volunteers.tasks import send_daily_shift_digest

User = get_user_model()


@pytest.fixture(autouse=True)
def site(db):
    site = Site.objects.get_current()
    site.domain = "automation.defna.org"
    site.save()
    Site.objects.clear_cache()
    return site


@pytest.fixture
def role(db):
    return Role.objects.create(name="Registration Desk", documentation_url="https://handbook.example/desk")


def make_user(name="vol"):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw12345!")


def at_local(hour, *, days=0):
    """A tz-aware datetime at ``hour`` local time, ``days`` from today."""
    today = timezone.localdate() + datetime.timedelta(days=days)
    return timezone.make_aware(datetime.datetime.combine(today, datetime.time(hour, 0)))


def make_shift(role, *, hour=9, days=0, capacity=1, title=None, length=2):
    start = at_local(hour, days=days)
    return Shift.objects.create(
        role=role,
        title=title or f"Desk {hour}:00",
        location="LaSalle Ballroom",
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=length),
        capacity=capacity,
    )


def html_part(message):
    for content, mimetype in message.alternatives:
        if mimetype == "text/html":
            return content
    raise AssertionError("no text/html alternative")


@pytest.mark.django_db
class TestWhoGetsIt:
    def test_a_volunteer_scheduled_today_is_emailed(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role), user=user)

        assert send_daily_shift_digest() == 1
        assert mail.outbox[0].to == [user.email]

    def test_a_volunteer_with_nothing_today_is_left_alone(self, role):
        """The whole point: don't hound people who aren't scheduled."""
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role, days=3), user=user)

        assert send_daily_shift_digest() == 0
        assert mail.outbox == []

    def test_a_day_with_no_shifts_sends_nothing_at_all(self, role):
        make_user()  # a volunteer exists, just isn't on today
        make_shift(role, days=2)

        assert send_daily_shift_digest() == 0
        assert mail.outbox == []

    def test_a_cancelled_signup_does_not_count_as_being_scheduled(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role), user=user, cancelled=True)

        assert send_daily_shift_digest() == 0
        assert mail.outbox == []

    def test_yesterdays_shift_does_not_trigger_one(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role, days=-1), user=user)

        assert send_daily_shift_digest() == 0
        assert mail.outbox == []

    def test_each_volunteer_gets_their_own(self, role):
        first, second = make_user("ada"), make_user("grace")
        VolunteerSignup.objects.create(shift=make_shift(role, hour=9), user=first)
        VolunteerSignup.objects.create(shift=make_shift(role, hour=13), user=second)

        assert send_daily_shift_digest() == 2
        assert sorted(m.to[0] for m in mail.outbox) == ["ada@example.com", "grace@example.com"]


@pytest.mark.django_db
class TestOneEmailPerPerson:
    def test_two_shifts_today_is_one_email_listing_both(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role, hour=9, title="Morning desk"), user=user)
        VolunteerSignup.objects.create(shift=make_shift(role, hour=14, title="Afternoon desk"), user=user)

        assert send_daily_shift_digest() == 1
        message = mail.outbox[0]

        assert "2 DjangoCon US volunteer shifts today" in message.subject
        for body in (message.body, html_part(message)):
            assert "Morning desk" in body
            assert "Afternoon desk" in body

    def test_running_it_twice_does_not_send_twice(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role), user=user)

        assert send_daily_shift_digest() == 1
        assert send_daily_shift_digest() == 0
        assert len(mail.outbox) == 1

    def test_one_bad_address_does_not_cost_everyone_else_theirs(self, role, monkeypatch):
        good, bad = make_user("good"), make_user("bad")
        VolunteerSignup.objects.create(shift=make_shift(role, hour=9), user=good)
        VolunteerSignup.objects.create(shift=make_shift(role, hour=11), user=bad)

        real_send = __import__("volunteers.tasks", fromlist=["send_rich_email"]).send_rich_email

        def explode_for_bad(**kwargs):
            if kwargs["recipients"] == [bad.email]:
                raise OSError("rejected")
            return real_send(**kwargs)

        monkeypatch.setattr("volunteers.tasks.send_rich_email", explode_for_bad)

        assert send_daily_shift_digest() == 1
        assert [m.to for m in mail.outbox] == [[good.email]]


@pytest.mark.django_db
class TestNoPressure:
    def test_open_shifts_are_a_count_not_a_list(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role, hour=9), user=user)
        make_shift(role, hour=15, days=1, title="Unfilled tomorrow")
        make_shift(role, hour=16, days=2, title="Also unfilled")

        assert send_daily_shift_digest() == 1
        for body in (mail.outbox[0].body, html_part(mail.outbox[0])):
            assert "still open this week" in body
            assert "Unfilled tomorrow" not in body, "listing openings turns a reminder into a recruiting drive"
            assert "Also unfilled" not in body

    def test_a_full_week_says_nothing_about_openings(self, role):
        user = make_user()
        today_shift = make_shift(role, hour=9)
        VolunteerSignup.objects.create(shift=today_shift, user=user)
        filled = make_shift(role, hour=15, days=1)
        VolunteerSignup.objects.create(shift=filled, user=make_user("other"))

        assert send_daily_shift_digest() == 1
        assert "still open this week" not in mail.outbox[0].body

    def test_closed_shifts_are_not_counted_as_openings(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role, hour=9), user=user)
        closed = make_shift(role, hour=15, days=1)
        closed.signups_open = False
        closed.save(update_fields=["signups_open"])

        assert send_daily_shift_digest() == 1
        assert "still open this week" not in mail.outbox[0].body


@pytest.mark.django_db
class TestContent:
    def test_it_sends_both_parts_with_times_and_links(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role, hour=9, title="Morning desk"), user=user)

        assert send_daily_shift_digest() == 1
        message = mail.outbox[0]

        assert message.content_subtype == "plain"
        assert "<html" in html_part(message)
        for body in (message.body, html_part(message)):
            assert "Morning desk" in body
            assert "LaSalle Ballroom" in body
            assert "9:00 AM" in body
            assert "https://automation.defna.org/volunteers/mine/" in body

    def test_the_role_guide_is_offered_when_the_role_has_one(self, role):
        user = make_user()
        VolunteerSignup.objects.create(shift=make_shift(role), user=user)

        assert send_daily_shift_digest() == 1
        assert "https://handbook.example/desk" in mail.outbox[0].body
