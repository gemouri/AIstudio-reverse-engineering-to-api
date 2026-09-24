# Protocol Notebook — Google AI Studio web (S1) internal API

Ngày khảo sát: 2026-09-03 · Tài khoản: <redacted>
Trạng thái: runtime-verified từng mục (mọi claim đều có số record corpus tương ứng).

## 1. Tổng quan bề mặt

AI Studio web (aistudio.google.com) gọi backend qua **JSON-encoded protobuf**
đição `/$rpc/<package>.<Service>/<Method>` trên 2 hostname:

| Host | Service | Vai trò |
|---|---|---|
| `alkalimakersuite-pa.clients6.google.com` | `google.internal.alkali.applications.makersuite.v1.MakerSuiteService` | toàn bộ nghiệp vụ (generate, prompts, models, keys…) |
| `waa-pa.clients6.google.com` | `google.internal.waa.v1.Waa` | Web-Attestation-Attest (anti-abuse) |

Content-Type: `application/json+protobuf`; X-User-Agent: `grpc-web-javascript/0.1`.

## 2. Endpoint inventory (đã bắt được, corpus cdp_net*.jsonl)

| Method | Vai trò | Payload (tóm tắt) |
|---|---|---|
| `GenerateContent` | chat chính | `[model, contents, safety, genconfig, waa_token]` — 11 trường |
| `CountTokens` | đếm token trước khi gửi | `[model, contents]` — KHÔNG cần waa token |
| `GenerateTitle` | tự sinh tên chat | `[user_text, model_answer]` — CẦN waa token riêng |
| `CreatePrompt` | lưu chat vào Drive | toàn bộ lịch sử + metadata |
| `ListPrompts` / `ListModels` / `ListRecentApplets` / `ListPromos` | catalog | `[n]` |
| `GenerateAccessToken` | token nội bộ | — |
| `GetUserPreferences`, `GetLoggingContext`, `GetAiStudioBenefitTier` | meta | — |
| `GenerateCloudApiKey` / `ListCloudApiKeys` / `UpdateCloudApiKey` / `DeleteCloudApiKey` | quản lý API key từ UI | (source-level, script_m_b.txt) |
| `Waa/Create`, `Waa/Ping` | attestation | `[key_id, secret, parent_token]` |

## 3. Auth — 3 lớp (runtime-verified)

```
1. Cookie jar .google.com: SID, HSID, SSID, APISID, SAPISID, __Secure-1P/3P* (13 cookies gửi tới clients6)
2. Authorization header — THUẬT TOÁN ĐÃ BROKEN (verified hash-match):
   SAPISIDHASH  <ts>_<sha1("{ts} {SAPISID} {origin}")>
   SAPISID1PHASH <ts>_<sha1("{ts} {__Secure-1PAPISID} {origin}")>
   SAPISID3PHASH <ts>_<sha1("{ts} {__Secure-3PAPISID} {origin}")>
   origin = https://aistudio.google.com — tái sinh được vô hạn từ cookies
3. X-Goog-Api-Key: AIzaSyDdP816... (web API key của AI Studio — key công khai nhúng trong app)
   + X-Goog-AuthUser: 0, X-AIStudio-Visit-Id: v1_<uuid>
```

**Bằng chứng**: replay byte-identical 200 ×3 (replay_test.py, replay_test2.py);
hash-match 3/3 variant (replay_test2.py ALGORITHM MATCH: True ×3).

## 4. Waa attestation — bức tường anti-abuse (phát hiện quan trọng nhất)

Payload `GenerateContent[4]` là token `!...` (~700-1500 chars). Ma trận thực nghiệm:

| Thay đổi so với capture | Kết quả |
|---|---|
| Không đổi (replay nguyên văn) | **200** — model trả lời đúng |
| Đổi model (`gemini-3.8-flash` → `3.1-flash-lite`, `antigravity-preview`) | **200** |
| Đổi temperature (0.95 → 0.5) | **200** |
| Đổi safety threshold (5 → 3) | **200** |
| **Đổi text user** | **403 "The caller does not have permission"** |
| Bỏ token (payload[4]=null) | **403** |

⇒ Token bind **nội dung text**, không bind model/params.

### 4.1 Cơ chế mint (source-level, script_m_b.txt @ gstatic boq-makersuite)

```js
_.hv = s => sha256_hex(TextEncoder.encode(s))          // SHA-256 thuần JS (h0-h7 constants @455107)
_.lw = req => _.hv(all_texts(req).join(" "))           // hash TOÀN BỘ text request
_.Cp = (provider, content) => provider.A.snapshot({G0b:{content}})   // WASM attestation
// GenerateContent: X = await _.Cp(a.zc, await _.lw(p)); payload[5] = X  (field 5 = index 4 mảng)
```

`snapshot()` là **WebAssembly** (waa blob ~46KB base64 nhận về từ `Waa/Create` response),
không gọi được từ global scope (closure). Token mint MỖI request, bind SHA-256(text).

### 4.2 Hàm ý kiến trúc

- **Pure HTTP replay chỉ hoạt động cho CHÍNH text đã capture** — không phải API thật.
- Đường sống: **browser-mints-token + HTTP/browser replay** — mint token bằng cách type text
  vào playground thật (verified e2e swap_e2e2: "42"), hoặc trình bày trong docs này:
  driver CDP tự hóa việc type + capture.
- Một token = sweep cùng text qua nhiều model/params → công cụ differential probing đẹp.

## 5. Response format (JSON-array protobuf)

```jsonc
// GenerateContent — stream các chunk JSON-array nối tiếp (XHR streaming, không SSE):
[ [[[[[[[null,"42"]],"model"]]],null,[14,1,81,...],...,"v1_..."],   // chunk 1: text
  [..., [null,"",...,["EtkCCt..."]], 1]],                          // chunk 2: thought/signature
  [null,null,null,["1788401607676393",5489501,657974339]] ]         // final: [id, ?, ?]

// Đường text đã verify: walk toàn cây, part [null, "<string>"] là text part.
// src/lib/extract.py — extract_answer() validated trên 3 corpus ('4', '42', '42')
```

ListModels (56KB): `[[["models/<id>",null,"version","Name","desc", input_tokens, output_tokens,
["generateContent","countTokens"], ...], ...]` — bao gồm cả model internal không có trong API
công khai: `antigravity-preview-05-2026` (đã dùng thật qua swap — 200).

## 6. GenConfig mặc định client tự gửi (giá trị nghiên cứu)

```jsonc
[3] = [null,null,null, 65536,  /*maxOutputTokens*/ 1,  /*candidateCount*/ 0.95, /*topP*/ 64, /*topK?*/
       null,..., 1, null,null,[1,null,null,2]]
[2] = [[null,null,7,5],[null,null,8,5],[null,null,9,5],[null,null,10,5]]  // 4 harm categories, threshold 5
```

## 7. Kiến trúc vận hành (đã deploy nội bộ)

```
Hermes (custom_providers.AIStudioRev) 
  → http://127.0.0.1:8788/v1 (façade OpenAI-compat, Flask)
    → src/replay/driver.py (CDP 9333 → farmer Chrome headed)
      → aistudio.google.com playground (mint waa + send + capture)
```

- Verified chain: `hermes -z ... -m asr_gemini-3.1-flash-lite --provider AIStudioRev` → "HERMES-E2E-OK"
- Guardrails: ≤50 req/ngày, ≤2 RPM (runtime-verified: request 3 liên tiếp → 429),
  kill-switch fail-closed (403/empty → trip + 503), fresh-chat mỗi request (chống rerun-trap).
- Watchdog: `src/watchdog/golden_diff.py` — golden "7×6"="42" qua façade, exit code
  0=ok / 1=drift / 2=killed / 3=façade-down.

## 8. Trần hoàn thiện — câu trả lời cho đề bài brainstorm

| Mức | Có được không | Bằng chứng |
|---|---|---|
| Protocol nghiệp vụ (endpoint, payload, response) | **100%** — parse + tái tạo tự do | corpus + driver generate text mới mỗi request |
| Auth (cookies → SAPISIDHASH) | **100%** — tái sinh được algorithm | hash-match 3/3 |
| Waa mint pure-HTTP | **0%** — WASM closure, bind text, một lần/text | 403 matrix |
| Waa mint qua browser | **100%** — nhưng có browser | swap_e2e + driver + HERMES-E2E-OK |
| Multi-model/params sweep mỗi token | **100%** | matrix C/D/E |
| Multi-turn conversation | Chưa làm (v1 single-turn fresh-chat) | — |
| Live/voice, image gen | Ngoài scope v1 (dự kiến phải wrap browser sâu hơn) | — |

**Kết luận**: trần của hybrid harvest-and-repo (B) với bề mặt chat là ~85-90% như ước tính
brainstorm — bức tường duy nhất là waa-WASM bind-text, và nó bị vượt bằng cách để browser
đóng vai "token minter". Reverse protocol 100%, mint 0% pure-HTTP, hybrid 100% tới ngày
Google thay đổi triệt để hơn.

## 9. Chế độ gãy (mode gãy → tín hiệu → hành động)

| Mode | Tín hiệu | Hành vi |
|---|---|---|
| Session chết | 401 UNAUTHENTICATED | farmer re-login tay (2 phút), refresh vault |
| Bot check | 403 + permission | kill-switch ON — dừng hoàn toàn, báo user |
| Schema drift | 200 nhưng extract rỗng | golden_diff exit 1 → re-capture corpus |
| Quota | 429 | façade đã tự hạ; chờ window |

## 10. Corpus index (đềm — không commit)

| File | Nội dung |
|---|---|
| `cdp_net.jsonl` | 128 events phiên capture 1 (headers đầy đủ + cookies) |
| `cdp_net2.jsonl` | 74 events phiên mint-intercept |
| `session_vault_raw.json` | 23 cookies (bảo mật) |
| `script_m_*.txt` | 2 script boq-makersuite (5.3MB) — waa lib + app code |
| `swap_e2e2_result.json` | bằng chứng e2e swap model |
| `golden_baseline.json` | watchdog baseline |

## 13. Function calling + system + multi-turn (03/09 tối — runtime-verified)

**Trả lời câu hỏi "hoạt động như cloud LLM": CÓ, khả thi.**

Phát hiện protocol quyết định:
- **waa bind TOÀN BỘ payload[1] (contents)** — inject contents = 403.
  ⇒ History phải đi qua TYPED TEXT (browser mint) — transcript 1 turn user.
- **payload[5] (systemInstruction) KHÔNG hash** — inject tự do (verified: BANANA).
- **payload[6] (tools) KHÔNG hash** — inject tự do (verified: functionCall 200).

Tools proto map (từ source gp() + capture):
  Schema: [1]=type(1str/2num/3int/4bool/5arr/6obj) [3]=desc [5]=enum [6]=items
          [7]=properties(kv) [8]=required [11/12]=min/max [13/14]=len [17/18/19]=oneOf/anyOf/allOf
  Declaration: [name, description, schema]
  Tool: [null, [decls]]
FunctionCall response part: [None×10, [name, [[[param,[None,None,val]]]], call_id]]
  (args 3-lớp bọc; id = "call_..." giống OpenAI)

**BẪY Schema index 19 (23/09, runtime-verified):** proto index 19 là **`not`**,
KHÔNG phải allOf. Bản cũ ghi `additionalProperties:false` vào p[19] → server trả
400 **non-retryable**:
`Invalid value at 'tools[0].function_declarations[N].parameters.properties[0].value.items.any_of[i].not': false`
→ giết cả request với mọi client gửi JSON Schema kiểu pydantic
`additionalProperties:false` (vd tool `skill_manage` của Hermes). `additionalProperties`
không có field tương ứng trong Schema proto → bỏ qua tĩnh lặng, KHÔNG map.
oneOf@16 / anyOf@17 / allOf@18 vẫn đúng (probe 23/09: 200 OK).
Verify chuẩn: replay payload thật 40 tools của client → 200 + function calling OK.

Façade agent mode (đã verify end-to-end):
- OpenAI tools → Gemini proto: schema_to_proto + openai_tools_to_gemini
- functionCall → tool_calls (chuẩn OpenAI: id/type/function.arguments JSON-string)
- finish_reason: "tool_calls" | "stop"
- Multi-turn: transcript flatten (USER/ASSISTANT/[TOOL RESULTS]) typed 1 turn;
  system → payload[5]; tools → payload[6]
- Chuỗi verify: tool_calls ({"city":"Tokyo"}) → round-trip với tool result →
  final answer đúng context; Hermes CLI multi-round (façade log 17:17-17:20);
  final agent verif: model đọc tool result, trả "AGENT-VERIF-9931" không gọi lại.

Trần khả năng cập nhật: ~95% trải nghiệm cloud LLM (chat + thinking + tools +
multi-turn + streaming). Còn lại: vision/image upload, JSON mode (responseMimeType
field đã biết vị trí), speed (typing mint ~15-25s/request).

## 14. Model mở rộng 12/09 — tier gating + protocol families (account Pro)

9 model mục tiêu nghiên cứu trên **AI Pro** (<account-a> — farmer /u/1/):

| Model | Kết quả runtime | Ghi chú |
|---|---|---|
| `lyria-3-pro-preview`, `lyria-3.5` | **200 OK** — trả semantic music tokens `[[A0]] [:] ...` | Music qua GenerateContent hoạt động như chat thường |
| `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | `[3,"This model only supports Interactions API."]` | KHÔNG phải permission/quota — cần protocol mới |
| `deep-research-preview/max-04-2026` | Cùng lỗi Interactions API | idem |
| `antigravity-preview-05-2026` | **Permission denied** cả free lẫn Pro | Khóa account-tier riêng (managed agent) |
| `veo-3.1-fast/lite-generate-preview` | Chưa probe — `predictLongRunning` | GenerateVideo RPC (xem §14.2) |

### 14.1 Tier/permission gating (source-level)

`kEa` (script_m_b.txt) chặn theo METHOD của model + benefit tier + flag:
- `hEa` = set method đặc biệt: GenerateContent, CountTokens, ProxyUnaryCall,
  CodeAssistantOffline, **CancelInteraction, CreateInteraction(±Stream),
  GetInteractionStream**, **GenerateVideo, GetGenerateVideoOperation**,
  StreamExtractVideoFrames.
- `iEa` = {GenerateVideo, GetGenerateVideoOperation} — cần flag `d`
  (video benefit), header `X-AIStudio-G1-Tier: TIER0/1/2`.
- `jEa` = {CreateInteraction(±Stream), GetInteractionStream, CancelInteraction} —
  cần flag `e` (agent benefit).
- Benefit tier enum: 3=TIER0 (free), 1=TIER1, 2=TIER2.

### 14.2 GenerateVideo RPC (veo, predictLongRunning)

- UI flow: `/prompts/new_video` (hoặc app `/apps/bundled/veo_studio`).
- RPC: `MakerSuiteService/GenerateVideo` — request `[model, prompt, api_key?]`
  (field 1/2/7, class `_.u8a`), response op → poll
  `GetGenerateVideoOperation(name, api_key?)` (class `_.d$a`).
- Veo free-tier cap message: "Veo is available with limited free generations
  per day…" — verify runtime khi triển khai.

### 14.3 Interactions API (omni, deep-research) — REVERSED 12/09 (runtime-verified)

Capture → decode → swap → driver → facade, toàn chuỗi chạy tới cửa quota.

**Request** `POST /$rpc/…/MakerSuiteService/CreateInteractionStream` (XHR, không fetch):
```jsonc
[1, 1, null,
 [ /* interaction config, 54 slots — non-null: */
   17: ["models/<id>", genconfig],        // model + genconfig
   26: [[[[[[["<prompt text>"]]]]]]],     // prompt — bọc 7 lớp
   53: [[[null,null,null,[null,null,null,null,null,2]]]]  // thinking cfg
 ],
 "!<waa token>",                           // payload[4] — CÙNG vị trí GenerateContent
 1]
```

**Response** (1+ JSON frames, mỗi frame = `[events]`):
- `ev[18][0][0]` = interaction id (`v1_…`) · `ev[18][0][17]` = `[model, genconfig]`
- **Answer delta**: `e[10] = [1, [["<text>"]]]` → text tại `e[10][1][0][0]`
- **Thinking delta**: `e[10][1][5][0][0][0]`
- Turn complete: `e[11]=[seq]` · Usage: `e[19][0][11]`
- **Error frame**: `[8,"You exceeded your current quota…"]` / `[3,"permission…"]`
  (cùng mã GenerateContent: 8=quota, 3=permission)

**Phát hiện quyết định:**
1. **waa bind payload[4] — cùng cơ chế GenerateContent** → kiến trúc farmer-swap
   áp dụng nguyên trạng; text phải type thật trên UI (mint qua browser).
2. **Model swap hoạt động**: `p[3][17][0]` đè model → verified response trả từ
   model swap với identity + model-echo đúng (`iswap_resp_13796_4843.json`).
3. UI flow: navigate `/prompts/new_chat?model=<interaction-model>&pli=1`
   (pli=1 GHIM account — không có nó Google snap về authuser=0).
4. Host-model trick: UI host = `gemini-omni-flash-preview` (interaction UI),
   swap payload trỏ model đích bất kỳ (omni-1.1, deep-research ×2).

**Trạng thái E2E**: **ANSWER-PASS VERIFIED 12/09 tối** (quota omni đã về —
`asr_gemini-omni-1.1-flash` trả `OMNI E2E OK` + reasoning_content 15.8s,
`model_verified` đúng). Toàn chuỗi capture→decode→swap→driver→facade→extract
hoàn tất. Facade: 4 model `INTERACTION_MODELS` (asr_gemini-omni-1.1-flash,
asr_gemini-omni-flash-preview, asr_deep-research-preview, asr_deep-research-max)
route qua `Driver.generate_interaction()`; 429 semantic khi quota-frame.

### 14.4 Farmer multi-account trap (12/09 — fix trong driver)

- Navigate tới URL AI Studio 'trần' (không /u/N/) → Google snap về
  **default account authuser=0** → mọi request chạy sai account.
- Driver fix: `aistudio_url_for()` giữ prefix `/u/N/` từ URL tab farmer
  (detect lúc `_connect`, dùng cho mọi Page.navigate).
- Kèm 2 fix đồng thời: (a) account Pro mặc định model paid (Omni) → UI khóa
  Run khi không có API key → driver tự switch UI về model free (flash-lite)
  trước khi swap; (b) account Pro default thinking MINIMAL trong
  genconfig `payload[3][16]=[1,null,null,LEVEL]` — nhiều model không hỗ trợ
  MINIMAL → hook PATCH normalize khi swap model.

### 14.5 Thinking create-or-override — ROOT CAUSE "MINIMAL not supported" (12/09 fix tối)

**Hiện tượng**: `asr_gemini-3.1-pro` 502 "empty response (schema drift?)" intermittent
(18:27–19:03, 4-5 fail/8 call); raw thật = `[,[3,"Thinking level MINIMAL is not
supported for this model.;  model=models/gemini-3.1-pro-preview"]]` — frame lỗi
server stream, KHÔNG phải JSON hợp lệ (dấu phẩy đầu).

**Root cause (runtime-verified bằng probe + instrumentation)**: hook cũ chỉ
normalize khi `p[3][16]` có sẵn ĐÚNG shape `[1,null,null,1]`. Sau free-model
switch (14.4a), UI host = flash-lite → payload host KHÔNG mang field thinking
→ guard `Array.isArray(p[3][16])` skip im lặng → swap sang pro-model mà
genconfig không thinking → server áp **account-default MINIMAL** → reject.
Intermittent vì: khi free-switch thất bại ngầm (UI vẫn pro) → field có sẵn →
PASS; khi switch thật (UI=lite) → FAIL.

**Fix (commit 12/09 tối)** — 3 mũi:
1. HOOK **create-or-override** `p[3][16]` theo TARGET model, không phụ thuộc
   UI host: explicit `sw.thinking_cfg` (từ driver) > lyria/lite → LOW=2
   (proven-200: swap_e2e2 lite + lyria PING) > khác → DEFAULT HIGH=3.
   Url-guard `/GenerateContent/` (GenerateTitle không mang genconfig).
2. Driver bỏ UI-set (mat-select Thinking Level — chết trên lite host 3s/request,
   trả `no-thinking-select`); map low/high/dynamic → `[1,None,None,2/3/4]` vào
   `swap.thinking_cfg`. MINIMAL=1 không bao giờ tự gửi.
3. Facade map error frame `[,[N,"msg"]]` → HTTP 400/429 semantic + msg thật
   (regex bóc vì frame không phải JSON); hết 502 "empty response" mù.

**Levels**: MINIMAL=1 (reject), LOW=2 (proven 200), HIGH=3 (proven 200),
DYNAMIC=4 (observed). waa KHÔNG hash p[3] (verified 03/09) → đè an toàn.

**E2E sau fix (12/09 19:4x)**: 8/8 PASS — pro-high, pro-off, 3.8-flash,
flash-lite, lyria (trả music tokens `[[A0]]…`), + 3 hammer pro liên tiếp.
Instrumentation `corpus/lastgen.json` ghi mọi generate(): p316 luôn được
create-or-override đúng (`[1,null,null,3]` cho pro-high).
Tools: `tools/probe_thinking{,2,3}.py`, `tools/scan_p316.py`, `tools/e2e_matrix.py`.

### 14.6 Live API (bidiGenerateContent) — REVERSED 12/09 tối

`gemini-3.1-flash-live-preview` KHÔNG dùng WebSocket — dùng **Google
WebChannel long-poll** (`webchannel-alkalimakersuite-pa.clients6.google.com/v1/bidiGenerateContent`):

- **Session flow**: UI /live?model=... → click Talk → copyright-agree dialog
  (×4 nút Agree lặp) → session active (nút Stop/Disconnect).
- **Handshake**: POST `count=0` → `[[0,["c","<gsessionid>","",8,14,30000]]]`.
- **Setup send**: `count=1&ofs=0&req0___data__=[null×5,"!waa",["models/...",
  [genconfig incl. voice "Zephyr"],[104857,[52428]]]]` — waa ở payload[5].
- **Text send**: `count=1&ofs=N&req0___data__=[null,null,[null,null,null,null,
  "TEXT"],null,null,"!waa"]` — text ở [2][4], waa ở [5].
- **Response stream**: long-poll hold ~60s, format `"<len>\n[[k,payload]]"`,
  frames tuần tự: 1 noop, 2 setup, 3 quota, 4 content, **5 = audio PCM
  24kHz** `["audio/pcm;rate=24000","<b64>"]`, 7 turn-id, 24/25 generation
  complete, 26 turn-id, 27/28 noop.
- **Decode**: concat PCM b64 → WAV 16-bit mono 24kHz (3.1s voice reply OK).
- Trap: Run/Enter KHÔNG submit khi session idle — phải Talk trước; Stop giết
  session (queued text không được process). Mic permission grant qua
  `Browser.grantPermissions` CDP.
- Corpus: `corpus/cap_live_full_audio.json` (199KB stream), 
  `corpus/live_u2_sample.wav`.

### 14.7 Deep-research response taxonomy — structured RESULT frame (12/09 tối)

Deep-research (Interactions API) KHÔNG stream deltas như omni — trả **result
frame** cuối (body 1.8MB):

```
event (e) = [parts]:
  e[1][0]     = thinking full text (research plan + progress)
  e[2][0]     = answer (markdown report)
  e[3][12][1] = image artifact b64 PNG (chart)  — e[3][29][N][2][1] idem
  e[4][0]     = sources markdown "**Sources:**\n1. [domain](url)…"
  e[4][33][N][1] = raw grounding URLs
```

`extract_interaction.py` giờ handle cả 2 shapes (A: omni delta stream,
B: research result frame). Facade surface thêm `media` (data-URI PNG) +
`sources` trong message.
Verified: deep-research "capital of France" → answer 334 chars + thinking
2560 chars + 1 PNG artifact + 5 sources.

**13/09 update — deep-research-max trả shape A multi-part (runtime-verified,
SE Asia run)**: response = chuỗi answer-deltas, KHÔNG phải 1 result frame B:

```
event[10]  e[10][1][0][0]  = text part 1 (14.5k chars)
event[12]  e[10][1] = [None, [1, <b64 PNG>]]  → b64 tại e[10][1][1][1]
           (PNG header iVBORw0…; guard len>1000 + header check)
event[13]  e[10][1][0][0]  = text part 2 (38.7k chars)
```

2 bugs đã fix trong extractor: (1) thiếu branch image trong shape-A loop;
(2) elif-chain cũ check `v[1][5]` (thinking) trên list len 2 → IndexError →
`except` nuốt cả chuỗi → image branch dù có cũng không chạy — image check
phải đứng TRƯỚC thinking check. E2E 13/09 (SE Asia research, /u/3/):
53.298-char report + PNG chart 99.983 bytes ("Singapore Dominates ASEAN
FDI", FDI 2024: SG $143B / VN $25.35B / ID $24B / MY $12.2B) + 76 sources —
screenshots `docs/screenshots/deep-research-max-*.png`.

### 14.8 Model registry + smart quota (12/09 tối) — user request

`src/facade/registry.py` = SSOT 26 models:
- **tier**: free (lite/gemma — cost 0) / pro (flash/pro — cost 1) / premium
  (image/music/video/live) / agent — 13/09: bỏ local cap 50/day (user
  directive); Google error frame [8] là limit duy nhất.
  (antigravity, deep-research — wrapper quanh attached model slot[78]).
- **protocol**: generate | interaction | live | longrunning — route() trả
  driver call tương ứng; /v1/models giờ trả metadata tier/protocol/media.
- **Quota** (13/09 update): Account class chỉ giữ per-model counters →
  `corpus/quota_ledger_u2.json` (thống kê, KHÔNG gate); hết quota → Google
  error frame [8] → facade map 429 message thật; meta chỉ còn quota_spend.
- Media surface (extract_media): image/jpeg ×2 (pro-image), image/mpeg
  (lyria), interaction images+sources (deep-research) — data-URI trong
  `message.media`.
- Driver unlock fix: paid-model lock sau test live → re-nav `?model=gemini-
  3.1-flash-lite` (URL param, không DOM click — click-path chết ở UI mới).


### 14.9 TTS — gemini-3.8-flash-tts / -lite-tts (24/09 — REVERSED, runtime-verified)

Both models use the same **GenerateContent RPC** (no new endpoint) but a separate UI at `/generate-speech`.

- Voices (70, shared by both models): ListModels slot[66] — Lumi, Bodi, …, Puck, Zephyr (en-US).
- Request: `p[0]` = model, `p[1]` = contents (one user turn per speech block), genconfig `p[3]`: `[4]=1, [5]=0.95, [6]=64`, **voice at `p[3][15] = [[["Fola"]]]`** (note: `p[3][14]=[3]` is a different field — do NOT overwrite), `p[4]` = waa token.
- Response: N parts `[null,null,["audio/l16; rate=24000; channels=1","<b64>"]]` — 16-bit LE mono 24 kHz PCM in 1920–5760-byte chunks; seconds = total_bytes / 48000.
- Driver: `Driver.generate_speech(text, model, voice, style, timeout_s)`.
- Facade: protocol `speech`; optional `"voice": "Puck"` in the request body → HOOK rewrites `p[3][15]` → `message.media = ["data:audio/wav;base64,…"]`.
- E2E verified 24/09: both models + voice override (payload capture shows `p[3][15]=[[["Puck"]]]`).

UI traps (runtime-verified):
1. The `/generate-speech` landing page has no composer — click an example card first; "New chat" closes it again.
2. Example composers pre-bake 3 speech blocks — delete blocks 2..N (last first) or the leftover text ships in `contents` (23.7s audio instead of 3.6s).
3. Run button has empty aria-label — match on textContent.
4. `__tswap` must be set AFTER navigation (the hook re-arms and resets window vars on every new document).
