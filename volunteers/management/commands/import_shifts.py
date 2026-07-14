import csv

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import get_current_timezone, is_naive, make_aware

from volunteers.models import Role, Shift

REQUIRED_COLUMNS = {"role", "title", "starts_at", "ends_at"}


class Command(BaseCommand):
    help = (
        "Bulk-create volunteer shifts from a CSV file. "
        "Columns: role, title, starts_at, ends_at, [description], [location], "
        "[capacity], [signups_open]. Datetimes are ISO 8601 (e.g. 2026-08-26T09:00)."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the CSV file of shifts.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without writing to the database.",
        )

    def handle(self, *args, **options):
        path = options["csv_path"]
        dry_run = options["dry_run"]

        try:
            handle = open(path, newline="", encoding="utf-8")
        except OSError as exc:
            raise CommandError(f"Could not open {path}: {exc}") from exc

        created = 0
        with handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")

            tz = get_current_timezone()
            for i, row in enumerate(reader, start=2):  # header is line 1
                role_name = (row.get("role") or "").strip()
                title = (row.get("title") or "").strip()
                if not role_name or not title:
                    raise CommandError(f"Line {i}: 'role' and 'title' are required.")

                starts_at = self._parse_dt(row.get("starts_at"), i, "starts_at", tz)
                ends_at = self._parse_dt(row.get("ends_at"), i, "ends_at", tz)
                if ends_at <= starts_at:
                    raise CommandError(f"Line {i}: ends_at must be after starts_at.")

                capacity = (row.get("capacity") or "1").strip() or "1"
                try:
                    capacity = int(capacity)
                except ValueError as exc:
                    raise CommandError(f"Line {i}: capacity '{capacity}' is not an integer.") from exc

                signups_open = (row.get("signups_open") or "true").strip().lower() not in {"false", "0", "no", ""}

                if dry_run:
                    self.stdout.write(f"[dry-run] would create: {title} ({role_name}) {starts_at}–{ends_at}")
                    created += 1
                    continue

                role, _ = Role.objects.get_or_create(name=role_name)
                Shift.objects.create(
                    role=role,
                    title=title,
                    description=(row.get("description") or "").strip(),
                    location=(row.get("location") or "").strip(),
                    starts_at=starts_at,
                    ends_at=ends_at,
                    capacity=capacity,
                    signups_open=signups_open,
                )
                created += 1

        verb = "Would create" if dry_run else "Created"
        self.stdout.write(self.style.SUCCESS(f"{verb} {created} shift(s)."))

    def _parse_dt(self, value, line, field, tz):
        value = (value or "").strip()
        dt = parse_datetime(value)
        if dt is None:
            raise CommandError(f"Line {line}: could not parse {field} '{value}' (use ISO 8601, e.g. 2026-08-26T09:00).")
        if is_naive(dt):
            dt = make_aware(dt, tz)
        return dt
