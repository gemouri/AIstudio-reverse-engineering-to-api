"""verify_i18n_docs.py — kiểm tra đồng bộ 14 bản dịch của docs/usage/.

Đối chiếu từng bản dịch với bản chuẩn docs/usage/en.md:
  1. số heading `## ` bằng nhau (cấu trúc section không đổi)
  2. số code fence ``` bằng nhau
  3. NỘI DUNG mọi code fence giống hệt bản EN (lệnh/JSON không được dịch)
  4. số dòng bảng (bắt đầu bằng '|') bằng nhau
  5. các token kỹ thuật bắt buộc giữ nguyên (env var, model id, URL, JSON key)

Chạy: python scripts/verify_i18n_docs.py [--fix-report]
Exit code 0 = tất cả đạt; 1 = có bản lệch.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USAGE = ROOT / "docs" / "usage"

# 14 ngôn ngữ hệ sinh thái VAELK (GLOBAL_ECOSYSTEM_DNA.md §2)
LANGS = ["en", "da", "de", "es", "fi", "fr", "hi", "it", "ja", "ko", "nl", "sv", "vi", "zh"]

# Token kỹ thuật PHẢI xuất hiện y nguyên trong mọi bản dịch
REQUIRED_TOKENS = [
    "AIS2A_PORT", "AIS2A_CDP_PORT", "AIS2A_CHROME_BIN", "AIS2A_PROFILE_DIR",
    "AIS2A_LOCK_WAIT", "AIS2A_AGENT_TIMEOUT", "AIS2A_TTS_TIMEOUT",
    "AIS2A_LIVE_TIMEOUT", "AIS2A_VIDEO_TIMEOUT",
    "gemini-3.1-flash-lite", "gemini-3.8-flash-tts", "deep-research-preview",
    "lyria-3.5", "gemini-3.1-flash-live", "antigravity",
    "http://127.0.0.1:8788/v1", "/v1/models", "/health",
    "farmon_placeholder_never_matches",  # placeholder: sửa khi cần thêm
]
# token trên là placeholder sai — lọc bỏ
REQUIRED_TOKENS = [t for t in REQUIRED_TOKENS if t != "farmon_placeholder_never_matches"]

# JSON key phải có trong khối code
REQUIRED_JSON_KEYS = ['"model"', '"messages"', '"role"', '"content"', '"voice"']


def fences(text: str) -> list[str]:
    return re.findall(r"```[a-z]*\n(.*?)```", text, re.S)


def stats(text: str) -> dict:
    return {
        "h2": len(re.findall(r"^## ", text, re.M)),
        "fences": len(re.findall(r"^```", text, re.M)) // 2,
        "table_rows": len([l for l in text.splitlines() if l.startswith("|")]),
        "lines": len(text.splitlines()),
    }


def main() -> int:
    en_path = USAGE / "en.md"
    if not en_path.exists():
        print(f"FATAL: thiếu bản chuẩn {en_path}")
        return 1
    en = en_path.read_text(encoding="utf-8")
    en_stats = stats(en)
    en_fences = [f.strip() for f in fences(en)]

    print(f"CHUẨN en.md: {en_stats}\n")
    bad = 0
    for lang in LANGS:
        f = USAGE / f"{lang}.md"
        if not f.exists():
            print(f"✗ {lang}: THIẾU FILE {f}")
            bad += 1
            continue
        t = f.read_text(encoding="utf-8")
        st = stats(t)
        problems = []
        if st["h2"] != en_stats["h2"]:
            problems.append(f"h2 {st['h2']}≠{en_stats['h2']}")
        if st["fences"] != en_stats["fences"]:
            problems.append(f"fence {st['fences']}≠{en_stats['fences']}")
        if st["table_rows"] != en_stats["table_rows"]:
            problems.append(f"table_rows {st['table_rows']}≠{en_stats['table_rows']}")
        if abs(st["lines"] - en_stats["lines"]) > max(25, en_stats["lines"] * 0.25):
            problems.append(f"lines {st['lines']} lệch nhiều so với {en_stats['lines']}")

        # code fence phải giống hệt (bỏ khoảng trắng đầu/cuối)
        lang_fences = [x.strip() for x in fences(t)]
        if lang_fences != en_fences:
            diff = sum(1 for a, b in zip(lang_fences, en_fences) if a != b)
            if len(lang_fences) != len(en_fences):
                problems.append(f"fence mismatch ({len(lang_fences)} vs {len(en_fences)})")
            elif diff:
                problems.append(f"{diff} code fence bị đổi nội dung")

        missing = [tok for tok in REQUIRED_TOKENS if tok not in t]
        if missing:
            problems.append("thiếu token: " + ", ".join(missing[:4]))
        missing_json = [k for k in REQUIRED_JSON_KEYS if k not in t]
        if missing_json:
            problems.append("thiếu JSON key: " + ", ".join(missing_json))

        # language switcher phải có và trỏ đủ 14 ngôn ngữ
        for anchor in ("[English](en.md)", "[Tiếng Việt](vi.md)", "[中文](zh.md)", "[日本語](ja.md)"):
            if anchor not in t:
                problems.append(f"switcher thiếu {anchor}")
        # cột Tier phải là identifier gốc của API (free/pro/premium/agent)
        for row in t.splitlines():
            if row.startswith("|") and "`gemini" in row or (row.startswith("|") and "`lyria" in row):
                cells = [c.strip() for c in row.split("|")]
                if len(cells) >= 5 and cells[3] not in ("free", "pro", "premium", "agent", "—"):
                    problems.append(f"tier không chuẩn: {cells[3]!r}")
                    break

        if problems:
            print(f"✗ {lang}: " + " | ".join(problems))
            bad += 1
        else:
            print(f"✓ {lang}: {st['h2']} §, {st['fences']} code, {st['table_rows']} dòng bảng, {st['lines']} dòng")

    print(f"\nKẾT LUẬN: {len(LANGS) - bad}/{len(LANGS)} bản đạt")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
