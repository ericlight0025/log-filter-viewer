# Log Filter Viewer 🔍

> **專為工程師與維運團隊設計的日誌過濾檢視器 (Log Filter Viewer)**  
> 同時提供 **Streamlit 現代 Web 版** 與 **零依賴單一 HTML 版**。解決傳統文字編輯器看大量 Log 時「搜尋關鍵字看不到前後文」以及「前後文重疊時行數重複印出」的痛點。

---

## 📁 專案目錄結構

本專案採用清楚的模組化目錄結構分類管理：

```text
log-filter-viewer/
├── streamlit_app/              # 現代化 Streamlit Web 應用程式
│   └── app.py                  # Streamlit 主程式 (支援自動轉接與雙點擊啟動)
├── standalone_html/            # 零依賴純前端單檔版本 (可離線獨立運作)
│   ├── index.html              # 主頁面
│   └── log-filter.html         # 完整功能單一檔案版
├── samples/                    # 測試範例與預設設定檔
│   ├── sample-server.log       # 247 行 Java 伺服器除錯範例 Log
│   └── example-preset.json     # 關鍵字與查詢條件預設檔範例
├── tests/                      # 自動化驗收測試套件
│   └── test_full.py            # 7 大核心模組端對端自動化測試
├── start.bat                   # Windows 一鍵啟動腳本 (自動開瀏覽器與解除 6666 限制)
├── run.bat                     # Windows 啟動腳本別名
├── requirements.txt            # Python 依賴清單 (streamlit>=1.40.0)
├── LICENSE                     # 完整官方 MIT 開源授權條款
├── .gitignore                  # Git 忽略設定
└── README.md                   # 專案說明文件
```

---

## ✨ 核心特色

1. **🚀 雙架構支援**
   - **Streamlit 現代 Web 版 (`streamlit_app/app.py`)**：支援一鍵啟動，具備直覺的資料互動、檔案即時切換與過濾。
   - **單檔零依賴純前端版 (`standalone_html/index.html`)**：免安裝、免伺服器，雙擊即可在任何瀏覽器秒開，敏感日誌 100% 留在本機。

2. **➕ 多關鍵字搜尋 (OR / AND 條件)**
   - 點擊 `➕` 可動態新增多組關鍵字，每組均有獨立顏色標記。
   - 支援 **符合任一 (OR)** 與 **符合全部 (AND)** 邏輯切換。
   - 不區分大小寫（Case-insensitive contains）。

3. **🕒 精確至秒的時間區間過濾**
   - 載入 Log 時自動解析時間戳記，預先填入檔案的最早與最晚時間。
   - 支援標準 ISO、常見日誌格式與 Java Log4j 毫秒逗號格式（`yyyy-MM-dd HH:mm:ss,SSS`）。
   - 遇到無時間戳記的行（如 Java Exception Stack Trace），自動智慧繼承上一筆時間。

4. **🧠 智慧上下文區間合併（前後 N 行不重複）**
   - 支援自訂前後上下文（±0、±3、±5、±10、±20、±50 行）。
   - **重疊區間自動 Merge**：當第 100 行與第 103 行皆命中時，自動合併為單一區間，**同一行號在畫面上最多只會出現一次**。

5. **🛡️ 終極安全高亮（Anti-Entity Splitting）**
   - 徹底解決傳統 Regex 置換導致 HTML 實體（如 `&amp;`、`<`）被切斷破圖的問題。
   - 命中行（Match）與上下文行（Context）具有不同底色區隔。

6. **📋 一鍵下載與複製**
   - 一鍵將過濾後的結果（含對齊行號與區塊分隔線）輸出為純文字，方便直接貼到 Slack 或 Issue 追蹤系統。

7. **💾 查詢條件匯出與匯入 (Presets)**
   - 可將關鍵字組合、條件、時間區間打包匯出為 JSON 設定檔。
   - 團隊成員可直接匯入設定檔，快速重現除錯查詢條件。

---

## 🚀 快速啟動

### 方式一：Windows 一鍵啟動 (最推薦)

直接在專案根目錄雙擊執行 **`start.bat`**（或 `run.bat`）：
- 自動檢測 Python 環境與補齊依賴套件。
- 自動啟動 Streamlit 服務（Port 6666）。
- 自動開啟 Edge / Chrome 瀏覽器並帶上 `--explicitly-allowed-ports=6666` 參數解除瀏覽器安全阻擋。

### 方式二：手動指令啟動

```bash
# 1. 安裝套件
pip install -r requirements.txt

# 2. 啟動 Streamlit
streamlit run streamlit_app/app.py --server.port 6666

# 或直接使用 Python 執行 (內建自動轉接)
py streamlit_app/app.py
```

### 方式三：純前端單檔版 (免安裝任何環境)

直接雙擊開啟 `standalone_html/index.html` 或 `standalone_html/log-filter.html` 即可使用。

---

## 🧪 自動化測試

本專案附帶完整的端對端自動化測試套件，涵蓋 7 大核心模組：

```bash
python tests/test_full.py
```

---

## 📄 授權條款 (MIT License)

本專案採用 **[MIT License](LICENSE)** 開源授權協議。

```text
MIT License

Copyright (c) 2026 ericlight0025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 授權概要說明：
* 🟢 **允許自由使用**：個人、公司內部或商業專案皆可免費使用。
* 🟢 **允許修改與分發**：可任意修改原始碼、重新打包、發布或整合至其他軟體中。
* 🟡 **唯一義務條件**：分發代碼時，必須保留上述原始版權宣告（Copyright）與授權許可聲明。
* ⚪ **免責條款**：作者不對本軟體的使用結果承擔任何明示或暗示的法律擔保責任。

完整授權內文請參閱根目錄的 [LICENSE](LICENSE) 檔案。
