"""檔案切換、設定往返、編碼與啟動失敗的行為回歸測試。"""

import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from streamlit_app.preset_utils import normalize_preset
import launch


class AppRegressionTests(unittest.TestCase):
    def setUp(self):
        self.uploads = {}
        self.downloads = {}
        original_uploader = st.file_uploader
        original_download = st.download_button
        original_sidebar_download = st.sidebar.download_button

        def uploader(label, *args, **kwargs):
            # AppTest 不支援上傳操作；保留原元件，僅替換它回傳的檔案。
            original_uploader(label, *args, **kwargs)
            return self.uploads.get(kwargs.get("key", label))

        def download(label, *args, **kwargs):
            self.downloads[label] = kwargs.get("data")
            return original_download(label, *args, **kwargs)

        def sidebar_download(label, *args, **kwargs):
            self.downloads[label] = kwargs.get("data")
            return original_sidebar_download(label, *args, **kwargs)

        self.addCleanup(patch.stopall)
        patch.object(st, "file_uploader", uploader).start()
        patch.object(st, "download_button", download).start()
        patch.object(st.sidebar, "download_button", sidebar_download).start()
        self.app = AppTest.from_file(str(ROOT / "streamlit_app/app.py")).run()
        self.assertHealthy()

    def assertHealthy(self):
        self.assertEqual(len(self.app.exception), 0, str(self.app.exception))

    def upload(self, name, content, preset=False):
        data = content.encode("utf-8") if isinstance(content, str) else content
        key = "preset_file_uploader" if preset else f"log_file_{self.app.session_state.log_upload_generation}"
        self.uploads[key] = SimpleNamespace(name=name, getvalue=lambda: data)
        self.app.run()
        self.assertHealthy()

    def preset(self):
        return json.loads(next(data for label, data in self.downloads.items() if "JSON" in label))

    def button(self, label):
        return next(button for button in self.app.button if label in button.label)

    def test_same_name_new_content_and_clear(self):
        self.upload("server.log", "2026-09-24 10:00:00 ERROR OLD")
        self.upload("server.log", "2026-09-24 11:00:00 ERROR NEW")
        self.assertIn("NEW", self.app.session_state.log_lines[0])
        exported = next(data for label, data in self.downloads.items() if ".txt" in label)
        self.assertIn("NEW", exported)
        self.assertNotIn("OLD", exported)
        self.button("清空資料").click().run()
        self.app.run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state.log_lines, [])
        # 清空後仍可重新選取相同檔名。
        self.upload("server.log", "ERROR AGAIN")
        self.assertEqual(self.app.session_state.log_lines, ["ERROR AGAIN"])

    def test_demo_replaces_upload_and_can_be_cleared(self):
        self.upload("server.log", "ERROR UPLOADED")
        self.button("載入範例").click().run()
        self.app.run()
        self.assertHealthy()
        self.assertEqual(self.app.session_state.file_name, "sample-server.log")
        self.assertNotIn("ERROR UPLOADED", self.app.session_state.log_lines)
        self.button("清空資料").click().run()
        self.assertEqual(self.app.session_state.log_lines, [])

    def test_url_demo_does_not_reload_after_clear(self):
        self.app.query_params["demo"] = "1"
        self.app.run()
        self.assertEqual(self.app.session_state.file_name, "sample-server.log")
        self.button("清空資料").click().run()
        self.app.run()
        self.assertEqual(self.app.session_state.log_lines, [])

    def test_preset_edits_add_delete_are_persistent(self):
        self.upload("preset.json", '{"keywords":["ERROR"]}', preset=True)
        self.app.text_input[0].input("WARN").run()
        self.app.run()
        self.assertEqual(self.app.text_input[0].value, "WARN")
        self.button("新增關鍵字").click().run()
        self.assertEqual(len(self.app.text_input), 2)
        self.app.text_input[1].input("timeout").run()
        self.button("✕").click().run()
        self.app.run()
        self.assertHealthy()
        self.assertEqual([item.value for item in self.app.text_input], ["timeout"])

    def test_round_trip_and_import_before_log(self):
        expected = {
            "schemaVersion": 1, "keywords": ["ERROR", "timeout"], "matchMode": "and",
            "contextLines": 0, "enableTimeFilter": True,
            "startTime": "2026-09-24T10:01:05", "endTime": "2026-09-24T10:02:30",
        }
        self.upload("preset.json", json.dumps(expected), preset=True)
        self.upload("server.log", "2026-09-24 10:00:00 ERROR timeout OLD\n"
                    "2026-09-24 10:01:05 ERROR timeout IN\n"
                    "2026-09-24 10:02:31 ERROR timeout OUT")
        self.assertEqual(self.preset(), expected)
        self.assertTrue(any("**1**" in item.value for item in self.app.markdown if "搜尋結果" in item.value))
        self.app.checkbox(key="enable_time").uncheck().run()
        self.app.run()
        self.app.checkbox(key="enable_time").check().run()
        self.assertEqual(self.preset(), expected)
        self.app.number_input(key="e_sec").set_value(29).run()
        changed = self.preset()
        self.assertEqual(changed["endTime"], "2026-09-24T10:02:29")
        self.uploads.pop("preset_file_uploader")
        self.app.run()
        self.upload("roundtrip.json", json.dumps(changed), preset=True)
        self.assertEqual(self.preset(), changed)

    def test_legacy_preset_restores_mode_context_and_toggle(self):
        legacy = {"keywords": ["WARN"], "match_mode": "符合全部 (AND)",
                  "context_lines": 20, "enable_time": True}
        self.upload("legacy.json", json.dumps(legacy), preset=True)
        self.assertEqual(self.preset()["matchMode"], "and")
        self.assertEqual(self.preset()["contextLines"], 20)
        self.assertTrue(self.preset()["enableTimeFilter"])

    def test_bad_preset_does_not_partially_modify_query(self):
        before = self.preset()
        bad = {"keywords": ["CHANGED"], "matchMode": "and", "contextLines": -1}
        self.upload("bad.json", json.dumps(bad), preset=True)
        self.assertGreater(len(self.app.error), 0)
        self.assertEqual(self.preset(), before)

    def test_encoding_error_blocks_stale_results_and_big5_recovers(self):
        self.upload("old.log", "ERROR OLD")
        self.upload("big5.log", "ERROR 中文錯誤".encode("big5"))
        self.assertGreater(len(self.app.error), 0)
        self.assertFalse(any("log-table\">" in item.value for item in self.app.markdown))
        self.app.selectbox(key="log_encoding").set_value("Big5").run()
        self.assertHealthy()
        self.assertEqual(len(self.app.error), 0)
        self.assertEqual(self.app.session_state.log_lines, ["ERROR 中文錯誤"])

    def test_upload_keeps_query_and_updates_default_time_range(self):
        self.upload("old.log", "2026-09-24 10:00:00 WARN")
        self.app.text_input[0].input("WARN").run()
        self.app.radio(key="match_mode").set_value("符合全部 (AND)").run()
        self.app.checkbox(key="enable_time").check().run()
        self.upload("new.log", "2026-09-25 15:00:00 WARN")
        self.assertEqual(self.app.text_input[0].value, "WARN")
        self.assertTrue(self.app.checkbox(key="enable_time").value)
        self.assertEqual(self.preset()["startTime"], "2026-09-25T15:00:00")
        self.assertEqual(self.preset()["matchMode"], "and")


class PresetValidationTests(unittest.TestCase):
    def test_html_legacy_sample_and_zero_context(self):
        preset = normalize_preset({"keywords": [" ERROR "], "contextLines": "0"})
        self.assertEqual(preset["contextLines"], 0)
        self.assertEqual(preset["keywords"], ["ERROR"])
        sample = json.loads((ROOT / "samples/example-preset.json").read_text(encoding="utf-8"))
        self.assertEqual(normalize_preset(sample)["matchMode"], "and")

    def test_invalid_types_and_ranges(self):
        invalid = [None, [], {"keywords": [1]}, {"matchMode": []}, {"contextLines": True},
                   {"enableTimeFilter": "false"}, {"startTime": "2026-02-30T00:00:00"},
                   {"startTime": "2026-09-25T00:00:00", "endTime": "2026-09-24T00:00:00"},
                   {"schemaVersion": 2}]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                normalize_preset(data)


class LauncherTests(unittest.TestCase):
    def test_dry_run_has_no_install_or_server_side_effects(self):
        with patch.object(launch, "dependency_ready", return_value=False), \
             patch.object(launch.subprocess, "call") as install, \
             patch.object(launch.subprocess, "Popen") as start:
            self.assertEqual(launch.main(["--dry-run"]), 0)
            install.assert_not_called()
            start.assert_not_called()

    def test_install_failure_stops_before_launch(self):
        with patch.object(launch, "dependency_ready", return_value=False), \
             patch.object(launch.subprocess, "call", return_value=7), \
             patch.object(launch.subprocess, "Popen") as start:
            self.assertEqual(launch.main(["--no-browser"]), 7)
            start.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows 批次檔測試")
    def test_batch_fallback_branches_with_safe_stubs(self):
        # 沿用原啟動器流程，僅把外部 Python 呼叫替換為可控的安全命令。
        source = (ROOT / "start.bat").read_text(encoding="utf-8")
        for python_exit, py_exit, expected in [(0, 1, "python"), (1, 0, "py"), (1, 1, None)]:
            with self.subTest(python_exit=python_exit, py_exit=py_exit), tempfile.TemporaryDirectory() as folder:
                fixture = source.replace('python -c "import sys"', f'cmd /d /c exit {python_exit}')
                fixture = fixture.replace('py -c "import sys"', f'cmd /d /c exit {py_exit}')
                fixture = fixture.replace('%PY_CMD% "%~dp0launch.py" %*', 'echo SELECTED=%PY_CMD%')
                fixture = fixture.replace('pause', 'rem pause')
                target = Path(folder) / "fixture.cmd"
                target.write_bytes(fixture.replace('\n', '\r\n').encode("ascii"))
                result = subprocess.run([os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(target), "--dry-run"], capture_output=True, text=True)
                if expected:
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn(f"SELECTED={expected}", result.stdout)
                else:
                    self.assertEqual(result.returncode, 1)
                    self.assertNotIn("SELECTED=", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
