"""capture_run.py — nghiêm túc ground-truth capture cho model đặc biệt AR.

1 run = full taxonomy: mọi $rpc request/response (body fetch NGAY tại
loadingFinished — chống buffer eviction), WebSocket frames (Live API),
DOM media dump (audio/video/img), quota ledger append tự động.

Usage:
  python tools/capture_run.py chat <model_id> <prompt> [timeout_s]
  python tools/capture_run.py interaction <model_id> <prompt> [timeout_s]
  python tools/capture_run.py url <nav_url_suffix> <prompt> [timeout_s]

Output: corpus/cap_<tag>_<ts>/ — events.jsonl, bodies/, dom.json, summary.json
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(r".")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "lib"))

from replay.driver import Driver, aistudio_url_for   # noqa: E402

MODE = sys.argv[1]                      # chat | interaction | url
MODEL = sys.argv[2]                    # models/... hoặc nav suffix
PROMPT = sys.argv[3]
TIMEOUT = int(sys.argv[4]) if len(sys.argv) > 4 else 180

TAG = MODEL.replace("models/", "").replace("/", "-")[:30]
STAMP = time.strftime("%H%M%S")
OUT = ROOT / "data" / f"cap_{TAG}_{STAMP}"
(OUT / "bodies").mkdir(parents=True, exist_ok=True)

INTEREST_RPC = ("alkalimakersuite", "waa-pa", "push)")


class Capturer(Driver):
    def __init__(self):
        super().__init__()
        self.events = []
        self.seen = set()          # requestIds đáng quan tâm
        self.fetch_queue = []      # requestIds chờ getResponseBody
        self.bodies = {}            # rid -> {url, mime, len, b64, file}
        self.pending = []           # events nhận trong lúc call()
        self.ws_frames = 0

    # -- CDP call cho phép event defer --
    def call(self, method, params):
        self.mid += 1
        rid = self.mid
        self.ws.send(json.dumps({"id": rid, "method": method, "params": params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == rid:
                return r.get("result", {})
            self.pending.append(r)

    def pump(self):
        while self.pending:
            self.on_evt(self.pending.pop(0))

    def on_evt(self, r):
        m, p = r.get("method", ""), r.get("params", {}) or {}
        if m == "Network.requestWillBeSent":
            rq = p.get("request", {})
            u = rq.get("url", "")
            if "alkalimakersuite" in u or "waa-pa" in u:
                self.events.append({"ev": "req", "id": p["requestId"], "url": u,
                                    "method": rq.get("method"),
                                    "postData": rq.get("postData") or ""})
                self.seen.add(p["requestId"])
        elif m == "Network.responseReceived":
            if p["requestId"] in self.seen:
                rp = p.get("response", {})
                self.events.append({"ev": "resp", "id": p["requestId"],
                                    "status": rp.get("status"),
                                    "mime": rp.get("mimeType"),
                                    "headers": {k: v for k, v in (rp.get("headers") or {}).items()
                                                if k.lower() in ("content-type", "content-length")}})
        elif m == "Network.loadingFinished":
            if p["requestId"] in self.seen:
                self.fetch_queue.append(p["requestId"])
        elif m in ("Network.webSocketCreated",):
            self.events.append({"ev": "ws-created", "url": p.get("url", "")})
        elif m in ("Network.webSocketFrameSent", "Network.webSocketFrameReceived"):
            self.ws_frames += 1
            d = (p.get("response", {}).get("payloadData") or "")[:3000]
            self.events.append({"ev": "ws-" + ("sent" if m.endswith("Sent") else "recv"), "data": d})

    def fetch_bodies(self):
        while self.fetch_queue:
            rid = self.fetch_queue.pop(0)
            try:
                b = self.call("Network.getResponseBody", {"requestId": rid})
                body = b.get("body") or ""
                meta = next((e for e in self.events if e.get("id") == rid and e.get("ev") == "resp"), {})
                entry = {"url": next((e["url"] for e in self.events if e.get("id") == rid and e.get("ev") == "req"), "?"),
                         "mime": meta.get("mime"), "len": len(body),
                         "base64": bool(b.get("base64Encoded"))}
                if body:
                    fname = f"bodies/{rid.replace('.', '_')}.{'bin' if entry['base64'] else 'txt'}"
                    data = base64.b64decode(body) if entry["base64"] else body.encode("utf-8", "replace")
                    (OUT / fname).write_bytes(data)
                    entry["file"] = fname
                    if not entry["base64"]:
                        entry["head"] = body[:400]
                self.bodies[rid] = entry
            except Exception as ex:
                self.bodies[rid] = {"err": str(ex)[:100]}

    # -- DOM media dump --
    def dom_dump(self):
        r = self.call("Runtime.evaluate", {
            "expression": """(() => {
              const out = {audio: [], video: [], img: [], downloads: []};
              document.querySelectorAll('audio').forEach(a => out.audio.push({
                src_type: (a.src||'').slice(0,30), len: (a.src||'').length,
                duration: a.duration, ready: a.readyState, cls: (a.className||'').toString().slice(0,50)}));
              document.querySelectorAll('video').forEach(v => out.video.push({
                src_type: (v.src||'').slice(0,30), len: (v.src||'').length,
                duration: v.duration, w: v.videoWidth, h: v.videoHeight}));
              document.querySelectorAll('img').forEach(i => {
                if ((i.src||'').startsWith('data:image')) out.img.push({
                  len: i.src.length, head: i.src.slice(0,60), w: i.naturalWidth, h: i.naturalHeight});});
              [...document.querySelectorAll('button, a')].filter(e => e.offsetParent &&
                /download|save|export/i.test((e.getAttribute('aria-label')||'')+(e.textContent||'')))
                .forEach(b => out.downloads.push((b.getAttribute('aria-label')||b.textContent||'').trim().slice(0,50)));
              return JSON.stringify(out);})()""",
            "returnByValue": True, "awaitPromise": True})
        return json.loads(r.get("result", {}).get("value") or "{}")


cap = Capturer()
cap._connect()
cap._ensure_hook()
cap._on_event = cap.on_evt

t0 = time.time()
# ---- navigation theo mode ----
base = aistudio_url_for(getattr(cap, "_page_url", None))
if MODE == "chat":
    nav = base
    cap._send("Page.navigate", {"url": nav})
elif MODE == "interaction":
    ui_model = "gemini-omni-flash-preview" if "omni" in MODEL else (
        "deep-research-preview-04-2026" if "deep-research" in MODEL else MODEL.replace("models/", ""))
    sep = "&" if "?" in base else "?"
    nav = f"{base}{sep}model={ui_model}"
    cap._send("Page.navigate", {"url": nav})
elif MODE == "url":
    nav = base.rsplit("/prompts/", 1)[0] + "/" + MODEL if "/" in MODEL else base
    cap._send("Page.navigate", {"url": nav})
else:
    raise SystemExit(f"unknown mode {MODE}")

# wait textarea
deadline = time.time() + 25
while time.time() < deadline:
    time.sleep(1.5)
    cap.pump()
    if cap.call("Runtime.evaluate", {"expression": "!!document.querySelector('textarea')",
                                     "returnByValue": True}).get("result", {}).get("value"):
        break

# ---- arm swap + run ----
if MODE == "interaction":
    cap.call("Runtime.evaluate", {
        "expression": f"window.__iswap = {json.dumps({'model': MODEL})}",
        "returnByValue": True})
else:
    think = [1, None, None, 2] if ("lyria" in MODEL or "lite" in MODEL) else None
    cap.call("Runtime.evaluate", {
        "expression": f"window.__swap = {json.dumps({'model': MODEL, 'thinking_cfg': think})}",
        "returnByValue": True})

msg = json.dumps(PROMPT)
trig = cap.call("Runtime.evaluate", {
    "expression": f"""(async () => {{
      const ta = document.querySelector('textarea');
      if (!ta) return 'no-input';
      ta.focus();
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(ta, {msg});
      ta.dispatchEvent(new Event('input', {{bubbles: true}}));
      await new Promise(r => setTimeout(r, 1000));
      const opts = {{key: 'Enter', code: 'Enter', keyCode: 13, which: 13, ctrlKey: true, bubbles: true, cancelable: true}};
      ta.dispatchEvent(new KeyboardEvent('keydown', opts));
      ta.dispatchEvent(new KeyboardEvent('keyup', opts));
      return 'sent';
    }})()""", "returnByValue": True, "awaitPromise": True}).get("result", {}).get("value")
print(f"[{TAG}] trigger: {trig}")

# ---- capture window ----
cap.ws.settimeout(3)
while time.time() - t0 < TIMEOUT:
    try:
        cap.on_evt(json.loads(cap.ws.recv()))
    except Exception:
        pass
    cap.pump()
    if cap.fetch_queue:
        cap.fetch_bodies()
        cap.pump()
    # dừng sớm khi mọi request đã done + không có WS nào đang mở
    if cap.events and time.time() - t0 > 40:
        reqs = [e for e in cap.events if e["ev"] == "req"]
        done_rids = set(cap.bodies)
        if all(r["id"] in done_rids for r in reqs) and not cap.fetch_queue and cap.ws_frames == 0:
            time.sleep(5)   # drain cuối
            try:
                while True:
                    cap.on_evt(json.loads(cap.ws.recv()))
            except Exception:
                pass
            cap.fetch_bodies()
            cap.pump()
            break

cap._on_event = lambda r: None
elapsed = time.time() - t0

# ---- finalize ----
dom = cap.dom_dump()
summary = {"tag": TAG, "model": MODEL, "mode": MODE, "prompt": PROMPT,
           "elapsed_s": round(elapsed, 1), "ts": time.strftime("%H:%M:%S"),
           "n_events": len(cap.events), "ws_frames": cap.ws_frames,
           "rpc_calls": sorted({e["url"].rsplit("/", 1)[-1].split("?")[0]
                                for e in cap.events if e["ev"] == "req"}),
           "bodies": list(cap.bodies.values()), "dom": dom}
(OUT / "events.jsonl").write_text(
    "\n".join(json.dumps(e, ensure_ascii=False) for e in cap.events), encoding="utf-8")
(OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")

print(f"[{TAG}] elapsed {elapsed:.1f}s | events {len(cap.events)} | ws {cap.ws_frames}")
print(f"  rpc: {summary['rpc_calls']}")
print(f"  dom: audio={len(dom.get('audio', []))} video={len(dom.get('video', []))} "
      f"img={len(dom.get('img', []))} dl={len(dom.get('downloads', []))}")
for b in cap.bodies.values():
    print(f"  body: {b.get('url','?')[:80]} | {b.get('mime')} | len={b.get('len')}")
print(f"  → {OUT}")

# ---- quota ledger append ----
ledger_p = ROOT / "data" / "quota_ledger.json"
try:
    ledger = json.loads(ledger_p.read_text(encoding="utf-8"))
except Exception:
    ledger = {"account": "/u/2/", "tests": []}
ok = any(b.get("len", 0) and not b.get("err") for b in cap.bodies.values())
ledger["tests"].append({"ts": time.strftime("%H:%M"), "model": MODEL, "mode": MODE,
                        "elapsed_s": round(elapsed, 1),
                        "rpc_count": len(summary["rpc_calls"]),
                        "body_ok": ok, "ws_frames": cap.ws_frames})
ledger_p.write_text(json.dumps(ledger, indent=1, ensure_ascii=False), encoding="utf-8")
print("  quota ledger updated")
