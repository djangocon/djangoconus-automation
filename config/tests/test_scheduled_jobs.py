"""What is allowed to run itself on a schedule."""

from django.conf import settings

MASS_EMAIL_TASKS = {
    # Mails every eligible attendee who has not been emailed yet.
    "tickets.tasks.send_pending_ticket_emails",
}


def test_no_mass_email_task_is_registered_as_a_schedule():
    """These stay manual on purpose.

    An entry in Q_SCHEDULES is one ``sync_schedules`` run away from being a live
    job, and that command gets run for unrelated reasons. django-q also starts a
    freshly created non-CRON schedule by firing it immediately, so adding one
    here does not merely schedule a send --- it sends. Anything that mails the
    whole roster should be a person's decision, not a side effect.
    """
    scheduled = {config["func"] for config in settings.Q_SCHEDULES.values()}

    assert not (scheduled & MASS_EMAIL_TASKS)


def test_every_schedule_names_a_real_import_path():
    """A typo here fails at run time in the worker, where nobody is watching."""
    for name, config in settings.Q_SCHEDULES.items():
        module_path, _, attr = config["func"].rpartition(".")
        module = __import__(module_path, fromlist=[attr])
        assert hasattr(module, attr), f"{name} points at {config['func']}, which does not exist"
