"""Re-syncing the schedule has to move a shift's room, not just its times.

A shift's location was written once, when the talk was first imported, and
never again: ``recompute_span`` refreshed starts_at/ends_at/title and left
location alone. So a room renamed upstream updated the Talk and left the Shift —
the thing volunteers actually read — pointing at the old room forever.
"""

import datetime

import pytest
from django.utils import timezone

from volunteers.models import Role, Shift, Talk

OLD_ROOM = "Sauganash Ballroom"
NEW_ROOM = "Sauganash Ballroom (West)"


@pytest.fixture
def role(db):
    return Role.objects.create(name="Session Chair")


def make_talk(shift, *, uid, location, offset_hours=10, length_hours=1, title="A Talk"):
    start = timezone.now() + datetime.timedelta(hours=offset_hours)
    return Talk.objects.create(
        shift=shift,
        external_uid=uid,
        title=title,
        location=location,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=length_hours),
    )


def make_shift(role, *, location):
    start = timezone.now() + datetime.timedelta(hours=10)
    return Shift.objects.create(
        role=role,
        title="A Talk",
        location=location,
        starts_at=start,
        ends_at=start + datetime.timedelta(hours=1),
    )


@pytest.mark.django_db
class TestLocationFollowsTheTalk:
    def test_a_renamed_room_reaches_the_shift(self, role):
        shift = make_shift(role, location=OLD_ROOM)
        talk = make_talk(shift, uid="uid-1", location=OLD_ROOM)

        # What a re-sync does: update the talk, then recompute its shift.
        talk.location = NEW_ROOM
        talk.save(update_fields=["location"])
        shift.recompute_span()

        shift.refresh_from_db()
        assert shift.location == NEW_ROOM

    def test_a_merged_shift_lists_every_room_it_covers(self, role):
        shift = make_shift(role, location=OLD_ROOM)
        make_talk(shift, uid="uid-1", location=NEW_ROOM, offset_hours=10)
        make_talk(shift, uid="uid-2", location="Wolf Point Ballroom", offset_hours=11)

        shift.recompute_span()

        shift.refresh_from_db()
        assert shift.location == f"{NEW_ROOM} / Wolf Point Ballroom"

    def test_one_room_across_several_talks_is_not_repeated(self, role):
        shift = make_shift(role, location="")
        make_talk(shift, uid="uid-1", location=NEW_ROOM, offset_hours=10)
        make_talk(shift, uid="uid-2", location=NEW_ROOM, offset_hours=11)

        shift.recompute_span()

        shift.refresh_from_db()
        assert shift.location == NEW_ROOM

    def test_a_feed_with_no_room_does_not_wipe_a_manual_one(self, role):
        """Organizers set locations by hand; a silent feed must not erase them."""
        shift = make_shift(role, location="Registration Desk")
        make_talk(shift, uid="uid-1", location="")

        shift.recompute_span()

        shift.refresh_from_db()
        assert shift.location == "Registration Desk"

    def test_shifts_with_no_talks_are_untouched(self, role):
        """Desk and manager shifts carry their own location."""
        shift = make_shift(role, location="LaSalle Ballroom")

        shift.recompute_span()

        shift.refresh_from_db()
        assert shift.location == "LaSalle Ballroom"
