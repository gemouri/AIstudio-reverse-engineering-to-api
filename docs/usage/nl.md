# Gebruikshandleiding — Google AI Studio → OpenAI-compatibele API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Dit project stuurt een echt Chrome-venster aan dat is aangemeld bij **je eigen**
Google AI Studio-sessie, en stelt die sessie opnieuw beschikbaar als een standaard
OpenAI-compatibele API op `http://127.0.0.1:8788/v1`. Er is geen Google API-sleutel en geen facturering —
het gebruikt de AI Studio-toegang die je account al heeft.

---

## 1. Vereisten

| Item | Notities |
|---|---|
| Besturingssysteem | Windows, macOS of Linux — **desktop met een scherm** (Chrome draait als een echt, zichtbaar venster) |
| Python | 3.10 of nieuwer |
| Browser | Google Chrome (Chromium of Edge werken ook) |
| Google-account | Elk account dat `aistudio.google.com` kan openen en een prompt kan versturen |
| Geheugen | ~2 GB vrij RAM terwijl Chrome en de API draaien |

## 2. Installatie

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Er zijn maar twee afhankelijkheden nodig: `flask` en `websocket-client`.

## 3. Eerste keer starten

### Stap 1 — start de speciale browser

```bash
python launch_chrome.py
```

Er opent een Chrome-venster op `aistudio.google.com` met een **eigen profiel**
(los van de browser die je dagelijks gebruikt). Meld je aan met je
Google-account — dit is alleen de eerste keer nodig; de sessie blijft in dat
profiel bewaard.

> **Houd dit venster open.** Het is het onderdeel dat per verzoek een
> token uit de pagina aanmaakt. Sluit je het, dan stopt de API.

### Stap 2 — start de API (nieuwe terminal)

```bash
python start.py
```

Verwachte regel: `Running on http://127.0.0.1:8788`.

## 4. Controleren of het werkt

Drie controles, van snelst naar meest volledig:

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

Hoe je `/health` leest:

| Veld | Betekenis |
|---|---|
| `status` | `ok` = API en browser zijn beide bereikbaar. `degraded` = de API draait maar de browser/CDP niet — herstart stap 1 |
| `hook` | `true` = de request-patching-hook is in de pagina geïnstalleerd (normaal) |
| `busy` / `running_model` / `running_for_s` | er loopt nu een verzoek, en hoe lang al |

## 5. De API gebruiken vanuit je tools

Elke OpenAI-compatibele client werkt. Zet de base-URL op
`http://127.0.0.1:8788/v1` en gebruik een willekeurige niet-lege string als API-sleutel.

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

OpenAI-achtige `tools` worden omgezet naar het Gemini-schema en antwoorden komen terug
als standaard `tool_calls`:

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

Stuur elke keer het volledige transcript mee, precies zoals bij elke OpenAI-compatibele API:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Andere clients

Wijs elk hulpmiddel dat de OpenAI API spreekt naar dezelfde base-URL: OpenWebUI,
LobeChat, LangChain, LlamaIndex, de OpenAI CLI, je eigen scripts. Gebruik voor clients
die aandringen op een API-sleutel een willekeurige placeholdersstring.

## 6. Modellen

`GET /v1/models` is de live bron van waarheid. Groepen en typisch gebruik:

| Groep | Modellen | Niveau | Typische tijd |
|---|---|---|---|
| Gratis chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro-chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Afbeeldingen | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Muziek | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Spraak (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Reasoner-agents | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Live stem | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Geblokkeerd upstream | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | geeft een fout terug — niet ondersteund op dit niveau |

Gratis modellen verbruiken geen betaald quotum. Pro-, premium- en agent-modellen gebruiken
het quotum van het aangemelde account; als Google weigert, krijg je een eerlijke
HTTP 429 met Google's eigen bericht.

## 7. Media-resultaten

Modellen die media produceren, leveren die in `choices[0].message.media` als
`data:`-URI's — render of sla ze direct op.

| Modelfamilie | `media[0]` begint met | Notities |
|---|---|---|
| Afbeeldingen | `data:image/jpeg;base64,` | dezelfde afbeelding verschijnt ook inline in `content` als markdown |
| Muziek | `data:audio/mpeg;base64,` | MP3 |
| Spraak (TTS) | `data:audio/wav;base64,` | 24 kHz mono WAV; de duur staat in `content` |
| Live stem | `data:audio/wav;base64,` | antwoorden met alleen stem hebben een vrijwel lege `content` |
| Diep onderzoek | `data:image/png;base64,` | grafiek-artefacten; het rapport zelf staat in `content`, het onderzoeksplan in `reasoning_content`, bronvermeldingen in `message.sources` |

### Een TTS-stem kiezen

Voeg een optioneel `voice`-veld toe aan de request body. De stemnaam is een van de
70 stemmen die AI Studio biedt — bijvoorbeeld `Fola` (de standaard in de UI), `Puck`,
`Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Operationele limieten

- **Één verzoek tegelijk.** De browser verwerkt één verzoek; een tweede
  verzoek wacht maximaal 90 seconden op het lopende verzoek (`AIS2A_LOCK_WAIT`) en
  faalt daarna met `503 farmer_busy`.
- **Client-timeouts.** Chat ~20–30 s, afbeeldingen ~30 s, TTS ~45 s, Live ~80 s,
  deep-research 2–5 minuten. Zet je client-timeout ruim voor agents
  (600 s of meer).
- **Geen lokale daglimiet.** Het grootboek telt alleen verzoeken per model per dag;
  het blokkeert niets. Google's eigen limiet is de echte limiet en komt naar buiten
  als HTTP 429.
- **Houd het volume menselijk.** Respecteer de servicevoorwaarden van AI Studio; gebruik
  dit niet om gratis niveaus te misbruiken.

## 9. Omgevingsvariabelen

| Variabele | Standaard | Betekenis |
|---|---|---|
| `AIS2A_PORT` | `8788` | API-poort |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP)-poort |
| `AIS2A_CHROME_BIN` | automatisch gedetecteerd | Pad naar de Chrome/Chromium/Edge-binary |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Speciaal browserprofiel (privé voor dit project) |
| `AIS2A_LOCK_WAIT` | `90` | Seconden dat een wachtend verzoek op de browser wacht |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Timeout aan serverzijde voor agent-modellen (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Timeout aan serverzijde voor spraakmodellen |
| `AIS2A_LIVE_TIMEOUT` | `120` | Timeout aan serverzijde voor Live stem |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Timeout aan serverzijde voor videotaken |

## 10. Probleemoplossing

| Symptoom | Oorzaak | Oplossing |
|---|---|---|
| `Connection refused` op poort 8788 | de API draait niet | `python start.py` |
| `/health` zegt `degraded`, of fouten noemen `farmer CDP port not reachable` | het Chrome-venster is gesloten of gecrasht | voer `python launch_chrome.py` opnieuw uit en meld je aan als dat gevraagd wordt |
| `503 farmer_busy` | er loopt nog een ander verzoek | wacht erop, of verhoog `AIS2A_LOCK_WAIT` |
| `429` van de API | Google's eigen quotum/limiet voor dat model | wacht, of stap over op een gratis model |
| `502` met een lege of onparseerbare body | AI Studio heeft iets in zijn interne protocol gewijzigd | bewaar de ruwe body, leg opnieuw vast met `tools/capture_run.py`, werk `src/lib/extract*.py` bij |
| Lege `content` maar `media` aanwezig | normaal voor afbeeldings-, muziek- en spraakmodellen | lees `choices[0].message.media` |
| Chrome toont "No API key selected" | het model dat in de UI is gekozen, is betaald vergrendeld | de driver navigeert automatisch opnieuw naar een gratis host; als het aanhoudt, kies dan één keer een gratis model in de modelkiezer van AI Studio |
| Model ontbreekt in `/v1/models` | het staat niet in het register | voeg het toe aan `src/facade/registry.py` |
| `antigravity` of `veo-*` geven een fout | upstream geblokkeerd op Google's niveau | niet bruikbaar via dit project — zie `docs/protocol-notebook.md` §15 |
| Het antwoord lijkt op het antwoord van een eerdere vraag | het verzoek is ingeslikt terwijl de browser vergrendeld was | controleer `/health` op `busy` en probeer het opnieuw |

## 11. Onderhoud

- Start `start.py` opnieuw na elke wijziging onder `src/`.
- Voer `python launch_chrome.py` opnieuw uit als de AI Studio-sessie verloopt (er verschijnt
  een aanmeldpagina in dat venster).
- Als antwoorden plots met `403` falen, zijn de sessie of het token per verzoek
  upstream gewijzigd: meld je opnieuw aan in het Chrome-venster en controleer
  daarna `/health` opnieuw.

## 12. Dieper graven

- `docs/protocol-notebook.md` — het volledige reverse-engineering-notitieboek: payload-
  vormen, protocolfamilies, notities per model en de modelaudit (§15).
- `tools/capture_run.py` — hulpmiddel voor ground-truth vastlegging (netwerk-bodies, DOM,
  WebSocket-frames) om een gewijzigd protocol opnieuw te reverse-engineeren.
