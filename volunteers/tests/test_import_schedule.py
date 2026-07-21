from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from volunteers.models import Role, Shift

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
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--dry-run", stdout=out)

    output = out.getvalue()
    assert "Found 2 event(s)" in output
    assert "Opening Keynote" in output
    assert "Building Better APIs" in output
    assert "Would import 2 shift(s)" in output
    assert Shift.objects.count() == 0


@pytest.mark.django_db
def test_import_schedule_creates_shifts(mock_ics_response):
    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", "--role=Session Chair", stdout=out)

    output = out.getvalue()
    assert "Created 2" in output

    assert Shift.objects.count() == 2
    assert Role.objects.filter(name="Session Chair").exists()

    keynote = Shift.objects.get(external_uid="keynote@example.com")
    assert keynote.title == "Opening Keynote"
    assert keynote.location == "Main Hall"
    assert "Welcome to the conference!" in keynote.description
    assert keynote.talk_url == "https://example.com/talks/keynote/"


@pytest.mark.django_db
def test_import_schedule_idempotent(mock_ics_response):
    call_command("import_schedule", "--url=https://example.com/schedule.ics", stdout=StringIO())
    assert Shift.objects.count() == 2

    out = StringIO()
    call_command("import_schedule", "--url=https://example.com/schedule.ics", stdout=out)
    output = out.getvalue()

    assert "Created 0" in output
    assert "updated 2" in output
    assert Shift.objects.count() == 2
