import sys
import os
import streamlit as st
import re
import html
import json
import datetime
import uuid

# 支援直接使用 `python app.py` 或 `py app.py` 啟動，自動轉接至 Streamlit 服務
if __name__ == "__main__":
    if not st.runtime.exists():
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", __file__, "--server.port", "6666"]
        sys.exit(stcli.main())

# ==============================================================================
# 頁面基本設定
# ==============================================================================
st.set_page_config(
    page_title="Log Filter Viewer",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自訂深色日誌閱讀器樣式
st.markdown("""
<style>
  /* 隱藏部分 Streamlit 預設留白 */
  .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
  }
  
  /* 關鍵字編號標籤色彩 (6色循環) */
  .kw-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 38px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    color: #fff;
    user-select: none;
    margin-right: 4px;
  }
  .kw-color-0, .highlight-0 { background: #8957e5; color: #fff; } /* 紫 */
  .kw-color-1, .highlight-1 { background: #b08800; color: #fff; } /* 琥珀 */
  .kw-color-2, .highlight-2 { background: #1f6feb; color: #fff; } /* 藍 */
  .kw-color-3, .highlight-3 { background: #238636; color: #fff; } /* 綠 */
  .kw-color-4, .highlight-4 { background: #bf4b8a; color: #fff; } /* 粉 */
  .kw-color-5, .highlight-5 { background: #da3633; color: #fff; } /* 紅 */

  .highlight {
    border-radius: 3px;
    padding: 1px 4px;
    font-weight: 600;
  }

  /* Log 表格容器 */
  .log-container {
    border: 1px solid #30363d;
    border-radius: 8px;
    background: #0d1117;
    overflow-x: auto;
    margin-top: 12px;
  }

  .log-table {
    width: 100%;
    border-collapse: collapse;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 13px;
    line-height: 1.5;
    color: #c9d1d9;
  }

  .log-table tr {
    border-bottom: 1px solid #161b22;
  }

  .log-table tr.context {
    background: #0d1117;
  }

  .log-table tr.match {
    background: #161f30;
  }

  .log-table tr.separator td {
    background: #161b22;
    text-align: center;
    color: #484f58;
    font-size: 12px;
    padding: 4px 0;
    user-select: none;
    letter-spacing: 4px;
  }

  .log-table .line-no {
    width: 75px;
    min-width: 75px;
    text-align: right;
    padding: 3px 12px;
    color: #6e7681;
    user-select: none;
    vertical-align: top;
    border-right: 1px solid #21262d;
    background: inherit;
  }

  .log-table tr.match .line-no {
    color: #f0883e;
    font-weight: 700;
  }

  .log-table .line-content {
    padding: 3px 14px;
    white-space: pre-wrap;
    word-break: break-all;
  }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# 時間解析與工具函式
# ==============================================================================
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
        except Exception:
            pass
    return None

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

def safe_highlight(raw_text: str, keywords: list):
    """使用 Regex Split 分割文字，100% 避免 HTML 實體被破壞的置換演算法"""
    valid_kws = [k.strip() for k in keywords if k.strip()]
    if not valid_kws:
        return html.escape(raw_text)

    # 建立關鍵字元資訊 (依長度降序排列)
    unique_kws = list(dict.fromkeys(valid_kws))
    unique_kws.sort(key=lambda s: len(s), reverse=True)

    # 建構含有單一 Capture Group 的正規表達式
    escaped_patterns = [re.escape(k) for k in unique_kws]
    combined_regex = re.compile(f"({'|'.join(escaped_patterns)})", re.IGNORECASE)

    parts = combined_regex.split(raw_text)
    out = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 0:
            out.append(html.escape(part))
        else:
            # 奇數項為關鍵字，找出對應的原始關鍵字顏色索引
            match_lower = part.lower()
            color_idx = 0
            for orig_idx, orig_kw in enumerate(keywords):
                if orig_kw.lower() == match_lower:
                    color_idx = orig_idx % 6
                    break
            out.append(f'<span class="highlight highlight-{color_idx}">{html.escape(part)}</span>')
    return "".join(out)


# ==============================================================================
# 初始化 Session State
# ==============================================================================
if "keyword_items" not in st.session_state:
    st.session_state.keyword_items = [{"id": str(uuid.uuid4()), "val": "ERROR"}]

if "log_lines" not in st.session_state:
    st.session_state.log_lines = []
    st.session_state.line_times = []
    st.session_state.file_name = ""
    st.session_state.min_time = None
    st.session_state.max_time = None


# ==============================================================================
# 側邊欄：檔案載入與預設條件管理
# ==============================================================================
with st.sidebar:
    st.header("📂 檔案與設定")
    
    uploaded_file = st.file_uploader("上傳 Log 檔案", type=None, help="支援 .log, .txt 或任何伺服器日誌檔")
    
    # 快捷載入預設範例檔
    col_demo, col_clear = st.columns(2)
    with col_demo:
        if st.button("📄 載入範例 Log", use_container_width=True):
            sample_candidates = [
                os.path.join(os.path.dirname(__file__), "..", "samples", "sample-server.log"),
                os.path.join(os.path.dirname(__file__), "samples", "sample-server.log"),
                os.path.join(os.getcwd(), "samples", "sample-server.log"),
                "samples/sample-server.log",
                "sample-server.log"
            ]
            sample_path = next((p for p in sample_candidates if os.path.exists(p)), None)
            if sample_path:
                try:
                    with open(sample_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    st.session_state.file_name = "sample-server.log"
                    lines = content.splitlines()
                    st.session_state.log_lines = lines
                    
                    # 解析時間
                    line_times = []
                    last_time = None
                    for l in lines:
                        t = parse_time(l)
                        if t:
                            last_time = t
                        line_times.append(last_time)
                    
                    st.session_state.line_times = line_times
                    valid_ts = [t for t in line_times if t is not None]
                    st.session_state.min_time = min(valid_ts) if valid_ts else None
                    st.session_state.max_time = max(valid_ts) if valid_ts else None
                    st.success("已載入範例 sample-server.log！")
                except Exception as e:
                    st.error(f"讀取範例失敗: {e}")
            else:
                st.error("找不到 samples/sample-server.log 檔案！")

    with col_clear:
        if st.button("🗑️ 清空資料", use_container_width=True):
            st.session_state.log_lines = []
            st.session_state.line_times = []
            st.session_state.file_name = ""
            st.session_state.min_time = None
            st.session_state.max_time = None
            st.rerun()

    # 如果有上傳檔案
    if uploaded_file is not None and uploaded_file.name != st.session_state.file_name:
        content = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        lines = content.splitlines()
        st.session_state.file_name = uploaded_file.name
        st.session_state.log_lines = lines

        line_times = []
        last_time = None
        for l in lines:
            t = parse_time(l)
            if t:
                last_time = t
            line_times.append(last_time)

        st.session_state.line_times = line_times
        valid_ts = [t for t in line_times if t is not None]
        st.session_state.min_time = min(valid_ts) if valid_ts else None
        st.session_state.max_time = max(valid_ts) if valid_ts else None
        st.rerun()

    st.divider()

    # 條件 Presets (匯入 / 匯出)
    st.subheader("💾 條件設定檔 (Preset)")
    preset_file = st.file_uploader("匯入設定 (JSON)", type=["json"], key="preset_file_uploader")
    if preset_file is not None:
        try:
            preset_data = json.loads(preset_file.getvalue().decode("utf-8"))
            if "keywords" in preset_data and isinstance(preset_data["keywords"], list):
                st.session_state.keyword_items = [
                    {"id": str(uuid.uuid4()), "val": kw} for kw in preset_data["keywords"]
                ]
                if not st.session_state.keyword_items:
                    st.session_state.keyword_items = [{"id": str(uuid.uuid4()), "val": ""}]
                st.success("已成功匯入查詢條件！")
        except Exception as e:
            st.error(f"解析設定檔失敗: {e}")


# ==============================================================================
# 主要介面
# ==============================================================================
st.title("📋 Log Filter Viewer")

# 檔案資訊橫幅
if st.session_state.log_lines:
    time_info = ""
    if st.session_state.min_time and st.session_state.max_time:
        time_info = f" | 🕒 時間範圍: `{st.session_state.min_time.strftime('%H:%M:%S')}` ～ `{st.session_state.max_time.strftime('%H:%M:%S')}`"
    st.info(f"📂 目前檔案：**{st.session_state.file_name}** | 共 **{len(st.session_state.log_lines):,}** 行{time_info}")
else:
    st.warning("👈 請先於左側邊欄選擇/上傳 Log 檔案，或點擊「📄 載入範例 Log」開始使用。")

# ------------------------------------------------------------------------------
# 1. 多關鍵字搜尋區 (支援 + 新增關鍵字)
# ------------------------------------------------------------------------------
st.subheader("🔍 關鍵字搜尋")

# 動態生成關鍵字列表
for idx, item in enumerate(st.session_state.keyword_items):
    c_badge, c_input, c_btn = st.columns([0.4, 8.6, 1.0])
    with c_badge:
        st.markdown(f'<div style="padding-top: 4px;"><span class="kw-badge kw-color-{idx % 6}">{idx + 1}</span></div>', unsafe_allow_html=True)
    with c_input:
        item["val"] = st.text_input(
            f"關鍵字 {idx + 1}",
            value=item["val"],
            key=f"kw_input_{item['id']}",
            placeholder=f"輸入關鍵字 (例如: {'ERROR' if idx==0 else 'timeout' if idx==1 else 'OrderService'})...",
            label_visibility="collapsed"
        )
    with c_btn:
        if len(st.session_state.keyword_items) > 1:
            if st.button("✕", key=f"del_{item['id']}", help="移除此關鍵字"):
                st.session_state.keyword_items.pop(idx)
                st.rerun()

col_add_btn, col_mode = st.columns([3, 7])
with col_add_btn:
    if st.button("➕ 新增關鍵字", use_container_width=True):
        st.session_state.keyword_items.append({"id": str(uuid.uuid4()), "val": ""})
        st.rerun()

with col_mode:
    match_mode = st.radio(
        "比對條件",
        options=["符合任一 (OR)", "符合全部 (AND)"],
        horizontal=True,
        label_visibility="collapsed"
    )

# ------------------------------------------------------------------------------
# 2. 時間區間過濾與 Context 設定
# ------------------------------------------------------------------------------
col_time_toggle, col_context = st.columns([6, 4])

with col_time_toggle:
    enable_time = st.checkbox("🕒 啟用時間區間過濾 (精確至秒)", value=False)

with col_context:
    context_lines = st.selectbox(
        "前後上下文行數",
        options=[0, 3, 5, 10, 20, 50],
        index=2,
        format_func=lambda x: f"±{x} 行" if x > 0 else "0 行 (僅命中行)"
    )

# 若啟用時間過濾，顯示開始與結束時間選擇器
start_dt, end_dt = None, None
if enable_time:
    t_col1, t_col2 = st.columns(2)
    default_start = st.session_state.min_time or datetime.datetime.now()
    default_end = (st.session_state.max_time or datetime.datetime.now()) + datetime.timedelta(seconds=1)

    with t_col1:
        c1, c2, c3 = st.columns([4, 4, 2])
        with c1:
            s_date = st.date_input("開始日期", value=default_start.date(), key="s_date")
        with c2:
            s_time = st.time_input("開始時間 (時:分)", value=default_start.time(), step=60, key="s_time")
        with c3:
            s_sec = st.number_input("秒", min_value=0, max_value=59, value=default_start.second, step=1, key="s_sec")
        start_dt = datetime.datetime.combine(s_date, s_time.replace(second=int(s_sec)))

    with t_col2:
        c4, c5, c6 = st.columns([4, 4, 2])
        with c4:
            e_date = st.date_input("結束日期", value=default_end.date(), key="e_date")
        with c5:
            e_time = st.time_input("結束時間 (時:分)", value=default_end.time(), step=60, key="e_time")
        with c6:
            e_sec = st.number_input("秒", min_value=0, max_value=59, value=default_end.second, step=1, key="e_sec")
        end_dt = datetime.datetime.combine(e_date, e_time.replace(second=int(e_sec)))

# 匯出條件 Preset 按鈕
current_kws = [item["val"].strip() for item in st.session_state.keyword_items if item["val"].strip()]
preset_payload = {
    "keywords": current_kws,
    "match_mode": match_mode,
    "context_lines": context_lines,
    "enable_time": enable_time
}
st.sidebar.download_button(
    "💾 下載目前條件設定檔 (JSON)",
    data=json.dumps(preset_payload, ensure_ascii=False, indent=2),
    file_name=f"log_preset_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    mime="application/json",
    use_container_width=True
)

st.divider()

# ==============================================================================
# 搜尋與區間合併邏輯
# ==============================================================================
if not st.session_state.log_lines:
    st.stop()

if not current_kws and not enable_time:
    st.info("💡 請至少輸入一個關鍵字，或勾選「啟用時間區間過濾」以開始分析日誌。")
    st.stop()

# 步驟 1: 找出所有命中的行號 (0-based)
log_lines = st.session_state.log_lines
line_times = st.session_state.line_times
clean_kws = [k.lower() for k in current_kws]
is_and = ("AND" in match_mode)

matches = []
for i, line in enumerate(log_lines):
    # 時間過濾
    if enable_time and start_dt and end_dt:
        t = line_times[i]
        if t:
            if not (start_dt <= t <= end_dt):
                continue
        else:
            continue

    # 關鍵字過濾
    if clean_kws:
        line_lower = line.lower()
        if is_and:
            matched = all(k in line_lower for k in clean_kws)
        else:
            matched = any(k in line_lower for k in clean_kws)
    else:
        matched = True  # 純時間過濾模式

    if matched:
        matches.append(i)

# 顯示統計
col_stat, col_copy = st.columns([7, 3])
with col_stat:
    st.markdown(f"📊 搜尋結果：共命中 **{len(matches):,}** 行")

if not matches:
    st.warning("🤷 找不到符合條件的日誌行。")
    st.stop()

# 步驟 2: 建立 ±context_lines 的區間
total_lines = len(log_lines)
raw_ranges = [
    [max(0, m - context_lines), min(total_lines - 1, m + context_lines)]
    for m in matches
]

# 步驟 3: 合併重疊或連續的區間 (防止重複顯示)
merged_ranges = merge_ranges(raw_ranges)
match_set = set(matches)

# 步驟 4: 產生純文字輸出 (提供下載)
export_text_lines = []
for r_idx, (start, end) in enumerate(merged_ranges):
    if r_idx > 0:
        export_text_lines.append("----------------------------------------------------------------------")
    for line_idx in range(start, end + 1):
        export_text_lines.append(f"{(line_idx + 1):>6} | {log_lines[line_idx]}")

final_export_text = "\n".join(export_text_lines)

with col_copy:
    st.download_button(
        "📋 下載過濾結果 (.txt)",
        data=final_export_text,
        file_name=f"filtered_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        mime="text/plain",
        use_container_width=True
    )

# 步驟 5: 渲染 HTML 表格 (含多色 Safe Highlight)
table_rows = []
for r_idx, (start, end) in enumerate(merged_ranges):
    if r_idx > 0:
        table_rows.append('<tr class="separator"><td colspan="2">⋯⋯⋯⋯⋯⋯</td></tr>')

    for line_idx in range(start, end + 1):
        is_match = (line_idx in match_set)
        row_cls = "match" if is_match else "context"
        
        # 安全高亮
        if is_match and current_kws:
            content_html = safe_highlight(log_lines[line_idx], current_kws)
        else:
            content_html = html.escape(log_lines[line_idx])

        table_rows.append(
            f'<tr class="{row_cls}">'
            f'<td class="line-no">{line_idx + 1}</td>'
            f'<td class="line-content">{content_html}</td>'
            f'</tr>'
        )

final_table_html = f'<div class="log-container"><table class="log-table">{"".join(table_rows)}</table></div>'
st.markdown(final_table_html, unsafe_allow_html=True)
