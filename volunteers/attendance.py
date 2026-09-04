"""Whether a volunteer actually holds a ticket, and which kind.

Someone volunteered without a ticket and only found out at the desk (#169), so
the coordinators need to see this before the day rather than at the door. The
answer already lives in the Ti.to webhook data — ``ticket_holders`` keeps the
most recent event per address and drops voided tickets, so a refunded ticket
correctly reads as "no ticket".
"""

from titowebhooks.reports import ticket_holders
from titowebhooks.views import EVENT_SLUG

NO_TICKET = {"has_ticket": False, "online": False, "ticket_type": ""}


def _any_ticket(title):
    """Every release counts here — we're asking "any ticket at all?"."""
    return True


def ticket_index():
    """``{email: {has_ticket, online, ticket_type}}`` for every live ticket."""
    return {
        person["Email"]: {
            "has_ticket": True,
            "online": person["Online"],
            "ticket_type": person["Ticket Type"],
        }
        for person in ticket_holders(_any_ticket, event_slug=EVENT_SLUG)
    }


def ticket_status(user, index):
    """Look one user up in a ``ticket_index()``. Unknown addresses have no ticket."""
    email = (getattr(user, "email", "") or "").strip().lower()
    return index.get(email, NO_TICKET)
