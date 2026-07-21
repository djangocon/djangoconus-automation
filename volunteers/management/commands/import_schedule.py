import re
import urllib.request
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from volunteers.models import Role, Shift

DEFAULT_URL = "https://2026.djangocon.us/schedule.ics"


class Command(BaseCommand):
    help = (
        "Import volunteer shifts from a DjangoCon US schedule ICS feed. "
        "Creates one shift per session with the specified role. Idempotent: "
        "existing shifts (matched by UID) are updated, not duplicated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default=DEFAULT_URL,
            help=f"URL to the ICS feed (default: {DEFAULT_URL})",
        )
        parser.add_argument(
            "--role",
            default="Session Chair",
            help="Role name for imported shifts (default: Session Chair)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and show what would be imported without writing to the database.",
        )

    def handle(self, *args, **options):
        url = options["url"]
        role_name = options["role"]
        dry_run = options["dry_run"]

        self.stdout.write(f"Fetching {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:
            raise CommandError(f"Failed to fetch ICS: {exc}") from exc

        events = self._parse_ics(raw)
        if not events:
            self.stdout.write(self.style.WARNING("No events found in feed."))
            return

        self.stdout.write(f"Found {len(events)} event(s)")

        if dry_run:
            existing = set(Shift.objects.values_list("external_uid", flat=True))
            new_count = 0
            update_count = 0
            for ev in events:
                is_new = ev["uid"] not in existing
                if is_new:
                    new_count += 1
                else:
                    update_count += 1
                label = "NEW" if is_new else "update"
                self.stdout.write(f"  [dry-run] [{label}] {ev['summary']} | {ev['dtstart']} – {ev.get('location', '')}")
            self.stdout.write(
                self.style.SUCCESS(f"Would create {new_count} new, update {update_count} existing shift(s).")
            )
            return

        role, _ = Role.objects.get_or_create(name=role_name)
        created = 0
        updated = 0

        for ev in events:
            uid = ev["uid"]
            defaults = {
                "role": role,
                "title": ev["summary"],
                "description": ev.get("description", ""),
                "location": ev.get("location", ""),
                "starts_at": ev["dtstart"],
                "ends_at": ev["dtend"],
                "talk_url": ev.get("url", ""),
            }
            shift, was_created = Shift.objects.update_or_create(
                external_uid=uid,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created}, updated {updated} shift(s)."))

    def _parse_ics(self, raw):
        """Minimal ICS parser — handles TZID datetimes and line unfolding."""
        raw = re.sub(r"\r\n[ \t]", "", raw)
        raw = raw.replace("\r\n", "\n").replace("\r", "\n")

        events = []
        current = None

        for line in raw.split("\n"):
            line = line.strip()
            if line == "BEGIN:VEVENT":
                current = {}
            elif line == "END:VEVENT":
                if current and "dtstart" in current and "dtend" in current and "summary" in current:
                    events.append(current)
                current = None
            elif current is not None:
                key, _, value = line.partition(":")
                key_lower = key.lower()

                if key_lower.startswith("dtstart"):
                    current["dtstart"] = self._parse_dt(key, value)
                elif key_lower.startswith("dtend"):
                    current["dtend"] = self._parse_dt(key, value)
                elif key_lower == "summary":
                    current["summary"] = value
                elif key_lower == "description":
                    current["description"] = self._unescape(value)
                elif key_lower == "location":
                    current["location"] = value
                elif key_lower == "uid":
                    current["uid"] = value
                elif key_lower == "url":
                    current["url"] = value

        return events

    def _parse_dt(self, key, value):
        """Parse DTSTART/DTEND with optional TZID parameter."""
        from zoneinfo import ZoneInfo

        tzid = None
        if ";" in key:
            for param in key.split(";")[1:]:
                if param.upper().startswith("TZID="):
                    tzid = param.split("=", 1)[1]

        value = value.replace("Z", "")
        if "T" in value:
            dt = datetime.strptime(value, "%Y%m%dT%H%M%S")
        else:
            dt = datetime.strptime(value, "%Y%m%d")

        if tzid:
            dt = dt.replace(tzinfo=ZoneInfo(tzid))
        else:
            dt = dt.replace(tzinfo=ZoneInfo("America/Chicago"))

        return dt

    def _unescape(self, value):
        """Unescape ICS text values."""
        return (
            value.replace("\\n", "\n")
            .replace("\\N", "\n")
            .replace("\\,", ",")
            .replace("\\;", ";")
            .replace("\\\\", "\\")
        )
