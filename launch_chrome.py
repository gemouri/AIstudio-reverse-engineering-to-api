#!/usr/bin/env python3
"""launch_chrome.py — start a dedicated Chrome/Chromium with CDP enabled.

The reverse-engineered driver talks to AI Studio through a real, signed-in
Chrome tab via the Chrome DevTools Protocol (CDP). This script launches a
SEPARATE Chrome instance (its own profile dir, so it never touches your
daily browser profile) with remote debugging on.

First run: a normal browser window opens → sign in with your Google account
at https://aistudio.google.com. Session cookies live in the profile dir, so
later runs start signed-in automatically.

Cross-platform: finds Chrome/Chromium/Edge in the usual locations; override
with AIS2A_CHROME_BIN. Debug port defaults to 9333 (AIS2A_CDP_PORT).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

PORT = int(os.environ.get("AIS2A_CDP_PORT", "9333"))
PROFILE = Path(os.environ.get("AIS2A_PROFILE_DIR",
                              Path.home() / ".ais2api" / "chrome-profile"))
AISTUDIO = "https://aistudio.google.com/"

CANDIDATES = {
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ],
}
CANDIDATES["linux"] = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "/usr/bin/google-chrome", "/usr/bin/chromium",
]


def find_browser() -> str:
    custom = os.environ.get("AIS2A_CHROME_BIN")
    if custom and Path(custom).exists():
        return custom
    for path in CANDIDATES.get(sys.platform, CANDIDATES["linux"]):
        if Path(path).exists():
            return path
        if "/" not in path and (w := shutil.which(path)):
            return w
    sys.exit("No Chrome/Chromium/Edge found. Set AIS2A_CHROME_BIN to the binary path.")


def cdp_alive() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            return True
    except OSError:
        return False


def main() -> None:
    if cdp_alive():
        print(f"[launch] CDP already live on :{PORT} — reusing existing browser.")
        return

    bin_path = find_browser()
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [
        bin_path,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run", "--no-default-browser-check",
        AISTUDIO,
    ]
    print(f"[launch] {bin_path}")
    print(f"[launch] profile: {PROFILE}")
    print(f"[launch] CDP port: {PORT}")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # wait for CDP
    for _ in range(40):
        time.sleep(1)
        if cdp_alive():
            print(f"[launch] CDP is up on 127.0.0.1:{PORT}.")
            print("[launch] FIRST RUN? Sign in with your Google account in the")
            print("[launch] browser window that just opened, then start the API:")
            print("[launch]     python start.py")
            return
    sys.exit("[launch] CDP did not come up within 40s — browser crashed? "
             "Close other Chrome instances with the same profile and retry.")


if __name__ == "__main__":
    main()
