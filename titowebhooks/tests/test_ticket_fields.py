"""The /tickets API and the webhooks describe the same ticket differently."""

from titowebhooks.models import TitoTicket
from titowebhooks.sync import _ticket_fields

API_TICKET = {
    "slug": "ti_pCWGdhrd6b5",
    "reference": "AB12-1",
    "price": 749.0,
    "release_title": "Speaker",
    "release_id": 1598007,
    "discount_code_used": None,
    "state": "complete",
    "void": False,
    "created_at": "2026-03-01T12:00:00.000Z",
}

WEBHOOK_TICKET = {
    "slug": "ti_test_poZATmK8dkd",
    "reference": "S6Q7-1",
    "price": "100.0",
    "release_price": "150.0",
    "release_title": "Early Bird",
    "release": {"id": 1207019, "title": "Early Bird"},
    "discount_code_used": "",
    "state_name": "complete",
    "created_at": "2026-02-10T03:51:49.000Z",
}


def fields(payload, **kwargs):
    return _ticket_fields(payload, "djangocon-us-2026", 2026, TitoTicket.SOURCE_API, **kwargs)


def test_api_ticket_keeps_its_release_id_for_the_price_lookup():
    result = fields(API_TICKET)

    assert result["release_id"] == 1598007
    assert result["price"] == 749.0
    assert result["release_price"] == 0.0  # the API simply doesn't send it
    assert result["state_name"] == "complete"
    assert result["voided"] is False


def test_api_void_flag_is_honoured():
    result = fields({**API_TICKET, "void": True})

    assert result["voided"] is True


def test_api_state_is_read_even_though_it_is_named_differently():
    result = fields({**API_TICKET, "state": "VOID", "void": False})

    assert result["voided"] is True


def test_webhook_ticket_still_maps_its_own_shape():
    result = fields(WEBHOOK_TICKET)

    assert result["release_id"] == 1207019  # nested under "release"
    assert result["release_price"] == 150.0
    assert result["price"] == 100.0
    assert result["voided"] is False


def test_webhook_void_state_name_is_honoured():
    result = fields({**WEBHOOK_TICKET, "state_name": "voided"})

    assert result["voided"] is True


def test_missing_discount_code_normalises_to_an_empty_string():
    assert fields(API_TICKET)["discount_code"] == ""
    assert fields({**API_TICKET, "discount_code_used": "  speaker "})["discount_code"] == "speaker"


def test_ticket_without_any_identifier_is_skipped():
    assert fields({"price": 100.0}) is None
