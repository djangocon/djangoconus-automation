"""Archive every outgoing message by BCCing it to a shared address.

Adding ``bcc=`` at each send site only covers the sites that exist today, and
the ones added later are exactly the ones nobody remembers to archive. Wrapping
the backend catches everything that goes through Django's mail plumbing --- the
ticket and volunteer emails, password resets, ``mail_admins`` --- without any
send site having to know about it.
"""

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend


class BccArchiveBackend(BaseEmailBackend):
    """Delegates to the real backend, adding the archive address to every BCC."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.connection = get_connection(
            backend=settings.EMAIL_ARCHIVE_INNER_BACKEND,
            fail_silently=fail_silently,
            **kwargs,
        )

    def send_messages(self, email_messages):
        address = getattr(settings, "EMAIL_BCC_ARCHIVE", "")
        if address:
            for message in email_messages:
                # Don't double up if the address is already a recipient - it
                # would get two copies and read as a bug in the archive.
                existing = {r.lower() for r in [*message.to, *message.cc, *message.bcc]}
                if address.lower() not in existing:
                    message.bcc = [*message.bcc, address]

        return self.connection.send_messages(email_messages)

    def open(self):
        return self.connection.open()

    def close(self):
        return self.connection.close()
