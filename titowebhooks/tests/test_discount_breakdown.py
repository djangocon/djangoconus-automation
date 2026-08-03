import pytest

from titowebhooks.models import TitoWebhookEvent
from titowebhooks.views import EVENT_SLUG, _discount_breakdown


def make_ticket(
    slug,
    code="",
    release_price="100.0",
    price=None,
    trigger="ticket.completed",
    release_title="Individual",
    event_slug=EVENT_SLUG,
    state_name="complete",
):
    """Build a Ti.to ticket webhook event shaped like the real payloads."""
    payload = {
        "_type": "ticket",
        "slug": slug,
        "reference": slug.upper(),
        "state_name": state_name,
        "release_price": release_price,
        "price": release_price if price is None else price,
        "discount_code_used": code,
        "release_title": release_title,
        "event": {"_type": "event", "slug": event_slug, "account_slug": "defna"},
    }
    return TitoWebhookEvent.objects.create(trigger=trigger, payload=payload, payload_text="")


def row_for(breakdown, code):
    return next(row for row in breakdown["rows"] if row["code"] == code)


@pytest.mark.django_db
def test_no_tickets_reports_no_data():
    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["has_data"] is False
    assert breakdown["rows"] == []
    assert breakdown["total_discount"] == 0


@pytest.mark.django_db
def test_groups_tickets_by_code_and_totals_the_discount():
    make_ticket("t1", code="SPEAKER", price="0.0")
    make_ticket("t2", code="SPEAKER", price="0.0")
    make_ticket("t3", code="EARLY25", price="75.0")

    breakdown = _discount_breakdown(EVENT_SLUG)

    speaker = row_for(breakdown, "SPEAKER")
    assert speaker["count"] == 2
    assert speaker["face_value"] == 200.0
    assert speaker["paid"] == 0.0
    assert speaker["discount"] == 200.0

    early = row_for(breakdown, "EARLY25")
    assert early["count"] == 1
    assert early["discount"] == 25.0

    assert breakdown["code_count"] == 2
    assert breakdown["discounted_tickets"] == 3
    assert breakdown["total_discount"] == 225.0


@pytest.mark.django_db
def test_tickets_without_a_code_get_their_own_row_pinned_last():
    make_ticket("t1", code="SPEAKER", price="0.0")
    make_ticket("t2")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert [row["code"] for row in breakdown["rows"]] == ["SPEAKER", ""]
    no_code = row_for(breakdown, "")
    assert no_code["count"] == 1
    assert no_code["discount"] == 0.0
    assert breakdown["total_tickets"] == 2
    assert breakdown["discounted_tickets"] == 1


@pytest.mark.django_db
def test_counts_each_ticket_once_using_the_latest_webhook():
    make_ticket("t1", code="SPEAKER", price="0.0")
    make_ticket("t1", code="SPEAKER", price="0.0", trigger="ticket.updated")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["total_tickets"] == 1
    assert row_for(breakdown, "SPEAKER")["count"] == 1


@pytest.mark.django_db
def test_drops_tickets_whose_latest_event_voided_them():
    make_ticket("t1", code="SPEAKER", price="0.0")
    make_ticket("t1", code="SPEAKER", price="0.0", trigger="ticket.voided")
    make_ticket("t2", code="SPEAKER", price="0.0")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["total_tickets"] == 1
    assert row_for(breakdown, "SPEAKER")["count"] == 1


@pytest.mark.django_db
def test_keeps_a_ticket_that_was_voided_then_reinstated():
    make_ticket("t1", code="SPEAKER", price="0.0", trigger="ticket.voided")
    make_ticket("t1", code="SPEAKER", price="0.0", trigger="ticket.updated")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["total_tickets"] == 1


@pytest.mark.django_db
def test_ignores_tickets_from_other_events():
    make_ticket("t1", code="SPEAKER", price="0.0")
    make_ticket("t2", code="SPEAKER", price="0.0", event_slug="djangocon-us-2019")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["total_tickets"] == 1


@pytest.mark.django_db
def test_collects_the_release_titles_a_code_was_used_on():
    make_ticket("t1", code="SPEAKER", price="0.0", release_title="Individual")
    make_ticket("t2", code="SPEAKER", price="0.0", release_title="Corporate")
    make_ticket("t3", code="SPEAKER", price="0.0", release_title="Individual")

    assert row_for(_discount_breakdown(EVENT_SLUG), "SPEAKER")["releases"] == ["Corporate", "Individual"]


@pytest.mark.django_db
def test_survives_missing_and_unparseable_prices():
    make_ticket("t1", code="SPEAKER", release_price=None, price=None)
    make_ticket("t2", code="SPEAKER", release_price="not-a-number", price="0.0")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert row_for(breakdown, "SPEAKER")["face_value"] == 0.0
    assert breakdown["total_discount"] == 0.0
