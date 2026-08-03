import datetime

import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoHistoricalEvent, TitoTicket
from titowebhooks.sales_curve import CHECKPOINTS, sales_curves

User = get_user_model()

URL = "/tito/sales/"
START = datetime.date(2026, 9, 15)


def make_event(year=2026, start_date=START, is_current=True, **extra):
    return TitoHistoricalEvent.objects.create(
        slug=f"djangocon-us-{year}",
        year=year,
        title=f"DjangoCon US {year}",
        start_date=start_date,
        is_current=is_current,
        releases=extra.get("releases"),
    )


def make_ticket(slug, year=2026, days_out=30, price=100.0, voided=False, created_at=None):
    """A ticket bought `days_out` days before the 2026 start date."""
    if created_at is None and days_out is not None:
        created_at = datetime.datetime.combine(
            START - datetime.timedelta(days=days_out),
            datetime.time(12, 0),
            tzinfo=datetime.timezone.utc,
        )
    return TitoTicket.objects.create(
        ticket_slug=slug,
        event_slug=f"djangocon-us-{year}",
        year=year,
        price=price,
        release_price=price,
        voided=voided,
        created_at=created_at,
    )


def at(series, days_out):
    """The cumulative pair recorded at a given checkpoint."""
    index = CHECKPOINTS.index(days_out)
    return series["tickets"][index], series["revenue"][index]


@pytest.mark.django_db
def test_no_events_reports_no_data():
    curves = sales_curves()

    assert curves["has_data"] is False
    assert curves["series"] == []
    assert curves["charts"] == []


@pytest.mark.django_db
def test_cumulative_counts_climb_toward_the_event():
    make_event()
    make_ticket("early", days_out=200)
    make_ticket("mid", days_out=45)
    make_ticket("late", days_out=2)

    series = sales_curves()["series"][0]

    assert at(series, 210) == (0, 0)  # nothing sold that far out
    assert at(series, 180) == (1, 100)  # the 200-days-out ticket has landed
    assert at(series, 30) == (2, 200)  # plus the 45-days-out one
    assert at(series, 0) == (3, 300)  # everything by event day


@pytest.mark.django_db
def test_final_totals_match_the_last_checkpoint():
    make_event()
    make_ticket("a", days_out=90, price=250.0)
    make_ticket("b", days_out=10, price=150.0)

    series = sales_curves()["series"][0]

    assert series["final_tickets"] == 2
    assert series["final_revenue"] == 400.0
    assert (series["final_tickets"], series["final_revenue"]) == at(series, 0)


@pytest.mark.django_db
def test_revenue_uses_paid_price_not_face_value():
    make_event()
    make_ticket("comped", days_out=30, price=0.0)
    make_ticket("full", days_out=30, price=500.0)

    assert sales_curves()["series"][0]["final_revenue"] == 500.0


@pytest.mark.django_db
def test_voided_tickets_are_excluded():
    make_event()
    make_ticket("good", days_out=30)
    make_ticket("gone", days_out=30, voided=True)

    assert sales_curves()["series"][0]["final_tickets"] == 1


@pytest.mark.django_db
def test_tickets_without_a_purchase_date_are_skipped():
    make_event()
    make_ticket("dated", days_out=30)
    make_ticket("undated", days_out=None, created_at=None)

    assert sales_curves()["series"][0]["final_tickets"] == 1


@pytest.mark.django_db
def test_sales_after_the_event_starts_clamp_to_day_zero():
    make_event()
    make_ticket("walkin", days_out=-3)

    series = sales_curves()["series"][0]

    assert at(series, 0) == (1, 100)
    assert at(series, 3) == (0, 0)


@pytest.mark.django_db
def test_years_without_a_start_date_are_reported_as_missing():
    make_event(year=2026)
    make_event(year=2019, start_date=None, is_current=False)
    make_ticket("a", days_out=30)
    make_ticket("old", year=2019, created_at=datetime.datetime(2019, 1, 1, tzinfo=datetime.timezone.utc))

    curves = sales_curves()

    assert [s["year"] for s in curves["series"]] == [2026]
    assert curves["missing"] == [{"year": 2019, "reason": "no start date"}]


@pytest.mark.django_db
def test_years_with_no_tickets_are_reported_as_missing():
    make_event(year=2026)
    make_ticket("a", days_out=30)
    make_event(year=2025, start_date=datetime.date(2025, 9, 8), is_current=False)

    curves = sales_curves()

    assert [s["year"] for s in curves["series"]] == [2026]
    assert curves["missing"] == [{"year": 2025, "reason": "no ticket detail synced"}]


@pytest.mark.django_db
def test_each_year_gets_its_own_series_and_color():
    make_event(year=2026)
    make_event(year=2025, start_date=datetime.date(2025, 9, 8), is_current=False)
    make_ticket("new", year=2026, days_out=30)
    make_ticket(
        "old",
        year=2025,
        created_at=datetime.datetime(2025, 8, 9, tzinfo=datetime.timezone.utc),  # 30 days out
    )

    curves = sales_curves()

    assert [s["year"] for s in curves["series"]] == [2026, 2025]  # newest first for the legend
    assert [c["year"] for c in curves["columns"]] == [2025, 2026]  # chronological for the table
    assert len({s["color"] for s in curves["series"]}) == 2


@pytest.mark.django_db
def test_chart_geometry_covers_every_checkpoint():
    make_event()
    make_ticket("a", days_out=200)
    make_ticket("b", days_out=5)

    tickets_chart = sales_curves()["charts"][0]
    line = tickets_chart["lines"][0]

    assert len(line["points"].split(" ")) == len(CHECKPOINTS)
    assert tickets_chart["max_value"] == 2
    # Series climbs, so SVG y (counted from the top) must fall.
    ys = [float(point.split(",")[1]) for point in line["points"].split(" ")]
    assert ys == sorted(ys, reverse=True)


@pytest.mark.django_db
def test_table_rows_line_up_with_the_checkpoints():
    make_event()
    make_ticket("a", days_out=30)

    curves = sales_curves()

    assert len(curves["table_rows"]) == len(CHECKPOINTS)
    assert curves["table_rows"][-1]["label"] == "Event"
    assert curves["table_rows"][-1]["cells"] == [{"year": 2026, "tickets": 1, "revenue": 100.0}]


@pytest.mark.django_db
def test_dashboard_renders_the_chart(client):
    user = User.objects.create_user(
        username="root", email="root@example.com", password="pw12345!", is_staff=True, is_superuser=True
    )
    client.force_login(user)
    make_event()
    make_ticket("a", days_out=30)

    response = client.get(URL)

    assert response.status_code == 200
    body = response.content.decode()
    assert "Sales pace by year" in body
    assert "<polyline" in body
    assert response.context["curves"]["has_data"] is True
