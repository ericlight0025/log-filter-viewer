import sys
import os
import streamlit as st
import re
import html
import json
import datetime
import uuid
import hashlib

# AppTest 與直接啟動都使用同一份設定檔驗證規則。
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
from preset_utils import CONTEXT_OPTIONS, MODE_LABELS, normalize_preset

# 支援直接使用 `python app.py` 或 `py app.py` 啟動，自動轉接至 Streamlit 服務
if __name__ == "__main__":
    if not st.runtime.exists():
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", __file__, "--server.port", "8686"]
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

# ==============================================================================
# 🎨 佈景主題設定 (支援 Obsidian 黑曜石、GitHub Dark、Dracula、Monokai)
# ==============================================================================
THEMES = {
    "Obsidian (黑曜石)": {
        "container_bg": "#161618",
        "table_bg": "#18181a",
        "match_bg": "#28203d",
        "match_line_no": "#c084fc",
        "context_bg": "#18181a",
        "line_no_color": "#636e7b",
        "line_no_border": "#2c2c32",
        "text_color": "#dcddde",
        "border_color": "#363640",
        "separator_bg": "#1f1d28",
        "separator_color": "#8b7bb0",
        "accent": "#9333ea",
        "palette": ["#9333ea", "#d97706", "#2563eb", "#059669", "#db2777", "#e11d48"]
    },
    "GitHub Dark (經典藍灰)": {
        "container_bg": "#0d1117",
        "table_bg": "#0d1117",
        "match_bg": "#161f30",
        "match_line_no": "#f0883e",
        "context_bg": "#0d1117",
        "line_no_color": "#6e7681",
        "line_no_border": "#21262d",
        "text_color": "#c9d1d9",
        "border_color": "#30363d",
        "separator_bg": "#161b22",
        "separator_color": "#484f58",
        "accent": "#58a6ff",
        "palette": ["#8957e5", "#b08800", "#1f6feb", "#238636", "#bf4b8a", "#da3633"]
    },
    "Dracula (吸血鬼)": {
        "container_bg": "#282a36",
        "table_bg": "#282a36",
        "match_bg": "#44475a",
        "match_line_no": "#ff79c6",
        "context_bg": "#282a36",
        "line_no_color": "#6272a4",
        "line_no_border": "#44475a",
        "text_color": "#f8f8f2",
        "border_color": "#6272a4",
        "separator_bg": "#21222c",
        "separator_color": "#bd93f9",
        "accent": "#bd93f9",
        "palette": ["#bd93f9", "#ffb86c", "#8be9fd", "#50fa7b", "#ff79c6", "#ff5555"]
    },
    "Monokai (高對比黑金)": {
        "container_bg": "#272822",
        "table_bg": "#272822",
        "match_bg": "#3e3d32",
        "match_line_no": "#a6e22e",
        "context_bg": "#272822",
        "line_no_color": "#75715e",
        "line_no_border": "#3e3d32",
        "text_color": "#f8f8f2",
        "border_color": "#49483e",
        "separator_bg": "#1e1f1c",
        "separator_color": "#a6e22e",
        "accent": "#f92672",
        "palette": ["#ae81ff", "#e6db74", "#66d9ef", "#a6e22e", "#fd971f", "#f92672"]
    }
}



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


def set_time_range(start, end):
    """保存隱藏的時間條件，並在建立元件前同步元件狀態。"""
    start = start.replace(microsecond=0)
    end = end.replace(microsecond=0)
    st.session_state.time_range = (start, end)
    for prefix, value in [("s", start), ("e", end)]:
        st.session_state[f"{prefix}_date"] = value.date()
        st.session_state[f"{prefix}_time"] = value.time().replace(second=0)
        st.session_state[f"{prefix}_sec"] = value.second


def load_log_content(content, name):
    """集中更新日誌資料與時間索引，保留沒有時間戳記的堆疊行。"""
    lines = content.splitlines()
    line_times = []
    last_time = None
    for line in lines:
        timestamp = parse_time(line)
        if timestamp is not None:
            last_time = timestamp
        line_times.append(last_time)
    valid_times = [t for t in line_times if t is not None]
    st.session_state.update(
        file_name=name, log_lines=lines, line_times=line_times,
        min_time=min(valid_times) if valid_times else None,
        max_time=max(valid_times) if valid_times else None,
    )
    if not st.session_state.get("preset_time_range", False):
        now = datetime.datetime.now().replace(microsecond=0)
        set_time_range(st.session_state.min_time or now,
                       (st.session_state.max_time or now) + datetime.timedelta(seconds=1))


def restore_time_inputs():
    """重新顯示元件時明確還原保存值，避免 Streamlit 沿用舊的初始化值。"""
    if st.session_state.enable_time:
        set_time_range(*st.session_state.time_range)


def reset_uploader():
    """以新 key 重建上傳元件，避免舊檔案在下一輪被重新讀回。"""
    st.session_state.log_upload_generation += 1
    st.session_state.loaded_upload = None
    st.session_state.log_error = ""


def clear_log():
    reset_uploader()
    st.session_state.update(log_lines=[], line_times=[], file_name="", min_time=None, max_time=None)
    st.session_state.log_notice = ""


def load_demo_log():
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
            with open(sample_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            load_log_content(content, "sample-server.log")
            return True
        except Exception:
            return False
    return False


def select_demo_log():
    if load_demo_log():
        reset_uploader()
        st.session_state.log_notice = "已載入範例 sample-server.log！"
    else:
        st.session_state.log_error = "無法讀取 samples/sample-server.log 檔案"


def apply_preset(preset):
    """此函式只在新設定檔匯入時執行，不覆蓋後續的手動調整。"""
    st.session_state.keyword_items = [
        {"id": str(uuid.uuid4()), "val": kw} for kw in (preset["keywords"] or [""])
    ]
    st.session_state.match_mode = MODE_LABELS[preset["matchMode"]]
    st.session_state.context_lines = preset["contextLines"]
    st.session_state.enable_time = preset["enableTimeFilter"]
    start, end = st.session_state.time_range
    if preset["startTime"]:
        start = datetime.datetime.fromisoformat(preset["startTime"])
    if preset["endTime"]:
        end = datetime.datetime.fromisoformat(preset["endTime"])
    st.session_state.preset_time_range = bool(preset["startTime"] or preset["endTime"])
    set_time_range(start, end)

# 初始化 Session State
if "keyword_items" not in st.session_state:
    st.session_state.keyword_items = [{"id": str(uuid.uuid4()), "val": "ERROR"}]

if "log_lines" not in st.session_state:
    st.session_state.log_lines = []
    st.session_state.line_times = []
    st.session_state.file_name = ""
    st.session_state.min_time = None
    st.session_state.max_time = None

for state_key, default in {
    "log_upload_generation": 0, "loaded_upload": None, "log_error": "", "log_notice": "",
    "imported_preset": None, "preset_error": "", "preset_time_range": False,
    "match_mode": MODE_LABELS["or"], "context_lines": 5, "enable_time": False,
}.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default
if "time_range" not in st.session_state:
    initial_time = datetime.datetime.now().replace(microsecond=0)
    set_time_range(initial_time, initial_time + datetime.timedelta(seconds=1))

# 若 URL 帶有 ?demo=1 且尚未載入日誌，自動載入範例檔 (方便預覽與截圖)
if st.query_params.get("demo") == "1" and not st.session_state.get("demo_initialized", False):
    load_demo_log()
    st.session_state.demo_initialized = True

# ==============================================================================
# 側邊欄：檔案載入與預設條件管理
# ==============================================================================
with st.sidebar:
    st.header("📂 檔案與設定")
    
    # 選擇日誌閱讀主題 (預設為 Obsidian 黑曜石風格)
    st.subheader("🎨 日誌主題 (Theme)")
    selected_theme_name = st.selectbox(
        "選擇閱讀主題",
        options=list(THEMES.keys()),
        index=0,
        help="支援 Obsidian (黑曜石)、GitHub Dark、Dracula、Monokai 配色"
    )
    theme = THEMES[selected_theme_name]

    st.divider()

    log_encoding = st.selectbox("日誌文字編碼", ["UTF-8", "Big5", "GB18030", "UTF-16"], key="log_encoding")
    uploaded_file = st.file_uploader(
        "上傳 Log 檔案", type=None, key=f"log_file_{st.session_state.log_upload_generation}",
        help="支援 .log, .txt 或任何伺服器日誌檔；解碼失敗時請選擇正確的文字編碼"
    )
    
    # 快捷載入預設範例檔
    col_demo, col_clear = st.columns(2)
    with col_demo:
        st.button("📄 載入範例 Log", use_container_width=True, on_click=select_demo_log)

    with col_clear:
        st.button("🗑️ 清空資料", use_container_width=True, on_click=clear_log)

    # 如果有上傳檔案
    if uploaded_file is not None:
        raw_bytes = uploaded_file.getvalue()
        upload_id = (uploaded_file.name, getattr(uploaded_file, "file_id", None),
                     hashlib.sha256(raw_bytes).hexdigest(), log_encoding)
        if upload_id != st.session_state.loaded_upload:
            try:
                codec = {"UTF-8": "utf-8-sig", "Big5": "big5", "GB18030": "gb18030", "UTF-16": "utf-16"}[log_encoding]
                content = raw_bytes.decode(codec)
                load_log_content(content, uploaded_file.name)
                st.session_state.loaded_upload = upload_id
                st.session_state.log_error = ""
                st.session_state.log_notice = ""
            except UnicodeError:
                st.session_state.log_error = f"無法以 {log_encoding} 解碼「{uploaded_file.name}」，請選擇正確編碼。尚未載入此檔案。"
    else:
        st.session_state.loaded_upload = None

    if st.session_state.log_notice:
        st.success(st.session_state.log_notice)
    if st.session_state.log_error:
        st.error(st.session_state.log_error)

    st.divider()

    # 條件 Presets (匯入 / 匯出)
    st.subheader("💾 條件設定檔 (Preset)")
    preset_file = st.file_uploader("匯入設定 (JSON)", type=["json"], key="preset_file_uploader")
    if preset_file is not None:
        preset_bytes = preset_file.getvalue()
        preset_id = (getattr(preset_file, "file_id", None), hashlib.sha256(preset_bytes).hexdigest())
        if preset_id != st.session_state.imported_preset:
            st.session_state.imported_preset = preset_id
            try:
                preset = normalize_preset(json.loads(preset_bytes.decode("utf-8-sig")))
                apply_preset(preset)
                st.session_state.preset_error = ""
                st.success("已成功匯入查詢條件！")
            except (ValueError, UnicodeError) as e:
                st.session_state.preset_error = f"解析設定檔失敗: {e}"
        if st.session_state.preset_error:
            st.error(st.session_state.preset_error)
    else:
        st.session_state.imported_preset = None
        st.session_state.preset_error = ""

# 動態產生主題 CSS
theme_palette_rules = "\n".join([f".kw-color-{i}, .highlight-{i} {{ background: {theme['palette'][i]} !important; color: #fff !important; }}" for i in range(6)])

st.markdown(f"""
<style>
  .block-container {{
    padding-top: 1.5rem;
    padding-bottom: 2rem;
  }}
  
  .kw-badge {{
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
  }}

  {theme_palette_rules}

  .highlight {{
    border-radius: 4px;
    padding: 1px 5px;
    font-weight: 600;
  }}

  .log-container {{
    border: 1px solid {theme['border_color']};
    border-radius: 8px;
    background: {theme['container_bg']};
    overflow-x: auto;
    margin-top: 12px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
  }}

  .log-table {{
    width: 100%;
    border-collapse: collapse;
    font-family: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 13px;
    line-height: 1.55;
    color: {theme['text_color']};
    background: {theme['table_bg']};
  }}

  .log-table tr {{
    border-bottom: 1px solid {theme['border_color']}33;
  }}

  .log-table tr.context {{
    background: {theme['context_bg']};
  }}

  .log-table tr.match {{
    background: {theme['match_bg']} !important;
  }}

  .log-table tr.separator td {{
    background: {theme['separator_bg']};
    text-align: center;
    color: {theme['separator_color']};
    font-size: 12px;
    padding: 5px 0;
    user-select: none;
    letter-spacing: 4px;
    border-top: 1px dashed {theme['border_color']};
    border-bottom: 1px dashed {theme['border_color']};
  }}

  .log-table .line-no {{
    width: 75px;
    min-width: 75px;
    text-align: right;
    padding: 3px 12px;
    color: {theme['line_no_color']};
    user-select: none;
    vertical-align: top;
    border-right: 1px solid {theme['line_no_border']};
    background: {theme['container_bg']};
  }}

  .log-table tr.match .line-no {{
    color: {theme['match_line_no']} !important;
    font-weight: 700;
  }}

  .log-table .line-content {{
    padding: 3px 14px;
    white-space: pre-wrap;
    word-break: break-all;
  }}
</style>
""", unsafe_allow_html=True)


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
        key="match_mode",
        label_visibility="collapsed"
    )

# ------------------------------------------------------------------------------
# 2. 時間區間過濾與 Context 設定
# ------------------------------------------------------------------------------
col_time_toggle, col_context = st.columns([6, 4])

with col_time_toggle:
    enable_time = st.checkbox("🕒 啟用時間區間過濾 (精確至秒)", key="enable_time", on_change=restore_time_inputs)

with col_context:
    context_lines = st.selectbox(
        "前後上下文行數",
        options=CONTEXT_OPTIONS,
        index=2,
        key="context_lines",
        format_func=lambda x: f"±{x} 行" if x > 0 else "0 行 (僅命中行)"
    )

# 若啟用時間過濾，顯示開始與結束時間選擇器
start_dt, end_dt = None, None
if enable_time:
    t_col1, t_col2 = st.columns(2)
    # 元件被隱藏時 Streamlit 會清理其 key，從保存的時間範圍恢復。
    if "s_date" not in st.session_state or "e_date" not in st.session_state:
        set_time_range(*st.session_state.time_range)

    with t_col1:
        c1, c2, c3 = st.columns([4, 4, 2])
        with c1:
            s_date = st.date_input("開始日期", value=None, key="s_date")
        with c2:
            s_time = st.time_input("開始時間 (時:分)", value=None, step=60, key="s_time")
        with c3:
            s_sec = st.number_input("秒", min_value=0, max_value=59, value=None, step=1, key="s_sec")
        if s_date is not None and s_time is not None and s_sec is not None:
            start_dt = datetime.datetime.combine(s_date, s_time.replace(second=int(s_sec)))

    with t_col2:
        c4, c5, c6 = st.columns([4, 4, 2])
        with c4:
            e_date = st.date_input("結束日期", value=None, key="e_date")
        with c5:
            e_time = st.time_input("結束時間 (時:分)", value=None, step=60, key="e_time")
        with c6:
            e_sec = st.number_input("秒", min_value=0, max_value=59, value=None, step=1, key="e_sec")
        if e_date is not None and e_time is not None and e_sec is not None:
            end_dt = datetime.datetime.combine(e_date, e_time.replace(second=int(e_sec)))
    if start_dt is not None and end_dt is not None:
        st.session_state.time_range = (start_dt, end_dt)

# 匯出條件 Preset 按鈕
current_kws = [item["val"].strip() for item in st.session_state.keyword_items if item["val"].strip()]
preset_payload = {
    "schemaVersion": 1,
    "keywords": current_kws,
    "matchMode": next(key for key, label in MODE_LABELS.items() if label == match_mode),
    "contextLines": context_lines,
    "enableTimeFilter": enable_time,
    "startTime": st.session_state.time_range[0].isoformat(timespec="seconds"),
    "endTime": st.session_state.time_range[1].isoformat(timespec="seconds"),
}
st.sidebar.download_button(
    "💾 下載目前條件設定檔 (JSON)",
    data=json.dumps(preset_payload, ensure_ascii=False, indent=2),
    file_name=f"log_preset_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    mime="application/json",
    disabled=(st.session_state.time_range[0] > st.session_state.time_range[1]
              or (enable_time and (start_dt is None or end_dt is None))),
    use_container_width=True
)

st.divider()

if st.session_state.log_error:
    st.warning("請先修正新檔案的文字編碼，避免誤用先前檔案的搜尋結果。")
    st.stop()
if enable_time and (start_dt is None or end_dt is None):
    st.error("請填寫完整的開始與結束日期時間。")
    st.stop()
if enable_time and start_dt > end_dt:
    st.error("開始時間不可晚於結束時間。")
    st.stop()

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
