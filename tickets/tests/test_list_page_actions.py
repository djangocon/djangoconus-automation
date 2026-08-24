"""Resend, reissue, and issue-by-address, driven from the ticket list page."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from tickets.models import OnlineAttendee, TicketEmailLog, TicketLink

User = get_user_model()
URL = "/tickets/list/"


@pytest.fixture(autouse=True)
def no_worker():
    with patch("tickets.services.async_task") as task:
        yield task


@pytest.fixture
def staff(client):
    user = User.objects.create_superuser(username="root", email="r@example.com", password="pw12345!")
    client.force_login(user)
    return user


def make_attendee(email="ada@example.com", year=2026):
    return OnlineAttendee.objects.create(name="Ada Lovelace", email=email, year=year)


def make_link(email=None, attendee=None, superseded=False):
    link = TicketLink.objects.create(
        link="https://ti.to/example/one",
        attendee_email=email,
        attendee=attendee,
        superseded_at=timezone.now() if superseded else None,
    )
    return link


def test_the_page_needs_staff(client):
    assert client.get(URL).status_code in {302, 403}


@pytest.mark.django_db
def test_resend_queues_the_same_link_again(client, staff):
    attendee = make_attendee()
    link = make_link(email=attendee.email, attendee=attendee)

    client.post(URL, {"action": "resend", "ticket": link.pk})

    log = TicketEmailLog.objects.get()
    assert log.to_email == attendee.email
    assert log.ticket_link_id == link.pk
    assert log.sent_by_id == staff.pk


@pytest.mark.django_db
def test_a_first_send_is_not_labelled_a_resend(client, staff):
    """Holding a link is not the same as having been emailed one."""
    attendee = make_attendee()
    make_link(email=attendee.email, attendee=attendee)

    client.post(URL, {"action": "resend", "ticket": TicketLink.objects.get().pk})

    assert TicketEmailLog.objects.get().kind == TicketEmailLog.KIND_INITIAL


@pytest.mark.django_db
def test_a_second_send_is_labelled_a_resend(client, staff):
    attendee = make_attendee()
    link = make_link(email=attendee.email, attendee=attendee)
    TicketEmailLog.objects.create(
        attendee=attendee, ticket_link=link, to_email=attendee.email, status=TicketEmailLog.STATUS_SENT
    )

    client.post(URL, {"action": "resend", "ticket": link.pk})

    assert TicketEmailLog.objects.latest("pk").kind == TicketEmailLog.KIND_RESEND


@pytest.mark.django_db
def test_reissue_supersedes_the_old_link_and_mails_a_new_one(client, staff):
    attendee = make_attendee()
    old = make_link(email=attendee.email, attendee=attendee)
    spare = TicketLink.objects.create(link="https://ti.to/example/spare")

    client.post(URL, {"action": "reissue", "ticket": old.pk})

    old.refresh_from_db()
    spare.refresh_from_db()
    assert old.superseded_at is not None
    assert spare.attendee_email == attendee.email
    assert TicketEmailLog.objects.get().kind == TicketEmailLog.KIND_REISSUE


@pytest.mark.django_db
def test_reissue_without_a_spare_link_changes_nothing(client, staff):
    """Better to refuse than to strand somebody with no link at all."""
    attendee = make_attendee()
    old = make_link(email=attendee.email, attendee=attendee)

    client.post(URL, {"action": "reissue", "ticket": old.pk})

    old.refresh_from_db()
    assert old.superseded_at is None
    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_a_superseded_row_cannot_be_mailed(client, staff):
    """Its URL stopped working, so sending it would be actively unhelpful."""
    attendee = make_attendee()
    dead = make_link(email=attendee.email, attendee=attendee, superseded=True)

    client.post(URL, {"action": "resend", "ticket": dead.pk})

    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_an_unassigned_row_cannot_be_mailed(client, staff):
    link = make_link()

    client.post(URL, {"action": "resend", "ticket": link.pk})

    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_a_made_up_ticket_id_does_not_blow_up(client, staff):
    response = client.post(URL, {"action": "resend", "ticket": "not-a-number"})

    assert response.status_code == 302
    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_a_link_held_by_someone_off_the_roster_is_refused(client, staff):
    """No attendee row means no address we are confident belongs to a person."""
    make_link(email="ghost@example.com")

    client.post(URL, {"action": "resend", "ticket": TicketLink.objects.get().pk})

    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_issuing_to_a_new_address_adds_them_to_the_roster_and_mails_them(client, staff):
    """The bulk-buyer case: the person attending is not who paid."""
    TicketLink.objects.create(link="https://ti.to/example/spare")

    client.post(
        URL, {"action": "assign_by_email", "email": "Colleague@Example.com", "name": "Grace Hopper", "send_email": "on"}
    )

    attendee = OnlineAttendee.objects.get()
    assert attendee.email == "colleague@example.com"  # normalized
    assert attendee.name == "Grace Hopper"
    assert attendee.source == OnlineAttendee.SOURCE_MANUAL
    assert TicketLink.objects.get().attendee_email == "colleague@example.com"
    assert TicketEmailLog.objects.get().to_email == "colleague@example.com"


@pytest.mark.django_db
def test_issuing_without_the_email_box_ticked_sends_nothing(client, staff):
    TicketLink.objects.create(link="https://ti.to/example/spare")

    client.post(URL, {"action": "assign_by_email", "email": "quiet@example.com"})

    assert TicketLink.objects.get().attendee_email == "quiet@example.com"
    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_issuing_to_an_address_that_already_holds_a_link_does_not_burn_a_second(client, staff):
    attendee = make_attendee("dup@example.com")
    held = make_link(email=attendee.email, attendee=attendee)
    TicketLink.objects.create(link="https://ti.to/example/spare")

    client.post(URL, {"action": "assign_by_email", "email": "dup@example.com", "send_email": "on"})

    assert TicketEmailLog.objects.get().ticket_link_id == held.pk
    assert TicketLink.objects.filter(attendee_email__isnull=True, superseded_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_a_bad_address_is_rejected(client, staff):
    TicketLink.objects.create(link="https://ti.to/example/spare")

    client.post(URL, {"action": "assign_by_email", "email": "not-an-email", "send_email": "on"})

    assert not OnlineAttendee.objects.exists()
    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_an_unknown_action_does_nothing(client, staff):
    attendee = make_attendee()
    make_link(email=attendee.email, attendee=attendee)

    response = client.post(URL, {"action": "nonsense", "ticket": TicketLink.objects.get().pk})

    assert response.status_code == 302
    assert not TicketEmailLog.objects.exists()


@pytest.mark.django_db
def test_the_buttons_render_only_for_live_assigned_rows(client, staff):
    attendee = make_attendee()
    make_link(email=attendee.email, attendee=attendee)
    make_link()  # unassigned

    body = client.get(URL).content.decode()

    assert body.count('value="resend"') == 1
    assert body.count('value="reissue"') == 1
    assert "Issue a ticket to an address" in body
