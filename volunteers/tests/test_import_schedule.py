from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from volunteers.models import Role, Shift, Talk

SAMPLE_ICS = """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VTIMEZONE
TZID:America/Chicago
END:VTIMEZONE
BEGIN:VEVENT
DTSTART;TZID=America/Chicago:20260908T091500
DTEND;TZID=America/Chicago:20260908T100000
UID:keynote@example.com
SUMMARY:Opening Keynote
LOCATION:Main Hall
DESCRIPTION:Welcome to the conference!\\nEnjoy the show.
URL:https://example.com/talks/keynote/
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/Chicago:20260908T105000
DTEND;TZID=America/Chicago:20260908T113500
UID:talk-1@example.com
SUMMARY:Building Better APIs
LOCATION:Room A
DESCRIPTION:Learn about APIs.
URL:https://example.com/talks/building-better-apis/
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture
def mock_ics_response():
    def _urlopen(url, timeout=None):
        class FakeResponse:
            def read(self):
                return SAMPLE_ICS.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        return FakeResponse()

    with patch("urllib.request.urlopen", _urlopen):
        yield


@pytest.mark.django_db
def test_import_schedule_dry_run(mock_ics_response):
    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--no-skip", "--dry-run", stdout=out)

    output = out.getvalue()
    assert "Found 2 event(s)" in output
    assert "Opening Keynote" in output
    assert "Building Better APIs" in output
    assert "Would create 2 new talk(s), update 0 existing" in output
    assert "[NEW]" in output
    assert Talk.objects.count() == 0


@pytest.mark.django_db
def test_import_schedule_dry_run_reports_updates(mock_ics_response):
    # First import for real, then dry-run should report both as updates, not new.
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--no-skip", stdout=StringIO())

    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--no-skip", "--dry-run", stdout=out)
    output = out.getvalue()
    assert "Would create 0 new talk(s), update 2 existing" in output
    assert "[update]" in output


@pytest.mark.django_db
def test_import_schedule_creates_talks_and_shifts(mock_ics_response):
    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--no-skip", "--role=Session Chair", stdout=out)

    assert "Imported 2 new talk(s)" in out.getvalue()

    # Each talk gets its own single-talk sign-up shift.
    assert Talk.objects.count() == 2
    assert Shift.objects.count() == 2
    assert Role.objects.filter(name="Session Chair").exists()

    keynote = Talk.objects.get(external_uid="keynote@example.com")
    assert keynote.title == "Opening Keynote"
    assert keynote.location == "Main Hall"
    assert "Welcome to the conference!" in keynote.description
    assert keynote.talk_url == "https://example.com/talks/keynote/"
    # ...covered by a shift that mirrors the talk.
    assert keynote.shift is not None
    assert keynote.shift.title == "Opening Keynote"
    assert keynote.shift.starts_at == keynote.starts_at


@pytest.mark.django_db
def test_import_schedule_idempotent(mock_ics_response):
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--no-skip", stdout=StringIO())
    assert Talk.objects.count() == 2
    assert Shift.objects.count() == 2

    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--no-skip", stdout=out)
    output = out.getvalue()

    assert "Imported 0 new talk(s), updated 2" in output
    # No duplicate talks or shifts on re-run.
    assert Talk.objects.count() == 2
    assert Shift.objects.count() == 2


@pytest.mark.django_db
def test_import_schedule_skips_non_talks_by_default(mock_ics_response):
    # "Opening Keynote" matches the default skip list; "Building Better APIs" doesn't.
    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", stdout=out)

    assert "Skipping 1 non-talk event(s)" in out.getvalue()
    assert Talk.objects.count() == 1
    assert Talk.objects.filter(title="Building Better APIs").exists()
    assert not Talk.objects.filter(title="Opening Keynote").exists()


@pytest.mark.django_db
def test_import_schedule_custom_skip_keyword(mock_ics_response):
    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--skip-keyword=api", stdout=out)

    # Only "Building Better APIs" matches "api"; the keynote is kept (defaults overridden).
    assert Talk.objects.filter(title="Opening Keynote").exists()
    assert not Talk.objects.filter(title="Building Better APIs").exists()
