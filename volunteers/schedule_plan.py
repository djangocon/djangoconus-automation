"""What changed in the conference schedule since we last imported it.

Read-only. Nothing here writes, and the screen it feeds has no bulk apply — the
importer matches talks by the feed's UID, and that UID encodes the start time
and title::

    UID:19-00-t0-welcome-reception@https://2026.djangocon.us

So a talk renamed or moved upstream arrives looking brand new, and a blind
import creates a second shift beside the block a coordinator already merged.
Showing the differences and linking to the admin lets a person fix the two or
three things that actually moved, instead of re-running an import that would
undo their merges.
"""

from __future__ import annotations

import dataclasses
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from volunteers.models import Shift, Talk

# Feed field -> human label, in the order a person would want to read them.
COMPARED_FIELDS = (
    ("title", "Title"),
    ("starts_at", "Starts"),
    ("ends_at", "Ends"),
    ("location", "Room"),
)


@dataclasses.dataclass(frozen=True)
class FieldChange:
    label: str
    before: object
    after: object

    @property
    def is_time(self) -> bool:
        return self.label in {"Starts", "Ends"}


@dataclasses.dataclass(frozen=True)
class NewTalk:
    """In the feed, no talk in the app with that UID."""

    title: str
    starts_at: object
    ends_at: object
    location: str
    # A shift already covering this slot means the UID churned rather than a new
    # session appearing — importing would double up on it.
    covered_by: Shift | None = None
    covered_by_talk_count: int = 0
    covered_by_signups: int = 0

    @property
    def is_probably_a_rename(self) -> bool:
        return self.covered_by is not None

    @property
    def add_url(self) -> str:
        """Admin add form, prefilled. Admin splits datetimes into _0/_1."""
        start = timezone.localtime(self.starts_at)
        end = timezone.localtime(self.ends_at)
        params = urlencode(
            {
                "title": self.title,
                "location": self.location,
                "starts_at_0": start.strftime("%Y-%m-%d"),
                "starts_at_1": start.strftime("%H:%M:%S"),
                "ends_at_0": end.strftime("%Y-%m-%d"),
                "ends_at_1": end.strftime("%H:%M:%S"),
            }
        )
        return f"{reverse('admin:volunteers_shift_add')}?{params}"

    @property
    def covered_by_edit_url(self) -> str:
        return reverse("admin:volunteers_shift_change", args=[self.covered_by.pk]) if self.covered_by else ""


@dataclasses.dataclass(frozen=True)
class ChangedTalk:
    """Same UID, but the feed now says something different."""

    talk: Talk
    changes: list[FieldChange]

    @property
    def shift(self) -> Shift | None:
        return self.talk.shift

    @property
    def edit_shift_url(self) -> str:
        return reverse("admin:volunteers_shift_change", args=[self.shift.pk]) if self.shift else ""

    @property
    def edit_talk_url(self) -> str:
        return reverse("admin:volunteers_talk_change", args=[self.talk.pk])


@dataclasses.dataclass(frozen=True)
class DroppedTalk:
    """In the app, no longer in the feed.

    Usually the other half of a rename. Never deleted automatically: it may be
    merged into a block and carry sign-ups.
    """

    talk: Talk
    signups: int

    @property
    def shift(self) -> Shift | None:
        return self.talk.shift

    @property
    def edit_shift_url(self) -> str:
        return reverse("admin:volunteers_shift_change", args=[self.shift.pk]) if self.shift else ""

    @property
    def delete_shift_url(self) -> str:
        return reverse("admin:volunteers_shift_delete", args=[self.shift.pk]) if self.shift else ""

    @property
    def delete_talk_url(self) -> str:
        return reverse("admin:volunteers_talk_delete", args=[self.talk.pk])


@dataclasses.dataclass(frozen=True)
class ScheduleDiff:
    new: list[NewTalk]
    changed: list[ChangedTalk]
    dropped: list[DroppedTalk]
    unchanged: int
    skipped: int

    @property
    def renames(self) -> list[NewTalk]:
        return [talk for talk in self.new if talk.is_probably_a_rename]

    @property
    def genuinely_new(self) -> list[NewTalk]:
        return [talk for talk in self.new if not talk.is_probably_a_rename]

    @property
    def has_changes(self) -> bool:
        return bool(self.new or self.changed or self.dropped)

    @property
    def signups_affected(self) -> int:
        return sum(talk.covered_by_signups for talk in self.renames)


def _diff_fields(talk: Talk, event: dict) -> list[FieldChange]:
    incoming = {
        "title": event["summary"],
        "starts_at": event["dtstart"],
        "ends_at": event["dtend"],
        "location": event.get("location", ""),
    }
    changes = []
    for field, label in COMPARED_FIELDS:
        before, after = getattr(talk, field), incoming[field]
        if before != after:
            changes.append(FieldChange(label=label, before=before, after=after))
    return changes


def build_diff(events, skipped: int = 0) -> ScheduleDiff:
    """Compare the feed against what's in the database. Writes nothing."""
    talks = list(Talk.objects.select_related("shift").exclude(external_uid=""))
    by_uid = {talk.external_uid: talk for talk in talks}
    feed_uids = {event["uid"] for event in events}

    by_start: dict[object, list[Talk]] = {}
    for talk in talks:
        by_start.setdefault(talk.starts_at, []).append(talk)

    shifts = Shift.objects.filter(talks__isnull=False).distinct()
    signups_by_shift = {shift.pk: shift.active_signups.count() for shift in shifts}
    talk_counts = {shift.pk: shift.talks.count() for shift in shifts}

    new, changed, unchanged = [], [], 0
    for event in events:
        talk = by_uid.get(event["uid"])
        if talk is None:
            covering = next((t for t in by_start.get(event["dtstart"], []) if t.shift_id), None)
            new.append(
                NewTalk(
                    title=event["summary"],
                    starts_at=event["dtstart"],
                    ends_at=event["dtend"],
                    location=event.get("location", ""),
                    covered_by=covering.shift if covering else None,
                    covered_by_talk_count=talk_counts.get(covering.shift_id, 0) if covering else 0,
                    covered_by_signups=signups_by_shift.get(covering.shift_id, 0) if covering else 0,
                )
            )
            continue

        diffs = _diff_fields(talk, event)
        if diffs:
            changed.append(ChangedTalk(talk=talk, changes=diffs))
        else:
            unchanged += 1

    dropped = [
        DroppedTalk(talk=talk, signups=signups_by_shift.get(talk.shift_id, 0))
        for talk in talks
        if talk.external_uid not in feed_uids
    ]

    return ScheduleDiff(
        new=sorted(new, key=lambda t: t.starts_at),
        changed=sorted(changed, key=lambda c: c.talk.starts_at),
        dropped=sorted(dropped, key=lambda d: d.talk.starts_at),
        unchanged=unchanged,
        skipped=skipped,
    )
