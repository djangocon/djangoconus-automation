"""The archive BCC that every outgoing message picks up."""

import pytest
from django.core import mail
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection, send_mail

BACKEND = "config.email_backends.BccArchiveBackend"
INNER = "django.core.mail.backends.locmem.EmailBackend"
ARCHIVE = "infrastructure@defna.org"


@pytest.fixture
def archiving(settings):
    """Wire the wrapper around locmem so sends land in mail.outbox."""
    settings.EMAIL_ARCHIVE_INNER_BACKEND = INNER
    settings.EMAIL_BCC_ARCHIVE = ARCHIVE
    settings.EMAIL_BACKEND = BACKEND
    mail.outbox = []
    return settings


def send(message, connection=None):
    message.connection = connection or get_connection(backend=BACKEND)
    message.send()
    return mail.outbox[-1]


def test_every_message_picks_up_the_archive_address(archiving):
    sent = send(EmailMessage(subject="Hi", body="b", from_email="f@x.com", to=["a@example.com"]))

    assert sent.bcc == [ARCHIVE]
    assert ARCHIVE in sent.recipients()


def test_the_archive_is_a_bcc_not_a_visible_header(archiving):
    """A visible recipient would expose the archive to every attendee."""
    sent = send(EmailMessage(subject="Hi", body="b", from_email="f@x.com", to=["a@example.com"]))

    assert sent.to == ["a@example.com"]
    assert sent.cc == []
    assert "Bcc" not in sent.message()


def test_an_existing_bcc_is_kept(archiving):
    sent = send(EmailMessage(subject="Hi", body="b", from_email="f@x.com", to=["a@x.com"], bcc=["b@x.com"]))

    assert sent.bcc == ["b@x.com", ARCHIVE]


@pytest.mark.parametrize("field", ["to", "cc", "bcc"])
def test_the_address_is_not_added_twice(archiving, field):
    """It would arrive twice and read as a bug in the archive."""
    sent = send(EmailMessage(subject="Hi", body="b", from_email="f@x.com", **{field: [ARCHIVE]}))

    assert sent.recipients().count(ARCHIVE) == 1


def test_matching_ignores_case(archiving):
    sent = send(EmailMessage(subject="Hi", body="b", from_email="f@x.com", to=["INFRASTRUCTURE@DEFNA.ORG"]))

    assert sent.bcc == []


def test_html_alternatives_survive_the_wrapper(archiving):
    message = EmailMultiAlternatives(subject="Hi", body="text", from_email="f@x.com", to=["a@x.com"])
    message.attach_alternative("<p>html</p>", "text/html")

    sent = send(message)

    assert sent.bcc == [ARCHIVE]
    assert sent.alternatives[0][0] == "<p>html</p>"


def test_send_mail_goes_through_the_wrapper_too(archiving):
    send_mail("Hi", "b", "f@x.com", ["a@x.com"], connection=get_connection(backend=BACKEND))

    assert mail.outbox[-1].bcc == [ARCHIVE]


def test_a_blank_archive_address_leaves_messages_alone(archiving):
    archiving.EMAIL_BCC_ARCHIVE = ""

    sent = send(EmailMessage(subject="Hi", body="b", from_email="f@x.com", to=["a@x.com"]))

    assert sent.bcc == []


def test_settings_ship_the_archive_address_by_default():
    """The whole point is that no send site has to opt in.

    EMAIL_BACKEND itself can't be asserted here: Django's test setup replaces it
    with locmem for the whole run, so it never reads as the wrapper no matter
    what settings.py says. The wiring is checked out of band instead --- see the
    settings block that picks the wrapper whenever this address is non-empty.
    """
    from django.conf import settings as real

    assert real.EMAIL_BCC_ARCHIVE == ARCHIVE
    assert real.EMAIL_ARCHIVE_INNER_BACKEND


def test_sending_several_messages_archives_each_one(archiving):
    connection = get_connection(backend=BACKEND)
    messages = [
        EmailMessage(subject=f"{i}", body="b", from_email="f@x.com", to=[f"a{i}@x.com"], connection=connection)
        for i in range(3)
    ]

    connection.send_messages(messages)

    assert [m.bcc for m in mail.outbox] == [[ARCHIVE]] * 3
