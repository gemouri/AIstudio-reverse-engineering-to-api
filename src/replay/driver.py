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
import re
import time
import urllib.request

import websocket

CDP_HTTP = "http://127.0.0.1:9333/json/list"
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
  window.__vswap = {model: null};
  window.__tswap = {voice: null, style: null};
  const PATCH = (bodyStr, url) => {
    try {
      // Interactions API (omni/deep-research): model ở p[3][17][0] (12/09 verified)
      if (/CreateInteractionStream/.test(url)) {
        const q = JSON.parse(bodyStr);
        const isw = window.__iswap || {};
        if (isw.model && q[3] && q[3][17]) q[3][17][0] = isw.model;
        return JSON.stringify(q);
      }
      // Veo GenerateVideo (13/09): model ở p[0], prompt p[1] — swap model only
      if (/GenerateVideo/.test(url)) {
        const q = JSON.parse(bodyStr);
        const vsw = window.__vswap || {};
        if (vsw.model && Array.isArray(q) && typeof q[0] === 'string') q[0] = vsw.model;
        return JSON.stringify(q);
      }
      if (!/GenerateContent|GenerateTitle/.test(url)) return bodyStr;
      const p = JSON.parse(bodyStr);
      // TTS voice config: /generate-speech UI places voice at p[3][15]
      // (= [[["Fola"]]]); p[3][14]=[3] is a different field — do NOT touch.
      const tsw = window.__tswap || {};
      if (Array.isArray(p) && Array.isArray(p[3]) && tsw.voice) {
        p[3][15] = [[[tsw.voice]]];
      }
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



def _payload_has_text(post_data: str, text: str) -> bool:
    """True if the request body contains our text (skip noise requests)."""
    return text in (post_data or "")



class CDPError(RuntimeError):
    pass


def _split_webchannel_frames(body: str) -> list:
    """Tách WebChannel body "<len>\\n[[k,payload]]" thành list payload JSON."""
    frames, i, n = [], 0, len(body)
    while i < n:
        j = body.find("\n", i)
        if j < 0:
            break
        try:
            ln = int(body[i:j])
        except ValueError:
            i = j + 1          # không phải len-prefix — bỏ dòng
            continue
        frames.append(body[j + 1:j + 1 + ln])
        i = j + 1 + ln
    return frames


def _live_decode(bodies: list, user_text: str) -> tuple[str, list]:
    """Decode WebChannel long-poll bodies → (model_text, [pcm_b64_total]).

    Frame format chuẩn: "<len>\\n[[k,payload]]" lặp. Parse len-prefix (KHÔNG
    regex toàn body — từng frame là JSON độc lập):
      - PCM: mọi cặp [mime, b64] mime.startswith("audio/") — decode TỪNG
        frame rồi concat raw bytes (padding b64 ở giữa chuỗi concat = garbage,
        bug 13/09: 197KB b64 → 2 bytes) → re-encode 1 chuỗi b64 duy nhất.
      - Text: strings từ frames, lọc noise: 'noop' heartbeat, user-echo,
        numeric-only. Live voice-only reply → text rỗng (đúng — corpus
        cap_live_full_audio.json: model trả audio, không text).
    """
    import base64
    raw_pcm = bytearray()
    texts: list[str] = []
    for body in bodies:
        for frame in _split_webchannel_frames(body):
            try:
                fj = json.loads(frame)
            except Exception:
                continue
            stack = [fj]
            while stack:
                node = stack.pop()
                if isinstance(node, list):
                    if (len(node) >= 2 and isinstance(node[0], str)
                            and node[0].startswith("audio/")
                            and isinstance(node[1], str)):
                        try:
                            raw_pcm += base64.b64decode(node[1])
                        except Exception:
                            pass
                        continue
                    stack.extend(node)
                elif isinstance(node, str) and len(node) >= 3:
                    texts.append(node)
    u_echo = (user_text or "").strip()
    import re as _re
    _uuid = _re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
    _hexish = _re.compile(r"^[A-Za-z0-9_-]{16,}$")   # session-id / b64 token
    keep = []
    for t in texts:
        s = t.strip()
        if (not s or s == "noop" or s.lower() == u_echo.lower()
                or s.replace(" ", "").isdigit()
                or _uuid.match(s) or _hexish.match(s) or s.upper() == "AUDIO"):
            continue
        if s not in keep:
            keep.append(s)
    pcm_b64 = [base64.b64encode(bytes(raw_pcm)).decode()] if raw_pcm else []
    return "\n".join(keep), pcm_b64


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
            (_P(r"D:\PROJECTS\aistudio-rev\corpus") / "lastgen.json").write_text(
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
        trig_js = f"""(async () => {{
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
        }})()"""
        trig = self._ev(trig_js)
        if trig not in ("sent",):
            raise CDPError(f"interaction trigger failed: {trig}")

        # capture CreateInteractionStream events
        # 13/09 RPC DRIFT: UI Agents tab giờ tách CreateInteraction + 
        # GetInteractionStream (2 requests riêng); bản cũ = CreateInteractionStream
        # 1 request. Watch cả 2 — "CreateInteraction" match cả substring cũ.
        events = []

        def on_evt(r):
            m, p = r.get("method", ""), r.get("params", {}) or {}
            if m == "Network.requestWillBeSent":
                u = p.get("request", {}).get("url", "")
                pd = p["request"].get("postData") or ""
                if "CreateInteraction" in u or "GetInteractionStream" in u:
                    events.append({"id": p["requestId"], "url": u, "postData": pd})
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
            # 13/09 FIX (Pro paid-lock race, interaction path): 15s không có
            # request → Run click bị "No API key selected" NUỐT. Trên account
            # Pro, SPA mount model paid mặc định (3.8 Flash + lock) trong lúc
            # load trước khi áp model host từ URL — driver click Run quá sớm
            # (textarea hiện trước model selector settle) → 0 request →
            # ngồi chờ hết deadline 600s ("tab không biến chuyển gì").
            # Account free không có paid default → không gặp race này.
            # Chờ lock clear (tối đa 45s) rồi re-trigger 1 lần; vẫn không có
            # request → fail NHANH với message rõ thay vì hang 600s.
            if not events:
                lock_deadline = time.time() + 45
                lock = True
                while time.time() < lock_deadline:
                    lock = self._ev(
                        "!![...document.querySelectorAll('button')]"
                        ".find(b=>/no api key/i.test(b.getAttribute('aria-label')||'')"
                        "&&b.offsetParent)")
                    if not lock:
                        break
                    time.sleep(2)
                if not lock:
                    print("[driver] interaction Run swallowed by paid-lock — "
                          "re-trigger after model settle…", flush=True)
                    self._ev(trig_js)
                    t = time.time() + 20
                    while time.time() < t and not events:
                        self.ws.settimeout(2)
                        try:
                            on_evt(json.loads(self.ws.recv()))
                        except websocket.WebSocketTimeoutException:
                            pass
                if not events:
                    raise CDPError(
                        "no CreateInteraction request — Run swallowed by "
                        "paid-model lock (re-trigger failed; check farmer tab)")
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

    # ------------------------------------------------------------------
    # 13/09 B3: Live API (bidiGenerateContent) — WebChannel long-poll (§14.6)
    # REVERSED 12/09: handshake count=0 → setup count=1 → text-send →
    # response long-poll "<len>\n[[k,payload]]"; frame 5 = PCM 24kHz b64.
    # Trap: text chỉ được process khi session ACTIVE (sau Talk) — §14.6.
    # ------------------------------------------------------------------
    def live_session(self, text: str, model: str, timeout_s: int = 120) -> dict:
        self._connect()
        self._ensure_hook()

        # 13/09 KHÔNG grant mic — grant audioCapture tự bật mic stream, spam
        # bidi upload channel (500+ UUID frames) và clobber text submit.
        # Corpus 12/09 capture OK không cần grant (permission đã persist).
        # Text-only prompt: mic không cần.

        base = aistudio_url_for(getattr(self, "_page_url", None))
        live_url = base.replace("/prompts/new_chat", "/live")
        sep = "&" if "?" in live_url else "?"
        self._send("Page.navigate",
                   {"url": f"{live_url}{sep}model={model.replace('models/', '', 1)}"})

        # 13/09 fix: Live UI KHÔNG có textarea lúc idle — chờ nút Talk xuất hiện
        # (aria-label 'Talk' — dump 13/09: btns gồm Talk/Share Screen/Microphone)
        deadline = time.time() + 30
        talk_found = False
        while time.time() < deadline:
            time.sleep(2)
            talk_found = self._ev("""(() => [...document.querySelectorAll('button')].some(b =>
              b.offsetParent && (b.getAttribute('aria-label')||'').trim() === 'Talk'))()""")
            if talk_found:
                break
        if not talk_found:
            raise CDPError("live UI never loaded (Talk button missing — model locked?)")

        # ---- arm capture TRƯỚC Talk (13/09 root-cause) ----
        # WebChannel handshake (count=0) + setup (count=1&ofs=0) fire ngay khi
        # Talk click — arm muộn = mất text-send POST → model không nhận prompt.
        # Mic uploads spam UUID frames (~89B, 5+/s) khi session active — filter
        # qua settle logic PCM (không đếm activity tổng).
        bidi: dict = {}
        bodies: list[str] = []
        state = {"last_pcm": 0.0, "got_pcm": False}

        def on_evt(r):
            m, p = r.get("method", ""), r.get("params", {}) or {}
            if m == "Network.requestWillBeSent":
                u = p.get("request", {}).get("url", "")
                if "bidiGenerateContent" in u:
                    bidi[p["requestId"]] = {"url": u, "done": False}
            elif m == "Network.loadingFinished":
                e = bidi.get(p.get("requestId"))
                if e is not None:
                    e["done"] = True

        self._on_event = on_evt

        # ---- Talk → copyright-agree ×4 → session active (flow §14.6) ----
        talk = self._ev("""(() => {
          const b = [...document.querySelectorAll('button')].find(b => b.offsetParent &&
            /talk|start/i.test((b.getAttribute('aria-label')||'') + (b.textContent||'')));
          if (!b) return 'no-talk-btn';
          b.click(); return 'talk-clicked';
        })()""")
        if talk != "talk-clicked":
            raise CDPError(f"live trigger failed: {talk}")

        for _ in range(4):   # copyright dialog lặp ×4 (observed)
            r = self._ev("""(() => {
              const b = [...document.querySelectorAll('button')].find(b => b.offsetParent &&
                /agree/i.test((b.getAttribute('aria-label')||'') + (b.textContent||'')));
              if (b) { b.click(); return 'agreed'; } return 'none';
            })()""")
            if r != "agreed":
                break
            time.sleep(1.5)

        active = False
        deadline = time.time() + 25
        while time.time() < deadline:
            time.sleep(2)
            active = self._ev("""(() => [...document.querySelectorAll('button')].some(b =>
              b.offsetParent && /stop|disconnect/i.test((b.getAttribute('aria-label')||'') +
                (b.textContent||''))))()""")
            if active:
                break
        if not active:
            raise CDPError("live session never became active (copyright dialog not cleared?)")

        # ---- type + submit (chỉ process khi active — trap §14.6) ----
        # 13/09: Live UI submit = nút Run (Ctrl+Return) — Enter thường chỉ
        # insert newline. Ưu tiên Run button, fallback Send, cuối cùng Ctrl+Enter.
        msg = json.dumps(text)
        trig = self._ev(f"""(async () => {{
          const ta = document.querySelector('textarea');
          if (!ta) return 'no-input';
          ta.focus();
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, {msg});
          ta.dispatchEvent(new Event('input', {{bubbles: true}}));
          await new Promise(r => setTimeout(r, 600));
          const run = [...document.querySelectorAll('button')]
            .find(b => b.offsetParent && !b.disabled &&
              (b.textContent||'').trim().toLowerCase().startsWith('run'));
          if (run) {{ run.click(); return 'run-clicked'; }}
          const send = [...document.querySelectorAll('button')]
            .find(b => b.offsetParent && !b.disabled &&
              /send/i.test((b.getAttribute('aria-label')||'') + (b.textContent||'')));
          if (send) {{ send.click(); return 'sent'; }}
          ta.dispatchEvent(new KeyboardEvent('keydown',
            {{key:'Enter', code:'Enter', ctrlKey:true, keyCode:13, bubbles:true}}));
          return 'ctrl-enter-fallback';
        }})()""")
        if trig not in ("run-clicked", "sent", "ctrl-enter-fallback"):
            raise CDPError(f"live text trigger failed: {trig}")

        # ---- capture loop (đã arm trước Talk — chỉ pump + settle) ----
        deadline = time.time() + timeout_s
        try:
            while time.time() < deadline:
                self.ws.settimeout(3)
                try:
                    on_evt(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
                # fetch body ngay khi request xong (long-poll giữ frame stream);
                # snapshot list() — on_evt có thể thêm entry mới giữa chừng
                for rid, e in list(bidi.items()):
                    if e["done"] and not e.get("fetched"):
                        e["fetched"] = True
                        try:
                            b = self._send("Network.getResponseBody", {"requestId": rid})
                            body = b.get("body") or ""
                            e["body"] = body
                            bodies.append(body)
                            if "audio/pcm" in body:
                                state["got_pcm"] = True
                                state["last_pcm"] = time.time()
                        except Exception:
                            e["body"] = ""
                # settle: model audio bắt đầu chảy + 5s không PCM mới
                if state["got_pcm"] and time.time() - state["last_pcm"] >= 5:
                    break
        finally:
            self._on_event = lambda r: None
            self.ws.settimeout(30)

        if not bidi:
            raise CDPError("no bidiGenerateContent request observed (Talk failed?)")

        # ---- Stop session (giải phóng farmer, không burn thêm) ----
        try:
            self._ev("""(() => {
              const stop = [...document.querySelectorAll('button')].find(b => b.offsetParent &&
                /stop|disconnect|end/i.test((b.getAttribute('aria-label')||'') +
                  (b.textContent||'')));
              if (stop) { stop.click(); return 'stopped'; } return 'no-stop';
            })()""")
        except Exception:
            pass

        ltext, pcm = _live_decode(bodies, text)
        return {"text": ltext, "pcm_b64": "".join(pcm), "frames": len(bodies),
                "request_count": len(bodies), "ours": True,
                "raw": "\n".join(bodies)[:100000]}

    # ------------------------------------------------------------------
    # 13/09 B3: Veo (GenerateVideo → GetGenerateVideoOperation poll) — §14.2.
    # Source-level: request [model, prompt, api_key?] (field 1/2/7); op poll
    # [name, api_key?]. Capture-driven qua UI /prompts/new_video; model swap
    # qua window.__vswap (HOOK mở rộng). CHƯA runtime-verified trước E2E.
    # ------------------------------------------------------------------
    def generate_video(self, text: str, model: str, timeout_s: int = 300) -> dict:
        self._connect()
        self._ensure_hook()

        base = aistudio_url_for(getattr(self, "_page_url", None))
        vurl = base.replace("/prompts/new_chat", "/prompts/new_video")
        sep = "&" if "?" in vurl else "?"
        self._send("Page.navigate",
                   {"url": f"{vurl}{sep}model={model.replace('models/', '', 1)}"})

        deadline = time.time() + 30
        while time.time() < deadline:
            time.sleep(2)
            if self._ev("!!document.querySelector('textarea')"):
                break
        if not self._ev("!!document.querySelector('textarea')"):
            raise CDPError("veo UI never loaded (no textarea)")

        self._ev(f'window.__vswap = {json.dumps({"model": model})}')

        msg = json.dumps(text)
        trig = self._ev(f"""(async () => {{
          const ta = document.querySelector('textarea');
          if (!ta) return 'no-input';
          ta.focus();
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, {msg});
          ta.dispatchEvent(new Event('input', {{bubbles: true}}));
          await new Promise(r => setTimeout(r, 800));
          const run = [...document.querySelectorAll('button')]
            .find(b => (b.textContent||'').trim().toLowerCase().startsWith('run') && !b.disabled);
          if (!run) return 'no-run-btn';
          run.click(); return 'sent';
        }})()""")
        if trig != "sent":
            raise CDPError(f"veo trigger failed: {trig}")

        # capture: GenerateVideo RPC + op polls + mọi body mime video/* (mp4 fetch)
        vids: dict = {}
        rpcs: dict = {}
        state = {"last_activity": time.time(), "have_video": False}

        def on_evt(r):
            m, p = r.get("method", ""), r.get("params", {}) or {}
            if m == "Network.requestWillBeSent":
                u = p.get("request", {}).get("url", "")
                if "GenerateVideo" in u:
                    rpcs[p["requestId"]] = {"url": u, "done": False,
                                            "post": (p.get("request", {}).get("postData") or "")[:300]}
                    state["last_activity"] = time.time()
            elif m == "Network.responseReceived":
                rp = p.get("response", {}) or {}
                mime = (rp.get("mimeType") or "")
                if mime.startswith("video/"):
                    vids[p["requestId"]] = {"url": p.get("response", {}).get("url", ""),
                                            "mime": mime, "done": False}
                    state["last_activity"] = time.time()
            elif m == "Network.loadingFinished":
                rid = p.get("requestId")
                if rid in rpcs:
                    rpcs[rid]["done"] = True
                    state["last_activity"] = time.time()
                if rid in vids:
                    vids[rid]["done"] = True
                    state["last_activity"] = time.time()

        self._on_event = on_evt
        deadline = time.time() + timeout_s
        t_veo_start = time.time()
        rpc_bodies, video_parts = [], []
        try:
            while time.time() < deadline:
                self.ws.settimeout(3)
                try:
                    on_evt(json.loads(self.ws.recv()))
                except websocket.WebSocketTimeoutException:
                    pass
                for rid, e in list(rpcs.items()):
                    if e["done"] and not e.get("fetched"):
                        e["fetched"] = True
                        try:
                            b = self._send("Network.getResponseBody", {"requestId": rid})
                            e["body"] = b.get("body") or ""
                            rpc_bodies.append(e["body"])
                            state["last_activity"] = time.time()
                        except Exception:
                            e["body"] = ""
                for rid, e in list(vids.items()):
                    if e["done"] and not e.get("fetched"):
                        e["fetched"] = True
                        try:
                            b = self._send("Network.getResponseBody", {"requestId": rid})
                            body = b.get("body") or ""   # base64 của mp4
                            video_parts.append({"mime": e["mime"], "b64": body})
                            state["have_video"] = True
                            state["last_activity"] = time.time()
                        except Exception:
                            pass
                # settle: có video HOẶC mọi rpc xong + 10s im
                quiet = time.time() - state["last_activity"] >= 10
                all_rpc_done = rpcs and all(e.get("fetched") for e in rpcs.values())
                if state["have_video"] and quiet:
                    break
                if all_rpc_done and quiet and time.time() - t_veo_start > 20:
                    break
        finally:
            self._on_event = lambda r: None
            self.ws.settimeout(30)

        if not rpcs:
            raise CDPError("no GenerateVideo request observed (Run failed?)")

        full = "\n".join(rpc_bodies)
        # video bytes ưu tiên; fallback URL googleusercontent trong op body
        video_b64 = None
        if video_parts:
            video_b64 = video_parts[0]
        urls = re.findall(r'https://[A-Za-z0-9.-]*googleusercontent\.com/[^\s"\\]+', full)
        return {"video_b64": video_b64, "video_url": urls[0] if urls else None,
                "request_count": len(rpcs), "ours": True, "raw": full[:100000]}


    # ------------------------------------------------------------------
    # 24/09: TTS (GenerateContent + speech config p[3][14], UI /generate-speech).
    # Corpus cap_tts_ui_run2.json: request [model, contents, p3(genconfig+
    # voice p[3][15]), waa]; response = N parts audio/l16;rate=24000;channels=1.
    # Voice list: slot[66] ListModels. UI: example composer hoặc Add block.
    # ------------------------------------------------------------------
    def generate_speech(self, text: str, model: str, voice: str | None = None,
                        style: str | None = None, timeout_s: int = 120) -> dict:
        self._connect()
        self._ensure_hook()

        # UI riêng của TTS: /generate-speech (không phải /prompts/new_chat)
        base = aistudio_url_for(getattr(self, "_page_url", None))
        surl = base.replace("/prompts/new_chat", "/generate-speech")
        sep = "&" if "?" in surl else "?"
        self._send("Page.navigate",
                   {"url": f"{surl}{sep}model={model.replace('models/', '', 1)}"})

        # đợi composer: textarea xuất hiện sau khi chọn example/model
        deadline = time.time() + 25
        while time.time() < deadline:
            time.sleep(2)
            if self._ev("!!document.querySelector('textarea')"):
                break
        if not self._ev("!!document.querySelector('textarea')"):
            # trang landing: click example đầu để mở composer
            self._ev("""(() => {
              const h = [...document.querySelectorAll('h3')].find(
                x => x.textContent.includes('Everyday Assistant'));
              if (h) { const c = h.closest('div[class]'); if (c) c.click(); }
            })()""")
            time.sleep(4)
            if not self._ev("!!document.querySelector('textarea')"):
                raise CDPError("speech composer never appeared")

        # composer example có 3 block pre-baked → XÓA block 2..N (bẫy 24/09:
        # text sót trong block kia bị đưa vào contents → audio dài 23s thay vì
        # ~4s). Xóa từ block CUỐI về block 1.
        nblocks = int(self._ev("document.querySelectorAll('textarea').length") or 1)
        if nblocks > 1:
            for _ in range(nblocks - 1):
                self._ev("""(() => {
                  const tas = [...document.querySelectorAll('textarea')];
                  if (tas.length < 2) return 'done';
                  const ta = tas[tas.length - 1];
                  const blk = ta.closest('div');
                  let node = blk, del = null, hops = 0;
                  while (node && hops < 6 && !del) {
                    del = [...node.querySelectorAll('button')].find(b =>
                      /delete speech block/i.test(b.getAttribute('aria-label')||''));
                    node = node.parentElement; hops++;
                  }
                  if (del) { del.click(); return 'deleted'; }
                  return 'no-del';
                })()""")
                time.sleep(1)
            left = int(self._ev("document.querySelectorAll('textarea').length") or 0)
            if left != 1:
                # fallback: clear text mọi block thừa
                self._ev("""(() => {
                  const tas = [...document.querySelectorAll('textarea')];
                  const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                  tas.forEach((ta, i) => { if (i > 0) { setter.call(ta, ''); ta.dispatchEvent(new Event('input', {bubbles: true})); } });
                })()""")

        # type text của ta vào block[0]
        msg = json.dumps(text)
        self._ev(f"""(async () => {{
          const ta = document.querySelector('textarea');
          if (!ta) return 'no-input';
          ta.focus();
          const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
          setter.call(ta, {msg});
          ta.dispatchEvent(new Event('input', {{bubbles: true}}));
          await new Promise(r => setTimeout(r, 800));
          return 'typed';
        }})()""")

        # voice + style: set window.__tswap cho HOOK (nếu thêm branch TTS)
        if voice or style:
            self._ev("window.__tswap = " + json.dumps({"voice": voice, "style": style}))

        # capture network — GenerateContent từ speech UI
        events = []
        got_ours = False

        def on_evt(r):
            nonlocal got_ours
            m, p = r.get("method", ""), r.get("params", {}) or {}
            if m == "Network.requestWillBeSent":
                u = p.get("request", {}).get("url", "")
                pd = p["request"].get("data") or p["request"].get("postData") or ""
                if "alkalimakersuite" in u and "GenerateContent" in u:
                    if _payload_has_text(pd, text):
                        events.append({"id": p["requestId"], "postData": pd, "done": False})
                        got_ours = True
            elif m == "Network.loadingFinished":
                for e in events:
                    if e["id"] == p.get("requestId"):
                        e["done"] = True

        self._on_event = on_evt
        try:
            # Run: nút textContent "Run" (aria-label rỗng — bẫy 24/09)
            self._ev("""(() => {
              const btns = [...document.querySelectorAll('button')];
              const run = btns.find(b =>
                ((b.getAttribute('aria-label')||'') + ' ' + (b.textContent||''))
                  .trim().startsWith('Run') && !b.disabled);
              if (run) run.click();
            })()""")
            deadline = time.time() + timeout_s
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
                    if time.time() - first_done >= 5:
                        break
                    time.sleep(1)
                else:
                    first_done = None
        finally:
            self._on_event = lambda r: None
            self.ws.settimeout(30)

        if not events:
            raise CDPError("no GenerateContent observed after Run (TTS)")

        bodies = []
        for e in events:
            try:
                r = self._send("Network.getResponseBody", {"requestId": e["id"]})
                bodies.append(r.get("body") or "")
            except Exception:
                pass
        raw = "\n".join(bodies)
        return {"raw": raw[:2_000_000], "request_count": len(events),
                "ours": True}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, r"D:\PROJECTS\aistudio-rev\src\lib")
    from extract import extract_answer

    drv = Driver()
    t0 = time.time()
    out = drv.generate("Say exactly: architecture B works", "models/gemini-3.1-flash-lite")
    print(f"elapsed {time.time()-t0:.1f}s, requests={out['request_count']}")
    print("ANSWER:", repr(extract_answer(out["raw"]))[:200])
