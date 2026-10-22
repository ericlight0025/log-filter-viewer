"""搜尋、區間合併與渲染的純函式，不依賴 Streamlit，方便單元測試。"""

import datetime
import html
import re
import time

# 使用者自訂的正規表達式交給 regex 套件執行：語法與 re 相容，且支援逾時，
# 避免 (a+)+$ 這類巢狀量詞讓整個服務卡死（ReDoS）。固定字串關鍵字仍用內建 re。
import regex


# HTML 版與 Streamlit 版共用的展示上限（含上下文、合併後的實際行數）
MAX_DISPLAY_ROWS = 50_000
# 單行比對逾時與整次搜尋／高亮的總時間預算（秒）
REGEX_LINE_TIMEOUT = 2.0
SEARCH_TIME_LIMIT = 15.0
# 使用者 regex 的語法錯誤可能來自 re 或 regex 套件
RegexError = (re.error, regex.error)


class SearchTimeout(TimeoutError):
    """正規表達式執行超過時間預算；訊息可直接顯示給使用者。"""

    def __init__(self, what="搜尋"):
        super().__init__(f"正規表達式{what}逾時（超過 {SEARCH_TIME_LIMIT:g} 秒），"
                         "請簡化表達式，避免巢狀量詞如 (a+)+，或縮小搜尋範圍。")


class _Deadline:
    """每隔一批行檢查一次總時間預算，檢查成本遠低於逐行比對。"""

    def __init__(self, what, limit=SEARCH_TIME_LIMIT, every=2048):
        self.what, self.deadline, self.every, self.count = what, time.monotonic() + limit, every, 0

    def tick(self):
        self.count += 1
        if self.count % self.every == 0 and time.monotonic() > self.deadline:
            raise SearchTimeout(self.what)
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
        flags = 0 if case_sensitive else regex.IGNORECASE
        compiled = [regex.compile(term, flags) for term in terms]
        return [lambda text, pat=pat: pat.search(text, timeout=REGEX_LINE_TIMEOUT) for pat in compiled]
    if not case_sensitive:
        terms = [term.lower() for term in terms]
    return [lambda text, term=term: term in text for term in terms]


def find_matches(lines, line_times, keywords, is_and, start=None, end=None,
                 exclude=(), use_regex=False, case_sensitive=False):
    """回傳命中的行號 (0-based)；沒有關鍵字時為純時間過濾模式，符合任一排除條件的行一律略過。

    正規表達式模式下超過時間預算會拋出 SearchTimeout。
    """
    include = compile_terms(keywords, use_regex, case_sensitive)
    excluded = compile_terms(exclude, use_regex, case_sensitive)
    fold = not use_regex and not case_sensitive
    check = all if is_and else any
    time_filter = start is not None and end is not None
    deadline = _Deadline("搜尋") if use_regex else None
    matches = []
    try:
        for i, line in enumerate(lines):
            if deadline:
                deadline.tick()
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
    except TimeoutError as exc:
        # regex 套件的單行逾時也以同一種錯誤回報
        raise SearchTimeout("搜尋") from exc
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
    source = "|".join(f"(?P<_kw{i}>{p if use_regex else re.escape(p)})" for i, p in enumerate(patterns))
    if use_regex:
        combined = regex.compile(source, 0 if case_sensitive else regex.IGNORECASE)
        find_all = lambda text: combined.finditer(text, timeout=REGEX_LINE_TIMEOUT)
    else:
        combined = re.compile(source, 0 if case_sensitive else re.IGNORECASE)
        find_all = combined.finditer
    deadline = _Deadline("高亮", every=256) if use_regex else None

    def highlight(raw_text):
        out = []
        pos = 0
        try:
            if deadline:
                deadline.tick()
            for match in find_all(raw_text):
                if match.start() == match.end():
                    continue
                out.append(html.escape(raw_text[pos:match.start()]))
                color = groups.get(match.lastgroup, 0)
                out.append(f'<span class="highlight highlight-{color}">{html.escape(match.group(0))}</span>')
                pos = match.end()
        except TimeoutError as exc:
            raise SearchTimeout("高亮") from exc
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
