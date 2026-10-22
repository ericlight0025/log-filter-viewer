"""搜尋、區間合併與渲染的純函式，不依賴 Streamlit，方便單元測試。"""

import datetime
import html
import re


# HTML 版與 Streamlit 版共用的展示上限（含上下文、合併後的實際行數）
MAX_DISPLAY_ROWS = 50_000
SEPARATOR_TEXT = "-" * 70

# 支援 Log4j / Spring / Linux 常見時間格式 (包含逗號毫秒)
TIME_REGEX = re.compile(r'(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)')


def parse_time(line: str):
    """解析行首附近的時間戳記為 datetime 物件"""
    if not line:
        return None
    match = TIME_REGEX.search(line[:120])
    if match:
        raw_str = match.group(1).replace(',', '.').replace('/', '-')
        if len(raw_str) >= 19 and raw_str[10] == ' ':
            raw_str = raw_str[:10] + 'T' + raw_str[11:]
        try:
            return datetime.datetime.fromisoformat(raw_str)
        except ValueError:
            pass
    return None


def index_times(lines):
    """建立每行的時間索引；沒有時間戳記的堆疊行沿用前一行的時間。"""
    line_times = []
    last_time = None
    for line in lines:
        timestamp = parse_time(line)
        if timestamp is not None:
            last_time = timestamp
        line_times.append(last_time)
    valid_times = [t for t in line_times if t is not None]
    return line_times, min(valid_times, default=None), max(valid_times, default=None)


def merge_ranges(ranges):
    """合併重疊或相鄰的 [start, end] 區間"""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [list(sorted_ranges[0])]
    for curr in sorted_ranges[1:]:
        last = merged[-1]
        if curr[0] <= last[1] + 1:
            last[1] = max(last[1], curr[1])
        else:
            merged.append(list(curr))
    return merged


def find_matches(lines, line_times, keywords, is_and, start=None, end=None):
    """回傳命中的行號 (0-based)；沒有關鍵字時為純時間過濾模式。"""
    clean_kws = [k.lower() for k in keywords]
    check = all if is_and else any
    time_filter = start is not None and end is not None
    matches = []
    for i, line in enumerate(lines):
        if time_filter:
            t = line_times[i]
            if t is None or not (start <= t <= end):
                continue
        if clean_kws:
            line_lower = line.lower()
            if not check(k in line_lower for k in clean_kws):
                continue
        matches.append(i)
    return matches


def context_ranges(matches, context_lines, total_lines):
    """建立 ±context_lines 的區間並合併，確保同一行不會重複顯示。"""
    return merge_ranges([
        [max(0, m - context_lines), min(total_lines - 1, m + context_lines)] for m in matches
    ])


def count_rows(ranges):
    return sum(end - start + 1 for start, end in ranges)


def build_highlighter(terms):
    """terms 為 (關鍵字, 色彩索引)；正規表達式只編譯一次，回傳逐行高亮函式。

    以 Regex 切割文字後分別跳脫，避免 HTML 實體被破壞。
    """
    colors = {}
    for text, color in terms:
        colors.setdefault(text.lower(), color)
    if not colors:
        return html.escape

    # 依長度降序排列，讓較長的關鍵字優先命中
    ordered = sorted(colors, key=len, reverse=True)
    combined = re.compile("|".join(re.escape(k) for k in ordered), re.IGNORECASE)

    def highlight(raw_text):
        out = []
        pos = 0
        for match in combined.finditer(raw_text):
            out.append(html.escape(raw_text[pos:match.start()]))
            color = colors.get(match.group(0).lower(), 0)
            out.append(f'<span class="highlight highlight-{color}">{html.escape(match.group(0))}</span>')
            pos = match.end()
        out.append(html.escape(raw_text[pos:]))
        return "".join(out)

    return highlight


def export_text(lines, ranges):
    """產生含對齊行號與分隔線的純文字結果。"""
    out = []
    for r_idx, (start, end) in enumerate(ranges):
        if r_idx > 0:
            out.append(SEPARATOR_TEXT)
        out.extend(f"{(i + 1):>6} | {lines[i]}" for i in range(start, end + 1))
    return "\n".join(out)


def render_table(lines, ranges, match_set, highlight):
    """渲染 HTML 表格；只有命中行套用關鍵字高亮。"""
    rows = []
    for r_idx, (start, end) in enumerate(ranges):
        if r_idx > 0:
            rows.append('<tr class="separator"><td colspan="2">⋯⋯⋯⋯⋯⋯</td></tr>')
        for i in range(start, end + 1):
            is_match = i in match_set
            content = highlight(lines[i]) if is_match else html.escape(lines[i])
            rows.append(
                f'<tr class="{"match" if is_match else "context"}">'
                f'<td class="line-no">{i + 1}</td>'
                f'<td class="line-content">{content}</td>'
                f'</tr>'
            )
    return f'<div class="log-container"><table class="log-table">{"".join(rows)}</table></div>'
