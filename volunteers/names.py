"""Putting a name to a volunteer.

Most accounts are created by ``AutoSignupRequestLoginCodeForm`` from nothing but
an email address, so ``first_name``/``last_name`` are usually empty and the
dashboard could only ever show the address. Ti.to already knows what attendees
are called, so the name is filled in from their ticket rather than asked for a
second time; volunteers who never bought a ticket can type one in themselves.
"""

from titowebhooks.models import TitoWebhookEvent


def display_name(user):
    """What to call this person on screen.

    Falls back to the email rather than the username: usernames are derived from
    the address ("jeff@example.com" -> "jeff"), so showing one loses information
    without gaining readability.
    """
    if user is None:
        return ""
    return user.get_full_name().strip() or (user.email or "").strip() or user.get_username()


def ticket_names():
    """``{email: (first_name, last_name)}`` for every attendee Ti.to named.

    Later events win — someone who corrects their name on a second ticket should
    show up under the corrected one.
    """
    names = {}
    for event in TitoWebhookEvent.objects.order_by("timestamp").iterator():
        payload = event.payload or {}
        email = (payload.get("email") or "").strip().lower()
        first = (payload.get("first_name") or "").strip()
        last = (payload.get("last_name") or "").strip()
        if email and (first or last):
            names[email] = (first, last)
    return names


def fill_missing_name(user, names=None):
    """Fill a blank name from the user's Ti.to ticket. Returns True if it did.

    Never overwrites a name that is already set — someone who typed their own
    name, or corrected the one from their ticket, keeps it. Pass ``names`` to
    reuse one ``ticket_names()`` lookup across many users.
    """
    if user.first_name or user.last_name:
        return False

    email = (user.email or "").strip().lower()
    if not email:
        return False

    if names is None:
        names = ticket_names()

    match = names.get(email)
    if not match:
        return False

    user.first_name, user.last_name = match
    user.save(update_fields=["first_name", "last_name"])
    return True
