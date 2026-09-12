"""registry.py — MODEL REGISTRY SSOT + smart quota routing (12/09).

Nguồn dữ liệu (ground truth đã verify):
  - ListModels corpus (79 models, methods slot[7], attached model slot[78])
                                    model (slot[78]), voices, context
  - UI model-selector corpus — categorization (8 tabs)
  - quota ledger — observed per-account test results
  - §14 protocol-notebook        — E2E 9/9 families

Thiết kế:
  Model          — id/protocol/tier/media/thinking/context/attached
  Account        — pool + daily budget + per-model counters
  route(model)   — model → (account, driver_path) với quota-awareness

Protocol families (runtime-verified):
  generate       — GenerateContent (chat + image + music inlineData)
  interaction    — CreateInteractionStream (omni, deep-research)
  live           — bidiGenerateContent qua Google WebChannel long-poll
  longrunning    — predictLongRunning (veo video generation)

Tier semantics (AI Studio web, KHÔNG phải API pricing):
  free    — flash-lite family + gemma: free tier AI Studio, không lock
  pro     — flash/pro family: burn quota Pro (67/50 observed → cap 50/day)
  premium — image/music/video: media generation, quota riêng theo slot
  agent   — antigravity/deep-research: wrapper, burn theo attached model
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER_DIR = ROOT / "data"
LEDGER_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Model registry — single source of truth
# ---------------------------------------------------------------------------
# entry: {
#   id: facade-facing short name,
#   model: full "models/..." id,
#   protocol: generate | interaction | live | longrunning,
#   tier: free | pro | premium | agent,
#   media: [media types model can RETURN],
#   thinking: default thinking level (None = model không hỗ trợ),
#   attached: "models/..." — model kèm theo (slot[78]) cho agent wrapper,
#   tabs: UI category tags,
#   note: verified facts,
# }
REGISTRY: list[dict] = [
    # ---- free tier (không burn Pro quota) ----
    {"id": "gemini-3.1-flash-lite", "model": "models/gemini-3.1-flash-lite",
     "protocol": "generate", "tier": "free", "media": ["text"],
     "thinking": None, "tabs": ["Gemini"],
     "note": "UI host chuẩn cho hook swap — free, không lock"},
    {"id": "gemini-3.5-flash-lite", "model": "models/gemini-3.5-flash-lite",
     "protocol": "generate", "tier": "free", "media": ["text"],
     "thinking": None, "tabs": ["Gemini"], "note": ""},
    {"id": "gemini-flash-lite-latest", "model": "models/gemini-flash-lite-latest",
     "protocol": "generate", "tier": "free", "media": ["text"],
     "thinking": None, "tabs": ["Gemini"], "note": "alias Google 12/09"},
    {"id": "gemma-4-26b-a4b-it", "model": "models/gemma-4-26b-a4b-it",
     "protocol": "generate", "tier": "free", "media": ["text"],
     "thinking": None, "tabs": ["Gemma"], "note": "MoE 4B active"},
    {"id": "gemma-4-31b-it", "model": "models/gemma-4-31b-it",
     "protocol": "generate", "tier": "free", "media": ["text"],
     "thinking": None, "tabs": ["Gemma"], "note": ""},

    # ---- pro tier (burn quota Pro ~50/day observed) ----
    {"id": "gemini-3.8-flash", "model": "models/gemini-3.8-flash",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"], "note": "E2E verified §14"},
    {"id": "gemini-3.7-flash", "model": "models/gemini-3.7-flash",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"], "note": ""},
    {"id": "gemini-3.6-flash", "model": "models/gemini-3.6-flash",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"], "note": "antigravity attached"},
    {"id": "gemini-3.5-flash", "model": "models/gemini-3.5-flash",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"], "note": "E2E verified §14"},
    {"id": "gemini-3.1-pro", "model": "models/gemini-3.1-pro-preview",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"],
     "note": "entity -preview (12/09 user confirm)"},
    {"id": "gemini-flash-latest", "model": "models/gemini-flash-latest",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"], "note": ""},
    {"id": "gemini-pro-latest", "model": "models/gemini-pro-latest",
     "protocol": "generate", "tier": "pro", "media": ["text"],
     "thinking": "high", "tabs": ["Gemini"], "note": ""},

    # ---- premium tier: IMAGE (GenerateContent + inlineData image parts) ----
    {"id": "gemini-3-pro-image", "model": "models/gemini-3-pro-image",
     "protocol": "generate", "tier": "premium", "media": ["image", "text"],
     "thinking": None, "tabs": ["Gemini", "Images"],
     "note": "Nano Banana Pro — 2 ảnh JPEG/response, part [null,null,['image/jpeg',b64]]"},
    {"id": "gemini-3.1-flash-image", "model": "models/gemini-3.1-flash-image",
     "protocol": "generate", "tier": "premium", "media": ["image", "text"],
     "thinking": None, "tabs": ["Gemini", "Images"],
     "note": "Nano Banana 2 — 1 ảnh, JPEG"},
    {"id": "gemini-3.1-flash-lite-image", "model": "models/gemini-3.1-flash-lite-image",
     "protocol": "generate", "tier": "premium", "media": ["image", "text"],
     "thinking": None, "tabs": ["Gemini", "Images"],
     "note": "lite variant — có thể free-rate; test 13/09"},

    # ---- premium tier: MUSIC (Lyria) ----
    {"id": "lyria-3.5", "model": "models/lyria-3.5",
     "protocol": "generate", "tier": "premium", "media": ["audio"],
     "thinking": None, "tabs": ["Music"],
     "note": "audio/mpeg inlineData → WAV data-URI trong DOM; thinking LOW proven-200"},
    {"id": "lyria-3-pro", "model": "models/lyria-3-pro-preview",
     "protocol": "generate", "tier": "premium", "media": ["audio"],
     "thinking": None, "tabs": ["Music"], "note": ""},

    # ---- premium tier: VIDEO (veo — predictLongRunning) ----
    {"id": "veo-3.1-generate", "model": "models/veo-3.1-generate-preview",
     "protocol": "longrunning", "tier": "premium", "media": ["video"],
     "thinking": None, "tabs": ["Video"],
     "note": "paid tier per ListModels desc — predictLongRunning RPC"},
    {"id": "veo-3.1-fast-generate", "model": "models/veo-3.1-fast-generate-preview",
     "protocol": "longrunning", "tier": "premium", "media": ["video"],
     "thinking": None, "tabs": ["Video"], "note": ""},
    {"id": "veo-3.1-lite-generate", "model": "models/veo-3.1-lite-generate-preview",
     "protocol": "longrunning", "tier": "premium", "media": ["video"],
     "thinking": None, "tabs": ["Video"], "note": ""},

    # ---- interaction tier (omni) ----
    {"id": "gemini-omni-1.1-flash", "model": "models/gemini-omni-1.1-flash",
     "protocol": "interaction", "tier": "pro", "media": ["text", "video"],
     "thinking": None, "tabs": ["Video"],
     "note": "Interactions API — E2E ANSWER-PASS §14.3"},
    {"id": "gemini-omni-flash-preview", "model": "models/gemini-omni-flash-preview",
     "protocol": "interaction", "tier": "pro", "media": ["text", "video"],
     "thinking": None, "tabs": ["Video"],
     "note": "UI host cho interaction swap"},

    # ---- agent tier (wrapper quanh attached model slot[78]) ----
    {"id": "deep-research-preview", "model": "models/deep-research-preview-04-2026",
     "protocol": "interaction", "tier": "agent", "media": ["text"],
     "thinking": None, "tabs": ["Agents"],
     "attached": "models/gemini-3.1-pro-preview",
     "ui_model": "deep-research-preview-04-2026",
     "note": "Interactions API; slot[47] cấu trúc giống antigravity; UI host phải đúng deep-research UI"},
    {"id": "deep-research-max", "model": "models/deep-research-max-preview-04-2026",
     "protocol": "interaction", "tier": "agent", "media": ["text"],
     "thinking": None, "tabs": ["Agents"],
     "attached": "models/gemini-3.1-pro-preview",
     "ui_model": "deep-research-max-preview-04-2026",
     "note": "max variant — burn nhiều hơn"},
    {"id": "antigravity", "model": "models/antigravity-preview-05-2026",
     "protocol": "interaction", "tier": "agent", "media": ["text"],
     "thinking": None, "tabs": ["Agents"],
     "attached": "models/gemini-3.8-flash",
     "ui_model": "antigravity-preview-05-2026",
     "note": "slot[78]=[null,null,1,1,1,'models/gemini-3.8-flash'] — managed agent wrapper"},

    # ---- live tier (bidiGenerateContent WebChannel) ----
    {"id": "gemini-3.1-flash-live", "model": "models/gemini-3.1-flash-live-preview",
     "protocol": "live", "tier": "premium", "media": ["audio", "text"],
     "thinking": None, "tabs": ["Live"],
     "note": "WebChannel long-poll; PCM 24kHz frames [[5,...]]; session qua Talk; copyright-agree ×4"},
]

BY_ID = {m["id"]: m for m in REGISTRY}


# ---------------------------------------------------------------------------
# Account pool + quota
# ---------------------------------------------------------------------------
class Account:
    """1 farmer Chrome profile / AI Studio account."""

    def __init__(self, u_prefix: str, email: str, pro: bool,
                 daily_budget: int = 50):
        self.u = u_prefix            # "/u/2/"
        self.email = email
        self.pro = pro
        self.daily_budget = daily_budget   # quota Pro/day (67/50 observed → 50)
        _u = u_prefix.strip('/').replace('/', '_')
        self.ledger_path = LEDGER_DIR / (f"quota_ledger_{_u}.json" if _u else "quota_ledger.json")
        self._load()

    def _load(self):
        try:
            d = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if d.get("day") == time.strftime("%Y-%m-%d"):
                self.spend = d.get("spend", 0)
                self.per_model = d.get("per_model", {})
                return
        except Exception:
            pass
        self.spend = 0
        self.per_model = {}

    def save(self):
        self.ledger_path.write_text(json.dumps({
            "account": f"{self.u} ({self.email})", "day": time.strftime("%Y-%m-%d"),
            "spend": self.spend, "per_model": self.per_model,
        }, indent=1), encoding="utf-8")

    def record(self, model_id: str, cost: int = 1, ok: bool = True, note: str = ""):
        """cost: 1 request = 1 quota unit pro/premium; free tier = 0."""
        self.per_model.setdefault(model_id, {"ok": 0, "err": 0})
        self.per_model[model_id]["ok" if ok else "err"] += 1
        self.spend += cost
        self.save()

    def budget_left(self) -> int:
        return max(0, self.daily_budget - self.spend)


# Public build: account = farmer session đang mở (u-prefix tự detect trong
# driver._connect từ URL tab). Budget là heuristic local — Google không expose
# quota số; server error frame (map 429/400 trong facade) mới là nguồn chân thực.
def _auto_account() -> Account:
    return Account("", "farmer-session (auto)", pro=True,
                   daily_budget=int(os.environ.get("AIS2A_DAILY_BUDGET", "50")))


ACCOUNTS: list[Account] = [_auto_account()]
ACTIVE = ACCOUNTS[0]


def route(model_id: str) -> dict:
    """Model → execution plan (account + protocol path + surface hints).

    Trả dict:
      ok / error        — model có trong registry không
      account           — Account được chọn (quota-aware)
      entry             — registry entry
      driver_call       — "generate" | "generate_interaction" | "live" | "longrunning"
      media_expected    — các part shapes extractor cần surface
    Quota policy:
      free   → mọi account, cost 0
      pro    → account Pro còn budget; hết → 429 (chưa có failover tab)
      premium/agent → chỉ account Pro; cost 1 (agent có thể +1 attached)
    """
    e = BY_ID.get(model_id)
    if not e:
        known = sorted(BY_ID)
        return {"ok": False, "error": f"model not in registry ({model_id})",
                "known_models": known}
    if e["tier"] != "free" and not ACTIVE.pro:
        return {"ok": False, "error": "needs Pro account", "entry": e}
    if e["tier"] != "free" and ACTIVE.budget_left() <= 0:
        return {"ok": False,
                "error": f"quota exhausted on {ACTIVE.email} "
                         f"({ACTIVE.spend}/{ACTIVE.daily_budget}) — tomorrow or add account",
                "entry": e}
    call = {"generate": "generate",
            "interaction": "generate_interaction",
            "live": "live_session",
            "longrunning": "longrunning"}[e["protocol"]]
    return {"ok": True, "account": ACTIVE, "entry": e, "driver_call": call,
            "media_expected": e["media"]}


def catalog() -> list[dict]:
    """/v1/models payload với metadata tier/protocol."""
    now = int(time.time())
    out = []
    for m in REGISTRY:
        wired = m["protocol"] in ("generate", "interaction")
        out.append({
            "id": m["id"], "object": "model", "created": now,
            "owned_by": "ais2api",
            "aistudio_tier": m["tier"],
            "protocol": m["protocol"],
            "media": m["media"],
            "thinking": m.get("thinking"),
            "attached_model": (m.get("attached") or "").replace("models/", "") or None,
            "status": "available" if wired else "protocol_reversed_not_wired",
        })
    return out
