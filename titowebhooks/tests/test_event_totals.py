import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoHistoricalEvent, TitoTicket
from titowebhooks.views import _annotate_event_totals

User = get_user_model()

URL = "/tito/sales/"


def make_event(year=2026, sold=10, price="100.0", is_current=True, releases=None):
    if releases is None:
        releases = [{"id": 1, "title": "Individual", "tickets_count": sold, "price": price, "quantity": 100}]
    return TitoHistoricalEvent.objects.create(
        slug=f"djangocon-us-{year}",
        year=year,
        title=f"DjangoCon US {year}",
        is_current=is_current,
        releases=releases,
    )


def make_ticket(slug, year=2026, price=100.0, voided=False):
    return TitoTicket.objects.create(
        ticket_slug=slug,
        event_slug=f"djangocon-us-{year}",
        year=year,
        price=price,
        voided=voided,
    )


def annotated(events=None):
    events = events if events is not None else list(TitoHistoricalEvent.objects.all())
    _annotate_event_totals(events)
    return {e.year: e for e in events}


@pytest.mark.django_db
def test_the_three_figures_reconcile():
    make_event(sold=3, price="100.0")  # raised = $300
    make_ticket("full", price=100.0)
    make_ticket("half", price=50.0)
    make_ticket("comp", price=0.0)

    event = annotated()[2026]

    assert event.total_revenue == 300.0
    assert event.revenue_total == 150.0
    assert event.discount_total == 150.0
    assert event.total_revenue - event.discount_total == event.revenue_total


@pytest.mark.django_db
def test_discount_is_the_gap_between_raised_and_revenue():
    # The shape of the real 2026 numbers: $104,637 raised, $73,655 taken in.
    make_event(sold=1, price="104637.0")
    make_ticket("a", price=73655.0)

    event = annotated()[2026]

    assert event.discount_total == 30982.0


@pytest.mark.django_db
def test_no_discount_when_everyone_paid_list():
    make_event(sold=2, price="100.0")
    make_ticket("a", price=100.0)
    make_ticket("b", price=100.0)

    event = annotated()[2026]

    assert event.discount_total == 0.0
    assert event.revenue_total == event.total_revenue


@pytest.mark.django_db
def test_discount_is_never_negative():
    """Unpriced releases sell for real money against no list price, so revenue can
    exceed face value. That is not a negative discount."""
    make_event(sold=1, releases=[{"id": 1, "title": "Sponsor", "tickets_count": 1, "price": None}])
    make_ticket("sponsor", price=750.0)

    event = annotated()[2026]

    assert event.total_revenue == 0.0  # no list price, so nothing counts toward Raised
    assert event.revenue_total == 750.0
    assert event.discount_total == 0.0
    assert event.face_value_understated is True


@pytest.mark.django_db
def test_year_without_ticket_detail_reports_none_not_zero():
    make_event(sold=5)

    event = annotated()[2026]

    assert event.has_ticket_detail is False
    assert event.discount_total is None
    assert event.revenue_total is None
    assert event.totals_partial is False


@pytest.mark.django_db
def test_voided_tickets_are_excluded_from_revenue():
    make_event(sold=1, price="100.0")
    make_ticket("kept", price=0.0)
    make_ticket("gone", price=500.0, voided=True)

    event = annotated()[2026]

    assert event.revenue_total == 0.0
    assert event.discount_total == 100.0


@pytest.mark.django_db
def test_partial_sync_is_flagged():
    make_event(sold=10, price="100.0")
    make_ticket("only-one", price=0.0)

    event = annotated()[2026]

    assert event.totals_partial is True
    assert event.ticket_detail_count == 1


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
    make_ticket("new", year=2026, price=25.0)
    make_ticket("old", year=2024, price=200.0)

    events = annotated()

    assert events[2026].discount_total == 75.0
    assert events[2026].revenue_total == 25.0
    assert events[2024].discount_total == 0.0
    assert events[2024].revenue_total == 200.0


@pytest.mark.django_db
def test_dashboard_shows_revenue_and_a_positive_discount(client):
    user = User.objects.create_superuser(username="root", email="r@example.com", password="pw12345!")
    client.force_login(user)
    make_event(year=2026, sold=2, price="100.0")
    make_event(year=2024, sold=2, price="100.0", is_current=False)
    make_ticket("now", year=2026, price=0.0)
    make_ticket("then", year=2024, price=0.0)

    body = client.get(URL).content.decode()

    assert "Revenue" in body
    assert "revenue" in body
    assert "Collected" not in body
    # Only the event summary is under test here; the discount-codes table below it
    # signs its own figures deliberately.
    summary = body.split("Discount codes")[0]
    # No hardcoded minus in front of the discount figure, and nothing like -$-1,234.
    assert "&minus;$" not in summary
    assert "-$-" not in summary
