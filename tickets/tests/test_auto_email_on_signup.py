"""Emailing a link the moment somebody buys an online ticket."""

import json
from unittest.mock import patch

import pytest
from django.test import Client

from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink, TicketRelease
from tickets.services import ensure_ticket_emailed
from tickets.tasks import email_new_online_attendee

WEBHOOK_URL = "/titowebhook/"


@pytest.fixture(autouse=True)
def no_worker():
    with patch("tickets.services.async_task") as task:
        yield task


@pytest.fixture(autouse=True)
def online_release(db):
    return TicketRelease.objects.create(title="Online- Individual", grants_venueless_access=True)


def make_attendee(email="ada@example.com", year=2026):
    return OnlineAttendee.objects.create(name="Ada Lovelace", email=email, year=year)


def make_links(n=1):
    return [TicketLink.objects.create(link=f"https://ti.to/example/{i}") for i in range(n)]


# --- the idempotent core -------------------------------------------------


@pytest.mark.django_db
def test_a_new_attendee_gets_their_link():
    make_links()
    attendee = make_attendee()

    log = ensure_ticket_emailed(attendee)

    assert log is not None
    assert attendee.active_ticket_link is not None
    assert TicketEmailLog.objects.count() == 1


@pytest.mark.django_db
def test_somebody_already_emailed_is_left_alone():
    """Ti.to retries webhooks; a retry must not mean a second link email."""
    make_links(2)
    attendee = make_attendee()
    ensure_ticket_emailed(attendee)

    assert ensure_ticket_emailed(attendee) is None
    assert TicketEmailLog.objects.count() == 1


@pytest.mark.django_db
def test_a_queued_send_also_counts_as_done():
    make_links(2)
    attendee = make_attendee()
    TicketEmailLog.objects.create(attendee=attendee, to_email=attendee.email,
                                  status=TicketEmailLog.STATUS_QUEUED)

    assert ensure_ticket_emailed(attendee) is None


@pytest.mark.django_db
def test_the_first_send_is_not_labelled_a_resend():
    make_links()
    attendee = make_attendee()

    ensure_ticket_emailed(attendee)

    assert TicketEmailLog.objects.get().kind == TicketEmailLog.KIND_INITIAL


# --- the worker task -----------------------------------------------------


@pytest.mark.django_db
def test_the_task_emails_the_attendee():
    make_links()
    attendee = make_attendee()

    assert email_new_online_attendee(attendee.pk) is True
    assert TicketEmailLog.objects.count() == 1


@pytest.mark.django_db
def test_the_task_respects_the_off_switch(settings):
    settings.TICKET_AUTO_EMAIL = False
    make_links()
    attendee = make_attendee()

    assert email_new_online_attendee(attendee.pk) is False
    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_an_empty_link_pool_fails_quietly_and_loudly(caplog):
    """Nothing to hand out; the fix is a human adding links, so it logs an error."""
    attendee = make_attendee()

    assert email_new_online_attendee(attendee.pk) is False
    assert "No ticket links left" in caplog.text


@pytest.mark.django_db
def test_a_missing_attendee_does_not_raise():
    assert email_new_online_attendee(999999) is False


# --- end to end through the webhook --------------------------------------


def post_webhook(client, payload, trigger="ticket.completed"):
    return client.post(
        WEBHOOK_URL,
        data=json.dumps(payload),
        content_type="application/json",
        headers={"x-webhook-name": trigger},
    )


def ticket_payload(email="new@example.com", release="Online- Individual"):
    return {
        "_type": "ticket",
        "slug": "ti_abc123",
        "reference": "ABC-1",
        "email": email,
        "name": "Grace Hopper",
        "release_title": release,
        "state_name": "complete",
        "created_at": "2026-08-23T12:00:00.000-05:00",
        "event": {"_type": "event", "slug": "djangocon-us-2026", "account_slug": "defna"},
    }


@pytest.mark.django_db
def test_buying_an_online_ticket_queues_the_email(settings):
    settings.TITO_SECURITY_TOKEN = ""
    make_links()

    with patch("titowebhooks.views.async_task") as queued:
        response = post_webhook(Client(), ticket_payload())

    assert response.status_code in {200, 201}
    assert OnlineAttendee.objects.filter(email="new@example.com").exists()
    assert any(call.args[0] == "tickets.tasks.email_new_online_attendee" for call in queued.call_args_list)


@pytest.mark.django_db
def test_buying_an_in_person_ticket_queues_nothing(settings):
    """Only releases flagged as granting Venueless access should trigger a send."""
    settings.TITO_SECURITY_TOKEN = ""
    make_links()

    with patch("titowebhooks.views.async_task") as queued:
        post_webhook(Client(), ticket_payload(release="Early-Bird Individual (In-person)"))

    assert not any(call.args[0] == "tickets.tasks.email_new_online_attendee" for call in queued.call_args_list)


@pytest.mark.django_db
def test_a_non_purchase_webhook_queues_nothing(settings):
    settings.TITO_SECURITY_TOKEN = ""

    with patch("titowebhooks.views.async_task") as queued:
        post_webhook(Client(), ticket_payload(), trigger="ticket.updated")

    assert not any(call.args[0] == "tickets.tasks.email_new_online_attendee" for call in queued.call_args_list)
