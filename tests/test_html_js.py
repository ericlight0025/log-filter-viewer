"""在 pytest 中執行 HTML 版的 Node.js 行為測試；未安裝 Node.js 時略過。"""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_html_behaviour():
    node = shutil.which("node")
    if node is None:
        pytest.skip("需要 Node.js 18 以上")
    script = Path(__file__).with_name("test_html.cjs")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
