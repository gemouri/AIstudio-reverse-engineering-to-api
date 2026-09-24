# Usage Guide — Google AI Studio → OpenAI-compatible API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

This project drives a real Chrome window that is signed into **your own** Google
AI Studio session, and re-exposes that session as a standard OpenAI-compatible
API on `http://127.0.0.1:8788/v1`. There is no Google API key and no billing —
it uses the AI Studio access your account already has.

---

## 1. Requirements

| Item | Notes |
|---|---|
| Operating system | Windows, macOS or Linux — **desktop with a display** (Chrome runs as a real, visible window) |
| Python | 3.10 or newer |
| Browser | Google Chrome (Chromium or Edge also work) |
| Google account | Any account that can open `aistudio.google.com` and send a prompt |
| Memory | ~2 GB free RAM while Chrome and the API run |

## 2. Install

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Only two dependencies are needed: `flask` and `websocket-client`.

## 3. First run

### Step 1 — start the dedicated browser

```bash
python launch_chrome.py
```

A Chrome window opens on `aistudio.google.com` using its **own profile**
(separate from the browser you use day to day). Sign in with your Google
account — this is needed only the first time; the session is kept in that
profile.

> **Keep this window open.** It is the component that mints a per-request
> token from the page. Closing it stops the API.

### Step 2 — start the API (new terminal)

```bash
python start.py
```

Expected line: `Running on http://127.0.0.1:8788`.

## 4. Verify that it works

Three checks, from quickest to most complete:

```bash
# 1) health — is the API up and is the browser reachable?
curl http://127.0.0.1:8788/health
# → {"status":"ok","hook":true,"busy":false,"running_model":null,"running_for_s":0}

# 2) catalog — every model the API can drive
curl http://127.0.0.1:8788/v1/models

# 3) a real answer
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.1-flash-lite","messages":[{"role":"user","content":"Reply with one word: PING"}]}'
```

How to read `/health`:

| Field | Meaning |
|---|---|
| `status` | `ok` = API and browser both reachable. `degraded` = API is up but the browser/CDP is not — restart step 1 |
| `hook` | `true` = the request-patching hook is installed in the page (normal) |
| `busy` / `running_model` / `running_for_s` | a request is currently running, and for how long |

## 5. Using the API from your tools

Any OpenAI-compatible client works. Set the base URL to
`http://127.0.0.1:8788/v1` and any non-empty string as the API key.

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### Streaming

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### Function calling (tools)

OpenAI-style `tools` are translated into the Gemini schema and answers come back
as standard `tool_calls`:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}]
resp = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "What's the weather in Hanoi?"}],
    tools=tools,
)
print(resp.choices[0].message.tool_calls)
```

### Multi-turn

Send the full transcript each time, exactly as with any OpenAI-compatible API:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Other clients

Point any tool that speaks the OpenAI API at the same base URL: OpenWebUI,
LobeChat, LangChain, LlamaIndex, the OpenAI CLI, your own scripts. For clients
that insist on an API key, use any placeholder string.

## 6. Models

`GET /v1/models` is the live source of truth. Groups and typical use:

| Group | Models | Tier | Typical time |
|---|---|---|---|
| Free chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Images | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Music | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Speech (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Reasoning agents | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Live voice | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Blocked upstream | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | returns an error — unsupported at this tier |

Free-tier models consume no paid quota. Pro, premium and agent models use the
quota of the signed-in account; when Google refuses, you receive an honest
HTTP 429 carrying Google's own message.

## 7. Media results

Models that produce media return them in `choices[0].message.media` as
`data:` URIs — render or save them directly.

| Model family | `media[0]` starts with | Notes |
|---|---|---|
| Images | `data:image/jpeg;base64,` | the same image also appears inline in `content` as markdown |
| Music | `data:audio/mpeg;base64,` | MP3 |
| Speech (TTS) | `data:audio/wav;base64,` | 24 kHz mono WAV; duration is reported in `content` |
| Live voice | `data:audio/wav;base64,` | voice-only replies have an empty-ish `content` |
| Deep research | `data:image/png;base64,` | chart artifacts; the report itself is in `content`, the research plan in `reasoning_content`, citations in `message.sources` |

### Choosing a TTS voice

Add an optional `voice` field to the request body. The voice name is any of the
70 voices offered by AI Studio — for example `Fola` (the UI default), `Puck`,
`Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Operational limits

- **One request at a time.** The browser handles a single request; a second
  request waits for the running one for up to 90 seconds (`AIS2A_LOCK_WAIT`) and
  then fails with `503 farmer_busy`.
- **Client timeouts.** Chat ~20–30 s, images ~30 s, TTS ~45 s, Live ~80 s,
  deep-research 2–5 minutes. Set your client timeout generously for agents
  (600 s or more).
- **No local daily cap.** The ledger only counts requests per model per day;
  it does not block anything. Google's own limit is the real limit and surfaces
  as HTTP 429.
- **Keep the volume human.** Respect the AI Studio terms of service; do not use
  this to abuse free tiers.

## 9. Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `AIS2A_PORT` | `8788` | API port |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP) port |
| `AIS2A_CHROME_BIN` | auto-detected | Path to the Chrome/Chromium/Edge binary |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Dedicated browser profile (private to this project) |
| `AIS2A_LOCK_WAIT` | `90` | Seconds a queued request waits for the browser |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Server-side timeout for agent models (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Server-side timeout for speech models |
| `AIS2A_LIVE_TIMEOUT` | `120` | Server-side timeout for Live voice |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Server-side timeout for video jobs |

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` on port 8788 | the API is not running | `python start.py` |
| `/health` says `degraded`, or errors mention `farmer CDP port not reachable` | the Chrome window was closed or crashed | run `python launch_chrome.py` again and sign in if asked |
| `503 farmer_busy` | another request is still running | wait for it, or raise `AIS2A_LOCK_WAIT` |
| `429` from the API | Google's own quota/limit for that model | wait, or switch to a free-tier model |
| `502` with an empty or unparsable body | AI Studio changed something in its internal protocol | keep the raw body, re-capture with `tools/capture_run.py`, update `src/lib/extract*.py` |
| Empty `content` but `media` is present | normal for image, music and speech models | read `choices[0].message.media` |
| Chrome shows "No API key selected" | the model selected in the UI is paid-locked | the driver re-navigates to a free host automatically; if it persists, pick a free model once in the AI Studio model picker |
| Model missing from `/v1/models` | it is not in the registry | add it to `src/facade/registry.py` |
| `antigravity` or `veo-*` error out | blocked upstream at Google's tier | not usable through this project — see `docs/protocol-notebook.md` §15 |
| The answer looks like a previous question's answer | the request was swallowed while the browser was locked | check `/health` for `busy`, then retry |

## 11. Upkeep

- Restart `start.py` after changing anything under `src/`.
- Re-run `python launch_chrome.py` if the AI Studio session expires (a sign-in
  page appears in that window).
- If responses start failing at once with `403`, the session or the per-request
  token changed upstream: sign in again in the Chrome window, then re-check
  `/health`.

## 12. Going deeper

- `docs/protocol-notebook.md` — the full reverse-engineering notebook: payload
  shapes, protocol families, per-model notes, and the model audit (§15).
- `tools/capture_run.py` — ground-truth capture tool (network bodies, DOM,
  WebSocket frames) used to re-reverse a changed protocol.
