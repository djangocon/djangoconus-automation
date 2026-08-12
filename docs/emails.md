# Email templates, messages, and triggers

Every email this app sends, what it looks like, and what causes it to go out.

Staff can preview all of these rendered at **`/staff/emails/`** ("Email Previews" in the
nav). The previews are driven by the registry in `config/emails.py`; `config/tests/test_email_previews.py`
walks the repo for email templates and fails if one isn't registered, so this list and that
page can't quietly drift from the code.

## At a glance

| Email | Recipient | Trigger | Sent by |
| --- | --- | --- | --- |
| [Sign-in code](#sign-in-code) | Anyone signing in | User requests a code at `/accounts/login/code/` | allauth (inline) |
| [Password reset](#password-reset) | Anyone resetting a password | User submits `/accounts/password/reset/` | allauth (inline) |
| [Ticket link — initial](#ticket-link) | Online attendee | Staff assigns a link to an attendee who had none | django-q2 worker |
| [Ticket link — resent](#ticket-link) | Online attendee | Staff re-emails an attendee who already holds a link | django-q2 worker |
| [Ticket link — reissued](#ticket-link) | Online attendee | Staff reissues, superseding the old link | django-q2 worker |
| [Volunteer shift reminder](#volunteer-shift-reminder) | Volunteer with a shift in <24h | **Hourly schedule** | django-q2 schedule |
| [Uncovered shift alert](#uncovered-shift-alert) | `VOLUNTEER_COORDINATOR_EMAILS` | A near-term shift loses its last volunteer | django-q2 worker |

Only two of the seven are time-driven; everything else is a user or staff action.

---

## Sign-in code

- **Templates:** `templates/account/email/login_code_subject.txt`,
  `templates/account/email/login_code_message.txt` (extends
  `templates/account/email/base_message.txt`)
- **Subject:** "Your DjangoCon US sign-in code"
- **Preview slug:** `login-code`

The passwordless sign-in code — this is how nearly everyone logs in
(`ACCOUNT_LOGIN_BY_CODE_ENABLED = True`, `ACCOUNT_LOGIN_METHODS = {"email"}`). The body
carries both the 6-digit code and a one-click confirm link back to
`account_confirm_login_code`.

**Trigger:** requesting a code at `/accounts/login/code/`. `ACCOUNT_FORMS` points
`request_login_code` at `config.account_forms.AutoSignupRequestLoginCodeForm`, so an
address with no account yet gets one created rather than being rejected — meaning this mail
doubles as the signup path.

allauth builds the whole message, subject included. `ACCOUNT_EMAIL_SUBJECT_PREFIX` is `""`,
so no `[example.com]` prefix is prepended.

## Password reset

- **Templates:** `templates/account/email/password_reset_key_subject.txt` (ours);
  allauth's default body, rendered on our `base_message.txt`
- **Subject:** "Reset your DjangoCon US password"
- **Preview slug:** `password-reset`

**Trigger:** submitting the form at `/accounts/password/reset/`. Rarely used in practice
given the sign-in-code flow above.

## Ticket link

- **Templates:** `templates/tickets/email/ticket_link.txt` + `.html` (multipart; one
  template pair serves all three variants, branching on `is_resend` / `is_reissue`)
- **Sender:** `tickets/tasks.py::send_ticket_link_email`, queued by
  `tickets/services.py::queue_ticket_email` via `async_task`
- **Preview slugs:** `ticket-link-initial`, `ticket-link-resend`, `ticket-link-reissue`

Delivers the online-conference link to an attendee. Three variants, distinguished by
`TicketEmailLog.kind`, which `assign_and_email` picks automatically:

| Kind | Chosen when | Subject |
| --- | --- | --- |
| `initial` | The attendee held no link | Your DjangoCon US online conference link |
| `resend` | The attendee already had a live link | Your DjangoCon US online conference link (resent) |
| `reissue` | Called with `reissue=True`; the old link is superseded | Your new DjangoCon US online conference link |

**Triggers** — all staff actions on the online-attendees page (`tickets/views.py`), never
automatic:

- **Assign by email** (`_handle_assign_by_email`) — staff pastes an address into the box
  with *send email* checked. Unchecked assigns a link silently, with no mail.
- **Bulk action `assign_and_email`** — assign a link and mail the selected attendees.
- **Bulk action `email`** — re-send only to selected attendees who *already* hold a link;
  it skips the rest, so a nudge can't drain the link pool.
- **Bulk action `reissue`** — supersede each selected attendee's link and mail the new one.

**Delivery bookkeeping:** a `TicketEmailLog` row is written *before* the task is dispatched,
so a send that never runs still shows as `queued` on the ticket-emails dashboard
(`/tickets/emails/`) rather than vanishing. The task is idempotent — an already-`sent` log is skipped, so a
retried task won't mail somebody twice — and failures are recorded on the log rather than
raised, so one bad address doesn't kill the rest of a bulk send.

## Volunteer shift reminder

- **Template:** `volunteers/templates/volunteers/email/shift_reminder.txt` (plain text)
- **Subject:** `Reminder: your DjangoCon US volunteer shift "<shift title>"`
- **Sender:** `volunteers/tasks.py::send_shift_reminders`
- **Preview slug:** `shift-reminder`

**Trigger: scheduled.** `Q_SCHEDULES["volunteer-shift-reminders"]` runs
`volunteers.tasks.send_shift_reminders` **hourly**. Each run mails every non-cancelled,
not-yet-reminded signup whose shift starts within the next `REMINDER_WINDOW_HOURS` (24).
`VolunteerSignup.reminded` is set on send, so each signup is reminded at most once.

Because the job is hourly and the window is 24h, a volunteer who signs up *inside* the
window gets their reminder at the next hourly run, not 24h ahead.

## Uncovered shift alert

- **Template:** `volunteers/templates/volunteers/email/shift_uncovered.txt` (plain text)
- **Subject:** `DjangoCon US volunteer needed: "<shift title>" just lost its only volunteer`
- **Sender:** `volunteers/tasks.py::notify_shift_uncovered`
- **Preview slug:** `shift-uncovered`

The only email that goes to organizers rather than an attendee or volunteer.

**Trigger:** a volunteer cancels a signup. `volunteers/views.py` dispatches
`async_task("volunteers.tasks.notify_shift_uncovered", signup.pk)`. The task then bails
quietly unless *all* of these hold:

1. `VOLUNTEER_COORDINATOR_EMAILS` is non-empty — blank (the default) disables the alert.
2. The shift has no remaining active signups.
3. The shift starts within `VOLUNTEER_UNCOVERED_ALERT_WINDOW_HOURS` (default 48) and hasn't
   already started.
4. More than `VOLUNTEER_UNCOVERED_ALERT_BUFFER_MINUTES` (default 60) elapsed between signup
   and cancellation — a quick change of mind isn't worth waking anyone up.

Send failures are logged and swallowed so a broken mail server can't break the volunteer's
cancel action.

---

## Not sent by this app

**EmailOctopus** is where bulk/marketing mail lives, and it is composed and sent *there*,
not here. This repo only pushes contacts and pulls stats:

- `titowebhooks/management/commands/send_to_emailoctopus.py` — manual command; queues
  `emailoctopus.utils.send_to_emailoctopus` per `TitoWebhookEvent`, subscribing each
  address to the default `Campaign` lists. Nothing is mailed by us; subscribing is what
  eventually puts them on an EmailOctopus send.
- `Q_SCHEDULES["emailoctopus-sync-campaigns"]` — **hourly** `emailoctopus.utils.sync_campaigns`,
  read-only campaign stats sync.

`Q_SCHEDULES["travel-safety-retention-policy"]` (**daily**) sends nothing; it enforces data
retention. `travel_safety`, `thunderdome`, `titowebhooks`, and `social_monitor` store email
addresses but never send mail.

## Delivery configuration

| Setting | Source | Note |
| --- | --- | --- |
| `EMAIL_URL` | env, via `dj_email_url` | Defaults to `console://` — **local dev prints mail to stdout instead of sending**. |
| `DEFAULT_FROM_EMAIL` | env | `DjangoCon US <hello@mail.defna.org>`. Also used as `support_email` in ticket emails. |
| `SERVER_EMAIL` | env | `hello@mail.defna.org` |
| `EMAIL_TIMEOUT` | env | 10s |
| `VOLUNTEER_COORDINATOR_EMAILS` | env (list) | Empty by default; gates the uncovered-shift alert. |

Production values are set in the Coolify UI, not in version control.

Everything except the two allauth emails is delivered by the **django-q2 worker**
(`start-worker.sh`), so if mail stops flowing but logins still work, check the worker
first.

## Adding a new email

1. Add the template(s) under an app's `templates/<app>/email/` directory.
2. Send it from a task (prefer the worker over the request path).
3. Register an `EmailPreview` in `config/emails.py` — with sample context that is
   **fabricated**, never read from the database, so no attendee's name or live ticket link
   can leak onto a preview page.
4. Add a row to the table at the top of this file.

Step 3 isn't optional: `config/tests/test_email_previews.py` fails the build on any email template that
isn't registered.
