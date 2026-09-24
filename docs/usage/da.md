# Brugsguide — Google AI Studio → OpenAI-kompatibel API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Dette projekt styrer et rigtigt Chrome-vindue, der er logget ind på **din egen**
Google AI Studio-session, og eksponerer den session igen som et standard
OpenAI-kompatibelt API på `http://127.0.0.1:8788/v1`. Der findes ingen Google
API-nøgle og ingen fakturering — det bruger den AI Studio-adgang, din konto
allerede har.

---

## 1. Krav

| Element | Bemærkninger |
|---|---|
| Operativsystem | Windows, macOS eller Linux — **desktop med skærm** (Chrome kører som et rigtigt, synligt vindue) |
| Python | 3.10 eller nyere |
| Browser | Google Chrome (Chromium eller Edge virker også) |
| Google-konto | Enhver konto, der kan åbne `aistudio.google.com` og sende en prompt |
| Hukommelse | ~2 GB fri RAM, mens Chrome og API'et kører |

## 2. Installation

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Der kræves kun to afhængigheder: `flask` og `websocket-client`.

## 3. Første kørsel

### Trin 1 — start den dedikerede browser

```bash
python launch_chrome.py
```

Der åbnes et Chrome-vindue på `aistudio.google.com` med sin **egen profil**
(adskilt fra den browser, du bruger til daglig). Log ind med din Google-konto —
det er kun nødvendigt første gang; sessionen gemmes i den profil.

> **Hold dette vindue åbent.** Det er den komponent, der udsteder et token pr.
> forespørgsel fra siden. Lukker du det, stopper API'et.

### Trin 2 — start API'et (nyt terminalvindue)

```bash
python start.py
```

Forventet linje: `Running on http://127.0.0.1:8788`.

## 4. Kontrollér, at det virker

Tre kontroller, fra den hurtigste til den mest fuldstændige:

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

Sådan læser du `/health`:

| Felt | Betydning |
|---|---|
| `status` | `ok` = API og browser kan begge nås. `degraded` = API'et kører, men browseren/CDP gør ikke — genstart trin 1 |
| `hook` | `true` = request-patching-hooken er installeret i siden (normalt) |
| `busy` / `running_model` / `running_for_s` | en forespørgsel kører lige nu, og hvor længe |

## 5. Brug API'et fra dine værktøjer

Enhver OpenAI-kompatibel klient virker. Sæt base-URL til
`http://127.0.0.1:8788/v1` og enhver ikke-tom streng som API-nøgle.

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

`tools` i OpenAI-stil oversættes til Gemini-skemaet, og svar kommer tilbage som
standard `tool_calls`:

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

Send hele transskriptet hver gang, præcis som med ethvert OpenAI-kompatibelt
API:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Andre klienter

Peg ethvert værktøj, der taler OpenAI-API'et, mod den samme base-URL: OpenWebUI,
LobeChat, LangChain, LlamaIndex, OpenAI CLI, dine egne scripts. Til klienter, der
insisterer på en API-nøgle, brug en vilkårlig pladsholderstreng.

## 6. Modeller

`GET /v1/models` er den levende sandhedskilde. Grupper og typisk brug:

| Gruppe | Modeller | Niveau | Typisk tid |
|---|---|---|---|
| Gratis chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Billeder | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Musik | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Tale (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Reasoning-agenter | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Live-stemme | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Blokeret upstream | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | returnerer en fejl — ikke understøttet på dette niveau |

Modeller på gratisniveau bruger ingen betalt kvote. Pro-, premium- og
agent-modeller bruger den kvote, den indloggede konto har; når Google afviser,
får du et ærligt HTTP 429 med Googles egen besked.

## 7. Medieresultater

Modeller, der producerer medier, returnerer dem i `choices[0].message.media` som
`data:`-URI'er — render eller gem dem direkte.

| Modelfamilie | `media[0]` starter med | Bemærkninger |
|---|---|---|
| Billeder | `data:image/jpeg;base64,` | det samme billede optræder også inline i `content` som markdown |
| Musik | `data:audio/mpeg;base64,` | MP3 |
| Tale (TTS) | `data:audio/wav;base64,` | 24 kHz mono WAV; varigheden rapporteres i `content` |
| Live-stemme | `data:audio/wav;base64,` | svar med kun stemme har et næsten tomt `content` |
| Deep research | `data:image/png;base64,` | diagramartefakter; selve rapporten er i `content`, research-planen i `reasoning_content`, kildehenvisninger i `message.sources` |

### Valg af TTS-stemme

Tilføj et valgfrit `voice`-felt i request-bodyen. Stemmenavnet er en af de 70
stemmer, AI Studio tilbyder — for eksempel `Fola` (UI-standarden), `Puck`,
`Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Driftsgrænser

- **Én forespørgsel ad gangen.** Browseren håndterer én forespørgsel; en anden
  forespørgsel venter på den kørende i op til 90 sekunder (`AIS2A_LOCK_WAIT`) og
  fejler derefter med `503 farmer_busy`.
- **Klient-timeouts.** Chat ~20–30 s, billeder ~30 s, TTS ~45 s, Live ~80 s,
  deep-research 2–5 minutter. Sæt din klient-timeout rundhåndet til agenter
  (600 s eller mere).
- **Ingen lokal daglig grænse.** Regnskabet tæller kun forespørgsler pr. model pr.
  dag; det blokerer ikke noget. Googles egen grænse er den reelle grænse og
  viser sig som HTTP 429.
- **Hold volumen menneskelig.** Respektér AI Studios servicevilkår; brug ikke
  dette til at misbruge gratisniveauer.

## 9. Miljøvariabler

| Variabel | Standard | Betydning |
|---|---|---|
| `AIS2A_PORT` | `8788` | API-port |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP)-port |
| `AIS2A_CHROME_BIN` | auto-detekteret | Sti til Chrome/Chromium/Edge-binæren |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Dedikeret browserprofil (privat for dette projekt) |
| `AIS2A_LOCK_WAIT` | `90` | Sekunder en forespørgsel i kø venter på browseren |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Server-side timeout for agent-modeller (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Server-side timeout for talemodeller |
| `AIS2A_LIVE_TIMEOUT` | `120` | Server-side timeout for Live-stemme |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Server-side timeout for videojob |

## 10. Fejlfinding

| Symptom | Årsag | Løsning |
|---|---|---|
| `Connection refused` på port 8788 | API'et kører ikke | `python start.py` |
| `/health` siger `degraded`, eller fejl nævner `farmer CDP port not reachable` | Chrome-vinduet blev lukket eller crashede | kør `python launch_chrome.py` igen, og log ind, hvis der spørges |
| `503 farmer_busy` | en anden forespørgsel kører stadig | vent på den, eller forhøj `AIS2A_LOCK_WAIT` |
| `429` fra API'et | Googles egen kvote/grænse for den model | vent, eller skift til en model på gratisniveau |
| `502` med en tom eller uplæsbar body | AI Studio ændrede noget i sin interne protokol | gem den rå body, optag igen med `tools/capture_run.py`, opdater `src/lib/extract*.py` |
| Tom `content`, men `media` findes | normalt for billed-, musik- og talemodeller | læs `choices[0].message.media` |
| Chrome viser "No API key selected" | modellen valgt i UI'et er betalingslåst | driveren navigerer automatisk til en gratis host igen; hvis det fortsætter, vælg en gratis model én gang i AI Studios modelvælger |
| Model mangler i `/v1/models` | den findes ikke i registret | tilføj den i `src/facade/registry.py` |
| `antigravity` eller `veo-*` fejler | blokeret upstream på Googles niveau | ikke brugbar gennem dette projekt — se `docs/protocol-notebook.md` §15 |
| Svaret ligner svaret på et tidligere spørgsmål | forespørgslen blev sluget, mens browseren var låst | tjek `/health` for `busy`, og prøv igen |

## 11. Vedligeholdelse

- Genstart `start.py`, efter du har ændret noget under `src/`.
- Kør `python launch_chrome.py` igen, hvis AI Studio-sessionen udløber (der vises
  en login-side i det vindue).
- Hvis svar pludselig begynder at fejle med `403`, er sessionen eller tokenet pr.
  forespørgsel ændret upstream: log ind igen i Chrome-vinduet, og tjek derefter
  `/health`.

## 12. Gå dybere

- `docs/protocol-notebook.md` — den fulde reverse-engineering-notebook:
  payload-former, protokolfamilier, noter pr. model og modelrevisionen (§15).
- `tools/capture_run.py` — værktøj til optagelse af ground truth (netværks-bodies,
  DOM, WebSocket-frames), brugt til at reverse en ændret protokol igen.
