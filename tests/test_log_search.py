"""log_search 純函式的單元測試。"""

import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "streamlit_app"))
from log_search import (build_highlighter, context_ranges, count_rows, export_text,
                        find_matches, index_times, merge_ranges, render_table)


def test_merge_ranges_joins_overlapping_and_adjacent():
    assert merge_ranges([[3, 5], [1, 3], [6, 7], [10, 10]]) == [[1, 7], [10, 10]]
    assert merge_ranges([]) == []


def test_find_matches_and_or_and_time():
    lines = ["2026-09-24 10:00:00 ERROR timeout", "at Foo.bar", "2026-09-24 10:05:00 ERROR", "INFO timeout"]
    times, first, last = index_times(lines)
    assert times[1] == times[0], "堆疊行沿用前一行時間"
    assert (first, last) == (datetime.datetime(2026, 9, 24, 10), datetime.datetime(2026, 9, 24, 10, 5))
    assert find_matches(lines, times, ["error", "TIMEOUT"], True) == [0]
    assert find_matches(lines, times, ["error", "TIMEOUT"], False) == [0, 2, 3]
    start, end = datetime.datetime(2026, 9, 24, 10, 1), datetime.datetime(2026, 9, 24, 10, 10)
    assert find_matches(lines, times, [], False, start, end) == [2, 3]


def test_context_ranges_and_row_count():
    ranges = context_ranges([0, 4, 20], 3, 22)
    assert ranges == [[0, 7], [17, 21]]
    assert count_rows(ranges) == 13


def test_highlighter_escapes_and_uses_badge_color():
    highlight = build_highlighter([("timeout", 1), ("ERROR", 0)])
    out = highlight('<b>error & Timeout</b>')
    assert "<b>" not in out and "&amp;" in out
    assert '<span class="highlight highlight-0">error</span>' in out
    assert '<span class="highlight highlight-1">Timeout</span>' in out


def test_highlighter_prefers_longest_keyword():
    out = build_highlighter([("ERR", 0), ("ERROR", 2)])("ERROR")
    assert out == '<span class="highlight highlight-2">ERROR</span>'


def test_export_and_render_share_ranges():
    lines = ["a", "ERROR", "c", "d", "e"]
    text = export_text(lines, [[0, 1], [4, 4]])
    assert text.splitlines()[0] == "     1 | a"
    assert len(text.splitlines()) == 4
    table = render_table(lines, [[0, 1], [4, 4]], {1}, build_highlighter([("ERROR", 0)]))
    assert table.count('class="separator"') == 1
    assert '<tr class="match"><td class="line-no">2</td>' in table
