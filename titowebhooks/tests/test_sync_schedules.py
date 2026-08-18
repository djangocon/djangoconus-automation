"""Registering background jobs from Q_SCHEDULES.

The map used to fall back to DAILY for anything it didn't recognise, so adding
``schedule_type: "CRON"`` — a type it had never been taught — silently produced
a daily job firing at whatever time the command happened to run. The volunteer
digest sat at 16:57 local for days looking correctly configured in settings.
These tests pin that cron works and that an unknown type fails loudly.
"""

import pytest
from django.core.management import call_command
from django_q.models import Schedule

from titowebhooks.management.commands.sync_schedules import UnknownScheduleType, _resolve_type

CRON_7AM = "0 7 * * *"


@pytest.fixture
def only_digest(settings):
    """One schedule, so a test isn't asserting against the whole roster."""
    settings.Q_SCHEDULES = {
        "volunteer-daily-digest": {
            "func": "volunteers.tasks.send_daily_shift_digest",
            "schedule_type": "CRON",
            "cron": CRON_7AM,
        }
    }
    return settings


@pytest.mark.django_db
class TestCronSchedules:
    def test_a_cron_entry_is_created_as_cron(self, only_digest):
        call_command("sync_schedules")

        schedule = Schedule.objects.get(name="volunteer-daily-digest")
        assert schedule.schedule_type == Schedule.CRON, "CRON must not silently become DAILY"
        assert schedule.cron == CRON_7AM

    def test_the_next_run_lands_at_7am_chicago(self, only_digest):
        """django-q feeds croniter timezone.localtime(), so 0 7 is 7am in TIME_ZONE.

        Asserted in Chicago rather than UTC on purpose: a UTC cron would drift an
        hour twice a year when daylight saving flips.
        """
        from django.utils.timezone import localtime

        call_command("sync_schedules")
        schedule = Schedule.objects.get(name="volunteer-daily-digest")

        assert localtime(schedule.calculate_next_run()).hour == 7

    def test_running_twice_does_not_duplicate(self, only_digest):
        call_command("sync_schedules")
        call_command("sync_schedules")

        assert Schedule.objects.filter(name="volunteer-daily-digest").count() == 1


class TestUnknownTypesFailLoudly:
    def test_an_unrecognised_type_raises(self):
        with pytest.raises(UnknownScheduleType) as exc:
            _resolve_type("some-job", {"schedule_type": "FORTNIGHTLY"})

        assert "FORTNIGHTLY" in str(exc.value)

    def test_a_typo_does_not_quietly_become_daily(self):
        """The actual failure mode: 'CRON' wasn't in the map, so it became DAILY."""
        with pytest.raises(UnknownScheduleType):
            _resolve_type("some-job", {"schedule_type": "Daily"})  # wrong case

    def test_cron_without_an_expression_raises(self):
        with pytest.raises(UnknownScheduleType) as exc:
            _resolve_type("some-job", {"schedule_type": "CRON"})

        assert "cron" in str(exc.value).lower()

    def test_known_types_still_resolve(self):
        assert _resolve_type("j", {"schedule_type": "HOURLY"}) == Schedule.HOURLY
        assert _resolve_type("j", {"schedule_type": "DAILY"}) == Schedule.DAILY
        assert _resolve_type("j", {"schedule_type": "CRON", "cron": CRON_7AM}) == Schedule.CRON
