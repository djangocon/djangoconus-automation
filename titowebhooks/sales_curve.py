"""Ticket sales as a function of how far out from the conference they happened.

Every year gets sampled at the same days-out checkpoints so the seasons can be
laid on top of each other: "where were we 30 days out in 2024 vs 2025?". The
spacing is deliberately uneven - roughly monthly while sales are slow, tightening
to weeks and then days as the conference approaches, which is when the curve moves.
"""

import math

from titowebhooks.models import TitoHistoricalEvent, TitoTicket

# Days before the conference start date, furthest out first.
CHECKPOINTS = [365, 330, 300, 270, 240, 210, 180, 150, 120, 90, 60, 30, 21, 14, 7, 3, 0]

# 2021 was the COVID year - the sales pattern says nothing useful about a normal
# season, so it would only distort a year-over-year read.
EXCLUDED_YEARS = {2021}

# A year whose synced tickets fall this far short of its snapshot total is only
# partially covered, so its curve sits below where that season really was.
COVERAGE_THRESHOLD = 0.95

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

    Takes (days_out, price) pairs. A ticket counts toward a checkpoint when it was
    bought at least that many days before the event, so the series only ever climbs
    as the checkpoints march toward day zero.
    """
    tickets = []
    revenue = []

    for checkpoint in CHECKPOINTS:
        sold = [(d, p) for d, p in days_out_values if d >= checkpoint]
        tickets.append(len(sold))
        revenue.append(sum(p for _, p in sold))

    return tickets, revenue


def _series_for_event(event: TitoHistoricalEvent) -> dict | None:
    """One year's curve, or None when we can't place its tickets in time."""
    if not event.start_date:
        return None

    tickets = TitoTicket.objects.filter(year=event.year, voided=False).exclude(created_at=None)

    days_out_values = [((event.start_date - t.created_at.date()).days, t.price) for t in tickets]
    # Tickets sold after the conference started (comps, walk-ins) still belong to
    # the season - clamp them to day zero rather than dropping them.
    days_out_values = [(max(d, 0), p) for d, p in days_out_values]

    if not days_out_values:
        return None

    ticket_counts, revenue = _cumulative_at_checkpoints(days_out_values)

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


def _chart(series: list[dict], key: str, is_money: bool, width: float = 720, height: float = 260) -> dict:
    """Build everything the template needs to draw one chart."""
    max_value = max((max(s[key]) for s in series), default=0)

    tick_count = 4
    step = _axis_step((max_value or 1) / tick_count)
    # Grow the axis to a whole number of steps so the top tick is round and the
    # highest point still sits inside the plot.
    axis_max = step * max(tick_count, math.ceil((max_value or 1) / step))
    ticks = [step * i for i in range(int(round(axis_max / step)) + 1)]

    x_step = width / (len(CHECKPOINTS) - 1) if len(CHECKPOINTS) > 1 else width

    lines = []
    for s in series:
        values = s[key]
        points = [
            {
                "x": i * x_step,
                "y": height - (v * height / axis_max if axis_max else 0),
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
    }


def sales_curves() -> dict:
    """Days-out ticket and revenue curves for every year we can chart."""
    events = list(TitoHistoricalEvent.objects.all().order_by("year"))
    chartable = [e for e in events if e.year not in EXCLUDED_YEARS]

    series = [s for s in (_series_for_event(e) for e in chartable) if s]
    for index, s in enumerate(series):
        s["color"] = SERIES_COLORS[index % len(SERIES_COLORS)]

    # Skipped years are worth naming - an empty chart otherwise looks like a bug.
    charted_years = {s["year"] for s in series}

    def _reason(event):
        if event.year in EXCLUDED_YEARS:
            return "excluded, COVID year"
        if not event.start_date:
            return "no start date"
        return "no ticket detail synced"

    missing = [{"year": e.year, "reason": _reason(e)} for e in events if e.year not in charted_years]
    partial = [s for s in series if s["partial"]]

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
        "charts": (
            [
                {"title": "Tickets sold", "is_money": False, "slug": "tickets", **_chart(series, "tickets", False)},
                {"title": "Revenue", "is_money": True, "slug": "revenue", **_chart(series, "revenue", True)},
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
