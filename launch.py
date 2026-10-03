"""Windows 一鍵啟動的依賴檢查、瀏覽器開啟與服務生命週期。"""

import argparse
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent


def dependency_ready():
    try:
        version = importlib.metadata.version("streamlit")
        return tuple(int(part) for part in version.split(".")[:2]) >= (1, 40)
    except (importlib.metadata.PackageNotFoundError, ValueError):
        return False


def open_browser(url):
    """優先使用 Chromium 系瀏覽器，保留既有 6666 連接埠設定。"""
    candidates = [shutil.which("msedge.exe"), shutil.which("chrome.exe")]
    for root_name in ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]:
        base = os.environ.get(root_name)
        if base:
            candidates.extend(str(Path(base) / relative) for relative in [
                "Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"
            ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                subprocess.Popen([candidate, "--explicitly-allowed-ports=6666", url])
                return
            except OSError:
                continue
    webbrowser.open(url)


def wait_until_ready(process, url):
    """確認服務已就緒再開瀏覽器，避免啟動時先顯示連線失敗。"""
    deadline = time.monotonic() + 20
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while process.poll() is None and time.monotonic() < deadline:
        try:
            with opener.open(url + "/_stcore/health", timeout=0.5) as response:
                if response.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.2)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="啟動 Log Filter Viewer")
    parser.add_argument("--dry-run", action="store_true", help="顯示啟動計畫，不安裝套件或啟動服務")
    parser.add_argument("--no-browser", action="store_true", help="只啟動服務")
    args = parser.parse_args(argv)
    command = [sys.executable, "-m", "streamlit", "run", str(ROOT / "streamlit_app/app.py"),
               "--server.port", "6666", "--server.headless", "true", "--server.address", "127.0.0.1"]
    if args.dry_run:
        print("Streamlit ready:", dependency_ready())
        print("Server command:", subprocess.list2cmdline(command))
        return 0
    if not dependency_ready():
        print("Installing project dependencies...", flush=True)
        result = subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], cwd=ROOT)
        if result != 0:
            print("Dependency installation failed; server was not started.", file=sys.stderr)
            return result
    url = "http://localhost:6666"
    print("Starting Log Filter Viewer:", url, flush=True)
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        if not args.no_browser and wait_until_ready(process, url):
            open_browser(url)
        return process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
            process.wait()
        return 130


if __name__ == "__main__":
    sys.exit(main())
