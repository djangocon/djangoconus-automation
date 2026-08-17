"""Show what a schedule sync would do before it does it.

The importer matches talks by the feed's UID, and that UID is built from the
talk's start time and title. A talk renamed upstream therefore arrives as a
brand-new talk and gets its own shift alongside the block a coordinator already
merged — which is how duplicate slots appeared during the 2026 conference, with
volunteers able to sign up for the wrong one.

These tests pin the screen that makes that visible, and the guard that stops the
importer running without someone having seen it.
"""

import datetime
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, Talk, VolunteerSignup
from volunteers.schedule_plan import build_plan

User = get_user_model()


@pytest.fixture
def role(db):
    return Role.objects.create(name="Session Chair")


@pytest.fixture
def coordinator(db):
    user = User.objects.create_user(username="chair", email="chair@example.com", password="pw12345!", is_staff=True)
    return user


@pytest.fixture
def staff_client(client, coordinator):
    client.force_login(coordinator)
    return client


def at(hour, *, day=24):
    return timezone.make_aware(datetime.datetime(2026, 8, day, hour, 0))


def make_talk(role, *, uid, title, hour, day=24, with_shift=True):
    start = at(hour, day=day)
    shift = None
    if with_shift:
        shift = Shift.objects.create(
            role=role, title=title, starts_at=start, ends_at=start + datetime.timedelta(minutes=30)
        )
    return Talk.objects.create(
        shift=shift,
        external_uid=uid,
        title=title,
        starts_at=start,
        ends_at=start + datetime.timedelta(minutes=30),
    )


def event(uid, title, hour, day=24, location="Sauganash Ballroom"):
    start = at(hour, day=day)
    return {
        "uid": uid,
        "summary": title,
        "dtstart": start,
        "dtend": start + datetime.timedelta(minutes=30),
        "location": location,
    }


@pytest.mark.django_db
class TestPlan:
    def test_a_known_uid_is_an_update(self, role):
        make_talk(role, uid="10-20-t0-talk@x", title="A Talk", hour=10)

        plan = build_plan([event("10-20-t0-talk@x", "A Talk", 10)])

        assert len(plan.updates) == 1
        assert plan.creates == []

    def test_an_unknown_uid_at_a_free_time_is_a_clean_create(self, role):
        plan = build_plan([event("13-50-t0-new@x", "Brand New Talk", 13)])

        assert len(plan.creates) == 1
        assert plan.clean_creates == plan.creates
        assert not plan.has_duplicates

    def test_a_churned_uid_over_an_existing_shift_is_flagged_as_a_duplicate(self, role):
        """The failure this screen exists for: retitled upstream, same slot."""
        make_talk(role, uid="15-40-t0-old-title@x", title="The Django UUID Story", hour=15)

        plan = build_plan([event("15-40-t0-new-title@x", "The Django UUID Story", 15)])

        assert plan.has_duplicates
        duplicate = plan.duplicates[0]
        assert duplicate.collides_with_title == "The Django UUID Story"
        assert plan.clean_creates == []

    def test_a_duplicate_reports_the_block_and_its_signups(self, role, coordinator):
        talk = make_talk(role, uid="15-40-t0-old@x", title="Talk", hour=15)
        VolunteerSignup.objects.create(shift=talk.shift, user=coordinator)

        plan = build_plan([event("15-40-t0-new@x", "Talk", 15)])

        duplicate = plan.duplicates[0]
        assert duplicate.collides_with_shift == talk.shift
        assert duplicate.collision_signups == 1
        assert plan.signups_at_risk == 1

    def test_cancelled_signups_are_not_counted_as_at_risk(self, role, coordinator):
        talk = make_talk(role, uid="15-40-t0-old@x", title="Talk", hour=15)
        VolunteerSignup.objects.create(shift=talk.shift, user=coordinator, cancelled=True)

        plan = build_plan([event("15-40-t0-new@x", "Talk", 15)])

        assert plan.signups_at_risk == 0

    def test_a_talk_the_feed_dropped_is_reported_but_never_deleted(self, role):
        make_talk(role, uid="09-00-t0-gone@x", title="Removed Talk", hour=9)

        plan = build_plan([event("10-20-t0-other@x", "Other", 10)])

        assert [m.title for m in plan.missing] == ["Removed Talk"]
        assert Talk.objects.filter(title="Removed Talk").exists(), "planning must not delete"

    def test_an_orphan_talk_does_not_count_as_a_collision(self, role):
        """A talk with no shift can't be duplicated — there's nothing to shadow."""
        make_talk(role, uid="15-40-t0-old@x", title="Orphan", hour=15, with_shift=False)

        plan = build_plan([event("15-40-t0-new@x", "Orphan", 15)])

        assert not plan.has_duplicates

    def test_an_empty_plan_knows_it_is_empty(self, role):
        make_talk(role, uid="10-20-t0-talk@x", title="A Talk", hour=10)
        assert build_plan([]).is_empty


@pytest.mark.django_db
class TestPreviewScreen:
    def test_it_renders_the_plan_without_writing_anything(self, staff_client, role):
        make_talk(role, uid="10-20-t0-talk@x", title="Existing Talk", hour=10)
        before = Talk.objects.count()

        with mock.patch(
            "volunteers.views.fetch_events",
            return_value=([event("13-50-t0-new@x", "Brand New Talk", 13)], 3),
        ):
            response = staff_client.get(reverse("volunteers:sync_preview"))

        assert response.status_code == 200
        body = response.content.decode()
        assert "Brand New Talk" in body
        assert Talk.objects.count() == before, "previewing must not write"

    def test_duplicates_are_called_out(self, staff_client, role):
        make_talk(role, uid="15-40-t0-old@x", title="The Django UUID Story", hour=15)

        with mock.patch(
            "volunteers.views.fetch_events",
            return_value=([event("15-40-t0-new@x", "The Django UUID Story", 15)], 0),
        ):
            body = staff_client.get(reverse("volunteers:sync_preview")).content.decode()

        assert "would duplicate a slot you already have" in body

    def test_a_dead_feed_does_not_500(self, staff_client):
        with mock.patch("volunteers.views.fetch_events", side_effect=OSError("feed is down")):
            response = staff_client.get(reverse("volunteers:sync_preview"))

        assert response.status_code == 302
        assert response.url == reverse("volunteers:dashboard")

    def test_the_preview_requires_dashboard_access(self, client, db):
        nobody = User.objects.create_user(username="nobody", email="n@example.com", password="pw12345!")
        client.force_login(nobody)

        response = client.get(reverse("volunteers:sync_preview"))

        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestApplyGuard:
    def test_applying_without_confirmation_is_refused(self, staff_client):
        with mock.patch("volunteers.views.call_command") as importer:
            response = staff_client.post(reverse("volunteers:sync_schedule"))

        importer.assert_not_called()
        assert response.url == reverse("volunteers:sync_preview")

    def test_confirming_runs_the_import(self, staff_client):
        with mock.patch("volunteers.views.call_command") as importer:
            staff_client.post(reverse("volunteers:sync_schedule"), {"confirm": "1"})

        importer.assert_called_once()
        assert importer.call_args.args[0] == "import_schedule"

    def test_rejecting_is_just_leaving_the_page(self, staff_client, role):
        """ "Reject all" is a link back to the dashboard — nothing to undo."""
        make_talk(role, uid="15-40-t0-old@x", title="Talk", hour=15)
        before = Talk.objects.count()

        with mock.patch(
            "volunteers.views.fetch_events",
            return_value=([event("15-40-t0-new@x", "Talk", 15)], 0),
        ):
            staff_client.get(reverse("volunteers:sync_preview"))

        assert Talk.objects.count() == before
