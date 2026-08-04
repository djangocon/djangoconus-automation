import datetime

import pytest
from django.contrib.auth import get_user_model

from titowebhooks.models import TitoHistoricalEvent, TitoTicket
from titowebhooks.sales_curve import CHECKPOINTS, EXCLUDED_YEARS, sales_curves

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
def test_covid_year_is_excluded_but_named():
    assert 2021 in EXCLUDED_YEARS

    make_event(year=2026)
    make_ticket("new", days_out=30)
    make_event(year=2021, start_date=datetime.date(2021, 9, 22), is_current=False)
    make_ticket("covid", year=2021, created_at=datetime.datetime(2021, 8, 23, tzinfo=datetime.timezone.utc))

    curves = sales_curves()

    assert [s["year"] for s in curves["series"]] == [2026]
    assert {"year": 2021, "reason": "excluded, COVID year"} in curves["missing"]
    assert curves["excluded_years"] == [2021]


@pytest.mark.django_db
def test_excluded_year_does_not_consume_a_series_color():
    make_event(year=2021, start_date=datetime.date(2021, 9, 22), is_current=False)
    make_ticket("covid", year=2021, created_at=datetime.datetime(2021, 8, 23, tzinfo=datetime.timezone.utc))
    make_event(year=2026)
    make_ticket("new", days_out=30)

    assert sales_curves()["series"][0]["color"] == "#f87171"  # the first color, not the second


@pytest.mark.django_db
def test_coverage_compares_synced_tickets_against_the_snapshot_total():
    make_event(releases=[{"tickets_count": 10, "price": "100.0"}])
    for i in range(10):
        make_ticket(f"t{i}", days_out=30)

    series = sales_curves()["series"][0]

    assert series["synced_tickets"] == 10
    assert series["snapshot_sold"] == 10
    assert series["coverage_percent"] == 100
    assert series["partial"] is False
    assert sales_curves()["partial"] == []


@pytest.mark.django_db
def test_partially_synced_year_is_flagged():
    make_event(releases=[{"tickets_count": 100, "price": "100.0"}])
    for i in range(40):
        make_ticket(f"t{i}", days_out=30)

    curves = sales_curves()
    series = curves["series"][0]

    assert series["coverage_percent"] == 40
    assert series["partial"] is True
    assert [s["year"] for s in curves["partial"]] == [2026]


@pytest.mark.django_db
def test_year_without_a_snapshot_total_is_not_flagged_as_partial():
    make_event()  # no releases, so there's nothing to compare against
    make_ticket("a", days_out=30)

    series = sales_curves()["series"][0]

    assert series["coverage"] is None
    assert series["partial"] is False


@pytest.mark.django_db
def test_revenue_is_discount_aware_for_every_year_not_just_the_current_one():
    make_event(year=2026)
    make_event(year=2024, start_date=datetime.date(2024, 9, 22), is_current=False)
    make_ticket("now-comp", year=2026, days_out=30, price=0.0)
    make_ticket("now-paid", year=2026, days_out=30, price=500.0)
    old = datetime.datetime(2024, 8, 23, tzinfo=datetime.timezone.utc)
    make_ticket("then-comp", year=2024, price=0.0, created_at=old)
    make_ticket("then-paid", year=2024, price=400.0, created_at=old)

    by_year = {s["year"]: s for s in sales_curves()["series"]}

    assert by_year[2026]["final_revenue"] == 500.0
    assert by_year[2024]["final_revenue"] == 400.0


@pytest.mark.django_db
def test_dashboard_warns_when_a_year_is_only_partly_synced(client):
    user = User.objects.create_superuser(username="root2", email="r2@example.com", password="pw12345!")
    client.force_login(user)
    make_event(releases=[{"tickets_count": 100, "price": "100.0"}])
    make_ticket("a", days_out=30)

    response = client.get(URL)

    assert "Not an even comparison yet" in response.content.decode()


@pytest.mark.django_db
def test_axis_ticks_are_round_ascending_and_cover_the_data():
    make_event()
    for i in range(37):  # an awkward max that used to give ticks like 9.7
        make_ticket(f"t{i}", days_out=30, price=1000.0)

    chart = sales_curves()["charts"][1]  # revenue

    assert chart["max_value"] == 37000
    assert chart["axis_max"] >= 37000  # the top line fits inside the plot
    assert chart["axis_max"] % 10000 == 0  # and lands on a round number
    # Rendered top to bottom, so y descends while the values climb.
    assert [g["y"] for g in chart["gridlines"]] == sorted([g["y"] for g in chart["gridlines"]], reverse=True)
    assert [g["label"] for g in chart["gridlines"]] == ["$0", "$10k", "$20k", "$30k", "$40k"]


@pytest.mark.django_db
def test_ticket_axis_is_not_formatted_as_money():
    make_event()
    for i in range(12):
        make_ticket(f"t{i}", days_out=30)

    labels = [g["label"] for g in sales_curves()["charts"][0]["gridlines"]]

    assert labels[0] == "0"
    assert not any("$" in label for label in labels)


@pytest.mark.django_db
def test_every_point_carries_a_hover_label():
    make_event()
    make_ticket("a", days_out=30, price=250.0)

    revenue_line = sales_curves()["charts"][1]["lines"][0]

    assert len(revenue_line["markers"]) == len(CHECKPOINTS)
    assert revenue_line["markers"][-1]["label"] == "2026 · Event · $250"
    tickets_line = sales_curves()["charts"][0]["lines"][0]
    assert tickets_line["markers"][-1]["label"] == "2026 · Event · 1 ticket"


@pytest.mark.django_db
def test_markers_line_up_with_the_polyline():
    make_event()
    make_ticket("a", days_out=200)
    make_ticket("b", days_out=5)

    line = sales_curves()["charts"][0]["lines"][0]
    drawn = [tuple(p.split(",")) for p in line["points"].split(" ")]

    assert len(drawn) == len(line["markers"])
    for (x, y), marker in zip(drawn, line["markers"], strict=True):
        assert float(x) == pytest.approx(marker["x"], abs=0.05)
        assert float(y) == pytest.approx(marker["y"], abs=0.05)


@pytest.mark.django_db
def test_dashboard_renders_hover_targets_and_the_expand_modal(client):
    user = User.objects.create_superuser(username="root3", email="r3@example.com", password="pw12345!")
    client.force_login(user)
    make_event()
    make_ticket("a", days_out=30, price=250.0)

    body = client.get(URL).content.decode()

    assert "<title>2026 · Event · $250</title>" in body
    assert 'id="chart-modal"' in body
    assert "data-chart" in body
    assert "click to enlarge" in body


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
