#!/usr/bin/env python3
"""start.py — boot the OpenAI-compatible API server.

Prerequisites: a Chrome with CDP on AIS2A_CDP_PORT (default 9333) and an
AI Studio tab signed in. Easiest path:

    python launch_chrome.py   # first run: sign in with your Google account
    python start.py           # API on http://127.0.0.1:8788/v1
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "lib"))
sys.path.insert(0, str(ROOT / "src" / "facade"))

from facade.app import app  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("AIS2A_PORT", "8788"))
    print(f"[start] OpenAI-compatible API on http://127.0.0.1:{port}/v1")
    print(f"[start] CDP target: {os.environ.get('AIS2A_CDP_URL', 'http://127.0.0.1:9333')}")
    app.run(host="127.0.0.1", port=port, threaded=True)
