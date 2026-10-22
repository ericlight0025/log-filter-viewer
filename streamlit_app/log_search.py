"""搜尋、區間合併與渲染的純函式，不依賴 Streamlit，方便單元測試。"""

import datetime
import html
import re


# HTML 版與 Streamlit 版共用的展示上限（含上下文、合併後的實際行數）
MAX_DISPLAY_ROWS = 50_000
SEPARATOR_TEXT = "-" * 70

# 支援 Log4j / Spring / Linux 常見時間格式 (包含逗號毫秒)
TIME_REGEX = re.compile(r'(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)')
# Apache / Nginx access log：[22/Oct/2026:14:00:00 +0800]，時區不換算
APACHE_REGEX = re.compile(r'(\d{2})/([A-Z][a-z]{2})/(\d{4}):(\d{2}):(\d{2}):(\d{2})')
# syslog：行首的 Oct 22 14:00:00（可帶 <PRI>），沒有年份
SYSLOG_REGEX = re.compile(r'(?:<\d{1,3}>)?([A-Z][a-z]{2}) {1,2}(\d{1,2}) (\d{2}):(\d{2}):(\d{2})')
MONTHS = {name: idx for idx, name in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_time(line: str, default_year=None):
    """解析行首附近的時間戳記為 datetime 物件；syslog 沒有年份時使用 default_year。"""
    if not line:
        return None
    prefix = line[:120]
    match = TIME_REGEX.search(prefix)
    if match:
        raw_str = match.group(1).replace(',', '.').replace('/', '-')
        if len(raw_str) >= 19 and raw_str[10] == ' ':
            raw_str = raw_str[:10] + 'T' + raw_str[11:]
        try:
            return datetime.datetime.fromisoformat(raw_str)
        except ValueError:
            return None
    match = APACHE_REGEX.search(prefix)
    if match and match.group(2) in MONTHS:
        day, month, year, hour, minute, second = match.groups()
        return _safe_datetime(year, MONTHS[month], day, hour, minute, second)
    match = SYSLOG_REGEX.match(prefix)
    if match and match.group(1) in MONTHS:
        month, day, hour, minute, second = match.groups()
        year = default_year or datetime.date.today().year
        return _safe_datetime(year, MONTHS[month], day, hour, minute, second)
    return None


def _safe_datetime(*parts):
    try:
        return datetime.datetime(*map(int, parts))
    except ValueError:
        return None


def index_times(lines, default_year=None):
    """建立每行的時間索引；沒有時間戳記的堆疊行沿用前一行的時間。"""
    line_times = []
    last_time = None
    for line in lines:
        timestamp = parse_time(line, default_year)
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


def compile_terms(terms, use_regex=False, case_sensitive=False):
    """回傳每個關鍵字的判斷函式；正規表達式語法錯誤時拋出 re.error。

    非正規表達式且不分大小寫時，判斷函式預期收到已轉小寫的行。
    """
    if use_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        return [re.compile(term, flags).search for term in terms]
    if not case_sensitive:
        terms = [term.lower() for term in terms]
    return [lambda text, term=term: term in text for term in terms]


def find_matches(lines, line_times, keywords, is_and, start=None, end=None,
                 exclude=(), use_regex=False, case_sensitive=False):
    """回傳命中的行號 (0-based)；沒有關鍵字時為純時間過濾模式，符合任一排除條件的行一律略過。"""
    include = compile_terms(keywords, use_regex, case_sensitive)
    excluded = compile_terms(exclude, use_regex, case_sensitive)
    fold = not use_regex and not case_sensitive
    check = all if is_and else any
    time_filter = start is not None and end is not None
    matches = []
    for i, line in enumerate(lines):
        if time_filter:
            t = line_times[i]
            if t is None or not (start <= t <= end):
                continue
        text = line.lower() if fold else line
        if include and not check(match(text) for match in include):
            continue
        if any(match(text) for match in excluded):
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


def build_highlighter(terms, use_regex=False, case_sensitive=False):
    """terms 為 (關鍵字, 色彩索引)；正規表達式只編譯一次，回傳逐行高亮函式。

    每個關鍵字包在具名群組中，由 lastgroup 找回顏色；命中片段與其餘文字分別跳脫，避免 HTML 實體被破壞。
    """
    colors = {}
    for text, color in terms:
        colors.setdefault(text if case_sensitive or use_regex else text.lower(), color)
    if not colors:
        return html.escape

    patterns = list(colors)
    if not use_regex:
        # 依長度降序排列，讓較長的關鍵字優先命中
        patterns.sort(key=len, reverse=True)
    groups = {f"_kw{i}": colors[p] for i, p in enumerate(patterns)}
    combined = re.compile(
        "|".join(f"(?P<_kw{i}>{p if use_regex else re.escape(p)})" for i, p in enumerate(patterns)),
        0 if case_sensitive else re.IGNORECASE,
    )

    def highlight(raw_text):
        out = []
        pos = 0
        for match in combined.finditer(raw_text):
            if match.start() == match.end():
                continue
            out.append(html.escape(raw_text[pos:match.start()]))
            color = groups.get(match.lastgroup, 0)
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
