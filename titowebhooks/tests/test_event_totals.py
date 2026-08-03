import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoHistoricalEvent, TitoTicket
from titowebhooks.views import _annotate_event_totals

User = get_user_model()

URL = "/tito/sales/"


def make_event(year=2026, sold=10, price="100.0", is_current=True):
    return TitoHistoricalEvent.objects.create(
        slug=f"djangocon-us-{year}",
        year=year,
        title=f"DjangoCon US {year}",
        is_current=is_current,
        releases=[{"title": "Individual", "tickets_count": sold, "price": price, "quantity": 100}],
    )


def make_ticket(slug, year=2026, release_price=100.0, price=100.0, voided=False):
    return TitoTicket.objects.create(
        ticket_slug=slug,
        event_slug=f"djangocon-us-{year}",
        year=year,
        release_price=release_price,
        price=price,
        voided=voided,
    )


def annotated(events=None):
    events = events if events is not None else list(TitoHistoricalEvent.objects.all())
    _annotate_event_totals(events)
    return {e.year: e for e in events}


@pytest.mark.django_db
def test_discounts_subtract_from_raised_to_give_the_total():
    make_event(sold=3, price="100.0")
    make_ticket("full", price=100.0)
    make_ticket("half", price=50.0)
    make_ticket("comp", price=0.0)

    event = annotated()[2026]

    assert event.total_revenue == 300.0  # face value, 3 x $100
    assert event.discount_total == 150.0  # $50 off one, $100 off another
    assert event.net_total == 150.0


@pytest.mark.django_db
def test_no_discounts_leaves_the_total_equal_to_raised():
    make_event(sold=2, price="100.0")
    make_ticket("a")
    make_ticket("b")

    event = annotated()[2026]

    assert event.discount_total == 0.0
    assert event.net_total == event.total_revenue


@pytest.mark.django_db
def test_year_without_ticket_detail_reports_none_not_zero():
    make_event(sold=5)

    event = annotated()[2026]

    assert event.has_ticket_detail is False
    assert event.discount_total is None
    assert event.net_total is None
    assert event.totals_partial is False


@pytest.mark.django_db
def test_voided_tickets_do_not_count_toward_discounts():
    make_event(sold=1, price="100.0")
    make_ticket("kept", price=0.0)
    make_ticket("gone", price=0.0, voided=True)

    assert annotated()[2026].discount_total == 100.0


@pytest.mark.django_db
def test_partial_sync_is_flagged():
    make_event(sold=10, price="100.0")
    make_ticket("only-one", price=0.0)

    event = annotated()[2026]

    assert event.totals_partial is True
    assert event.discounted_ticket_count == 1


@pytest.mark.django_db
def test_fully_synced_year_is_not_flagged_as_partial():
    make_event(sold=2, price="100.0")
    make_ticket("a", price=0.0)
    make_ticket("b", price=0.0)

    assert annotated()[2026].totals_partial is False


@pytest.mark.django_db
def test_each_year_gets_its_own_totals():
    make_event(year=2026, sold=1, price="100.0")
    make_event(year=2024, sold=1, price="200.0", is_current=False)
    make_ticket("new", year=2026, release_price=100.0, price=25.0)
    make_ticket("old", year=2024, release_price=200.0, price=200.0)

    events = annotated()

    assert events[2026].discount_total == 75.0
    assert events[2026].net_total == 25.0
    assert events[2024].discount_total == 0.0
    assert events[2024].net_total == 200.0


@pytest.mark.django_db
def test_dashboard_shows_discounts_and_total_for_current_and_past_years(client):
    user = User.objects.create_superuser(username="root", email="r@example.com", password="pw12345!")
    client.force_login(user)
    make_event(year=2026, sold=2, price="100.0")
    make_event(year=2024, sold=2, price="100.0", is_current=False)
    make_ticket("now", year=2026, price=0.0)
    make_ticket("then", year=2024, price=0.0)

    body = client.get(URL).content.decode()

    assert "Discounts" in body  # the current-event tile
    assert "discounts" in body  # the per-year summary line
    assert "Total" in body
