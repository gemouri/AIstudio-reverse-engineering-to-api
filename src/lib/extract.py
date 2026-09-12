"""Response extraction for MakerSuiteService/GenerateContent — validated against corpus.

Discriminators (validated on thinking_capture.json 03/09):
  answer part  = [null, "text"]                        (len 2)
  thought part = [null, "text", ..., 1]                (len 13, tail flag 1)
  signature    = [null, "", ..., [b64]]               (len 15, tail = thought signature)

Media parts (12/09 image captures verified):
  image part   = [null, null, ["image/jpeg", "<b64>"]]  (mime at [2][0], b64 at [2][1])
  audio part   = [null, null, ["audio/mpeg", "<b64>"]]  (lyria — WAV data-URI in DOM)
  Live API PCM = ["audio/pcm;rate=24000", "<b64>"]      (WebChannel frames [[5,...]])
"""
from __future__ import annotations

import base64
import json


def _walk(node, on_answer, on_thought, on_media=None):
    if isinstance(node, list):
        if len(node) == 2 and node[0] is None and isinstance(node[1], str):
            on_answer(node[1])
            return
        if (len(node) >= 3 and node[0] is None and isinstance(node[1], str)
                and isinstance(node[-1], int) and node[-1] == 1):
            on_thought(node[1])
            return
        # media part: [null, null, ["image/jpeg", "<b64>", ...]]
        if (on_media is not None and len(node) >= 3 and node[0] is None
                and node[1] is None and isinstance(node[2], list)
                and len(node[2]) >= 2 and isinstance(node[2][0], str)
                and isinstance(node[2][1], str)
                and "/" in node[2][0]):
            mime, b64 = node[2][0], node[2][1]
            if mime.startswith(("image/", "audio/", "video/")):
                try:
                    data = base64.b64decode(b64)
                except Exception:
                    data = b""
                on_media(mime, data, node[2][2:] if len(node[2]) > 2 else [])
                return
            # text/plain media-like part → treat as answer (lyria etc.)
            if mime == "text/plain" and node[2][1]:
                on_answer(node[2][1])
                return
        for child in node:
            _walk(child, on_answer, on_thought, on_media)


def extract_answer(body: str) -> str:
    try:
        data = json.loads(body)
    except Exception:
        return ""
    if not isinstance(data, list):
        return ""
    answers = []
    for chunk in data:
        _walk(chunk, answers.append, lambda t: None)
    return "".join(answers)


def extract_media(body: str) -> list[dict]:
    """Generic media parts — [{mime, size, b64, extras}], giữ thứ tự xuất hiện.

    Verified shapes (12/09):
      gemini-3-pro-image : 2× ["image/jpeg", b64]  (2 ảnh/response)
      gemini-3.1-flash-image: 1× ["image/jpeg", b64]
      lyria-3.5          : ["audio/mpeg", b64]
    """
    try:
        data = json.loads(body)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []

    def on_media(mime: str, data_bytes: bytes, extras: list):
        out.append({"mime": mime, "size": len(data_bytes),
                    "b64": base64.b64encode(data_bytes).decode(),
                    "extras": extras})

    for chunk in data:
        _walk(chunk, lambda t: None, lambda t: None, on_media)
    return out


def extract_thinking(body: str) -> str:
    try:
        data = json.loads(body)
    except Exception:
        return ""
    if not isinstance(data, list):
        return ""
    thoughts = []
    for chunk in data:
        _walk(chunk, lambda t: None, thoughts.append)
    return "".join(thoughts)


def extract_usage(body: str) -> dict:
    """Final metadata chunk: [null,null,null,["<ts>", total, ?]]."""
    try:
        data = json.loads(body)
    except Exception:
        return {}
    for chunk in reversed(data):
        try:
            meta = chunk[3]
            if isinstance(meta, list) and isinstance(meta[0], list) and len(meta[0]) >= 3:
                # observed: [23,3,736,...] on thought chunks -> prompt/completion/total
                return {"prompt_tokens": meta[0][0] if isinstance(meta[0][0], int) else 0,
                        "completion_tokens": meta[0][1] if isinstance(meta[0][1], int) else 0,
                        "total_tokens": meta[0][2] if isinstance(meta[0][2], int) else 0}
        except (TypeError, IndexError):
            continue
    return {}


if __name__ == "__main__":
    from pathlib import Path
    CORPUS = Path(r".\corpus")

    print("== validation ==")
    for f, what in (("swap_e2e2_result.json", "list"), ("thinking_capture.json", "list")):
        for e in json.loads((CORPUS / f).read_text(encoding="utf-8")):
            rb = e.get("respBody") or ""
            if not rb:
                continue
            print(f"{f}: answer={extract_answer(rb)!r:.80} thinking={extract_thinking(rb)[:80]!r}")
    for line in (CORPUS / "cdp_net.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("ev") == "req" and "GenerateContent" in r.get("url", "") and r.get("respBody"):
            print(f"cdp_net: answer={extract_answer(r['respBody'])!r}")
