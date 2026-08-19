from unittest.mock import patch

import pytest

from titowebhooks.models import TitoDiscountCode
from titowebhooks.sync import _discount_code_fields, sync_tito_discount_codes

SLUG = "djangocon-us-2026"


def payload(code="Wharton", tito_id=9308875, quantity=4, quantity_used=2, **extra):
    """A discount code shaped like the real /discount_codes response."""
    data = {
        "_type": "discount_code",
        "id": tito_id,
        "code": code,
        "description": "Sell for 100.0% less. 2/4 available.",
        "quantity": quantity,
        "quantity_used": quantity_used,
        "tickets_count": 2,
        "registrations_count": 1,
        "state": "current",
        "discount_code_type": "PercentOffDiscountCode",
        "type": "PercentOffDiscountCode",
        "value": "100.0",
        "share_url": f"https://ti.to/defna/{SLUG}/discount/{code}",
        "start_at": None,
        "end_at": None,
    }
    data.update(extra)
    return data


def test_flattens_a_code_into_model_fields():
    fields = _discount_code_fields(payload(), SLUG, 2026)

    assert fields["tito_id"] == 9308875
    assert fields["code"] == "Wharton"
    assert fields["quantity"] == 4
    assert fields["quantity_used"] == 2
    assert fields["value"] == 100.0
    assert fields["discount_type"] == "PercentOffDiscountCode"
    assert fields["state"] == "current"


def test_a_null_quantity_stays_none_rather_than_becoming_zero():
    """None is "no cap"; 0 would read as "none left", which is the opposite."""
    assert _discount_code_fields(payload(quantity=None), SLUG, 2026)["quantity"] is None


def test_skips_a_code_with_no_id_or_no_code():
    assert _discount_code_fields(payload(id=None), SLUG, 2026) is None
    assert _discount_code_fields(payload(code="  "), SLUG, 2026) is None


def test_parses_the_dates_tito_sends():
    fields = _discount_code_fields(payload(end_at="2026-07-31T23:59:59.000-05:00"), SLUG, 2026)

    assert fields["end_at"].year == 2026
    assert fields["end_at"].month == 7


@pytest.fixture
def credentials():
    with patch("titowebhooks.sync._get_credentials", return_value=("defna", "token")):
        yield


@pytest.mark.django_db
def test_sync_stores_codes_for_the_event(credentials):
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload()]) as fetch:
        summary = sync_tito_discount_codes(slugs=[SLUG])

    assert fetch.call_count == 1
    assert summary["created"] == 1

    code = TitoDiscountCode.objects.get()
    assert code.code == "Wharton"
    assert code.year == 2026
    assert code.remaining == 2
    assert code.unlimited is False


@pytest.mark.django_db
def test_sync_updates_an_existing_code_in_place(credentials):
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload(quantity_used=2)]):
        sync_tito_discount_codes(slugs=[SLUG])
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload(quantity_used=3)]):
        summary = sync_tito_discount_codes(slugs=[SLUG])

    assert summary["updated"] == 1
    assert TitoDiscountCode.objects.get().quantity_used == 3


@pytest.mark.django_db
def test_sync_drops_codes_tito_no_longer_has(credentials):
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload(), payload(code="gone", tito_id=42)]):
        sync_tito_discount_codes(slugs=[SLUG])
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload()]):
        summary = sync_tito_discount_codes(slugs=[SLUG])

    assert summary["deleted"] == 1
    assert [c.code for c in TitoDiscountCode.objects.all()] == ["Wharton"]


@pytest.mark.django_db
def test_a_failed_fetch_leaves_existing_codes_alone(credentials):
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload()]):
        sync_tito_discount_codes(slugs=[SLUG])
    with patch("titowebhooks.sync.get_discount_codes", return_value=None):
        summary = sync_tito_discount_codes(slugs=[SLUG])

    assert summary["failed"] == [SLUG]
    assert summary["deleted"] == 0
    assert TitoDiscountCode.objects.count() == 1


@pytest.mark.django_db
def test_sync_needs_credentials():
    with patch("titowebhooks.sync._get_credentials", return_value=(None, None)):
        assert "error" in sync_tito_discount_codes(slugs=[SLUG])


@pytest.mark.django_db
def test_codes_for_different_events_do_not_collide(credentials):
    """The unique key is (event, tito_id), so the same id in two years is fine."""
    with patch("titowebhooks.sync.get_discount_codes", return_value=[payload()]):
        sync_tito_discount_codes(slugs=[SLUG, "djangocon-us-2025"])

    assert TitoDiscountCode.objects.count() == 2


@pytest.mark.django_db
def test_remaining_never_goes_negative():
    """Ti.to lets an organizer lower a cap below what is already redeemed."""
    code = TitoDiscountCode(event_slug=SLUG, year=2026, tito_id=1, code="X", quantity=2, quantity_used=5)

    assert code.remaining == 0
    assert code.used_up is True


@pytest.mark.django_db
def test_discount_labels_read_the_way_tito_writes_them():
    percent = TitoDiscountCode(discount_type="PercentOffDiscountCode", value=10.0)
    money = TitoDiscountCode(discount_type="MoneyOffDiscountCode", value=60.0)

    assert percent.discount_label == "10% off"
    assert money.discount_label == "$60 off"
