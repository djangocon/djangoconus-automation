"""Ticket sales as a function of how far out from the conference they happened.

Every year gets sampled at the same days-out checkpoints so the seasons can be
laid on top of each other: "where were we 30 days out in 2024 vs 2025?". The
spacing is deliberately uneven - roughly monthly while sales are slow, tightening
to weeks and then days as the conference approaches, which is when the curve moves.
"""

import math

from django.utils import timezone

from titowebhooks.models import TitoHistoricalEvent, TitoTicket

# Days before the conference start date, furthest out first.
CHECKPOINTS = [365, 330, 300, 270, 240, 210, 180, 150, 120, 90, 60, 30, 21, 14, 7, 3, 0]

# 2021 was the COVID year - the sales pattern says nothing useful about a normal
# season, so it would only distort a year-over-year read.
EXCLUDED_YEARS = {2021}

# A year whose synced tickets fall this far short of its snapshot total is only
# partially covered, so its curve sits below where that season really was.
COVERAGE_THRESHOLD = 0.95

# 2019 ran far bigger than any season since, so it stretches both axes and flattens
# the years anyone is actually comparing. Off by default, available on request.
OPTIONAL_YEARS = {2019}

# The axes are pinned rather than scaled to the data, so the charts keep the same
# shape season to season and one big year doesn't visually flatten the others. The
# revenue ceiling lifts when 2019 is shown, because it needs the room.
REVENUE_AXIS_STEP = 50_000
REVENUE_AXIS_MAX = 200_000
REVENUE_AXIS_MAX_WITH_OPTIONAL = 250_000

CHART_WIDTH = 720
CHART_HEIGHT = 260

TICKETS_AXIS_STEP = 100
TICKETS_AXIS_MAX = 550
TICKETS_AXIS_MAX_WITH_OPTIONAL = 700

# Releases matched by these keywords do not represent another attendee, so they are
# left out of the head count. Their money still counts toward revenue.
#
# Sprints and tutorials are add-ons bought on top of a conference ticket; a donation
# is not a ticket at all. Matching on the title is crude, but Ti.to gives us nothing
# structural to key off - releases carry no type or category field.
ADDON_KEYWORDS = ("sprint", "tutorial", "donation")

# Distinct enough to tell apart on a dark background, oldest year to newest.
SERIES_COLORS = [
    "#f87171",
    "#fb923c",
    "#facc15",
    "#a3e635",
    "#34d399",
    "#22d3ee",
    "#818cf8",
    "#e879f9",
]


def _label(days_out: int) -> str:
    if days_out == 0:
        return "Event"
    if days_out < 30:
        return f"{days_out}d"
    months = round(days_out / 30)
    return f"{months}mo"


CHECKPOINT_LABELS = [_label(d) for d in CHECKPOINTS]


def _cumulative_at_checkpoints(days_out_values: list[tuple[int, float]]) -> tuple[list[int], list[float]]:
    """Cumulative ticket count and revenue at each checkpoint.

    Takes (days_out, price, is_conference_ticket) triples. A ticket counts toward a
    checkpoint when it was bought at least that many days before the event, so the
    series only ever climbs as the checkpoints march toward day zero.

    Sprints, tutorials and donations inflate a head count without representing
    another attendee, so they are left out of the count but kept in revenue, where
    the money is real either way.
    """
    tickets = []
    revenue = []

    for checkpoint in CHECKPOINTS:
        sold = [row for row in days_out_values if row[0] >= checkpoint]
        tickets.append(sum(1 for _, _, is_conference in sold if is_conference))
        revenue.append(sum(price for _, price, _ in sold))

    return tickets, revenue


def _x_for_days_out(days_out: int, x_step: float) -> float | None:
    """Where a given distance-out falls along the x axis, or None if off the chart.

    The checkpoints are unevenly spaced, so this interpolates within whichever pair
    the day lands between rather than scaling linearly across the whole range.
    """
    if days_out > CHECKPOINTS[0] or days_out < CHECKPOINTS[-1]:
        return None

    for i in range(len(CHECKPOINTS) - 1):
        high, low = CHECKPOINTS[i], CHECKPOINTS[i + 1]
        if high >= days_out >= low:
            span = high - low
            fraction = (high - days_out) / span if span else 0
            return (i + fraction) * x_step

    return None


def _today_marker(events: list[TitoHistoricalEvent], x_step: float, today) -> dict | None:
    """Vertical rule showing how far out the current season is right now.

    Anchored to the current event, since that is the only season still in motion -
    it tells you which part of the older curves you should be comparing against.
    """
    current = next((e for e in events if e.is_current and e.start_date), None)
    if not current:
        return None

    days_out = (current.start_date - today).days
    if days_out < 0:
        return None  # the conference has already started; the whole chart is history

    x = _x_for_days_out(days_out, x_step)
    if x is None:
        return None

    return {"x": x, "days_out": days_out, "label": f"today · {_when_label(days_out)}"}


def _is_addon(release_title: str) -> bool:
    """True when a release is not a person attending: an add-on, or a donation."""
    title = (release_title or "").lower()
    return any(keyword in title for keyword in ADDON_KEYWORDS)


def _series_for_event(event: TitoHistoricalEvent) -> dict | None:
    """One year's curve, or None when we can't place its tickets in time."""
    if not event.start_date:
        return None

    tickets = TitoTicket.objects.filter(year=event.year, voided=False).exclude(created_at=None)

    days_out_values = [
        # Tickets sold after the conference started (comps, walk-ins) still belong to
        # the season - clamp them to day zero rather than dropping them.
        (max((event.start_date - t.created_at.date()).days, 0), t.price, not _is_addon(t.release_title))
        for t in tickets
    ]

    if not days_out_values:
        return None

    ticket_counts, revenue = _cumulative_at_checkpoints(days_out_values)
    addons = sum(1 for _, _, is_conference in days_out_values if not is_conference)

    # How much of the season we actually hold. The snapshot totals come straight from
    # Ti.to's release counts, so a shortfall means tickets we never synced - and a
    # curve that sits low for reasons that have nothing to do with how sales went.
    snapshot_sold = event.total_sold or 0
    synced = len(days_out_values)
    coverage = (synced / snapshot_sold) if snapshot_sold else None
    sources = sorted(
        TitoTicket.objects.filter(year=event.year, voided=False).values_list("source", flat=True).distinct()
    )

    return {
        "year": event.year,
        "title": event.title,
        "is_current": event.is_current,
        "start_date": event.start_date,
        "tickets": ticket_counts,
        "revenue": revenue,
        "final_tickets": ticket_counts[-1],
        "final_revenue": revenue[-1],
        "addon_tickets": addons,
        "synced_tickets": synced,
        "snapshot_sold": snapshot_sold,
        "coverage": coverage,
        "coverage_percent": round(coverage * 100) if coverage is not None else None,
        "partial": coverage is not None and coverage < COVERAGE_THRESHOLD,
        "sources": sources,
    }


def _polyline(values: list[float], max_value: float, width: float, height: float) -> str:
    """SVG point string for a series, scaled to the plot box.

    x marches left-to-right across the checkpoints (furthest out on the left,
    event day on the right); y is inverted because SVG counts down from the top.
    """
    if len(values) < 2:
        return ""

    step = width / (len(values) - 1)
    scale = height / max_value if max_value else 0

    return " ".join(f"{i * step:.1f},{height - (v * scale):.1f}" for i, v in enumerate(values))


def _when_label(days_out: int) -> str:
    """Spelled-out distance for the hover readout, where "1mo" is too terse."""
    if days_out == 0:
        return "on event day"
    if days_out == 1:
        return "1 day out"
    return f"{days_out} days out"


def _format_value(value: float, is_money: bool) -> str:
    """Exact value for hover readouts - no rounding, this is the number you came for."""
    if is_money:
        return f"${value:,.0f}"
    return f"{value:,.0f} ticket{'' if value == 1 else 's'}"


def _axis_step(rough_step: float) -> float:
    """Round a step up to the nearest 1, 2, 2.5 or 5 times a power of ten.

    Scaling the data max directly gives ticks like 75,600 and 226,800, which are
    unreadable at a glance. Snapping the step to a round number gives 80k / 160k /
    240k instead, at the cost of a little headroom above the top line.
    """
    if rough_step <= 0:
        return 1.0

    magnitude = 10 ** math.floor(math.log10(rough_step))
    for multiple in (1, 2, 2.5, 5, 10):
        if rough_step <= multiple * magnitude:
            return multiple * magnitude
    return 10 * magnitude


def _format_axis(value: float, is_money: bool) -> str:
    """Compact tick label: 0, 240, 24k, 1.2M - with a $ when it's money.

    Ticket counts stay written out for longer than dollars do: an axis reading
    750 / 1k looks like two different units, where 750 / 1,000 plainly doesn't.
    """
    prefix = "$" if is_money else ""
    abbreviate_from = 1_000 if is_money else 10_000

    for divisor, suffix in ((1_000_000, "M"), (1_000, "k")):
        if abs(value) >= max(divisor, abbreviate_from):
            scaled = value / divisor
            # One decimal only when it carries information: 1.2M, but 24k not 24.0k.
            text = f"{scaled:.1f}".rstrip("0").rstrip(".")
            return f"{prefix}{text}{suffix}"

    return f"{prefix}{value:,.0f}"


def _chart(
    series: list[dict],
    key: str,
    is_money: bool,
    width: float = CHART_WIDTH,
    height: float = CHART_HEIGHT,
    step: float | None = None,
    axis_max: float | None = None,
    today_marker: dict | None = None,
) -> dict:
    """Build everything the template needs to draw one chart.

    Pass step and axis_max to pin the scale - useful when a chart should keep the
    same shape from year to year instead of rescaling itself around whichever
    season happened to sell the most.
    """
    max_value = max((max(s[key]) for s in series), default=0)

    if step is None or axis_max is None:
        tick_count = 4
        step = _axis_step((max_value or 1) / tick_count)
        # Grow the axis to a whole number of steps so the top tick is round and the
        # highest point still sits inside the plot.
        axis_max = step * max(tick_count, math.ceil((max_value or 1) / step))

    # Ticks stop at the last whole step at or below the ceiling, so a cap that isn't a
    # multiple of the step (550 by 100s) gets 0..500 and a little headroom, rather
    # than a stray label hanging above the plot.
    ticks = [step * i for i in range(int(math.floor(axis_max / step + 1e-9)) + 1)]
    # A pinned axis can be shorter than the data. Draw those points along the top
    # rather than off the canvas, and let the caller say so on the page.
    clipped = max_value > axis_max

    x_step = width / (len(CHECKPOINTS) - 1) if len(CHECKPOINTS) > 1 else width

    lines = []
    for s in series:
        values = s[key]
        points = [
            {
                "x": i * x_step,
                "y": height - (min(v, axis_max) * height / axis_max if axis_max else 0),
                "value": v,
                "when": _when_label(CHECKPOINTS[i]),
                "value_label": _format_value(v, is_money),
                "label": f"{s['year']} · {CHECKPOINT_LABELS[i]} · {_format_value(v, is_money)}",
            }
            for i, v in enumerate(values)
        ]
        lines.append(
            {
                "year": s["year"],
                "color": s["color"],
                "is_current": s["is_current"],
                "points": " ".join(f"{p['x']:.1f},{p['y']:.1f}" for p in points),
                "markers": points,
                "final": values[-1],
            }
        )

    gridlines = [
        {"y": height - (tick * height / axis_max if axis_max else 0), "label": _format_axis(tick, is_money)}
        for tick in ticks
    ]

    x_labels = [
        {"x": i * x_step, "label": label}
        for i, label in enumerate(CHECKPOINT_LABELS)
        # Every other label so they don't collide on narrow screens.
        if i % 2 == 0 or i == len(CHECKPOINT_LABELS) - 1
    ]

    return {
        "width": width,
        "height": height,
        "lines": lines,
        "gridlines": gridlines,
        "x_labels": x_labels,
        "max_value": max_value,
        "axis_max": axis_max,
        "step": step,
        "clipped": clipped,
        "today": today_marker,
    }


def sales_curves(include_optional: bool = False, today=None) -> dict:
    """Days-out ticket and revenue curves for every year we can chart.

    include_optional brings back the years held out by default (2019), which needs
    taller axes to fit. today anchors the "we are here" rule and is injectable so
    tests do not depend on the calendar.
    """
    today = today or timezone.localdate()
    events = list(TitoHistoricalEvent.objects.all().order_by("year"))
    hidden = EXCLUDED_YEARS if include_optional else EXCLUDED_YEARS | OPTIONAL_YEARS
    chartable = [e for e in events if e.year not in hidden]

    series = [s for s in (_series_for_event(e) for e in chartable) if s]
    for index, s in enumerate(series):
        s["color"] = SERIES_COLORS[index % len(SERIES_COLORS)]

    # Skipped years are worth naming - an empty chart otherwise looks like a bug.
    charted_years = {s["year"] for s in series}

    def _reason(event):
        if event.year in EXCLUDED_YEARS:
            return "excluded, COVID year"
        if event.year in OPTIONAL_YEARS and not include_optional:
            return "hidden by default, it skews the comparison"
        if not event.start_date:
            return "no start date"
        return "no ticket detail synced"

    missing = [{"year": e.year, "reason": _reason(e)} for e in events if e.year not in charted_years]
    partial = [s for s in series if s["partial"]]

    x_step = CHART_WIDTH / (len(CHECKPOINTS) - 1) if len(CHECKPOINTS) > 1 else CHART_WIDTH
    marker = _today_marker(events, x_step, today)

    tickets_max = TICKETS_AXIS_MAX_WITH_OPTIONAL if include_optional else TICKETS_AXIS_MAX
    revenue_max = REVENUE_AXIS_MAX_WITH_OPTIONAL if include_optional else REVENUE_AXIS_MAX

    return {
        "has_data": bool(series),
        # Newest first for the legend and summary; the table columns below stay in
        # chronological order to match the cell order.
        "series": sorted(series, key=lambda s: -s["year"]),
        "columns": [{"year": s["year"], "color": s["color"]} for s in series],
        "checkpoint_labels": CHECKPOINT_LABELS,
        "checkpoints": CHECKPOINTS,
        # Any year charted off incomplete data makes the comparison misleading, so
        # say so on the page rather than letting a low curve read as slow sales.
        "partial": sorted(partial, key=lambda s: -s["year"]),
        "excluded_years": sorted(EXCLUDED_YEARS),
        "optional_years": sorted(OPTIONAL_YEARS),
        "include_optional": include_optional,
        "today": marker,
        "charts": (
            [
                {
                    "title": "Tickets sold",
                    "note": "attendees only, excluding sprints, tutorials and donations",
                    "is_money": False,
                    "slug": "tickets",
                    **_chart(
                        series,
                        "tickets",
                        False,
                        step=TICKETS_AXIS_STEP,
                        axis_max=tickets_max,
                        today_marker=marker,
                    ),
                },
                {
                    "title": "Revenue",
                    "note": "every line item, including sprints, tutorials and donations",
                    "is_money": True,
                    "slug": "revenue",
                    **_chart(
                        series,
                        "revenue",
                        True,
                        step=REVENUE_AXIS_STEP,
                        axis_max=revenue_max,
                        today_marker=marker,
                    ),
                },
            ]
            if series
            else []
        ),
        "missing": missing,
        "table_rows": [
            {
                "label": label,
                "days_out": CHECKPOINTS[i],
                "cells": [{"year": s["year"], "tickets": s["tickets"][i], "revenue": s["revenue"][i]} for s in series],
            }
            for i, label in enumerate(CHECKPOINT_LABELS)
        ],
    }
