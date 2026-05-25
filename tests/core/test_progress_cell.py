"""Tests for the progress-bar cell renderer in ``app.widgets.tabs``.

``progress_cell`` draws the per-row progress in the queue Treeviews as a
fixed-width block bar plus the exact percentage, so the user sees a
graphical trend and the number in one column.
"""
from __future__ import annotations

from app.widgets.tabs import marquee_cell, progress_cell


def _bar(cell: str) -> str:
    # The block bar is always the first 10 cells; the rest is " NNN%".
    return cell[:10]


def test_progress_cell_zero():
    cell = progress_cell(0)
    assert _bar(cell) == "░" * 10
    assert cell.endswith("  0%")


def test_progress_cell_full():
    cell = progress_cell(100)
    assert _bar(cell) == "█" * 10
    assert cell.endswith("100%")


def test_progress_cell_half():
    cell = progress_cell(50)
    assert _bar(cell) == "█" * 5 + "░" * 5
    assert cell.endswith(" 50%")


def test_progress_cell_rounds_to_nearest_segment():
    assert _bar(progress_cell(42)) == "█" * 4 + "░" * 6   # 4.2 -> 4
    assert _bar(progress_cell(47)) == "█" * 5 + "░" * 5   # 4.7 -> 5


def test_progress_cell_clamps_out_of_range():
    assert _bar(progress_cell(-10)) == "░" * 10
    assert _bar(progress_cell(150)) == "█" * 10
    assert progress_cell(150).endswith("100%")


def test_progress_cell_handles_float_and_bad_input():
    assert progress_cell(33.7).endswith(" 34%")
    assert _bar(progress_cell(None)) == "░" * 10  # type: ignore[arg-type]


def test_progress_cell_has_constant_width():
    # Constant width keeps the column from jittering as the number grows.
    widths = {len(progress_cell(p)) for p in (0, 5, 50, 99, 100)}
    assert widths == {15}


# --- marquee_cell: indeterminate "working" animation ----------------------


def test_marquee_cell_always_three_lit_blocks():
    for frame in range(0, 25):
        assert marquee_cell(frame).count("█") == 3


def test_marquee_cell_constant_width():
    assert len({len(marquee_cell(f)) for f in range(0, 25)}) == 1


def test_marquee_cell_advances_with_frame():
    # Consecutive frames differ, so the bar visibly moves.
    assert marquee_cell(0) != marquee_cell(1)


def test_marquee_cell_wraps_each_track_length():
    # The lit window has a 10-segment period, so it loops smoothly.
    assert marquee_cell(0) == marquee_cell(10)
