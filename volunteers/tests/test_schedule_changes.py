"""What changed in the conference feed, and nothing more.

The importer matches talks by the feed's UID, and that UID encodes the start
time and title — so a talk renamed upstream arrives looking brand new, and a
bulk import creates a second shift beside the block a coordinator merged. That
is how duplicate slots appeared during the 2026 conference.

This screen is read-only by design: it shows the differences and links them into
the admin. These tests pin that it reports the right differences and that
nothing on the volunteer side can write.
"""

import datetime
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from volunteers.models import Role, Shift, Talk, VolunteerSignup
from volunteers.schedule_plan import build_diff

User = get_user_model()

CHANGES_URL = "volunteers:schedule_changes"


@pytest.fixture
def role(db):
    return Role.objects.create(name="Session Chair")


@pytest.fixture
def coordinator(db):
    return User.objects.create_user(username="chair", email="chair@example.com", password="pw12345!", is_staff=True)


@pytest.fixture
def staff_client(client, coordinator):
    client.force_login(coordinator)
    return client


def at(hour, *, day=24, minute=0):
    return timezone.make_aware(datetime.datetime(2026, 8, day, hour, minute))


def make_talk(role, *, uid, title, hour, day=24, with_shift=True, location="Sauganash Ballroom"):
    start = at(hour, day=day)
    end = start + datetime.timedelta(minutes=30)
    shift = None
    if with_shift:
        shift = Shift.objects.create(role=role, title=title, location=location, starts_at=start, ends_at=end)
    return Talk.objects.create(
        shift=shift, external_uid=uid, title=title, location=location, starts_at=start, ends_at=end
    )


def event(uid, title, hour, day=24, minute=0, location="Sauganash Ballroom"):
    start = at(hour, day=day, minute=minute)
    return {
        "uid": uid,
        "summary": title,
        "dtstart": start,
        "dtend": start + datetime.timedelta(minutes=30),
        "location": location,
    }


@pytest.mark.django_db
class TestWhatChanged:
    def test_an_identical_talk_is_unchanged(self, role):
        make_talk(role, uid="talk@x", title="A Talk", hour=10)

        diff = build_diff([event("talk@x", "A Talk", 10)])

        assert diff.unchanged == 1
        assert not diff.has_changes

    def test_a_moved_talk_reports_the_old_and_new_time(self, role):
        make_talk(role, uid="talk@x", title="A Talk", hour=10)

        diff = build_diff([event("talk@x", "A Talk", 10, minute=30)])

        assert len(diff.changed) == 1
        labels = {change.label for change in diff.changed[0].changes}
        assert labels == {"Starts", "Ends"}
        assert diff.changed[0].changes[0].before == at(10)
        assert diff.changed[0].changes[0].after == at(10, minute=30)

    def test_a_moved_room_is_reported(self, role):
        make_talk(role, uid="talk@x", title="A Talk", hour=10)

        diff = build_diff([event("talk@x", "A Talk", 10, location="Wolf Point Ballroom")])

        change = diff.changed[0].changes[0]
        assert change.label == "Room"
        assert change.before == "Sauganash Ballroom"
        assert change.after == "Wolf Point Ballroom"

    def test_a_talk_at_a_free_slot_is_genuinely_new(self, role):
        diff = build_diff([event("new@x", "Brand New", 13)])

        assert [t.title for t in diff.genuinely_new] == ["Brand New"]
        assert diff.renames == []

    def test_a_new_uid_over_an_existing_shift_reads_as_a_rename(self, role):
        """The dangerous case — importing this would double up the slot."""
        make_talk(role, uid="old-uid@x", title="The Django UUID Story", hour=15)

        diff = build_diff([event("new-uid@x", "The Django UUID Story", 15)])

        assert len(diff.renames) == 1
        assert diff.genuinely_new == []
        assert diff.renames[0].covered_by is not None

    def test_a_rename_reports_the_signups_at_stake(self, role, coordinator):
        talk = make_talk(role, uid="old-uid@x", title="Talk", hour=15)
        VolunteerSignup.objects.create(shift=talk.shift, user=coordinator)

        diff = build_diff([event("new-uid@x", "Talk", 15)])

        assert diff.renames[0].covered_by_signups == 1
        assert diff.signups_affected == 1

    def test_cancelled_signups_are_not_counted(self, role, coordinator):
        talk = make_talk(role, uid="old-uid@x", title="Talk", hour=15)
        VolunteerSignup.objects.create(shift=talk.shift, user=coordinator, cancelled=True)

        assert build_diff([event("new-uid@x", "Talk", 15)]).signups_affected == 0

    def test_a_talk_the_feed_dropped_is_listed(self, role):
        make_talk(role, uid="gone@x", title="Removed Talk", hour=9)

        diff = build_diff([event("other@x", "Other", 10)])

        assert [d.talk.title for d in diff.dropped] == ["Removed Talk"]

    def test_an_orphan_talk_is_not_treated_as_covering_a_slot(self, role):
        make_talk(role, uid="old@x", title="Orphan", hour=15, with_shift=False)

        diff = build_diff([event("new@x", "Orphan", 15)])

        assert diff.renames == []
        assert len(diff.genuinely_new) == 1


@pytest.mark.django_db
class TestNothingIsWritten:
    def test_building_the_diff_writes_nothing(self, role):
        make_talk(role, uid="gone@x", title="Removed Talk", hour=9)
        talks, shifts = Talk.objects.count(), Shift.objects.count()

        build_diff([event("new@x", "Brand New", 13)])

        assert Talk.objects.count() == talks
        assert Shift.objects.count() == shifts

    def test_the_screen_writes_nothing(self, staff_client, role):
        make_talk(role, uid="talk@x", title="A Talk", hour=10)
        talks, shifts = Talk.objects.count(), Shift.objects.count()

        with mock.patch("volunteers.views.fetch_events", return_value=([event("new@x", "Brand New", 13)], 2)):
            response = staff_client.get(reverse(CHANGES_URL))

        assert response.status_code == 200
        assert Talk.objects.count() == talks
        assert Shift.objects.count() == shifts

    def test_there_is_no_bulk_apply_endpoint(self):
        """Confirm/deny was removed: the only route in is read-only."""
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            reverse("volunteers:sync_schedule")


@pytest.mark.django_db
class TestScreen:
    def test_it_shows_new_changed_and_dropped(self, staff_client, role):
        make_talk(role, uid="moved@x", title="Moved Talk", hour=10)
        make_talk(role, uid="gone@x", title="Vanished Talk", hour=11)

        feed = [event("moved@x", "Moved Talk", 10, minute=30), event("fresh@x", "Brand New", 13)]
        with mock.patch("volunteers.views.fetch_events", return_value=(feed, 0)):
            body = staff_client.get(reverse(CHANGES_URL)).content.decode()

        assert "Brand New" in body
        assert "Moved Talk" in body
        assert "Vanished Talk" in body

    def test_a_rename_links_to_the_existing_shift_in_the_admin(self, staff_client, role):
        talk = make_talk(role, uid="old@x", title="Renamed Talk", hour=15)

        with mock.patch("volunteers.views.fetch_events", return_value=([event("new@x", "Renamed Talk", 15)], 0)):
            body = staff_client.get(reverse(CHANGES_URL)).content.decode()

        assert reverse("admin:volunteers_shift_change", args=[talk.shift.pk]) in body
        assert "looks" in body and "renamed talk" in body

    def test_a_dropped_talk_offers_a_delete_link(self, staff_client, role):
        talk = make_talk(role, uid="gone@x", title="Vanished", hour=9)

        with mock.patch("volunteers.views.fetch_events", return_value=([], 0)):
            body = staff_client.get(reverse(CHANGES_URL)).content.decode()

        assert reverse("admin:volunteers_shift_delete", args=[talk.shift.pk]) in body

    def test_a_new_talk_offers_a_prefilled_add_link(self, staff_client, role):
        with mock.patch("volunteers.views.fetch_events", return_value=([event("new@x", "Brand New", 13)], 0)):
            body = staff_client.get(reverse(CHANGES_URL)).content.decode()

        assert reverse("admin:volunteers_shift_add") in body
        assert "Brand+New" in body or "Brand%20New" in body, "the add link should prefill the title"

    def test_no_changes_says_so(self, staff_client, role):
        make_talk(role, uid="talk@x", title="A Talk", hour=10)

        with mock.patch("volunteers.views.fetch_events", return_value=([event("talk@x", "A Talk", 10)], 0)):
            body = staff_client.get(reverse(CHANGES_URL)).content.decode()

        assert "Nothing has changed" in body

    def test_a_dead_feed_does_not_500(self, staff_client):
        with mock.patch("volunteers.views.fetch_events", side_effect=OSError("feed is down")):
            response = staff_client.get(reverse(CHANGES_URL))

        assert response.status_code == 302
        assert response.url == reverse("volunteers:dashboard")

    def test_it_requires_dashboard_access(self, client, db):
        nobody = User.objects.create_user(username="nobody", email="n@example.com", password="pw12345!")
        client.force_login(nobody)

        assert client.get(reverse(CHANGES_URL)).status_code in (302, 403)
