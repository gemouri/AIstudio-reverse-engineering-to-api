# Nutzungsanleitung — Google AI Studio → OpenAI-kompatible API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Dieses Projekt steuert ein echtes Chrome-Fenster, das bei **Ihrer eigenen**
Google AI Studio-Sitzung angemeldet ist, und stellt diese Sitzung erneut als
Standard-API im OpenAI-kompatiblen Format unter `http://127.0.0.1:8788/v1`
bereit. Es gibt keinen Google-API-Schlüssel und keine Abrechnung — es nutzt den
AI Studio-Zugang, den Ihr Konto bereits besitzt.

---

## 1. Voraussetzungen

| Element | Hinweise |
|---|---|
| Betriebssystem | Windows, macOS oder Linux — **Desktop mit Anzeige** (Chrome läuft als echtes, sichtbares Fenster) |
| Python | 3.10 oder neuer |
| Browser | Google Chrome (Chromium oder Edge funktionieren ebenfalls) |
| Google-Konto | Jedes Konto, das `aistudio.google.com` öffnen und einen Prompt senden kann |
| Arbeitsspeicher | ca. 2 GB freier RAM, während Chrome und die API laufen |

## 2. Installation

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Es sind nur zwei Abhängigkeiten erforderlich: `flask` und `websocket-client`.

## 3. Erster Start

### Schritt 1 — den dedizierten Browser starten

```bash
python launch_chrome.py
```

Ein Chrome-Fenster öffnet sich auf `aistudio.google.com` und verwendet ein
**eigenes Profil** (getrennt von dem Browser, den Sie täglich nutzen). Melden
Sie sich mit Ihrem Google-Konto an — dies ist nur beim ersten Mal nötig; die
Sitzung bleibt in diesem Profil erhalten.

> **Lassen Sie dieses Fenster geöffnet.** Es ist die Komponente, die aus der
> Seite ein Token pro Anfrage erzeugt. Wird es geschlossen, stoppt die API.

### Schritt 2 — die API starten (neues Terminal)

```bash
python start.py
```

Erwartete Zeile: `Running on http://127.0.0.1:8788`.

## 4. Funktionsprüfung

Drei Prüfungen, von der schnellsten bis zur vollständigsten:

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

So lesen Sie `/health`:

| Feld | Bedeutung |
|---|---|
| `status` | `ok` = API und Browser sind beide erreichbar. `degraded` = die API läuft, aber der Browser/CDP nicht — Schritt 1 neu starten |
| `hook` | `true` = der Hook zum Patchen der Anfragen ist in die Seite eingebunden (normal) |
| `busy` / `running_model` / `running_for_s` | aktuell läuft eine Anfrage, und seit wie lange |

## 5. Die API aus Ihren Werkzeugen nutzen

Jeder OpenAI-kompatible Client funktioniert. Setzen Sie die Basis-URL auf
`http://127.0.0.1:8788/v1` und verwenden Sie eine beliebige nicht leere
Zeichenkette als API-Schlüssel.

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

### Funktionsaufrufe (tools)

`tools` im OpenAI-Stil werden in das Gemini-Schema übersetzt, und Antworten
kommen als Standard-`tool_calls` zurück:

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

### Mehrere Runden

Senden Sie jedes Mal das vollständige Transkript, genau wie bei jeder anderen
OpenAI-kompatiblen API:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Andere Clients

Richten Sie jedes Werkzeug, das die OpenAI-API spricht, auf dieselbe Basis-URL:
OpenWebUI, LobeChat, LangChain, LlamaIndex, die OpenAI-CLI, Ihre eigenen
Skripte. Bei Clients, die auf einem API-Schlüssel bestehen, verwenden Sie eine
beliebige Platzhalter-Zeichenkette.

## 6. Modelle

`GET /v1/models` ist die lebende Quelle der Wahrheit. Gruppen und typische
Verwendung:

| Gruppe | Modelle | Stufe | Typische Dauer |
|---|---|---|---|
| Kostenloser Chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro-Chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Bilder | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Musik | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Sprache (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Reasoning-Agenten | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Live-Stimme | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Upstream blockiert | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | gibt einen Fehler zurück — auf dieser Stufe nicht unterstützt |

Modelle der kostenlosen Stufe verbrauchen kein bezahltes Kontingent. Pro-,
Premium- und Agent-Modelle nutzen das Kontingent des angemeldeten Kontos; wenn
Google ablehnt, erhalten Sie ein ehrliches HTTP 429 mit Googles eigener
Meldung.

## 7. Medien-Ergebnisse

Modelle, die Medien erzeugen, geben diese in `choices[0].message.media` als
`data:`-URIs zurück — rendern oder speichern Sie sie direkt.

| Modellfamilie | `media[0]` beginnt mit | Hinweise |
|---|---|---|
| Bilder | `data:image/jpeg;base64,` | dasselbe Bild erscheint zusätzlich inline in `content` als Markdown |
| Musik | `data:audio/mpeg;base64,` | MP3 |
| Sprache (TTS) | `data:audio/wav;base64,` | 24 kHz Mono-WAV; die Dauer wird in `content` angegeben |
| Live-Stimme | `data:audio/wav;base64,` | reine Sprachantworten haben ein nahezu leeres `content` |
| Deep Research | `data:image/png;base64,` | Chart-Artefakte; der Bericht selbst steht in `content`, der Rechercheplan in `reasoning_content`, Zitate in `message.sources` |

### Auswahl einer TTS-Stimme

Fügen Sie dem Anfragekörper ein optionales Feld `voice` hinzu. Der Stimmname ist
eine der 70 Stimmen, die AI Studio anbietet — zum Beispiel `Fola` (die
Standardeinstellung der UI), `Puck`, `Lumi`, `Kore`, `Zephyr`, `Aoede`,
`Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Betriebliche Grenzen

- **Eine Anfrage zur Zeit.** Der Browser bearbeitet jeweils genau eine Anfrage;
  eine zweite Anfrage wartet bis zu 90 Sekunden auf die laufende
  (`AIS2A_LOCK_WAIT`) und schlägt dann mit `503 farmer_busy` fehl.
- **Client-Timeouts.** Chat ca. 20–30 s, Bilder ca. 30 s, TTS ca. 45 s, Live
  ca. 80 s, Deep Research 2–5 Minuten. Setzen Sie das Timeout Ihres Clients für
  Agenten großzügig (600 s oder mehr).
- **Keine lokale Tagesgrenze.** Das Ledger zählt lediglich Anfragen pro Modell
  und Tag; es blockiert nichts. Googles eigenes Limit ist das echte Limit und
  zeigt sich als HTTP 429.
- **Halten Sie das Volumen human.** Respektieren Sie die Nutzungsbedingungen
  von AI Studio; nutzen Sie dies nicht, um kostenlose Stufen zu missbrauchen.

## 9. Umgebungsvariablen

| Variable | Standard | Bedeutung |
|---|---|---|
| `AIS2A_PORT` | `8788` | API-Port |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP)-Port |
| `AIS2A_CHROME_BIN` | automatisch erkannt | Pfad zur Binärdatei von Chrome/Chromium/Edge |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | dediziertes Browserprofil (privat für dieses Projekt) |
| `AIS2A_LOCK_WAIT` | `90` | Sekunden, die eine wartende Anfrage auf den Browser wartet |
| `AIS2A_AGENT_TIMEOUT` | `1500` | serverseitiges Timeout für Agent-Modelle (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | serverseitiges Timeout für Sprachmodelle |
| `AIS2A_LIVE_TIMEOUT` | `120` | serverseitiges Timeout für die Live-Stimme |
| `AIS2A_VIDEO_TIMEOUT` | `600` | serverseitiges Timeout für Video-Jobs |

## 10. Fehlerbehebung

| Symptom | Ursache | Lösung |
|---|---|---|
| `Connection refused` auf Port 8788 | die API läuft nicht | `python start.py` |
| `/health` meldet `degraded`, oder Fehler nennen `farmer CDP port not reachable` | das Chrome-Fenster wurde geschlossen oder ist abgestürzt | `python launch_chrome.py` erneut ausführen und bei Aufforderung anmelden |
| `503 farmer_busy` | eine andere Anfrage läuft noch | warten Sie darauf, oder erhöhen Sie `AIS2A_LOCK_WAIT` |
| `429` von der API | Googles eigenes Kontingent/Limit für dieses Modell | warten Sie, oder wechseln Sie zu einem Modell der kostenlosen Stufe |
| `502` mit leerem oder nicht parsbarem Body | AI Studio hat etwas an seinem internen Protokoll geändert | den rohen Body aufbewahren, mit `tools/capture_run.py` neu erfassen, `src/lib/extract*.py` aktualisieren |
| Leeres `content`, aber `media` ist vorhanden | normal bei Bild-, Musik- und Sprachmodellen | `choices[0].message.media` lesen |
| Chrome zeigt „No API key selected“ | das in der UI ausgewählte Modell ist kostenpflichtig gesperrt | der Treiber navigiert automatisch zu einem kostenlosen Host; bleibt es bestehen, wählen Sie im Modellwähler von AI Studio einmalig ein kostenloses Modell |
| Modell fehlt in `/v1/models` | es ist nicht in der Registry eingetragen | fügen Sie es in `src/facade/registry.py` hinzu |
| `antigravity` oder `veo-*` brechen mit Fehler ab | upstream bei Googles Stufe blockiert | über dieses Projekt nicht nutzbar — siehe `docs/protocol-notebook.md` §15 |
| Die Antwort sieht aus wie die Antwort auf eine vorherige Frage | die Anfrage wurde verschluckt, während der Browser gesperrt war | prüfen Sie `/health` auf `busy` und versuchen Sie es dann erneut |

## 11. Wartung

- Starten Sie `start.py` neu, nachdem Sie etwas unter `src/` geändert haben.
- Führen Sie `python launch_chrome.py` erneut aus, wenn die AI Studio-Sitzung
  abläuft (in diesem Fenster erscheint eine Anmeldeseite).
- Wenn Antworten plötzlich mit `403` fehlschlagen, haben sich die Sitzung oder
  das Token pro Anfrage upstream geändert: melden Sie sich im Chrome-Fenster
  erneut an und prüfen Sie anschließend `/health` erneut.

## 12. Weiterführend

- `docs/protocol-notebook.md` — das vollständige Notizbuch zum Reverse
  Engineering: Payload-Formen, Protokollfamilien, Hinweise pro Modell und das
  Modell-Audit (§15).
- `tools/capture_run.py` — Werkzeug zur Ground-Truth-Erfassung (Netzwerk-Bodies,
  DOM, WebSocket-Frames), mit dem ein geändertes Protokoll erneut
  rekonstruiert wird.
