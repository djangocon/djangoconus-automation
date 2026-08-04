import pytest
from django.core import mail

from tickets.models import TicketEmailLog
from tickets.services import assign_link
from tickets.tasks import send_ticket_link_email


@pytest.fixture
def log(ticket_links, attendee):
    link = assign_link(attendee.email, attendee=attendee)
    return TicketEmailLog.objects.create(
        attendee=attendee,
        ticket_link=link,
        to_email=attendee.email,
        kind=TicketEmailLog.KIND_INITIAL,
    )


@pytest.mark.django_db
def test_send_delivers_branded_html_and_text(log):
    assert send_ticket_link_email(log.pk) is True

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["online@example.com"]
    assert "DjangoCon US" in message.subject
    assert log.ticket_link.link in message.body

    html_body, content_type = message.alternatives[0]
    assert content_type == "text/html"
    assert log.ticket_link.link in html_body
    assert "Online Buyer" in html_body

    log.refresh_from_db()
    assert log.status == TicketEmailLog.STATUS_SENT
    assert log.date_sent is not None
    assert log.subject == message.subject


@pytest.mark.django_db
def test_send_is_not_repeated_for_an_already_sent_log(log):
    send_ticket_link_email(log.pk)
    assert send_ticket_link_email(log.pk) is False
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_send_records_failure_instead_of_raising(log, monkeypatch):
    def boom(self, *args, **kwargs):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", boom)

    assert send_ticket_link_email(log.pk) is False

    log.refresh_from_db()
    assert log.status == TicketEmailLog.STATUS_FAILED
    assert "smtp exploded" in log.error


@pytest.mark.django_db
def test_send_fails_cleanly_when_the_link_is_gone(log):
    log.ticket_link.delete()
    log.refresh_from_db()

    assert send_ticket_link_email(log.pk) is False
    log.refresh_from_db()
    assert log.status == TicketEmailLog.STATUS_FAILED
    assert not mail.outbox


@pytest.mark.django_db
def test_reissue_copy_warns_the_old_link_is_dead(log):
    log.kind = TicketEmailLog.KIND_REISSUE
    log.save(update_fields=["kind"])

    send_ticket_link_email(log.pk)

    assert "no longer works" in mail.outbox[0].body
