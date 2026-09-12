"""CDP driver — the heart of architecture B (validated in swap_e2e2).

Flow per request (NO page reload between requests — hook persists):
  1. ensure hook installed (addScriptToEvaluateOnNewDocument, idempotent)
  2. set window.__swap = {model, temperature}
  3. type user text into the playground textarea + run
  4. capture GenerateContent via CDP Network events + getResponseBody
  5. extract answer via lib.extract

Requires: farmer Chrome on 127.0.0.1:9333 with AI Studio tab open (auto-reopens if needed).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

import websocket

CDP_HTTP = os.environ.get("AIS2A_CDP_URL", "http://127.0.0.1:9333") + "/json/list"
AISTUDIO_URL = "https://aistudio.google.com/prompts/new_chat"

def aistudio_url_for(page_url: str | None = None) -> str:
    """URL AI Studio giữ nguyên account prefix /u/N/ nếu farmer đang ở profile
    multi-account (authuser). Navigate về URL 'trần' khiến Google snap về
    default account (authuser=0) — vô hiệu hoá account đang chọn (12/09:
    farmer ở /u/1/ Pro nhưng mọi request chạy trên /u/0 free).
    Thêm &pli=1 (user cung cấp link chuẩn) — ghim account khi load."""
    base = AISTUDIO_URL
    if page_url and "/u/" in page_url:
        import re as _re
        m = _re.search(r"(/u/\d+/)", page_url)
        if m:
            base = AISTUDIO_URL.replace("aistudio.google.com/",
                                        "aistudio.google.com" + m.group(1), 1)
    # pli=1: pin account — kể cả URL trần cũng không bị redirect sang authuser=0
    sep = "&" if "?" in base else "?"
    return base + sep + "pli=1"

HOOK = r"""
(() => {
  // ALWAYS re-arm: scripts stack over sessions; the LAST-installed PATCH wins
  // because each wrapper calls the previous with its own (possibly patched) body.
  window.__asrHooked = 1;
  window.__swap = {model: null, temperature: null, tools: null, system: null, contents: null};
  window.__iswap = {model: null};
  const PATCH = (bodyStr, url) => {
    try {
      // Interactions API (omni/deep-research): model ở p[3][17][0] (12/09 verified)
      if (/CreateInteractionStream/.test(url)) {
        const q = JSON.parse(bodyStr);
        const isw = window.__iswap || {};
        if (isw.model && q[3] && q[3][17]) q[3][17][0] = isw.model;
        return JSON.stringify(q);
      }
      if (!/GenerateContent|GenerateTitle/.test(url)) return bodyStr;
      const p = JSON.parse(bodyStr);
      const sw = window.__swap || {};
      if (sw.model) p[0] = sw.model;
      if (sw.temperature != null && p[3]) p[3][5] = sw.temperature;
      if (sw.system) p[5] = [[[null, sw.system]]];
      if (sw.tools) { p[6] = sw.tools; if (p[10] == null) p[10] = 1; }
      if (sw.contents) p[1] = sw.contents;
      // thinking-config (12/09 ROOT-CAUSE FIX): TARGET model quyết định level —
      // CREATE-or-OVERRIDE, không phụ thuộc UI host.
      // Bug cũ: chỉ normalize khi p[3][16] có sẵn đúng shape MINIMAL. UI free-model
      // (lite) không có field này → skip → swap sang pro → server áp default
      // MINIMAL → reject [3,"Thinking level MINIMAL is not supported…"].
      // Levels (proven 200): LOW=2, HIGH=3; DYNAMIC=4 observed; MINIMAL=1 bị
      // 3.8-flash & pro reject. waa KHÔNG hash p[3] (verified 03/09) → an toàn.
      // GenerateTitle KHÔNG mang genconfig p[3] — chỉ rewrite thinking trên
      // GenerateContent (url-guard), tránh tạo p[3] giả cho title request.
      if (/GenerateContent/.test(url) && sw.model) {
        if (!Array.isArray(p[3])) p[3] = [];
        if (Array.isArray(sw.thinking_cfg)) p[3][16] = sw.thinking_cfg;  // explicit driver
        else if (Array.isArray(sw.thinking)) p[3][16] = sw.thinking;     // legacy list
        else if (/lyria|lite/.test(sw.model)) p[3][16] = [1, null, null, 2];  // LOW proven-200 (swap_e2e2 lite, lyria PING)
        else p[3][16] = [1, null, null, 3];                              // DEFAULT HIGH (user policy 12/09)
      }
      return JSON.stringify(p);
    } catch (e) { return bodyStr; }
  };
  const ox = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(m, u, ...rest) {
    this.__u = String(u); return ox.call(this, m, u, ...rest);
  };
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(body) {
    let b = body;
    if (this.__u && /alkalimakersuite/.test(this.__u) && typeof body === 'string') {
      b = PATCH(b, this.__u);
    }
    return os.call(this, b);
  };
})()
"""


class CDPError(RuntimeError):
    pass


class Driver:
    def __init__(self, port_http: str = CDP_HTTP):
        self.http = port_http
        self.ws = None
        self.mid = 0
        self._hook_installed = False

    # ---- connection ----
    def _targets(self) -> list:
        return json.load(urllib.request.urlopen(self.http, timeout=5))

    def _connect(self):
        """Find or re-open the AI Studio tab; attach a fresh WS."""
        for attempt in range(3):
            try:
                targets = self._targets()
            except Exception:
                raise CDPError("farmer Chrome CDP port not reachable (is it running?)")
            page = next((t for t in targets
                         if t.get("type") == "page" and "aistudio.google.com" in t.get("url", "")), None)
            if page:
                self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30)
                # remember the account prefix (/u/N/) so navigations stay on it
                self._page_url = page.get("url", "")
                return
            # no AI Studio tab: open one (session cookies in profile auto-login)
            browser = next((t for t in targets if t.get("webSocketDebuggerUrl") and t.get("type") == "browser"), None)
            if browser:
                bws = websocket.create_connection(browser["webSocketDebuggerUrl"], timeout=10)
                bws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                                     "params": {"url": aistudio_url_for(getattr(self, "_page_url", None))}}))
                try:
                    bws.recv()
                except Exception:
                    pass
                bws.close()
            time.sleep(6)
        raise CDPError("could not find/open AI Studio tab")

    def _send(self, method: str, params: dict | None = None) -> dict:
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.mid:
                return r.get("result", {})
            self._on_event(r)

    def _on_event(self, r: dict):
        pass  # subclass-drivers override; base ignores

    def _ev(self, expr: str, timeout_note: str = ""):
        r = self._send("Runtime.evaluate",
                       {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise CDPError(f"eval failed {timeout_note}: {str(r['exceptionDetails'])[:200]}")
        return r.get("result", {}).get("value")

    # ---- hook management ----
    def _ensure_hook(self):
        """Install hook for future navigations AND eval it directly into the
        current page (addScript only fires on NEXT navigation — after
        Page.navigate to a fresh chat the hook must already be live)."""
        self._send("Page.enable")
        self._send("Network.enable")
        self._send("Runtime.enable")
        self._send("Page.addScriptToEvaluateOnNewDocument", {"source": HOOK})
        # direct-eval: covers the CURRENT page state too
        self._ev(HOOK)

    # ---- health ----
    def healthy(self) -> bool:
        try:
            self._connect()
            ok = self._ev("window.__asrHooked === 1")
            logged = self._ev(
                "!!document.querySelector('textarea') || document.body.textContent.includes('Sign in') === false ? 'checking' : 'signin'")
            return True
        except Exception:
            return False

    # ---- core request ----
    def generate(self, text: str, model: str, temperature: float | None = None,
                 thinking: str | None = None, tools: list | None = None,
                 system: str | None = None, history: list | None = None,
                 timeout_s: int = 180) -> dict:
        """Run one chat turn through the playground.

        text:      the LAST user message (typed into the UI for the waa mint)
        tools:     Gemini-shape tools (payload[6] format) — injected post-mint
        system:    system instruction — injected into payload[5]
        history:   prior turns as Gemini contents (payload[1] list format);
                   the typed text is replaced by [history + this turn]
        """
        self._connect()
        self._ensure_hook()

        # FRESH CHAT each request: single-turn, no rerun-button ambiguity.
        # (addScriptToEvaluateOnNewDocument persists across navigation.)
        # Keep the /u/N/ account prefix so Google doesn't snap to authuser=0.
        nav_url = aistudio_url_for(getattr(self, "_page_url", None))
        self._send("Page.navigate", {"url": nav_url})
        # poll for textarea up to 20s
        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1.5)
            if self._ev("!!document.querySelector('textarea')"):
                break
        if not self._ev("!!document.querySelector('textarea')"):
            raise CDPError("textarea never appeared after fresh-chat navigation (signed out?)")

        # ---- paid-model unlock (12/09 FIX): URL model param, không DOM click ----
        # UI mới: ms-model-selector KHÔNG còn button.model-selector-card —
        # click-path cũ chết ("no-selector"). Sau test live, tab default về
        # Gemini 3.8 Flash (paid) → "No API key selected" → Run không fire.
        # Navigate lại với ?model=gemini-3.1-flash-lite (free) — hook swap vẫn
        # route payload sang model thật, UI host chỉ cần unlocked.
        if self._ev("""(() => {
          const b = [...document.querySelectorAll('button')]
            .find(b => /no api key/i.test(b.getAttribute('aria-label')||'') && b.offsetParent);
          return !!b;
        })()"""):
            print("[driver] paid model locked UI (no API key) — re-nav with free model…", flush=True)
            sep = "&" if "?" in nav_url else "?"
            self._send("Page.navigate", {"url": f"{nav_url}{sep}model=gemini-3.1-flash-lite"})
            deadline2 = time.time() + 20
            while time.time() < deadline2:
                time.sleep(1.5)
                if self._ev("!!document.querySelector('textarea')"):
                    break
            locked = self._ev("""(() => {
              const b = [...document.querySelectorAll('button')]
                .find(b => /no api key/i.test(b.getAttribute('aria-label')||'') && b.offsetParent);
              return !!b;
            })()""")
            print(f"[driver] unlock: {'still-locked (try anyway)' if locked else 'OK'}", flush=True)

        # thinking level → HOOK create-or-override theo TARGET model (12/09 fix).
        # Bỏ UI-set (mat-select Thinking Level): lite host không có control này,
        # chết 3s mỗi request trên màn Pro-locked; HOOK tự lo đúng level.
        TH_LEVELS = {"low": 2, "high": 3, "dynamic": 4}
        thinking_cfg = None
        if thinking:
            want = thinking.strip().lower()
            if want in TH_LEVELS:
                thinking_cfg = [1, None, None, TH_LEVELS[want]]
            # "off"/"none"/"default" → None → HOOK default theo target model
        swap = {"model": model, "temperature": temperature,
                "tools": tools, "system": system, "contents": None,
                "thinking_cfg": thinking_cfg}
        if history:
            swap["contents"] = list(history) + [[[[None, text]], "user"]]
        self._ev("window.__swap = " + json.dumps(swap))

        # type + run (focus FIRST — key events need it)
        msg = json.dumps(text)
        frag = text[:25].replace("'", "\\'")
        trig = self._ev(f"""(async () => {{
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
        }})()""")
        if trig == "no-input":
            raise CDPError("no textarea — page state unexpected")

        # capture network; verify the sent request actually contains OUR text
        events = []
        deadline = time.time() + timeout_s
        got_ours = False

        def on_evt(r):
            nonlocal got_ours
            m, p = r.get("method", ""), r.get("params", {}) or {}
            if m == "Network.requestWillBeSent":
                u = p.get("request", {}).get("url", "")
                pd = p["request"].get("postData") or ""
                if "alkalimakersuite" in u and "GenerateContent" in u:
                    events.append({"id": p["requestId"], "postData": pd})
                    got_ours = True
            elif m == "Network.loadingFinished":
                for e in events:
                    if e["id"] == p["requestId"]:
                        e["done"] = True

        self._on_event = on_evt
        try:
            # wait for our GenerateContent to fire
            t_deadline = time.time() + 12
            while time.time() < t_deadline and not events:
                self.ws.settimeout(2)
                try:
                    on_evt(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
            # fallback: click exact Run button if Ctrl+Enter didn't fire ours
            if not self._request_has_text(events, text):
                self._ev("""(() => {
                  const btns = [...document.querySelectorAll('button')];
                  const run = btns.find(b => (b.getAttribute('aria-label')||'').trim() === 'Run' && !b.disabled);
                  if (run) run.click();
                })()""")
                t_deadline = time.time() + 12
                while time.time() < t_deadline:
                    self.ws.settimeout(2)
                    try:
                        on_evt(json.loads(self.ws.recv()))
                    except websocket.WebSocketTimeoutException:
                        pass
                    if self._request_has_text(events, text):
                        break
            # wait for completion
            first_all_done = None   # timestamp when ALL current events looked done
            while time.time() < deadline:
                self.ws.settimeout(3)
                try:
                    on_evt(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
                if events and all(e.get("done") for e in events):
                    if first_all_done is None:
                        first_all_done = time.time()
                    # hold the window open 6s for late multi-chunk events
                    if time.time() - first_all_done >= 6:
                        break
                    time.sleep(1)
                    try:
                        while True:
                            on_evt(json.loads(self.ws.recv()))
                    except Exception:
                        pass
        finally:
            self._on_event = lambda r: None
            self.ws.settimeout(30)

        if not events:
            raise CDPError("no GenerateContent request observed (trigger failed?)")
        if not self._request_has_text(events, text):
            raise CDPError("GenerateContent fired but did not contain our text (rerun trap?)")

        # debug/probe access: last captured events (postData shape inspection)
        self._last_events = events

        # fetch bodies
        bodies = []
        for e in events:
            try:
                b = self._send("Network.getResponseBody", {"requestId": e["id"]})
                bodies.append(b.get("body") or "")
            except Exception:
                pass
        raw = "".join(bodies)

        # 12/09 instrumentation: dump last generate() call (request shapes + resp head)
        try:
            from pathlib import Path as _P
            def _p316(pd):
                try:
                    p = json.loads(pd)
                    return p[3][16] if (isinstance(p, list) and isinstance(p[3], list)
                                        and len(p[3]) > 16) else "ABSENT"
                except Exception:
                    return "PARSE_FAIL"
            _dump = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "model": model, "thinking": thinking,
                "requests": [{"p316": _p316(e.get("postData") or "")}
                             for e in events],
                "raw_head": raw[:1500],
            }
            (_P(os.environ.get("AIS2A_DATA_DIR", str(Path(__file__).resolve().parents[2] / "data"))) / "lastgen.json").write_text(
                json.dumps(_dump, indent=1), encoding="utf-8")
        except Exception:
            pass

        return {"raw": raw, "request_count": len(events)}

    @staticmethod
    def _request_has_text(events: list, text: str) -> bool:
        """Check both raw and JSON-escaped forms (payload embeds \\n etc.)."""
        needle = text.strip()[:30]
        if not needle:
            return bool(events)
        escaped = json.dumps(needle, ensure_ascii=False)[1:-1]
        for e in events:
            pd = e.get("postData") or ""
            if needle in pd or escaped in pd:
                return True
        return False


    def generate_interaction(self, text: str, model: str,
                             timeout_s: int = 300, ui_model: str | None = None) -> dict:
        """Run one turn qua Interactions API (omni / deep-research models).

        Flow (runtime-verified 12/09):
          navigate /prompts/new_chat?model=<UI-model>  (interaction UI)
          → set window.__iswap.model = target model
          → type text + click Run
          → capture CreateInteractionStream request+response qua CDP
        Trả {"raw": <response frames>, "request_count": N}.

        ui_model: model interaction CÓ SẴN trên UI làm host. Mặc định
        gemini-omni-flash-preview. Với deep-research PHẢI dùng đúng
        deep-research UI (?model=deep-research-preview-04-2026) — omni
        host trả response rỗng cho model deep-research (E2E 12/09 tối:
        14s empty vs 128s full khi host đúng).
        waa bind: payload[4] — cùng cơ chế GenerateContent (đã verify).
        """
        self._connect()
        self._ensure_hook()

        base = aistudio_url_for(getattr(self, "_page_url", None))
        ui = ui_model or "gemini-omni-flash-preview"   # interaction UI host model
        sep = "&" if "?" in base else "?"
        self._send("Page.navigate", {"url": f"{base}{sep}model={ui}"})

        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(1.5)
            if self._ev("!!document.querySelector('textarea')"):
                break
        if not self._ev("!!document.querySelector('textarea')"):
            raise CDPError("textarea never appeared (interaction UI failed to load?)")

        # arm swap for Interactions
        self._ev(f'window.__iswap = {json.dumps({"model": model})}')

        # type + click Run (Run button text-based — interaction UI dùng text 'Run')
        msg = json.dumps(text)
        trig = self._ev(f"""(async () => {{
          const ta = document.querySelector('textarea');
          if (!ta) return 'no-input';
          ta.focus();
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, {msg});
          ta.dispatchEvent(new Event('input', {{bubbles: true}}));
          await new Promise(r => setTimeout(r, 1000));
          const run = [...document.querySelectorAll('button')]
            .find(b => (b.textContent||'').trim().startsWith('Run') && !b.disabled);
          if (!run) return 'no-run-btn';
          run.click();
          return 'sent';
        }})()""")
        if trig not in ("sent",):
            raise CDPError(f"interaction trigger failed: {trig}")

        # capture CreateInteractionStream events
        events = []

        def on_evt(r):
            m, p = r.get("method", ""), r.get("params", {}) or {}
            if m == "Network.requestWillBeSent":
                u = p.get("request", {}).get("url", "")
                pd = p["request"].get("postData") or ""
                if "CreateInteractionStream" in u:
                    events.append({"id": p["requestId"], "postData": pd})
            elif m == "Network.loadingFinished":
                for e in events:
                    if e["id"] == p.get("requestId"):
                        e["done"] = True

        self._on_event = on_evt
        deadline = time.time() + timeout_s
        try:
            # wait for request
            t = time.time() + 15
            while time.time() < t and not events:
                self.ws.settimeout(2)
                try:
                    on_evt(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
            # wait for completion (stream chảy lâu — deep-research nhiều phút)
            first_done = None
            while time.time() < deadline:
                self.ws.settimeout(3)
                try:
                    on_evt(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
                if events and all(e.get("done") for e in events):
                    if first_done is None:
                        first_done = time.time()
                    if time.time() - first_done >= 6:
                        break
                    time.sleep(1)
                    try:
                        while True:
                            on_evt(json.loads(self.ws.recv()))
                    except Exception:
                        pass
        finally:
            self._on_event = lambda r: None
            self.ws.settimeout(30)

        if not events:
            raise CDPError("no CreateInteractionStream request observed (trigger failed?)")

        # verify our text present (waa bind giống GenerateContent)
        needle = text.strip()[:30]
        ours = any(needle in (e.get("postData") or "")
                   or json.dumps(needle, ensure_ascii=False)[1:-1] in (e.get("postData") or "")
                   for e in events)

        bodies = []
        for e in events:
            try:
                b = self._send("Network.getResponseBody", {"requestId": e["id"]})
                bodies.append(b.get("body") or "")
            except Exception:
                pass
        return {"raw": "".join(bodies), "request_count": len(events), "ours": ours}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r".\src\lib")
    from extract import extract_answer

    drv = Driver()
    t0 = time.time()
    out = drv.generate("Say exactly: architecture B works", "models/gemini-3.1-flash-lite")
    print(f"elapsed {time.time()-t0:.1f}s, requests={out['request_count']}")
    print("ANSWER:", repr(extract_answer(out["raw"]))[:200])
