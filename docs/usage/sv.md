# Användarguide — Google AI Studio → OpenAI-kompatibelt API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Det här projektet styr ett riktigt Chrome-fönster som är inloggat på **din egen**
Google AI Studio-session, och exponerar sessionen igen som ett standardmässigt
OpenAI-kompatibelt API på `http://127.0.0.1:8788/v1`. Det finns ingen Google
API-nyckel och ingen fakturering — den använder den AI Studio-åtkomst ditt konto
redan har.

---

## 1. Krav

| Post | Kommentar |
|---|---|
| Operativsystem | Windows, macOS eller Linux — **stationär dator med skärm** (Chrome körs som ett riktigt, synligt fönster) |
| Python | 3.10 eller nyare |
| Webbläsare | Google Chrome (Chromium eller Edge fungerar också) |
| Google-konto | Vilket konto som helst som kan öppna `aistudio.google.com` och skicka en prompt |
| Minne | ~2 GB ledigt RAM medan Chrome och API:et körs |

## 2. Installation

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Bara två beroenden behövs: `flask` och `websocket-client`.

## 3. Första körningen

### Steg 1 — starta den dedikerade webbläsaren

```bash
python launch_chrome.py
```

Ett Chrome-fönster öppnas på `aistudio.google.com` med sin **egen profil**
(separat från webbläsaren du använder dagligen). Logga in med ditt Google-konto
— det behövs bara första gången; sessionen sparas i den profilen.

> **Håll fönstret öppet.** Det är komponenten som skapar en token per begäran
> från sidan. Stängs det slutar API:et att fungera.

### Steg 2 — starta API:et (ny terminal)

```bash
python start.py
```

Förväntad rad: `Running on http://127.0.0.1:8788`.

## 4. Verifiera att det fungerar

Tre kontroller, från snabbast till mest fullständig:

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

Så tolkar du `/health`:

| Fält | Betydelse |
|---|---|
| `status` | `ok` = både API:et och webbläsaren nås. `degraded` = API:et är igång men webbläsaren/CDP är det inte — starta om steg 1 |
| `hook` | `true` = kroken för att patcha begäranden är installerad i sidan (normalt) |
| `busy` / `running_model` / `running_for_s` | en begäran körs just nu, och hur länge |

## 5. Använda API:et från dina verktyg

Alla OpenAI-kompatibla klienter fungerar. Sätt bas-URL:en till
`http://127.0.0.1:8788/v1` och valfri icke-tom sträng som API-nyckel.

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

### Funktionsanrop (tools)

`tools` i OpenAI-stil översätts till Gemini-schemat och svaren kommer tillbaka
som vanliga `tool_calls`:

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

### Flera turer

Skicka hela transkriptet varje gång, precis som med alla OpenAI-kompatibla API:er:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Andra klienter

Peka vilket verktyg som helst som talar OpenAI-API:et mot samma bas-URL:
OpenWebUI, LobeChat, LangChain, LlamaIndex, OpenAI CLI, dina egna skript. För
klienter som kräver en API-nyckel, använd valfri platshållarsträng.

## 6. Modeller

`GET /v1/models` är den levande källan till sanning. Grupper och typisk användning:

| Grupp | Modeller | Nivå | Typisk tid |
|---|---|---|---|
| Gratis chatt | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro-chatt | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Bilder | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Musik | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Tal (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Resonemangsagenter | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Live-röst | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Blockerade uppströms | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | returnerar ett fel — stöds inte på denna nivå |

Modeller på gratissnivån förbrukar ingen betald kvot. Pro-, premium- och
agentmodeller använder kvoten för det inloggade kontot; när Google nekar får du
en ärlig HTTP 429 med Googles eget meddelande.

## 7. Medieresultat

Modeller som producerar media returnerar dem i `choices[0].message.media` som
`data:`-URI:er — rendera eller spara dem direkt.

| Modellfamilj | `media[0]` börjar med | Kommentar |
|---|---|---|
| Bilder | `data:image/jpeg;base64,` | samma bild visas även inline i `content` som markdown |
| Musik | `data:audio/mpeg;base64,` | MP3 |
| Tal (TTS) | `data:audio/wav;base64,` | 24 kHz mono WAV; längden rapporteras i `content` |
| Live-röst | `data:audio/wav;base64,` | svar med bara röst har ett i stort sett tomt `content` |
| Djup research | `data:image/png;base64,` | diagramartefakter; själva rapporten ligger i `content`, researchplanen i `reasoning_content`, källhänvisningar i `message.sources` |

### Välja en TTS-röst

Lägg till ett valfritt fält `voice` i begärandekroppen. Rösten kan vara vilken
som helst av de 70 röster AI Studio erbjuder — till exempel `Fola` (standard i
gränssnittet), `Puck`, `Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Driftsgränser

- **En begäran i taget.** Webbläsaren hanterar en enda begäran; en andra
  begäran väntar på den som kör i upp till 90 sekunder (`AIS2A_LOCK_WAIT`) och
  misslyckas därefter med `503 farmer_busy`.
- **Klienttimeout.** Chatt ~20–30 s, bilder ~30 s, TTS ~45 s, Live ~80 s,
  djup research 2–5 minuter. Sätt klientens timeout generöst för agenter
  (600 s eller mer).
- **Inget lokalt dagstak.** Liggaren räknar bara begäranden per modell och dag;
  den blockerar ingenting. Googles egen gräns är den verkliga gränsen och visas
  som HTTP 429.
- **Håll volymen mänsklig.** Respektera AI Studios användarvillkor; använd inte
  detta för att missbruka gratissnivåer.

## 9. Miljövariabler

| Variabel | Standard | Betydelse |
|---|---|---|
| `AIS2A_PORT` | `8788` | API-port |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools-port (CDP) |
| `AIS2A_CHROME_BIN` | identifieras automatiskt | Sökväg till Chrome-/Chromium-/Edge-binären |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Dedikerad webbläsarprofil (privat för detta projekt) |
| `AIS2A_LOCK_WAIT` | `90` | Sekunder en köad begäran väntar på webbläsaren |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Timeout på serversidan för agentmodeller (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Timeout på serversidan för talmodeller |
| `AIS2A_LIVE_TIMEOUT` | `120` | Timeout på serversidan för Live-röst |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Timeout på serversidan för videouppgifter |

## 10. Felsökning

| Symtom | Orsak | Åtgärd |
|---|---|---|
| `Connection refused` på port 8788 | API:et körs inte | `python start.py` |
| `/health` visar `degraded`, eller fel nämner `farmer CDP port not reachable` | Chrome-fönstret stängdes eller kraschade | kör `python launch_chrome.py` igen och logga in om det efterfrågas |
| `503 farmer_busy` | en annan begäran körs fortfarande | vänta på den, eller höj `AIS2A_LOCK_WAIT` |
| `429` från API:et | Googles egen kvot/gräns för den modellen | vänta, eller byt till en modell på gratissnivån |
| `502` med tom eller otolkbar kropp | AI Studio ändrade något i sitt interna protokoll | spara den råa kroppen, fånga igen med `tools/capture_run.py`, uppdatera `src/lib/extract*.py` |
| Tomt `content` men `media` finns | normalt för bild-, musik- och talmodeller | läs `choices[0].message.media` |
| Chrome visar "No API key selected" | modellen som valts i gränssnittet är låst bakom betalning | drivrutinen navigerar automatiskt om till en gratisvärd; om det kvarstår, välj en gratismodell en gång i AI Studios modellväljare |
| Modell saknas i `/v1/models` | den finns inte i registret | lägg till den i `src/facade/registry.py` |
| `antigravity` eller `veo-*` ger fel | blockerat uppströms på Googles nivå | går inte att använda via detta projekt — se `docs/protocol-notebook.md` §15 |
| Svaret ser ut som svaret på en tidigare fråga | begäran svaldes medan webbläsaren var låst | kontrollera `busy` i `/health` och försök igen |

## 11. Underhåll

- Starta om `start.py` efter att ha ändrat något under `src/`.
- Kör `python launch_chrome.py` igen om AI Studio-sessionen går ut (en
  inloggningssida visas i det fönstret).
- Om svaren plötsligt börjar misslyckas med `403` har sessionen eller token per
  begäran ändrats uppströms: logga in igen i Chrome-fönstret och kontrollera
  sedan `/health` på nytt.

## 12. Gå djupare

- `docs/protocol-notebook.md` — den fullständiga anteckningsboken för reverse
  engineering: payloadformer, protokollfamiljer, anteckningar per modell och
  modellrevisionen (§15).
- `tools/capture_run.py` — verktyg för att fånga grundsanning (nätverkskroppar,
  DOM, WebSocket-ramar) som används för att reverse-engineera ett ändrat
  protokoll på nytt.
