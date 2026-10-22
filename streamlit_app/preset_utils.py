"""兩個介面共用的設定檔格式與舊版相容規則。"""

import datetime
import re


CONTEXT_OPTIONS = [0, 3, 5, 10, 20, 50]
MODE_LABELS = {"or": "符合任一 (OR)", "and": "符合全部 (AND)"}


def normalize_preset(data):
    """完整驗證後回傳標準格式，避免匯入到一半才發現錯誤。"""
    if not isinstance(data, dict):
        raise ValueError("設定檔必須是 JSON 物件")
    version = data.get("schemaVersion", 1)
    if type(version) is not int or version != 1:
        raise ValueError("不支援此設定檔版本")

    keywords = data.get("keywords", [])
    if not isinstance(keywords, list) or any(not isinstance(k, str) for k in keywords):
        raise ValueError("keywords 必須是字串陣列")

    mode = data.get("matchMode", data.get("match_mode", "or"))
    mode = {label: key for key, label in MODE_LABELS.items()}.get(mode, mode) if isinstance(mode, str) else None
    if mode not in MODE_LABELS:
        raise ValueError("比對條件必須是 or 或 and")

    context = data.get("contextLines", data.get("context_lines", 5))
    if isinstance(context, str) and context.isascii() and context.isdigit():
        context = int(context)
    if type(context) is not int or context not in CONTEXT_OPTIONS:
        raise ValueError("上下文行數必須是 0、3、5、10、20 或 50")

    enabled = data.get("enableTimeFilter", data.get("enable_time", False))
    if type(enabled) is not bool:
        raise ValueError("時間過濾開關必須是布林值")

    # 以下為新增的選填欄位，舊設定檔沒有時使用預設值
    flags = {}
    for name, label in [("useRegex", "正規表達式"), ("caseSensitive", "區分大小寫")]:
        flags[name] = data.get(name, False)
        if type(flags[name]) is not bool:
            raise ValueError(f"{label}開關必須是布林值")
    exclude = data.get("excludeKeyword", "")
    if not isinstance(exclude, str):
        raise ValueError("excludeKeyword 必須是字串")

    times = {}
    for canonical, legacy in [("startTime", "start_time"), ("endTime", "end_time")]:
        value = data.get(canonical, data.get(legacy, ""))
        if not isinstance(value, str):
            raise ValueError("時間必須是日期時間字串")
        if value:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?", value):
                raise ValueError("時間格式必須為 YYYY-MM-DDTHH:MM:SS")
            try:
                value = datetime.datetime.fromisoformat(value).isoformat(timespec="seconds")
            except ValueError as exc:
                raise ValueError("設定檔包含無效的日期時間") from exc
        times[canonical] = value
    if times["startTime"] and times["endTime"] and times["startTime"] > times["endTime"]:
        raise ValueError("開始時間不可晚於結束時間")

    return {
        "schemaVersion": 1,
        "keywords": [k.strip() for k in keywords if k.strip()],
        "matchMode": mode,
        "contextLines": context,
        "enableTimeFilter": enabled,
        **times,
        **flags,
        "excludeKeyword": exclude.strip(),
    }
