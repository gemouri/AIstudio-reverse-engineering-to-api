# Käyttöohje — Google AI Studio → OpenAI-yhteensopiva API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Tämä projekti ohjaa oikeaa Chrome-ikkunaa, joka on kirjautuneena **omaan** Google
AI Studio -istuntoosi, ja tarjoaa tämän istunnon uudelleen tavallisena
OpenAI-yhteensopivana API:na osoitteessa `http://127.0.0.1:8788/v1`. Google
API -avainta tai laskutusta ei tarvita — se käyttää sitä AI Studio -käyttöoikeutta,
joka tililläsi jo on.

---

## 1. Vaatimukset

| Kohde | Huomautukset |
|---|---|
| Käyttöjärjestelmä | Windows, macOS tai Linux — **näytöllinen työpöytä** (Chrome toimii oikeana, näkyvänä ikkunana) |
| Python | 3.10 tai uudempi |
| Selain | Google Chrome (Chromium tai Edge toimivat myös) |
| Google-tili | Mikä tahansa tili, joka voi avata `aistudio.google.com` ja lähettää kehotteen |
| Muisti | ~2 GB vapaata RAM-muistia, kun Chrome ja API ovat käynnissä |

## 2. Asennus

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Vain kaksi riippuvuutta tarvitaan: `flask` ja `websocket-client`.

## 3. Ensimmäinen käynnistys

### Vaihe 1 — käynnistä oma selain

```bash
python launch_chrome.py
```

Chrome-ikkuna avautuu osoitteessa `aistudio.google.com` käyttäen sen **omaa
profiilia** (erillään päivittäin käyttämästäsi selaimesta). Kirjaudu sisään
Google-tililläsi — tämä tarvitaan vain ensimmäisellä kerralla; istunto säilyy
siinä profiilissa.

> **Pidä tämä ikkuna auki.** Se on komponentti, joka valmistaa pyyntökohtaisen
> tokenin sivulta. Sen sulkeminen pysäyttää API:n.

### Vaihe 2 — käynnistä API (uusi pääte)

```bash
python start.py
```

Odotettu rivi: `Running on http://127.0.0.1:8788`.

## 4. Toimivuuden varmistaminen

Kolme tarkistusta, nopeimmasta täydellisimpään:

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

Näin luet `/health`-vastauksen:

| Kenttä | Merkitys |
|---|---|
| `status` | `ok` = API ja selain ovat molemmat tavoitettavissa. `degraded` = API on pystyssä, mutta selain/CDP ei — käynnistä vaihe 1 uudelleen |
| `hook` | `true` = pyyntöjen muokkauskoukku on asennettu sivulle (normaali) |
| `busy` / `running_model` / `running_for_s` | pyyntö on parhaillaan käynnissä, ja kuinka kauan |

## 5. API:n käyttö omista työkaluista

Mikä tahansa OpenAI-yhteensopiva asiakasohjelma toimii. Aseta perus-URLiksi
`http://127.0.0.1:8788/v1` ja API-avaimeksi mikä tahansa ei-tyhjä merkkijono.

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### Suoratoisto

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### Funktion kutsuminen (työkalut)

OpenAI-tyyliset `tools` käännetään Geminin skeemaksi ja vastaukset palaavat
tavallisina `tool_calls`-kenttinä:

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

### Monivaiheinen keskustelu

Lähetä koko keskusteluhistoria joka kerta, täsmälleen kuten minkä tahansa
OpenAI-yhteensopivan API:n kanssa:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Muut asiakasohjelmat

Ohjaa mikä tahansa OpenAI API:a puhuva työkalu samaan perus-URLiin: OpenWebUI,
LobeChat, LangChain, LlamaIndex, OpenAI CLI, omat skriptisi. Asiakasohjelmille,
jotka vaativat API-avaimen, käytä mitä tahansa paikkamerkkijonoa.

## 6. Mallit

`GET /v1/models` on elävä totuuden lähde. Ryhmät ja tyypillinen käyttö:

| Ryhmä | Mallit | Taso | Tyypillinen aika |
|---|---|---|---|
| Ilmainen chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro-chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Kuvat | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Musiikki | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Puhe (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Päättelyagentit | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Reaaliaikainen ääni | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Estetty ylävirrassa | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | palauttaa virheen — ei tuettu tällä tasolla |

Ilmaisen tason mallit eivät kuluta maksettua kiintiötä. Pro-, premium- ja
agenttimallit käyttävät kirjautuneen tilin kiintiötä; kun Google kieltäytyy, saat
rehellisen HTTP 429 -vastauksen, joka sisältää Googlen oman viestin.

## 7. Mediatulokset

Mediaa tuottavat mallit palauttavat sen `choices[0].message.media`-kentässä
`data:`-URI:na — renderöi tai tallenna ne suoraan.

| Malliperhe | `media[0]` alkaa | Huomautukset |
|---|---|---|
| Kuvat | `data:image/jpeg;base64,` | sama kuva näkyy myös rivinsisäisesti `content`-kentässä markdownina |
| Musiikki | `data:audio/mpeg;base64,` | MP3 |
| Puhe (TTS) | `data:audio/wav;base64,` | 24 kHz mono-WAV; kesto ilmoitetaan `content`-kentässä |
| Reaaliaikainen ääni | `data:audio/wav;base64,` | pelkästään äänestä koostuvissa vastauksissa `content` on lähes tyhjä |
| Syvätutkimus | `data:image/png;base64,` | kaavioartefaktit; itse raportti on `content`-kentässä, tutkimussuunnitelma `reasoning_content`-kentässä, viittaukset `message.sources`-kentässä |

### TTS-äänen valinta

Lisää valinnainen `voice`-kenttä pyynnön runkoon. Äänen nimi on mikä tahansa
AI Studion tarjoamista 70 äänestä — esimerkiksi `Fola` (käyttöliittymän oletus),
`Puck`, `Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Toiminnalliset rajat

- **Yksi pyyntö kerrallaan.** Selain käsittelee yhden pyynnön; toinen pyyntö
  odottaa käynnissä olevaa enintään 90 sekuntia (`AIS2A_LOCK_WAIT`) ja
  epäonnistuu sen jälkeen virheellä `503 farmer_busy`.
- **Asiakasohjelman aikakatkaisut.** Chat ~20–30 s, kuvat ~30 s, TTS ~45 s,
  Live ~80 s, deep-research 2–5 minuuttia. Aseta asiakasohjelmasi aikakatkaisu
  väljästi agenteille (600 s tai enemmän).
- **Ei paikallista päiväkohtaista rajaa.** Kirjanpito laskee vain pyynnöt mallia
  ja päivää kohti; se ei estä mitään. Googlen oma raja on todellinen raja ja
  näkyy HTTP 429 -vastauksena.
- **Pidä käyttömäärä inhimillisenä.** Noudata AI Studion käyttöehtoja; älä
  käytä tätä ilmaisten tasojen väärinkäyttöön.

## 9. Ympäristömuuttujat

| Muuttuja | Oletus | Merkitys |
|---|---|---|
| `AIS2A_PORT` | `8788` | API-portti |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP) -portti |
| `AIS2A_CHROME_BIN` | tunnistetaan automaattisesti | Polku Chrome/Chromium/Edge-binääriin |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Oma selainprofiili (yksityinen tälle projektille) |
| `AIS2A_LOCK_WAIT` | `90` | Sekunnit, jotka jonossa oleva pyyntö odottaa selainta |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Palvelinpuolen aikakatkaisu agenttimalleille (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Palvelinpuolen aikakatkaisu puhemalleille |
| `AIS2A_LIVE_TIMEOUT` | `120` | Palvelinpuolen aikakatkaisu Live-äänelle |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Palvelinpuolen aikakatkaisu videotehtäville |

## 10. Vianmääritys

| Oire | Syy | Korjaus |
|---|---|---|
| `Connection refused` portissa 8788 | API ei ole käynnissä | `python start.py` |
| `/health` näyttää `degraded`, tai virheet mainitsevat `farmer CDP port not reachable` | Chrome-ikkuna suljettiin tai kaatui | suorita `python launch_chrome.py` uudelleen ja kirjaudu sisään, jos sitä pyydetään |
| `503 farmer_busy` | toinen pyyntö on vielä käynnissä | odota sitä tai kasvata arvoa `AIS2A_LOCK_WAIT` |
| `429` API:sta | Googlen oma kiintiö/raja kyseiselle mallille | odota tai vaihda ilmaisen tason malliin |
| `502` tyhjällä tai jäsentämättömällä rungolla | AI Studio muutti jotain sisäisessä protokollassaan | säilytä raaka runko, kaappaa uudelleen työkalulla `tools/capture_run.py`, päivitä `src/lib/extract*.py` |
| Tyhjä `content`, mutta `media` on läsnä | normaalia kuva-, musiikki- ja puhemalleille | lue `choices[0].message.media` |
| Chrome näyttää "No API key selected" | käyttöliittymässä valittu malli on lukittu maksulliseen tasoon | ajuri navigoi automaattisesti takaisin ilmaiselle isännälle; jos tila jatkuu, valitse ilmainen malli kerran AI Studion mallivalitsimesta |
| Malli puuttuu `/v1/models`-listasta | se ei ole rekisterissä | lisää se tiedostoon `src/facade/registry.py` |
| `antigravity` tai `veo-*` antavat virheen | estetty ylävirrassa Googlen tasolla | ei käytettävissä tämän projektin kautta — katso `docs/protocol-notebook.md` §15 |
| Vastaus näyttää edellisen kysymyksen vastaukselta | pyyntö hukkui selaimen ollessa lukittu | tarkista `/health`-kenttä `busy` ja yritä uudelleen |

## 11. Ylläpito

- Käynnistä `start.py` uudelleen, kun olet muuttanut jotain `src/`-hakemistossa.
- Suorita `python launch_chrome.py` uudelleen, jos AI Studio -istunto vanhenee
  (ikkunaan ilmestyy kirjautumissivu).
- Jos vastaukset alkavat yhtäkkiä epäonnistua koodilla `403`, istunto tai
  pyyntökohtainen token on muuttunut ylävirrassa: kirjaudu uudelleen
  Chrome-ikkunassa ja tarkista sen jälkeen `/health`.

## 12. Syvemmälle

- `docs/protocol-notebook.md` — täysi reverse-engineering-muistikirja:
  hyötykuorman muodot, protokollaperheet, mallikohtaiset muistiinpanot ja
  malliauditointi (§15).
- `tools/capture_run.py` — ground-truth-kaappaustyökalu (verkkorungot, DOM,
  WebSocket-kehykset), jolla muuttunut protokolla voidaan reverse-engineerata
  uudelleen.
