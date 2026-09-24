# 사용 안내 — Google AI Studio → OpenAI 호환 API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

이 프로젝트는 **사용자 본인**의 Google AI Studio 세션에 로그인된 실제 Chrome 창을
구동하고, 그 세션을 `http://127.0.0.1:8788/v1`에서 표준 OpenAI 호환 API로 다시
노출합니다. Google API 키도 결제도 필요하지 않습니다 —
이미 계정이 보유한 AI Studio 접근 권한을 사용합니다.

---

## 1. 요구 사항

| 항목 | 비고 |
|---|---|
| 운영 체제 | Windows, macOS 또는 Linux — **디스플레이가 있는 데스크톱** (Chrome이 실제로 보이는 창으로 실행됩니다) |
| Python | 3.10 이상 |
| 브라우저 | Google Chrome (Chromium 또는 Edge도 동작합니다) |
| Google 계정 | `aistudio.google.com`을 열고 프롬프트를 보낼 수 있는 계정이면 무엇이든 됩니다 |
| 메모리 | Chrome과 API가 실행되는 동안 약 2 GB의 여유 RAM |

## 2. 설치

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

필요한 의존성은 `flask`와 `websocket-client` 두 개뿐입니다.

## 3. 첫 실행

### 1단계 — 전용 브라우저 실행

```bash
python launch_chrome.py
```

Chrome 창이 **자체 프로필**로 `aistudio.google.com`에 열립니다
(일상적으로 사용하는 브라우저와는 분리됩니다). Google 계정으로 로그인하십시오 —
이 작업은 최초 한 번만 필요하며, 세션은 해당 프로필에 유지됩니다.

> **이 창을 열어 두십시오.** 이 창이 페이지에서 요청별 토큰을 발급하는
> 구성 요소입니다. 창을 닫으면 API가 중단됩니다.

### 2단계 — API 실행 (새 터미널)

```bash
python start.py
```

예상 출력: `Running on http://127.0.0.1:8788`.

## 4. 동작 확인

가장 빠른 것부터 가장 완전한 것까지, 세 가지 점검입니다:

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

`/health` 읽는 방법:

| 필드 | 의미 |
|---|---|
| `status` | `ok` = API와 브라우저 모두 도달 가능. `degraded` = API는 살아 있으나 브라우저/CDP가 아님 — 1단계를 재시작하십시오 |
| `hook` | `true` = 요청 패치 훅이 페이지에 설치됨 (정상) |
| `busy` / `running_model` / `running_for_s` | 현재 요청이 실행 중인지, 그리고 얼마나 오래 실행되었는지 |

## 5. 도구에서 API 사용하기

모든 OpenAI 호환 클라이언트가 동작합니다. 기본 URL을
`http://127.0.0.1:8788/v1`로 설정하고, API 키에는 비어 있지 않은 임의의 문자열을 사용하십시오.

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### 스트리밍

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### 함수 호출 (tools)

OpenAI 방식의 `tools`는 Gemini 스키마로 변환되며, 응답은 표준 `tool_calls`로
돌아옵니다:

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

### 멀티턴

OpenAI 호환 API에서와 마찬가지로, 매번 전체 대화 기록을 전송하십시오:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### 기타 클라이언트

OpenAI API를 지원하는 모든 도구를 동일한 기본 URL로 향하게 하십시오: OpenWebUI,
LobeChat, LangChain, LlamaIndex, OpenAI CLI, 자체 스크립트 등. API 키를 반드시
요구하는 클라이언트에는 임의의 자리 표시자 문자열을 사용하십시오.

## 6. 모델

`GET /v1/models`가 실시간 기준 정보원입니다. 그룹과 일반적인 용도:

| 그룹 | 모델 | 등급 | 일반적인 소요 시간 |
|---|---|---|---|
| 무료 채팅 | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30초 |
| Pro 채팅 | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30초 |
| 이미지 | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35초 |
| 음악 | `lyria-3.5`, `lyria-3-pro` | premium | 45–60초 |
| 음성 (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | 약 45초 |
| 추론 에이전트 | `deep-research-preview`, `deep-research-max` | agent | 2–5분 |
| 라이브 음성 | `gemini-3.1-flash-live` | premium | 약 80초 |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30초 |
| 업스트림 차단 | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | 오류를 반환합니다 — 이 등급에서는 지원되지 않습니다 |

무료 등급 모델은 유료 할당량을 소비하지 않습니다. Pro, 프리미엄, 에이전트 모델은
로그인한 계정의 할당량을 사용하며, Google이 거부하면 Google 자체의 메시지를 담은
정직한 HTTP 429를 받게 됩니다.

## 7. 미디어 결과

미디어를 생성하는 모델은 `choices[0].message.media`에 `data:` URI로 결과를
반환합니다 — 그대로 렌더링하거나 저장하십시오.

| 모델 계열 | `media[0]` 시작 문자열 | 비고 |
|---|---|---|
| 이미지 | `data:image/jpeg;base64,` | 같은 이미지가 `content`에도 마크다운으로 인라인 표시됩니다 |
| 음악 | `data:audio/mpeg;base64,` | MP3 |
| 음성 (TTS) | `data:audio/wav;base64,` | 24 kHz 모노 WAV, 길이는 `content`에 보고됩니다 |
| 라이브 음성 | `data:audio/wav;base64,` | 음성만 있는 응답은 `content`가 거의 비어 있습니다 |
| 심층 리서치 | `data:image/png;base64,` | 차트 산출물입니다. 보고서 자체는 `content`에, 리서치 계획은 `reasoning_content`에, 인용은 `message.sources`에 있습니다 |

### TTS 음성 선택

요청 본문에 선택적 `voice` 필드를 추가하십시오. 음성 이름은 AI Studio가 제공하는
70개 음성 중 아무거나 가능합니다 — 예를 들어 `Fola` (UI 기본값), `Puck`,
`Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon` 등입니다.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. 운영상 한계

- **한 번에 하나의 요청만.** 브라우저는 단일 요청을 처리합니다. 두 번째
  요청은 실행 중인 요청을 최대 90초까지 기다린 뒤(`AIS2A_LOCK_WAIT`)
  `503 farmer_busy`로 실패합니다.
- **클라이언트 타임아웃.** 채팅 약 20–30초, 이미지 약 30초, TTS 약 45초, Live 약 80초,
  심층 리서치 2–5분입니다. 에이전트에는 클라이언트 타임아웃을 넉넉하게
  (600초 이상) 설정하십시오.
- **로컬 일일 상한 없음.** 원장은 모델별 일일 요청 수만 집계하며
  아무것도 차단하지 않습니다. 실제 한도는 Google 자체의 한도이며
  HTTP 429로 나타납니다.
- **사용량을 사람 수준으로 유지하십시오.** AI Studio 서비스 약관을 준수하고,
  무료 등급을 악용하는 데 이 도구를 사용하지 마십시오.

## 9. 환경 변수

| 변수 | 기본값 | 의미 |
|---|---|---|
| `AIS2A_PORT` | `8788` | API 포트 |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP) 포트 |
| `AIS2A_CHROME_BIN` | 자동 감지 | Chrome/Chromium/Edge 바이너리 경로 |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | 전용 브라우저 프로필 (이 프로젝트 전용) |
| `AIS2A_LOCK_WAIT` | `90` | 대기 중인 요청이 브라우저를 기다리는 시간(초) |
| `AIS2A_AGENT_TIMEOUT` | `1500` | 에이전트 모델(심층 리서치)의 서버 측 타임아웃 |
| `AIS2A_TTS_TIMEOUT` | `120` | 음성 모델의 서버 측 타임아웃 |
| `AIS2A_LIVE_TIMEOUT` | `120` | 라이브 음성의 서버 측 타임아웃 |
| `AIS2A_VIDEO_TIMEOUT` | `600` | 비디오 작업의 서버 측 타임아웃 |

## 10. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| 포트 8788에서 `Connection refused` | API가 실행 중이 아님 | `python start.py` |
| `/health`가 `degraded`를 보고하거나 오류에 `farmer CDP port not reachable`이 언급됨 | Chrome 창이 닫혔거나 종료됨 | `python launch_chrome.py`를 다시 실행하고, 요청되면 로그인하십시오 |
| `503 farmer_busy` | 다른 요청이 아직 실행 중 | 기다리거나 `AIS2A_LOCK_WAIT`를 높이십시오 |
| API로부터의 `429` | 해당 모델에 대한 Google 자체의 할당량/한도 | 기다리거나 무료 등급 모델로 전환하십시오 |
| 본문이 비었거나 파싱할 수 없는 `502` | AI Studio의 내부 프로토콜이 변경됨 | 원본 본문을 보관하고 `tools/capture_run.py`로 다시 캡처한 뒤 `src/lib/extract*.py`를 갱신하십시오 |
| `content`는 비었는데 `media`는 존재 | 이미지, 음악, 음성 모델에서는 정상 | `choices[0].message.media`를 읽으십시오 |
| Chrome이 "No API key selected"를 표시 | UI에서 선택된 모델이 유료 전용 | 드라이버가 자동으로 무료 호스트로 다시 이동합니다. 계속되면 AI Studio 모델 선택기에서 무료 모델을 한 번 선택하십시오 |
| `/v1/models`에 모델이 없음 | 레지스트리에 없음 | `src/facade/registry.py`에 추가하십시오 |
| `antigravity` 또는 `veo-*`가 오류를 냄 | Google 등급에서 업스트림 차단됨 | 이 프로젝트로는 사용할 수 없습니다 — `docs/protocol-notebook.md` §15를 참조하십시오 |
| 이전 질문의 답변처럼 보이는 응답 | 브라우저가 잠긴 동안 요청이 삼켜짐 | `/health`에서 `busy`를 확인한 뒤 재시도하십시오 |

## 11. 유지 관리

- `src/` 아래에서 무엇이든 변경한 뒤에는 `start.py`를 재시작하십시오.
- AI Studio 세션이 만료되면(해당 창에 로그인 페이지가 나타납니다)
  `python launch_chrome.py`를 다시 실행하십시오.
- 응답이 갑자기 `403`으로 실패하기 시작하면, 세션 또는 요청별 토큰이
  업스트림에서 변경된 것입니다: Chrome 창에서 다시 로그인한 뒤
  `/health`를 재확인하십시오.

## 12. 더 깊이 살펴보기

- `docs/protocol-notebook.md` — 전체 리버스 엔지니어링 노트: 페이로드
  형태, 프로토콜 계열, 모델별 참고 사항, 모델 감사(§15).
- `tools/capture_run.py` — 변경된 프로토콜을 다시 리버스 엔지니어링할 때 쓰는 실측
  캡처 도구(네트워크 본문, DOM, WebSocket 프레임)입니다.
