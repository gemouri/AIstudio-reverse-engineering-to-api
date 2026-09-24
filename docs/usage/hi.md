# उपयोग गाइड — Google AI Studio → OpenAI-compatible API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

यह प्रोजेक्ट एक असली Chrome विंडो चलाता है जो **आपके ही** Google
AI Studio session में साइन-इन होती है, और उसी session को `http://127.0.0.1:8788/v1`
पर एक मानक OpenAI-compatible API के रूप में फिर से उजागर करता है। यहाँ न कोई
Google API key है और न कोई billing — यह उसी AI Studio access का उपयोग करता है
जो आपके account के पास पहले से है।

---

## 1. आवश्यकताएँ

| मद | विवरण |
|---|---|
| Operating system | Windows, macOS या Linux — **display वाला desktop** (Chrome एक असली, दिखाई देने वाली विंडो के रूप में चलता है) |
| Python | 3.10 या उससे नया |
| Browser | Google Chrome (Chromium या Edge भी काम करते हैं) |
| Google account | कोई भी account जो `aistudio.google.com` खोल सके और prompt भेज सके |
| Memory | Chrome और API चलते समय लगभग 2 GB मुक्त RAM |

## 2. इंस्टॉल

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

केवल दो dependencies चाहिए: `flask` और `websocket-client`।

## 3. पहला रन

### चरण 1 — समर्पित browser शुरू करें

```bash
python launch_chrome.py
```

एक Chrome विंडो `aistudio.google.com` पर खुलती है और वह अपनी **अलग profile**
का उपयोग करती है (आपके रोज़मर्रा के browser से अलग)। अपने Google account से
साइन इन करें — यह केवल पहली बार ज़रूरी है; session उसी profile में सुरक्षित
रहता है।

> **इस विंडो को खुला रखें।** यही वह component है जो पेज से प्रति-request
> token बनाता है। इसे बंद करने पर API रुक जाती है।

### चरण 2 — API शुरू करें (नया terminal)

```bash
python start.py
```

अपेक्षित पंक्ति: `Running on http://127.0.0.1:8788`.

## 4. जाँचें कि यह काम करता है

तीन जाँचें, सबसे तेज़ से सबसे पूरी तक:

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

`/health` को कैसे पढ़ें:

| फ़ील्ड | अर्थ |
|---|---|
| `status` | `ok` = API और browser दोनों उपलब्ध हैं। `degraded` = API चालू है पर browser/CDP नहीं — चरण 1 दोबारा चलाएँ |
| `hook` | `true` = पेज में request-patching hook लगा हुआ है (सामान्य) |
| `busy` / `running_model` / `running_for_s` | इस समय एक request चल रही है, और कितने समय से |

## 5. अपने tools से API का उपयोग

कोई भी OpenAI-compatible client काम करता है। base URL को
`http://127.0.0.1:8788/v1` पर सेट करें और API key के रूप में कोई भी non-empty
string रखें।

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

OpenAI-शैली के `tools` को Gemini schema में बदला जाता है और उत्तर मानक
`tool_calls` के रूप में वापस आते हैं:

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

हर बार पूरा transcript भेजें, ठीक वैसे ही जैसे किसी भी OpenAI-compatible API के साथ:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### अन्य clients

हर उस tool को, जो OpenAI API बोलता है, इसी base URL पर इंगित करें: OpenWebUI,
LobeChat, LangChain, LlamaIndex, OpenAI CLI, आपकी अपनी scripts. जो clients
API key पर ज़ोर देते हैं, उनके लिए कोई भी placeholder string रखें।

## 6. मॉडल

`GET /v1/models` ही जीवंत स्रोत है। समूह और सामान्य उपयोग:

| समूह | Models | Tier | सामान्य समय |
|---|---|---|---|
| Free chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Images | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Music | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Speech (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Reasoning agents | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Live voice | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Blocked upstream | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | error लौटाते हैं — इस tier पर समर्थित नहीं |

Free-tier models कोई paid quota नहीं खर्च करते। Pro, premium और agent models
साइन-इन किए गए account का quota उपयोग करते हैं; जब Google मना करता है, तो आपको
Google का ही संदेश लिए हुए एक सच्चा HTTP 429 मिलता है।

## 7. Media परिणाम

जो models media बनाते हैं, वे उन्हें `choices[0].message.media` में `data:`
URIs के रूप में लौटाते हैं — उन्हें सीधे render करें या save करें।

| Model family | `media[0]` की शुरुआत | विवरण |
|---|---|---|
| Images | `data:image/jpeg;base64,` | वही image `content` में भी markdown के रूप में inline दिखती है |
| Music | `data:audio/mpeg;base64,` | MP3 |
| Speech (TTS) | `data:audio/wav;base64,` | 24 kHz mono WAV; अवधि `content` में बताई जाती है |
| Live voice | `data:audio/wav;base64,` | केवल-voice वाले उत्तरों का `content` लगभग खाली होता है |
| Deep research | `data:image/png;base64,` | chart artifacts; रिपोर्ट स्वयं `content` में, research plan `reasoning_content` में, और citations `message.sources` में |

### TTS voice चुनना

request body में एक वैकल्पिक `voice` field जोड़ें। voice का नाम AI Studio द्वारा
दिए गए 70 voices में से कोई भी हो सकता है — जैसे `Fola` (UI का default), `Puck`,
`Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`।

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. परिचालन सीमाएँ

- **एक समय में एक ही request।** browser एक ही request संभालता है; दूसरी request
  चल रही request के लिए अधिकतम 90 सेकंड (`AIS2A_LOCK_WAIT`) प्रतीक्षा करती है और
  फिर `503 farmer_busy` के साथ विफल हो जाती है।
- **Client timeouts।** Chat ~20–30 s, images ~30 s, TTS ~45 s, Live ~80 s,
  deep-research 2–5 मिनट। agents के लिए अपना client timeout उदार रखें
  (600 s या अधिक)।
- **कोई स्थानीय दैनिक cap नहीं।** ledger केवल प्रति model प्रति दिन requests
  गिनता है; यह कुछ भी रोकता नहीं। Google की अपनी सीमा ही असली सीमा है और वह
  HTTP 429 के रूप में सामने आती है।
- **मात्रा मानवीय रखें।** AI Studio की terms of service का पालन करें; इसका
  उपयोग free tiers के दुरुपयोग के लिए न करें।

## 9. Environment variables

| चर | Default | अर्थ |
|---|---|---|
| `AIS2A_PORT` | `8788` | API port |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP) port |
| `AIS2A_CHROME_BIN` | auto-detected | Chrome/Chromium/Edge binary का path |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | समर्पित browser profile (इस प्रोजेक्ट के लिए ही निजी) |
| `AIS2A_LOCK_WAIT` | `90` | queue में लगी request browser के लिए कितने सेकंड प्रतीक्षा करती है |
| `AIS2A_AGENT_TIMEOUT` | `1500` | agent models (deep-research) के लिए server-side timeout |
| `AIS2A_TTS_TIMEOUT` | `120` | speech models के लिए server-side timeout |
| `AIS2A_LIVE_TIMEOUT` | `120` | Live voice के लिए server-side timeout |
| `AIS2A_VIDEO_TIMEOUT` | `600` | video jobs के लिए server-side timeout |

## 10. समस्या-निवारण

| लक्षण | कारण | समाधान |
|---|---|---|
| port 8788 पर `Connection refused` | API चल नहीं रही | `python start.py` |
| `/health` में `degraded`, या errors में `farmer CDP port not reachable` | Chrome विंडो बंद हो गई या crash हो गई | `python launch_chrome.py` दोबारा चलाएँ और पूछे जाने पर साइन इन करें |
| `503 farmer_busy` | कोई दूसरी request अभी चल रही है | उसके पूरा होने की प्रतीक्षा करें, या `AIS2A_LOCK_WAIT` बढ़ाएँ |
| API से `429` | उस model के लिए Google की ही quota/सीमा | प्रतीक्षा करें, या किसी free-tier model पर स्विच करें |
| खाली या unparsable body के साथ `502` | AI Studio ने अपने आंतरिक protocol में कुछ बदल दिया | raw body सुरक्षित रखें, `tools/capture_run.py` से दोबारा capture करें, `src/lib/extract*.py` अपडेट करें |
| `content` खाली पर `media` मौजूद | image, music और speech models के लिए सामान्य | `choices[0].message.media` पढ़ें |
| Chrome में "No API key selected" दिखता है | UI में चुना गया model paid-locked है | driver स्वयं किसी free host पर दोबारा जाता है; यदि समस्या बनी रहे, तो AI Studio model picker में एक बार कोई free model चुनें |
| `/v1/models` में model नहीं दिखता | वह registry में नहीं है | उसे `src/facade/registry.py` में जोड़ें |
| `antigravity` या `veo-*` error देते हैं | Google के tier पर upstream से blocked | इस प्रोजेक्ट से उपयोग नहीं हो सकते — देखें `docs/protocol-notebook.md` §15 |
| उत्तर पिछले सवाल के उत्तर जैसा दिखता है | browser के locked रहते समय request निगल ली गई | `/health` में `busy` जाँचें, फिर दोबारा प्रयास करें |

## 11. रखरखाव

- `src/` के अंतर्गत कुछ भी बदलने के बाद `start.py` दोबारा शुरू करें।
- यदि AI Studio session समाप्त हो जाए (उस विंडो में sign-in पेज दिखने लगे), तो
  `python launch_chrome.py` फिर से चलाएँ।
- यदि उत्तर अचानक `403` के साथ विफल होने लगें, तो upstream पर session या
  प्रति-request token बदल गया है: Chrome विंडो में दोबारा साइन इन करें, फिर
  `/health` दोबारा जाँचें।

## 12. और गहराई में

- `docs/protocol-notebook.md` — पूरी reverse-engineering notebook: payload
  shapes, protocol families, प्रति-model नोट्स, और model audit (§15)।
- `tools/capture_run.py` — ground-truth capture tool (network bodies, DOM,
  WebSocket frames) जिसका उपयोग बदले हुए protocol को दोबारा reverse करने के लिए
  किया जाता है।
