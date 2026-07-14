# Volunteers

Lets signed-in attendees sign up to help run DjangoCon US. A pared-down adaptation
of the PyCon volunteer system — shifts carry their own times and capacity instead of
hanging off a full conference schedule.

## Models

- **Role** — a kind of job (Registration Desk, Room Monitor, Setup…).
- **Shift** — a single block of work: role, title, start/end, location, `capacity`,
  and a `signups_open` toggle. Exposes `filled`, `spots_left`, `is_full`, `can_sign_up()`.
- **VolunteerSignup** — one attendee claiming one shift (`unique(shift, user)`).
  `cancelled` is a soft-cancel; `reminded` tracks whether a reminder email went out.

- **CalendarToken** — per-user UUID powering an unauthenticated iCal feed.

## Flow

- `/volunteers/` — browse upcoming shifts grouped by day; sign up / cancel.
- `/volunteers/mine/` — the attendee's own shifts, total hours, and a private
  calendar-subscription URL.
- `/volunteers/dashboard/` — staff-only coverage + roster.
- `/volunteers/calendar/<token>.ics` — iCal feed of a volunteer's shifts,
  reachable by token (calendar apps can't log in). Excludes cancelled signups.

Signing up enforces three rules: shift capacity, no overlap with a shift you're
already on, and a per-person cap of `VOLUNTEER_MAX_HOURS` (default 8).

## Bulk-creating shifts

Import many shifts from a CSV (columns: `role, title, starts_at, ends_at`, plus
optional `description, location, capacity, signups_open`; datetimes are ISO 8601).
Roles are created on demand.

```
python manage.py import_shifts shifts.csv          # create
python manage.py import_shifts shifts.csv --dry-run # validate only
```

## Reminders

`volunteers.tasks.send_shift_reminders` emails volunteers whose shift starts within
24 hours (once per signup). Scheduled hourly via `Q_SCHEDULES`
(`volunteer-shift-reminders`), or run manually:

```
python manage.py send_volunteer_reminders
```

## Settings

- `VOLUNTEER_MAX_HOURS` (env, default `8`) — per-person hour cap.

## Setup

Create `Role`s and `Shift`s in the Django admin, then attendees can sign up.
