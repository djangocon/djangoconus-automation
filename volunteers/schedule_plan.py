"""Work out what a schedule sync would do, before it does it.

The importer matches talks by the feed's UID, and that UID is built from the
talk's start time and title::

    UID:19-00-t0-welcome-reception@https://2026.djangocon.us

So retitling or moving a talk upstream mints a *new* UID, and the importer sees
a brand-new talk: it creates a fresh single-talk shift while the original stays
inside whatever block a coordinator merged it into. That is how duplicate slots
at the same time appear, and how someone ends up signed up for a stray single
instead of the block.

Nothing here writes. It builds a plan the dashboard can show, with the
collisions called out, so a coordinator can decide before anything changes.
"""

from __future__ import annotations

import dataclasses

from volunteers.models import Shift, Talk


@dataclasses.dataclass(frozen=True)
class PlannedTalk:
    """One event from the feed and what importing it would do."""

    uid: str
    title: str
    starts_at: object
    ends_at: object
    location: str
    action: str  # "create" or "update"
    # Set when a create would land on top of a talk we already have. This is the
    # duplicate case, and the only reason this screen exists.
    collides_with_shift: Shift | None = None
    collides_with_title: str = ""
    collision_signups: int = 0
    collision_talk_count: int = 0

    @property
    def is_duplicate(self) -> bool:
        return self.action == "create" and self.collides_with_shift is not None


@dataclasses.dataclass(frozen=True)
class MissingTalk:
    """A talk we hold that the feed no longer lists.

    Never deleted — a coordinator may have merged it into a block, and it may
    carry sign-ups. Shown so the drift is visible rather than silent.
    """

    title: str
    starts_at: object
    shift: Shift | None
    signups: int


@dataclasses.dataclass(frozen=True)
class SyncPlan:
    creates: list[PlannedTalk]
    updates: list[PlannedTalk]
    missing: list[MissingTalk]
    skipped: int

    @property
    def duplicates(self) -> list[PlannedTalk]:
        return [talk for talk in self.creates if talk.is_duplicate]

    @property
    def clean_creates(self) -> list[PlannedTalk]:
        return [talk for talk in self.creates if not talk.is_duplicate]

    @property
    def signups_at_risk(self) -> int:
        return sum(talk.collision_signups for talk in self.duplicates)

    @property
    def is_empty(self) -> bool:
        return not (self.creates or self.updates)

    @property
    def has_duplicates(self) -> bool:
        return bool(self.duplicates)


def build_plan(events, skipped: int = 0) -> SyncPlan:
    """Compare parsed feed events against what's in the database."""
    known_uids = set(Talk.objects.exclude(external_uid="").values_list("external_uid", flat=True))
    feed_uids = {event["uid"] for event in events}

    # One query for everything the feed covers, so collision lookup is in memory.
    by_start: dict[object, list[Talk]] = {}
    for talk in Talk.objects.select_related("shift").all():
        by_start.setdefault(talk.starts_at, []).append(talk)

    signups_by_shift = {
        shift.pk: shift.active_signups.count() for shift in Shift.objects.filter(talks__isnull=False).distinct()
    }
    talk_counts = {shift.pk: shift.talks.count() for shift in Shift.objects.filter(talks__isnull=False).distinct()}

    creates, updates = [], []
    for event in events:
        is_new = event["uid"] not in known_uids
        planned = {
            "uid": event["uid"],
            "title": event["summary"],
            "starts_at": event["dtstart"],
            "ends_at": event["dtend"],
            "location": event.get("location", ""),
            "action": "create" if is_new else "update",
        }

        if is_new:
            # A talk already sitting at this start time means the UID churned
            # rather than a genuinely new session appearing.
            existing = [talk for talk in by_start.get(event["dtstart"], []) if talk.shift_id]
            if existing:
                clash = existing[0]
                planned.update(
                    collides_with_shift=clash.shift,
                    collides_with_title=clash.title,
                    collision_signups=signups_by_shift.get(clash.shift_id, 0),
                    collision_talk_count=talk_counts.get(clash.shift_id, 1),
                )
            creates.append(PlannedTalk(**planned))
        else:
            updates.append(PlannedTalk(**planned))

    missing = [
        MissingTalk(
            title=talk.title,
            starts_at=talk.starts_at,
            shift=talk.shift,
            signups=signups_by_shift.get(talk.shift_id, 0),
        )
        for talk in Talk.objects.select_related("shift").exclude(external_uid="")
        if talk.external_uid not in feed_uids
    ]

    return SyncPlan(
        creates=sorted(creates, key=lambda t: t.starts_at),
        updates=sorted(updates, key=lambda t: t.starts_at),
        missing=sorted(missing, key=lambda t: t.starts_at),
        skipped=skipped,
    )
