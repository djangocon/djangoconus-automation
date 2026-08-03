import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoHistoricalEvent, TitoTicket
from titowebhooks.views import _annotate_event_totals

User = get_user_model()

URL = "/tito/sales/"
RELEASE_ID = 1598009


def make_event(year=2026, sold=10, price="100.0", is_current=True, releases=None):
    if releases is None:
        releases = [{"id": RELEASE_ID, "title": "Individual", "tickets_count": sold, "price": price, "quantity": 100}]
    return TitoHistoricalEvent.objects.create(
        slug=f"djangocon-us-{year}",
        year=year,
        title=f"DjangoCon US {year}",
        is_current=is_current,
        releases=releases,
    )


def make_ticket(slug, year=2026, price=100.0, release_id=RELEASE_ID, release_price=0.0, voided=False):
    """A ticket as the /tickets API gives it to us: paid price, no release_price."""
    return TitoTicket.objects.create(
        ticket_slug=slug,
        event_slug=f"djangocon-us-{year}",
        year=year,
        release_id=release_id,
        release_price=release_price,
        price=price,
        voided=voided,
    )


def annotated(events=None):
    events = events if events is not None else list(TitoHistoricalEvent.objects.all())
    _annotate_event_totals(events)
    return {e.year: e for e in events}


@pytest.mark.django_db
def test_discount_is_face_value_minus_paid_using_the_release_list_price():
    make_event(sold=3, price="100.0")
    make_ticket("full", price=100.0)
    make_ticket("half", price=50.0)
    make_ticket("comp", price=0.0)

    event = annotated()[2026]

    assert event.discount_total == 150.0  # $50 off one, $100 off another
    assert event.collected_total == 150.0  # what actually came in


@pytest.mark.django_db
def test_discount_is_never_negative():
    """The whole reason this broke: the API omits release_price, so a naive
    face-minus-paid produced negative discounts that rendered as -$-1,234."""
    make_event(sold=1, price="100.0")
    make_ticket("api-shaped", price=749.0)  # paid more than list

    event = annotated()[2026]

    assert event.discount_total == 0.0
    assert event.discount_total >= 0
    assert event.collected_total == 749.0


@pytest.mark.django_db
def test_missing_release_price_on_the_ticket_falls_back_to_the_release():
    make_event(sold=1, price="600.0")
    make_ticket("no-price-on-ticket", price=100.0, release_price=0.0)

    assert annotated()[2026].discount_total == 500.0


@pytest.mark.django_db
def test_release_price_on_the_ticket_wins_when_present():
    make_event(sold=1, price="600.0")
    make_ticket("webhook-shaped", price=100.0, release_price=400.0)

    assert annotated()[2026].discount_total == 300.0


@pytest.mark.django_db
def test_collected_is_the_sum_of_what_was_paid_not_raised_minus_discounts():
    # Sponsor releases carry no list price, so face value can't be derived for them.
    make_event(
        sold=2,
        releases=[
            {"id": 1, "title": "Individual", "tickets_count": 1, "price": "500.0"},
            {"id": 2, "title": "Sponsor", "tickets_count": 1, "price": None},
        ],
    )
    make_ticket("individual", price=400.0, release_id=1)
    make_ticket("sponsor", price=750.0, release_id=2)

    event = annotated()[2026]

    assert event.collected_total == 1150.0  # real money, both tickets
    assert event.discount_total == 100.0  # only the priced release can be compared
    assert event.discounts_incomplete is True
    assert event.priced_ticket_count == 1


@pytest.mark.django_db
def test_unpriced_releases_do_not_count_as_free_giveaways():
    make_event(sold=1, releases=[{"id": 1, "title": "Comp", "tickets_count": 1, "price": None}])
    make_ticket("comp", price=0.0, release_id=1)

    event = annotated()[2026]

    assert event.discount_total == 0.0  # unknown face value, not a $0 face value
    assert event.discounts_incomplete is True


@pytest.mark.django_db
def test_year_without_ticket_detail_reports_none_not_zero():
    make_event(sold=5)

    event = annotated()[2026]

    assert event.has_ticket_detail is False
    assert event.discount_total is None
    assert event.collected_total is None
    assert event.totals_partial is False


@pytest.mark.django_db
def test_voided_tickets_are_excluded_from_both_figures():
    make_event(sold=1, price="100.0")
    make_ticket("kept", price=0.0)
    make_ticket("gone", price=500.0, voided=True)

    event = annotated()[2026]

    assert event.discount_total == 100.0
    assert event.collected_total == 0.0


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
    make_ticket("new", year=2026, price=25.0)
    make_ticket("old", year=2024, price=200.0)

    events = annotated()

    assert events[2026].discount_total == 75.0
    assert events[2026].collected_total == 25.0
    assert events[2024].discount_total == 0.0
    assert events[2024].collected_total == 200.0


@pytest.mark.django_db
def test_dashboard_shows_discounts_and_collected_without_a_double_negative(client):
    user = User.objects.create_superuser(username="root", email="r@example.com", password="pw12345!")
    client.force_login(user)
    make_event(year=2026, sold=2, price="100.0")
    make_event(year=2024, sold=2, price="100.0", is_current=False)
    make_ticket("now", year=2026, price=0.0)
    make_ticket("then", year=2024, price=0.0)

    body = client.get(URL).content.decode()

    assert "Discounts" in body
    assert "Collected" in body
    assert "&minus;$-" not in body
    assert "-$-" not in body
