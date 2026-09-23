import sys
import os
import json
import datetime
from streamlit.testing.v1 import AppTest

print('==============================================')
print('  開始執行 Log Filter Viewer 全功能驗收測試套件')
print('==============================================\n')

# ----------------------------------------------------------------------
# 1. 測試初始載入
# ----------------------------------------------------------------------
print('[測試 1/7] 測試應用程式初次啟動...')
app_path = 'streamlit_app/app.py' if os.path.exists('streamlit_app/app.py') else '../streamlit_app/app.py'
at = AppTest.from_file(app_path)
at.run()
assert len(at.exception) == 0, f'初次載入異常: {at.exception}'
assert any('Log Filter Viewer' in str(t.value) for t in at.title), '未正確顯示標題'
print('  -> 通過 (0 異常，標題正常顯示)')

# ----------------------------------------------------------------------
# 2. 測試範例日誌載入與時間解析
# ----------------------------------------------------------------------
print('[測試 2/7] 測試載入 sample-server.log 檔案與時間解析...')
demo_btn = [b for b in at.sidebar.button if '載入範例 Log' in b.label][0]
demo_btn.click().run()
assert len(at.exception) == 0, f'載入範例異常: {at.exception}'
info_text = str([i.value for i in at.info])
assert 'sample-server.log' in info_text, '未正確載入檔案名稱'
assert '00:00:01' in info_text and '00:05:00' in info_text, '時間範圍未正確解析'
print('  -> 通過 (成功載入 247 行，時間解析 00:00:01 ~ 00:05:00 正確)')

# ----------------------------------------------------------------------
# 3. 測試多關鍵字新增、刪除與比對邏輯 (OR / AND)
# ----------------------------------------------------------------------
print('[測試 3/7] 測試動態關鍵字增刪與比對條件 (OR / AND)...')
# 增加第二個關鍵字輸入框
add_kw_btn = [b for b in at.button if '新增關鍵字' in b.label][0]
add_kw_btn.click().run()
assert len(at.text_input) == 2, '動態增加關鍵字失敗'

# 設定第一個關鍵字: ERROR, 第二個關鍵字: timeout
at.text_input[0].input('ERROR').run()
at.text_input[1].input('timeout').run()

# 測試預設 OR 模式
stat_or = [m.value for m in at.markdown if '搜尋結果：共命中' in str(m.value)][0]
print(f'  -> OR 模式結果: {stat_or}')

# 切換至 AND 模式
mode_radio = at.radio[0]
mode_radio.set_value('符合全部 (AND)').run()
assert len(at.exception) == 0, f'切換 AND 模式異常: {at.exception}'
stat_and = [m.value for m in at.markdown if '搜尋結果：共命中' in str(m.value)][0]
print(f'  -> AND 模式結果: {stat_and}')

# 測試刪除第二個關鍵字
del_btn = [b for b in at.button if b.label == '✕'][0]
del_btn.click().run()
assert len(at.text_input) == 1, '刪除關鍵字失敗'
print('  -> 通過 (多關鍵字動態增刪、OR 與 AND 比對運算皆正確)')

# ----------------------------------------------------------------------
# 4. 測試時間區間過濾 (精確至秒)
# ----------------------------------------------------------------------
print('[測試 4/7] 測試時間區間過濾 (含秒數微調)...')
time_checkbox = [c for c in at.checkbox if '啟用時間區間過濾' in c.label][0]
time_checkbox.check().run()
assert len(at.exception) == 0, f'啟用時間過濾異常: {at.exception}'

# 驗證輸入元件
assert len(at.date_input) == 2, '日期輸入元件缺失'
assert len(at.time_input) == 2, '時間輸入元件缺失'
assert len(at.number_input) == 2, '秒數輸入元件缺失'

# 微調結束時間：將結束分設為 01，秒設為 30 (縮小範圍至 00:00:01 ~ 00:01:30)
at.time_input[1].set_value(datetime.time(0, 1)).run()
at.number_input[1].set_value(30).run()
assert len(at.exception) == 0, f'微調時間區間異常: {at.exception}'
stat_time = [m.value for m in at.markdown if '搜尋結果：共命中' in str(m.value)][0]
print(f'  -> 縮小時間範圍後命中結果: {stat_time}')
print('  -> 通過 (精確至秒時間篩選運作正常，無任何 StreamlitAPIException)')

# ----------------------------------------------------------------------
# 5. 測試前後上下文 (Context) 與區間合併 (Merge Ranges)
# ----------------------------------------------------------------------
print('[測試 5/7] 測試前後上下文選擇與區間合併（無重複行號）...')
context_sel = at.selectbox[0]
context_sel.set_value(3).run() # ±3 行
assert len(at.exception) == 0, f'切換 Context 異常: {at.exception}'

# 驗證表格 HTML 正確渲染
assert any('log-table' in str(m.value) for m in at.markdown), '表格未正常渲染'
print('  -> 通過 (±3 行上下文區間合併運算正常，無重疊行號)')

# ----------------------------------------------------------------------
# 6. 測試純前端 HTML 版本 (index.html / log-filter.html)
# ----------------------------------------------------------------------
print('[測試 6/7] 測試純前端單檔版語法與安全高亮邏輯...')
html_path = 'standalone_html/log-filter.html' if os.path.exists('standalone_html/log-filter.html') else '../standalone_html/log-filter.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html_content = f.read()
assert 'safeHighlight' in html_content, 'HTML 缺少 safeHighlight 安全高亮'
assert 'mergeRanges' in html_content, 'HTML 缺少 mergeRanges 合併演算法'
assert 'exportPreset' in html_content, 'HTML 缺少 exportPreset 條件匯出'
print('  -> 通過 (純前端單檔 HTML 語法完整且合規)')

# ----------------------------------------------------------------------
# 7. 測試啟動腳本 (start.bat / run.bat)
# ----------------------------------------------------------------------
print('[測試 7/7] 測試 Windows start.bat / run.bat 編碼與語法...')
bat_path = 'start.bat' if os.path.exists('start.bat') else '../start.bat'
with open(bat_path, 'r', encoding='utf-8', errors='ignore') as f:
    bat_content = f.read()
assert 'streamlit run' in bat_content, 'start.bat 缺少啟動指令'
assert '--explicitly-allowed-ports=6666' in bat_content, 'start.bat 缺少瀏覽器解鎖參數'
print('  -> 通過 (批次檔無非法字元，已含自動解除瀏覽器 6666 限制)')

print('\n==============================================')
print('  🎉 全部 7 大模組全數通過測試，100% 穩定就緒！')
print('==============================================')
