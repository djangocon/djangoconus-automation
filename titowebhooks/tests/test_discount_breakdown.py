import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoDiscountCode, TitoHistoricalEvent, TitoTicket
from titowebhooks.views import EVENT_SLUG, _discount_breakdown

User = get_user_model()

RELEASES = [
    {"id": 1, "title": "Individual", "price": "100.0"},
    {"id": 2, "title": "Corporate", "price": "200.0"},
    {"id": 3, "title": "Sponsor", "price": None},
]


@pytest.fixture(autouse=True)
def event():
    """Every case needs the release list - it is where face value comes from."""
    return TitoHistoricalEvent.objects.create(
        slug=EVENT_SLUG,
        year=2026,
        title="DjangoCon US 2026",
        is_current=True,
        releases=RELEASES,
    )


def make_ticket(
    slug,
    code="",
    release_id=1,
    release_title="Individual",
    price=100.0,
    release_price=0.0,
    voided=False,
    event_slug=EVENT_SLUG,
):
    """A ticket as the /tickets API gives it to us: no release_price on the row."""
    return TitoTicket.objects.create(
        ticket_slug=slug,
        event_slug=event_slug,
        year=int(event_slug.rsplit("-", 1)[-1]),
        discount_code=code,
        release_id=release_id,
        release_title=release_title,
        release_price=release_price,
        price=price,
        voided=voided,
    )


def make_code(code, quantity=10, quantity_used=0, tito_id=None, state="current", value=100.0, event_slug=EVENT_SLUG):
    return TitoDiscountCode.objects.create(
        event_slug=event_slug,
        year=int(event_slug.rsplit("-", 1)[-1]),
        tito_id=tito_id if tito_id is not None else abs(hash(code)) % 10_000_000,
        code=code,
        discount_type="PercentOffDiscountCode",
        value=value,
        quantity=quantity,
        quantity_used=quantity_used,
        state=state,
    )


def row_for(breakdown, code):
    return next(row for row in breakdown["rows"] if row["code"] == code)


@pytest.mark.django_db
def test_no_tickets_and_no_codes_reports_no_data():
    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["has_data"] is False
    assert breakdown["rows"] == []
    assert breakdown["total_discount"] == 0
    assert breakdown["has_code_data"] is False


@pytest.mark.django_db
def test_groups_tickets_by_code_and_totals_the_discount():
    make_ticket("t1", code="SPEAKER", price=0.0)
    make_ticket("t2", code="SPEAKER", price=0.0)
    make_ticket("t3", code="EARLY25", price=75.0)

    breakdown = _discount_breakdown(EVENT_SLUG)

    speaker = row_for(breakdown, "SPEAKER")
    assert speaker["count"] == 2
    assert speaker["face_value"] == 200.0
    assert speaker["paid"] == 0.0
    assert speaker["discount"] == 200.0

    assert row_for(breakdown, "EARLY25")["discount"] == 25.0
    assert breakdown["code_count"] == 2
    assert breakdown["discounted_tickets"] == 3
    assert breakdown["total_discount"] == 225.0


@pytest.mark.django_db
def test_face_value_comes_from_the_release_when_the_ticket_has_no_price():
    make_ticket("t1", code="SPEAKER", release_id=2, release_title="Corporate", price=0.0)

    assert row_for(_discount_breakdown(EVENT_SLUG), "SPEAKER")["face_value"] == 200.0


@pytest.mark.django_db
def test_a_price_on_the_ticket_wins_over_the_release_lookup():
    """Webhook-sourced rows carry their own release_price; trust it over ours."""
    make_ticket("t1", code="SPEAKER", release_price=499.0, price=0.0)

    assert row_for(_discount_breakdown(EVENT_SLUG), "SPEAKER")["face_value"] == 499.0


@pytest.mark.django_db
def test_releases_with_no_list_price_contribute_no_face_value():
    make_ticket("t1", code="revsys", release_id=3, release_title="Sponsor", price=0.0)

    row = row_for(_discount_breakdown(EVENT_SLUG), "revsys")
    assert row["face_value"] == 0.0
    assert row["discount"] == 0.0


@pytest.mark.django_db
def test_tickets_without_a_code_get_their_own_row_pinned_last():
    make_ticket("t1", code="SPEAKER", price=0.0)
    make_ticket("t2")

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert [row["code"] for row in breakdown["rows"]] == ["SPEAKER", ""]
    assert row_for(breakdown, "")["count"] == 1
    assert breakdown["discounted_tickets"] == 1


@pytest.mark.django_db
def test_voided_tickets_are_dropped():
    make_ticket("t1", code="SPEAKER", price=0.0)
    make_ticket("t2", code="SPEAKER", price=0.0, voided=True)

    assert row_for(_discount_breakdown(EVENT_SLUG), "SPEAKER")["count"] == 1


@pytest.mark.django_db
def test_ignores_tickets_from_other_events():
    make_ticket("t1", code="SPEAKER", price=0.0)
    make_ticket("t2", code="SPEAKER", price=0.0, event_slug="djangocon-us-2019")

    assert _discount_breakdown(EVENT_SLUG)["total_tickets"] == 1


@pytest.mark.django_db
def test_collects_the_release_titles_a_code_was_used_on():
    make_ticket("t1", code="SPEAKER", release_id=1, release_title="Individual", price=0.0)
    make_ticket("t2", code="SPEAKER", release_id=2, release_title="Corporate", price=0.0)
    make_ticket("t3", code="SPEAKER", release_id=1, release_title="Individual", price=0.0)

    assert row_for(_discount_breakdown(EVENT_SLUG), "SPEAKER")["releases"] == ["Corporate", "Individual"]


@pytest.mark.django_db
def test_an_issued_code_nobody_used_still_gets_a_row():
    make_code("BUTTONDOWN", quantity=4)

    breakdown = _discount_breakdown(EVENT_SLUG)
    row = row_for(breakdown, "BUTTONDOWN")

    assert row["count"] == 0
    assert row["issued"] == 4
    assert row["redeemed"] == 0
    assert row["remaining"] == 4
    assert row["unused"] is True
    assert breakdown["unused_code_count"] == 1
    assert breakdown["has_code_data"] is True


@pytest.mark.django_db
def test_availability_is_joined_onto_the_redeemed_row():
    make_code("Wharton", quantity=4, quantity_used=2)
    make_ticket("t1", code="Wharton", price=0.0)
    make_ticket("t2", code="Wharton", price=0.0)

    row = row_for(_discount_breakdown(EVENT_SLUG), "Wharton")

    assert row["count"] == 2
    assert row["issued"] == 4
    assert row["remaining"] == 2
    assert row["unused"] is False
    assert row["used_up"] is False


@pytest.mark.django_db
def test_the_join_ignores_case_and_keeps_titos_spelling():
    make_code("Wharton", quantity=4, quantity_used=1)
    make_ticket("t1", code="wharton", price=0.0)

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert [row["code"] for row in breakdown["rows"]] == ["Wharton"]
    assert row_for(breakdown, "Wharton")["count"] == 1


@pytest.mark.django_db
def test_a_fully_redeemed_code_reads_as_used_up():
    make_code("foxley", quantity=1, quantity_used=1)

    row = row_for(_discount_breakdown(EVENT_SLUG), "foxley")

    assert row["remaining"] == 0
    assert row["used_up"] is True
    assert row["unused"] is False


@pytest.mark.django_db
def test_an_uncapped_code_reports_no_remaining_count():
    make_code("DJANGONEWS", quantity=None, quantity_used=2)

    breakdown = _discount_breakdown(EVENT_SLUG)
    row = row_for(breakdown, "DJANGONEWS")

    assert row["unlimited"] is True
    assert row["issued"] is None
    assert row["remaining"] is None
    assert breakdown["uncapped_code_count"] == 1
    # Uncapped codes can't contribute to a remaining total without inventing a number.
    assert breakdown["total_remaining"] == 0
    assert breakdown["total_issued"] == 0


@pytest.mark.django_db
def test_a_code_redeemed_but_no_longer_in_tito_is_flagged_unknown():
    make_ticket("t1", code="DELETEDCODE", price=0.0)

    row = row_for(_discount_breakdown(EVENT_SLUG), "DELETEDCODE")

    assert row["known"] is False
    assert row["issued"] is None
    assert row["remaining"] is None


@pytest.mark.django_db
def test_redemptions_tito_counted_beat_our_ticket_count_for_unused():
    """Ti.to counts redemptions against the cap; tickets carrying the code are a
    different number. A code Ti.to says was redeemed is not "unused" just because
    no ticket of ours shows it."""
    make_code("speaker", quantity=50, quantity_used=24)

    row = row_for(_discount_breakdown(EVENT_SLUG), "speaker")

    assert row["count"] == 0
    assert row["redeemed"] == 24
    assert row["unused"] is False


@pytest.mark.django_db
def test_unused_codes_sort_after_redeemed_ones_and_before_the_no_code_row():
    make_code("USED", quantity=10, quantity_used=1)
    make_code("NEVER", quantity=10)
    make_ticket("t1", code="USED", price=0.0)
    make_ticket("t2")

    assert [row["code"] for row in _discount_breakdown(EVENT_SLUG)["rows"]] == ["USED", "NEVER", ""]


@pytest.mark.django_db
def test_ignores_codes_from_other_events():
    make_code("OTHER", event_slug="djangocon-us-2019")

    assert _discount_breakdown(EVENT_SLUG)["rows"] == []


@pytest.mark.django_db
def test_totals_add_up_across_capped_and_uncapped_codes():
    make_code("A", quantity=10, quantity_used=4)
    make_code("B", quantity=5, quantity_used=5)
    make_code("C", quantity=None, quantity_used=3)

    breakdown = _discount_breakdown(EVENT_SLUG)

    assert breakdown["issued_code_count"] == 3
    assert breakdown["total_issued"] == 15
    assert breakdown["total_redeemed"] == 12
    assert breakdown["total_remaining"] == 6


@pytest.mark.django_db
def test_the_dashboard_renders_availability_next_to_usage(client):
    user = User.objects.create_superuser(username="root", email="r@example.com", password="pw12345!")
    client.force_login(user)
    make_code("Wharton", quantity=4, quantity_used=2)
    make_code("button-down", quantity=4)
    make_ticket("t1", code="Wharton", price=0.0)

    body = client.get("/tito/sales/").content.decode()

    assert "Used / issued" in body
    assert "Wharton" in body
    # The code nobody has touched shows up at all, which is the point of the join.
    assert "button-down" in body
    assert "unused" in body
    assert "2 code" in body or "2 codes" in body
