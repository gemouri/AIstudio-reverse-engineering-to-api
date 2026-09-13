"""OpenAI-compatible façade over the CDP driver — FULL AGENT MODE.

Native function calling (validated): OpenAI tools -> Gemini proto inject;
functionCall response -> OpenAI tool_calls. Multi-turn via contents inject.
NO rate caps (user directive). Thinking stream as reasoning_content.
"""
from __future__ import annotations

import json
import os
import re
import time
import threading
import contextlib
from pathlib import Path

from flask import Flask, Response, jsonify, request, stream_with_context

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from replay.driver import CDPError, Driver           # noqa: E402
from extract import extract_answer, extract_thinking, extract_usage, extract_media  # noqa: E402
from extract_interaction import extract_interaction  # noqa: E402
from tools import openai_tools_to_gemini, find_function_calls       # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from registry import BY_ID, REGISTRY, ACTIVE, route as route_model  # noqa: E402

app = Flask(__name__)

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "rate_state.json"
STATE.parent.mkdir(parents=True, exist_ok=True)

# 12/09: farmer = 1 tab Chrome duy nhất — mọi request phải SERIAL.
# Không lock: 2 request chồng nhau → navigate giữa chừng của nhau →
# "did not contain our text" 502 cho người thua (bắt gặp 97/50 quota burn).
FARMER_LOCK = threading.Lock()

# 13/09 hardening (sau incident "mọi model chết im, tab không động tác"):
# 1 thread interaction chết từng giữ FARMER_LOCK vĩnh viễn → mọi request sau
# xếp hàng VÔ HẠN — client không thấy gì, tab Chrome không động. Giờ:
#   - acquire CÓ timeout (env AIS2A_LOCK_WAIT, default 90s) → thua cuộc nhận
#     503 farmer_busy rõ ràng thay vì treo im (client retry được ngay)
#   - /health báo held_model + held_s → nhìn 1 phát biết pipeline đang chạy gì
#   - nhiều session Hermes cùng dùng: serialize qua 1 facade — an toàn
_lock_info = {"model": None, "since": 0.0}


class FarmerBusy(RuntimeError):
    """Farmer pipeline đang bận — request này nhận 503, thử lại sau."""


@contextlib.contextmanager
def farmer_pipeline(model_id: str, wait_s: float | None = None):
    wait = wait_s if wait_s is not None else float(os.environ.get("AIS2A_LOCK_WAIT", "90"))
    if not FARMER_LOCK.acquire(timeout=wait):
        held = round(time.time() - _lock_info["since"], 1) if _lock_info["since"] else -1
        raise FarmerBusy(
            f"farmer pipeline busy (running model={_lock_info['model']} for {held}s) — "
            f"one Chrome tab serves requests serially; retry shortly")
    _lock_info.update(model=model_id, since=time.time())
    try:
        yield
    finally:
        _lock_info.update(model=None, since=0.0)
        FARMER_LOCK.release()

# 12/09 REFACTOR: model routing giờ đọc từ src/facade/registry.py (SSOT).
# Mọi model entry: id/model/protocol/tier/media/thinking/attached.
# MODELS/INTERACTION_MODELS vẫn giữ backward-compat shape {facade_id: models/...}
MODELS = {m["id"]: m["model"] for m in REGISTRY if m["protocol"] == "generate"}
INTERACTION_MODELS = {m["id"]: m["model"] for m in REGISTRY
                      if m["protocol"] == "interaction"}
# 12/09: Interactions API models (omni / deep-research) — đi qua
# generate_interaction() chứ không phải generate() (GenerateContent).
# Server trả 400 "only supports Interactions API" nếu sai cửa.
THINKING_MODELS = {m["id"] for m in REGISTRY if m.get("thinking")}   # lite không có thinking
MEDIA_MODELS = {m["id"] for m in REGISTRY
                if any(x != "text" for x in (m.get("media") or []))}


@app.get("/v1/models")
def models():
    """Model list + tier/protocol metadata (registry SSOT)."""
    from registry import catalog  # lazy import tránh circular
    return jsonify(object="list", data=catalog())


def _count_request():
    try:
        s = {"day": None, "count": 0, "timestamps": []}
        if STATE.exists():
            s = json.loads(STATE.read_text(encoding="utf-8"))
        today = time.strftime("%Y-%m-%d")
        if s.get("day") != today:
            s.update(day=today, count=0, timestamps=[])
        s["count"] = s.get("count", 0) + 1
        STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception:
        pass


def _pcm_to_wav_b64(pcm_b64: str) -> str:
    """PCM 16-bit mono 24kHz (Live API §14.6) → WAV container b64."""
    import base64
    import struct
    raw = base64.b64decode(pcm_b64)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVEfmt " + \
        struct.pack("<IHHIIHH", 16, 1, 1, 24000, 48000, 2, 16) + b"data" + \
        struct.pack("<I", len(raw))
    return base64.b64encode(hdr + raw).decode()


def build_gemini_history(messages: list) -> tuple[str | None, list | None, str]:
    """Build (system, history=None, typed_text) for the waa-binding reality.

    VERIFIED PROTOCOL FACTS (03/09):
      - waa token binds ALL request text contents (payload[1]) — injected
        contents = 403. So history MUST go through the typed text (mint).
      - systemInstruction (payload[5]) and tools (payload[6]) are NOT hashed —
        inject freely.
    Therefore: full conversation transcript (incl. tool calls/results) is typed
    as ONE user turn; system prompt goes into payload[5].
    """
    system_parts = []
    transcript = []
    last_user = None
    pending_tool_outputs = []

    def flush_tools():
        if pending_tool_outputs:
            transcript.append("[TOOL RESULTS]\n" + "\n".join(pending_tool_outputs))
            pending_tool_outputs.clear()

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content") or ""
        tool_calls = m.get("tool_calls") or []

        if role == "system":
            system_parts.append(content)
        elif role == "user":
            flush_tools()
            transcript.append(f"USER: {content}")
            last_user = content
        elif role == "assistant":
            if tool_calls:
                calls_txt = "; ".join(
                    f'{tc.get("function", {}).get("name")}({tc.get("function", {}).get("arguments")})'
                    for tc in tool_calls)
                transcript.append(f"ASSISTANT (tool call): {calls_txt}")
            elif content:
                transcript.append(f"ASSISTANT: {content}")
        elif role == "tool":
            pending_tool_outputs.append(
                f'{m.get("name", "tool")} -> {content}')

    flush_tools()

    system = "\n".join(system_parts) if system_parts else None
    if not transcript:
        typed = last_user or "Continue."
    else:
        # The LAST "USER:" line is the current question — everything else is context.
        # Rebuild: context = all but the final user turn, question = final user turn.
        # Simplest robust form: transcript minus final USER line becomes context
        # (kept in the SAME typed message so the mint covers everything).
        lines = list(transcript)
        question = last_user
        if lines and lines[-1].startswith("USER: ") and question:
            lines[-1] = lines[-1][len("USER: "):]
        typed = "\n\n".join(lines) if lines else (question or "Continue.")
    return system, None, typed


@app.post("/v1/chat/completions")
def chat_completions():
    payload = request.get_json(force=True, silent=True) or {}
    raw_model = payload.get("model") or "gemini-3.8-flash"
    model = raw_model[4:] if raw_model.startswith("asr_") else raw_model
    entry = BY_ID.get(model)
    # 13/09 B3: BY_ID giờ là SSOT dispatch — live/longrunning có branch riêng
    if entry is None:
        return jsonify(error={"message": f"model '{raw_model}' not found",
                              "type": "invalid_request_error"}), 404
    messages = payload.get("messages") or []
    if not messages:
        return jsonify(error={"message": "messages required", "type": "invalid_request_error"}), 400

    # ---- smart quota routing (12/09 registry) ----
    plan = route_model(model)
    if not plan["ok"]:
        code = 429 if "quota" in plan.get("error", "") else 400
        return jsonify(error={"message": plan["error"], "type": "quota_error" if code == 429
                              else "invalid_request_error"}), code
    entry = plan["entry"]

    _count_request()

    # ---- Live API branch (13/09 B3 — bidiGenerateContent WebChannel §14.6) ----
    if entry["protocol"] == "live":
        last_user = next((m.get("content") or "" for m in reversed(messages)
                          if m.get("role") == "user"), "Hello.")
        if not isinstance(last_user, str):   # multimodal content list → flatten text
            last_user = " ".join(p.get("text", "") for p in last_user
                                 if isinstance(p, dict)) or "Hello."
        drv = Driver()
        t0 = time.time()
        try:
            with farmer_pipeline(model):
                out = drv.live_session(last_user, entry["model"],
                                        timeout_s=int(os.environ.get("AIS2A_LIVE_TIMEOUT", "120")))
        except FarmerBusy as e:
            return jsonify(error={"message": str(e), "type": "farmer_busy"}), 503
        except CDPError as e:
            return jsonify(error={"message": f"driver: {e}", "type": "server_error"}), 502
        except Exception as e:
            return jsonify(error={"message": f"driver error: {e}", "type": "server_error"}), 502

        answer = (out.get("text") or "").strip()
        pcm_b64 = out.get("pcm_b64") or ""
        ACTIVE.record(model, cost=1, ok=bool(answer or pcm_b64))
        if not answer and not pcm_b64:
            return jsonify(error={"message": "live session returned no text/audio (schema drift?)",
                                  "type": "server_error"}), 502
        msg = {"role": "assistant", "content": answer or "(voice-only reply)"}
        if pcm_b64:
            msg["media"] = [f"data:audio/wav;base64,{_pcm_to_wav_b64(pcm_b64)}"]
        meta = {"elapsed_s": round(time.time() - t0, 1), "protocol": "live",
                "frames": out.get("frames"), "model_verified": entry["model"],
                "quota_spend": ACTIVE.spend, "quota_budget": ACTIVE.daily_budget}
        return jsonify(
            id=f"chatcmpl-aistudio{int(time.time()*1000)}", object="chat.completion",
            created=int(time.time()), model=model,
            choices=[{"index": 0, "message": msg, "finish_reason": "stop"}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            aistudio_rev_meta=meta,
        )

    # ---- Veo video branch (13/09 B3 — GenerateVideo predictLongRunning §14.2) ----
    if entry["protocol"] == "longrunning":
        last_user = next((m.get("content") or "" for m in reversed(messages)
                          if m.get("role") == "user"), "A calm ocean wave at sunset.")
        if not isinstance(last_user, str):
            last_user = " ".join(p.get("text", "") for p in last_user
                                 if isinstance(p, dict)) or "A calm ocean wave at sunset."
        drv = Driver()
        t0 = time.time()
        try:
            with farmer_pipeline(model):
                out = drv.generate_video(last_user, entry["model"],
                                         timeout_s=int(os.environ.get("AIS2A_VIDEO_TIMEOUT", "600")))
        except FarmerBusy as e:
            return jsonify(error={"message": str(e), "type": "farmer_busy"}), 503
        except CDPError as e:
            return jsonify(error={"message": f"driver: {e}", "type": "server_error"}), 502
        except Exception as e:
            return jsonify(error={"message": f"driver error: {e}", "type": "server_error"}), 502

        ACTIVE.record(model, cost=1, ok=bool(out.get("video_b64") or out.get("video_url")))
        if not out.get("video_b64") and not out.get("video_url"):
            return jsonify(error={"message": "video generation returned no video (quota or slow op? raw: "
                                            + (out.get("raw") or "")[:200] + ")",
                                  "type": "server_error"}), 502
        msg = {"role": "assistant",
               "content": out.get("video_url") or "Video generated — see media field."}
        if out.get("video_b64"):
            msg["media"] = [f"data:{out['video_b64']['mime']};base64,{out['video_b64']['b64']}"]
        meta = {"elapsed_s": round(time.time() - t0, 1), "protocol": "longrunning",
                "request_count": out.get("request_count"),
                "quota_spend": ACTIVE.spend, "quota_budget": ACTIVE.daily_budget}
        return jsonify(
            id=f"chatcmpl-aistudio{int(time.time()*1000)}", object="chat.completion",
            created=int(time.time()), model=model,
            choices=[{"index": 0, "message": msg, "finish_reason": "stop"}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            aistudio_rev_meta=meta,
        )

    # ---- Interactions API branch (omni / deep-research) ----
    # Single-turn: flatten toàn transcript thành 1 prompt typed (waa bind).
    # Extract qua extract_interaction(); reasoning_content = thinking stream.
    if model in INTERACTION_MODELS:
        sys_parts = [m.get("content") or "" for m in messages if m.get("role") == "system"]
        convo = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue
            content = m.get("content") or ""
            tc = m.get("tool_calls") or []
            if role == "user":
                convo.append(f"USER: {content}")
            elif role == "assistant":
                if tc:
                    calls = "; ".join(f'{t.get("function", {}).get("name")}({t.get("function", {}).get("arguments")})' for t in tc)
                    convo.append(f"ASSISTANT (tool call): {calls}")
                elif content:
                    convo.append(f"ASSISTANT: {content}")
            elif role == "tool":
                convo.append(f"[TOOL RESULT] {m.get('name', 'tool')} -> {content}")
        typed = "\n\n".join(
            (["SYSTEM INSTRUCTIONS:\n" + "\n".join(sys_parts)] if sys_parts else []) + convo)

        drv = Driver()
        t0 = time.time()
        # B1-fix (13/09): agent tier cần fetch/process artifacts lớn — 420s
        # hardcode từng timeout giữa response. 600s mặc định + env override.
        agent_timeout = int(os.environ.get("AIS2A_AGENT_TIMEOUT", "600"))
        try:
            with farmer_pipeline(model):
                out = drv.generate_interaction(typed, INTERACTION_MODELS[model],
                                                timeout_s=agent_timeout,
                                                ui_model=entry.get("ui_model"))
        except FarmerBusy as e:
            return jsonify(error={"message": str(e), "type": "farmer_busy"}), 503
        except CDPError as e:
            return jsonify(error={"message": f"driver: {e}", "type": "server_error"}), 502
        except Exception as e:
            return jsonify(error={"message": f"driver error: {e}", "type": "server_error"}), 502

        ix = extract_interaction(out["raw"])
        answer, reasoning = ix["answer"], ix["thinking"]
        # interaction extras: research artifacts (images + sources markdown)
        research_imgs = [f"data:image/png;base64,{b64}" for b64 in ix.get("images") or []]
        research_sources = ix.get("sources") or None
        # quota ledger (interaction — omni/deep-research/antigravity; agent burn theo attached)
        cost = 1
        ACTIVE.record(model, cost=cost, ok=bool(answer or reasoning))
        # Server-side error frame (quota/permission) → đúng semantic HTTP
        if ix["error"]:
            msg = ix["error"]
            code = 429 if "quota" in msg.lower() else 502
            return jsonify(error={"message": f"interaction: {msg}", "type": "server_error"}), code
        if not answer and not reasoning:
            return jsonify(error={"message": "empty interaction response (schema drift?)",
                                  "type": "server_error"}), 502

        created = int(time.time())
        completion_id = f"chatcmpl-aistudio{int(time.time()*1000)}"
        meta = {"elapsed_s": round(time.time() - t0, 1), "requests_sent": out["request_count"],
                "protocol": "interactions", "model_verified": ix["model"]}

        if payload.get("stream"):
            def isse():
                for piece in ([reasoning[i:i+60] for i in range(0, len(reasoning), 60)] if reasoning else []):
                    yield "data: " + json.dumps({
                        "id": completion_id, "object": "chat.completion.chunk", "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"reasoning_content": piece}, "finish_reason": None}],
                    }) + "\n\n"
                for piece in [answer[i:i+40] for i in range(0, len(answer), 40)]:
                    yield "data: " + json.dumps({
                        "id": completion_id, "object": "chat.completion.chunk", "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                    }) + "\n\n"
                yield "data: " + json.dumps({
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }) + "\n\n"
                yield "data: [DONE]\n\n"
            return Response(stream_with_context(isse()), mimetype="text/event-stream")

        msg = {"role": "assistant", "content": answer or None}
        if reasoning:
            msg["reasoning_content"] = reasoning
        if research_imgs:
            msg["media"] = research_imgs
        if research_sources:
            msg["sources"] = research_sources
        return jsonify(
            id=completion_id, object="chat.completion", created=created, model=model,
            choices=[{"index": 0, "message": msg, "finish_reason": "stop"}],
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            aistudio_rev_meta=meta,
        )

    thinking = (payload.get("thinking") or payload.get("reasoning_effort"))
    if isinstance(thinking, str) and thinking.lower() in ("none", "off", "minimal"):
        thinking = "off"
    if thinking in (None, False) and model in THINKING_MODELS:
        thinking = "high"

    # tools: OpenAI -> Gemini proto
    openai_tools = payload.get("tools") or []
    gemini_tools = openai_tools_to_gemini(openai_tools) if openai_tools else None

    system, history, last_user = build_gemini_history(messages)

    drv = Driver()
    t0 = time.time()
    try:
        with farmer_pipeline(model):   # serialize toàn bộ farmer interaction (navigate→type→capture)
            out = drv.generate(last_user, MODELS[model],
                           temperature=payload.get("temperature"),
                           thinking=thinking,
                           tools=gemini_tools,
                           system=system,
                           history=history)
    except FarmerBusy as e:
        return jsonify(error={"message": str(e), "type": "farmer_busy"}), 503
    except CDPError as e:
        return jsonify(error={"message": f"driver: {e}", "type": "server_error"}), 502
    except Exception as e:
        return jsonify(error={"message": f"driver error: {e}", "type": "server_error"}), 502

    answer = extract_answer(out["raw"])
    reasoning = extract_thinking(out["raw"])
    usage = extract_usage(out["raw"])
    tool_calls = find_function_calls(out["raw"])
    media = extract_media(out["raw"]) if model in MEDIA_MODELS else []

    # quota ledger record (registry 12/09) — cost theo tier
    cost = 0 if entry["tier"] == "free" else 1
    ACTIVE.record(model, cost=cost, ok=bool(answer or media or tool_calls))

    # 12/09: error frame server (GenerateContent) — map sang HTTP semantic thay
    # vì rơi xuống "empty response (schema drift?)" mù mịt. Frames observed:
    #   [,[3,"Thinking level MINIMAL…"]]  (leading-comma stream concat)
    #   [[[null,[4,"The prompt could not be submitted…"]…]]]  (policy filter)
    # Bóc bằng regex không-anchors — tìm [N,"msg"] gần đầu payload; N: 3=invalid
    # argument/thinking, 4=prohibited content, 8=quota.
    if not answer and not reasoning and not tool_calls:
        m = re.search(r'\[\s*(?:,\s*)?\[\s*([0-9]+)\s*,\s*"([^"]{1,300})', out["raw"][:3000])
        if m and int(m.group(1)) in (3, 4, 8):
            code, msg = int(m.group(1)), m.group(2)
            # strip markdown link trong msg policy (giữ text)
            msg = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", msg)
            http = 429 if code == 8 else 400
            return jsonify(error={"message": msg, "type": "server_error",
                                  "aistudio_code": code}), http
        return jsonify(error={"message": "empty response (schema drift? farmer needs attention)",
                              "type": "server_error"}), 502

    created = int(time.time())
    completion_id = f"chatcmpl-aistudio{int(time.time()*1000)}"
    meta = {"elapsed_s": round(time.time() - t0, 1), "requests_sent": out["request_count"],
            "thinking_level": thinking, "tools_injected": bool(gemini_tools),
            "aistudio_tier": entry["tier"], "protocol": entry["protocol"],
            "quota_spend": ACTIVE.spend, "quota_budget": ACTIVE.daily_budget}
    # media surface (image/music): data-URI list — client render trực tiếp
    media_uris = [f"data:{m['mime']};base64,{m['b64']}" for m in media]

    # ---- tool-call response (agent loop round 1) ----
    if tool_calls and not answer:
        msg = {"role": "assistant", "content": None, "tool_calls": tool_calls}
        if reasoning:
            msg["reasoning_content"] = reasoning
        # 12/09 FIX: stream client (Hermes mặc định stream=true) phải nhận SSE —
        # jsonify ở đây từng trả JSON thường → client đọc 0 frame → EmptyStreamError
        # → retry 30 attempts × farmer reload mỗi attempt (bắt tận tay session
        # "lấy lại ngữ cảnh Stilvik" attempt 7/30, burn 67/50 quota).
        if payload.get("stream"):
            def sse_tools():
                for piece in ([reasoning[i:i+60] for i in range(0, len(reasoning), 60)] if reasoning else []):
                    yield "data: " + json.dumps({
                        "id": completion_id, "object": "chat.completion.chunk", "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"reasoning_content": piece}, "finish_reason": None}],
                    }) + "\n\n"
                first = True
                for tc in tool_calls:
                    delta = {"tool_calls": [{**tc, "index": 0}]} if first else {"tool_calls": [{**tc, "index": 0}]}
                    if first:
                        delta["role"] = "assistant"
                        first = False
                    yield "data: " + json.dumps({
                        "id": completion_id, "object": "chat.completion.chunk", "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    }) + "\n\n"
                yield "data: " + json.dumps({
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                }) + "\n\n"
                yield "data: [DONE]\n\n"
            return Response(stream_with_context(sse_tools()), mimetype="text/event-stream")
        return jsonify(
            id=completion_id, object="chat.completion", created=created, model=model,
            choices=[{"index": 0, "message": msg, "finish_reason": "tool_calls"}],
            usage={"prompt_tokens": usage.get("prompt_tokens", 0),
                   "completion_tokens": usage.get("completion_tokens", 0),
                   "total_tokens": usage.get("total_tokens", 0)},
            aistudio_rev_meta=meta,
        )

    # ---- normal / mixed response ----
    if payload.get("stream"):
        def sse():
            for piece in ([reasoning[i:i+60] for i in range(0, len(reasoning), 60)] if reasoning else []):
                yield "data: " + json.dumps({
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"reasoning_content": piece}, "finish_reason": None}],
                }) + "\n\n"
            first = True
            for piece in [answer[i:i+40] for i in range(0, len(answer), 40)]:
                delta = {"content": piece}
                if first and tool_calls:
                    delta["tool_calls"] = tool_calls
                    first = False
                yield "data: " + json.dumps({
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                }) + "\n\n"
            # media chunks (data-URI từng ảnh/nhạc) — finish_reason None giữ stream mở
            for uri in media_uris:
                yield "data: " + json.dumps({
                    "id": completion_id, "object": "chat.completion.chunk", "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": f"\n![media]({uri})"}, "finish_reason": None}],
                }) + "\n\n"
            yield "data: " + json.dumps({
                "id": completion_id, "object": "chat.completion.chunk", "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }) + "\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(sse()), mimetype="text/event-stream")

    msg = {"role": "assistant", "content": answer or None}
    if reasoning:
        msg["reasoning_content"] = reasoning
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if media_uris:
        msg["media"] = media_uris          # data-URI list — render được mọi nơi
    return jsonify(
        id=completion_id, object="chat.completion", created=created, model=model,
        choices=[{"index": 0, "message": msg,
                  "finish_reason": "tool_calls" if tool_calls and not answer else "stop"}],
        usage={"prompt_tokens": usage.get("prompt_tokens", 0),
               "completion_tokens": usage.get("completion_tokens", 0),
               "total_tokens": usage.get("total_tokens", 0)},
        aistudio_rev_meta=meta,
    )


@app.get("/health")
def health():
    try:
        drv = Driver()
        drv._connect()
        hooked = drv._ev("window.__asrHooked === 1")
        held_s = round(time.time() - _lock_info["since"], 1) if _lock_info["since"] else 0
        return jsonify(status="ok" if hooked else "degraded", hook=hooked,
                       busy=bool(_lock_info["model"]), running_model=_lock_info["model"],
                       running_for_s=held_s)
    except Exception as e:
        return jsonify(status="down", error=str(e)[:150]), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("AIS2A_PORT", "8788")), threaded=True)
