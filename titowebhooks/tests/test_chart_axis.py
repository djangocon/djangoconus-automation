import pytest

from titowebhooks.sales_curve import _axis_step, _format_axis, _format_value


@pytest.mark.parametrize(
    "rough,expected",
    [
        (1, 1),
        (1.5, 2),
        (2.1, 2.5),
        (3, 5),
        (7, 10),
        (75_600, 100_000),
        (18_000, 20_000),
        (120, 200),
        (240, 250),
    ],
)
def test_axis_step_snaps_up_to_a_round_number(rough, expected):
    assert _axis_step(rough) == expected


def test_axis_step_survives_zero_and_negatives():
    assert _axis_step(0) == 1.0
    assert _axis_step(-5) == 1.0


@pytest.mark.parametrize(
    "value,is_money,expected",
    [
        (0, True, "$0"),
        (240, False, "240"),
        (24_000, True, "$24k"),
        (80_000, True, "$80k"),
        (1_200_000, True, "$1.2M"),
        (2_000_000, False, "2M"),
        (500, True, "$500"),
        # Counts stay written out until they get big, so an axis never mixes 750 with 1k.
        (1_000, False, "1,000"),
        (7_500, False, "7,500"),
        (20_000, False, "20k"),
    ],
)
def test_axis_labels_are_compact_and_round(value, is_money, expected):
    assert _format_axis(value, is_money) == expected


@pytest.mark.parametrize(
    "value,is_money,expected",
    [
        (73_655, True, "$73,655"),
        (0, True, "$0"),
        (1, False, "1 ticket"),
        (280, False, "280 tickets"),
        (0, False, "0 tickets"),
    ],
)
def test_hover_readouts_show_the_exact_figure(value, is_money, expected):
    assert _format_value(value, is_money) == expected
