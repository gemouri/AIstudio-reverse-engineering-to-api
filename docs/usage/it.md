# Guida all'uso — Google AI Studio → API compatibile con OpenAI

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Questo progetto pilota una vera finestra Chrome collegata alla **propria**
sessione Google AI Studio e riespone tale sessione come API standard
compatibile con OpenAI su `http://127.0.0.1:8788/v1`. Non servono una chiave API
Google né un account di fatturazione — viene utilizzato l'accesso ad AI Studio
di cui l'account dispone già.

---

## 1. Requisiti

| Voce | Note |
|---|---|
| Sistema operativo | Windows, macOS o Linux — **desktop con display** (Chrome viene eseguito come finestra reale e visibile) |
| Python | 3.10 o versione successiva |
| Browser | Google Chrome (funzionano anche Chromium ed Edge) |
| Account Google | Qualsiasi account in grado di aprire `aistudio.google.com` e inviare un prompt |
| Memoria | ~2 GB di RAM libera durante l'esecuzione di Chrome e dell'API |

## 2. Installazione

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Sono necessarie soltanto due dipendenze: `flask` e `websocket-client`.

## 3. Primo avvio

### Passo 1 — avviare il browser dedicato

```bash
python launch_chrome.py
```

Si apre una finestra Chrome su `aistudio.google.com` con un **profilo
dedicato** (separato dal browser utilizzato quotidianamente). Accedere con il
proprio account Google — l'operazione è necessaria solo la prima volta; la
sessione viene conservata in quel profilo.

> **Mantenere aperta questa finestra.** È il componente che genera dalla pagina
> un token per ogni richiesta. Chiuderla interrompe l'API.

### Passo 2 — avviare l'API (nuovo terminale)

```bash
python start.py
```

Riga attesa: `Running on http://127.0.0.1:8788`.

## 4. Verificare che funzioni

Tre controlli, dal più rapido al più completo:

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

Come interpretare `/health`:

| Campo | Significato |
|---|---|
| `status` | `ok` = API e browser entrambi raggiungibili. `degraded` = l'API è attiva ma il browser/CDP no — riavviare il passo 1 |
| `hook` | `true` = l'hook di patching delle richieste è installato nella pagina (normale) |
| `busy` / `running_model` / `running_for_s` | una richiesta è attualmente in esecuzione, e da quanto tempo |

## 5. Usare l'API dai propri strumenti

Qualsiasi client compatibile con OpenAI funziona. Impostare come base URL
`http://127.0.0.1:8788/v1` e una stringa qualsiasi non vuota come chiave API.

### Python (SDK OpenAI)

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

### Chiamata di funzioni (tools)

I `tools` in stile OpenAI vengono tradotti nello schema Gemini e le risposte
tornano come `tool_calls` standard:

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

### Multi-turno

Inviare ogni volta la trascrizione completa, esattamente come con qualsiasi API
compatibile con OpenAI:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Altri client

Puntare qualsiasi strumento che parli l'API OpenAI allo stesso base URL:
OpenWebUI, LobeChat, LangChain, LlamaIndex, la CLI OpenAI, i propri script. Per
i client che pretendono una chiave API, usare una stringa segnaposto qualsiasi.

## 6. Modelli

`GET /v1/models` è la fonte di verità in tempo reale. Gruppi e uso tipico:

| Gruppo | Modelli | Livello | Tempo tipico |
|---|---|---|---|
| Chat gratuita | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Chat Pro | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Immagini | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Musica | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Voce (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Agenti di ragionamento | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Voce live | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Bloccati a monte | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | restituisce un errore — non supportati a questo livello |

I modelli del livello gratuito non consumano quota a pagamento. I modelli Pro,
premium e agent utilizzano la quota dell'account con cui è stato effettuato
l'accesso; quando Google rifiuta, si riceve un onesto HTTP 429 che riporta il
messaggio di Google stesso.

## 7. Risultati multimediali

I modelli che producono contenuti multimediali li restituiscono in
`choices[0].message.media` come URI `data:` — visualizzarli o salvarli
direttamente.

| Famiglia di modelli | `media[0]` inizia con | Note |
|---|---|---|
| Immagini | `data:image/jpeg;base64,` | la stessa immagine compare anche inline in `content` come markdown |
| Musica | `data:audio/mpeg;base64,` | MP3 |
| Voce (TTS) | `data:audio/wav;base64,` | WAV mono a 24 kHz; la durata è riportata in `content` |
| Voce live | `data:audio/wav;base64,` | le risposte solo vocali hanno un `content` quasi vuoto |
| Deep research | `data:image/png;base64,` | artefatti grafici; il report vero e proprio è in `content`, il piano di ricerca in `reasoning_content`, le citazioni in `message.sources` |

### Scegliere una voce TTS

Aggiungere al corpo della richiesta un campo opzionale `voice`. Il nome della
voce può essere una qualsiasi delle 70 voci offerte da AI Studio — per esempio
`Fola` (predefinita nell'interfaccia), `Puck`, `Lumi`, `Kore`, `Zephyr`,
`Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Limiti operativi

- **Una richiesta alla volta.** Il browser gestisce una sola richiesta; una
  seconda richiesta attende quella in corso per un massimo di 90 secondi
  (`AIS2A_LOCK_WAIT`) e poi fallisce con `503 farmer_busy`.
- **Timeout del client.** Chat ~20–30 s, immagini ~30 s, TTS ~45 s, Live ~80 s,
  deep-research 2–5 minuti. Impostare un timeout del client generoso per gli
  agenti (600 s o più).
- **Nessun limite giornaliero locale.** Il registro conta soltanto le richieste
  per modello al giorno; non blocca nulla. Il limite reale è quello di Google e
  si manifesta come HTTP 429.
- **Mantenere un volume umano.** Rispettare i termini di servizio di AI Studio;
  non utilizzare il progetto per abusare dei livelli gratuiti.

## 9. Variabili d'ambiente

| Variabile | Predefinito | Significato |
|---|---|---|
| `AIS2A_PORT` | `8788` | Porta dell'API |
| `AIS2A_CDP_PORT` | `9333` | Porta di Chrome DevTools (CDP) |
| `AIS2A_CHROME_BIN` | rilevato automaticamente | Percorso del binario Chrome/Chromium/Edge |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Profilo browser dedicato (privato per questo progetto) |
| `AIS2A_LOCK_WAIT` | `90` | Secondi di attesa di una richiesta in coda per il browser |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Timeout lato server per i modelli agent (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Timeout lato server per i modelli vocali |
| `AIS2A_LIVE_TIMEOUT` | `120` | Timeout lato server per la voce Live |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Timeout lato server per i job video |

## 10. Risoluzione dei problemi

| Sintomo | Causa | Soluzione |
|---|---|---|
| `Connection refused` sulla porta 8788 | l'API non è in esecuzione | `python start.py` |
| `/health` indica `degraded`, oppure gli errori citano `farmer CDP port not reachable` | la finestra Chrome è stata chiusa o è andata in crash | eseguire di nuovo `python launch_chrome.py` e accedere se richiesto |
| `503 farmer_busy` | un'altra richiesta è ancora in corso | attenderla, oppure aumentare `AIS2A_LOCK_WAIT` |
| `429` dall'API | quota/limite di Google per quel modello | attendere, oppure passare a un modello del livello gratuito |
| `502` con corpo vuoto o non analizzabile | AI Studio ha modificato qualcosa nel proprio protocollo interno | conservare il corpo grezzo, riacquisire con `tools/capture_run.py`, aggiornare `src/lib/extract*.py` |
| `content` vuoto ma `media` presente | normale per i modelli di immagini, musica e voce | leggere `choices[0].message.media` |
| Chrome mostra "No API key selected" | il modello selezionato nell'interfaccia è bloccato perché a pagamento | il driver naviga automaticamente verso un host gratuito; se il problema persiste, selezionare una volta un modello gratuito nel selettore di modelli di AI Studio |
| Modello assente da `/v1/models` | non è presente nel registro | aggiungerlo a `src/facade/registry.py` |
| `antigravity` o `veo-*` restituiscono un errore | bloccati a monte per il livello di Google | non utilizzabili tramite questo progetto — vedere `docs/protocol-notebook.md` §15 |
| La risposta sembra quella di una domanda precedente | la richiesta è stata inghiottita mentre il browser era bloccato | controllare `busy` in `/health`, poi riprovare |

## 11. Manutenzione

- Riavviare `start.py` dopo qualsiasi modifica sotto `src/`.
- Eseguire di nuovo `python launch_chrome.py` se la sessione AI Studio scade
  (in quella finestra compare una pagina di accesso).
- Se le risposte iniziano a fallire tutte insieme con `403`, la sessione o il
  token per richiesta sono cambiati a monte: accedere di nuovo nella finestra
  Chrome, poi ricontrollare `/health`.

## 12. Per approfondire

- `docs/protocol-notebook.md` — il notebook completo di reverse engineering:
  forme dei payload, famiglie di protocollo, note per modello e l'audit dei
  modelli (§15).
- `tools/capture_run.py` — strumento di acquisizione ground-truth (corpi di
  rete, DOM, frame WebSocket) usato per rifare il reverse engineering di un
  protocollo modificato.
