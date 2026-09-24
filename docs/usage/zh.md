# 使用指南 — Google AI Studio → OpenAI 兼容 API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

本项目驱动一个真实的 Chrome 窗口，该窗口已登录 **您自己的** Google AI Studio 会话，并将该会话重新暴露为 `http://127.0.0.1:8788/v1` 上标准的 OpenAI 兼容 API。无需 Google API 密钥，也不产生任何费用——它使用的是您账户已具备的 AI Studio 访问权限。

---

## 1. 环境要求

| 项目 | 说明 |
|---|---|
| 操作系统 | Windows、macOS 或 Linux —— **带显示器的桌面环境**（Chrome 以真实可见的窗口运行） |
| Python | 3.10 或更高版本 |
| 浏览器 | Google Chrome（Chromium 或 Edge 亦可） |
| Google 账户 | 任何能够打开 `aistudio.google.com` 并发送提示词的账户 |
| 内存 | Chrome 与 API 同时运行时约需 2 GB 空闲内存 |

## 2. 安装

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

仅需两个依赖：`flask` 与 `websocket-client`。

## 3. 首次运行

### 第 1 步 —— 启动专用浏览器

```bash
python launch_chrome.py
```

Chrome 窗口会以自己的**独立配置文件**打开 `aistudio.google.com`（与您日常使用的浏览器相互隔离）。请使用您的 Google 账户登录——仅在首次运行时需要；会话会保存在该配置文件中。

> **请保持此窗口开启。** 正是它从页面中为每个请求生成令牌。关闭它，API 随即停止。

### 第 2 步 —— 启动 API（新开一个终端）

```bash
python start.py
```

预期输出行：`Running on http://127.0.0.1:8788`。

## 4. 验证是否可用

三项检查，由简至全：

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

如何解读 `/health`：

| 字段 | 含义 |
|---|---|
| `status` | `ok` = API 与浏览器均可访问。`degraded` = API 正常，但浏览器/CDP 不可用 —— 请重启第 1 步 |
| `hook` | `true` = 请求改写钩子已注入页面（正常状态） |
| `busy` / `running_model` / `running_for_s` | 当前是否有请求正在运行，以及已运行多久 |

## 5. 在您的工具中使用该 API

任何 OpenAI 兼容客户端均可使用。将基础 URL 设为 `http://127.0.0.1:8788/v1`，API 密钥填写任意非空字符串。

### Python（OpenAI SDK）

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### 流式输出

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### 函数调用（tools）

OpenAI 风格的 `tools` 会被转换为 Gemini schema，返回的答案则是标准的 `tool_calls`：

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

### 多轮对话

每次都发送完整对话记录，与任何 OpenAI 兼容 API 完全一致：

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### 其他客户端

将任何支持 OpenAI API 的工具指向同一基础 URL：OpenWebUI、LobeChat、LangChain、LlamaIndex、OpenAI CLI，或您自己的脚本。对于强制要求 API 密钥的客户端，填入任意占位字符串即可。

## 6. 模型

`GET /v1/models` 是实时的权威来源。分组与典型用途：

| 分组 | 模型 | 层级 | 典型耗时 |
|---|---|---|---|
| 免费对话 | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 秒 |
| Pro 对话 | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 秒 |
| 图像 | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 秒 |
| 音乐 | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 秒 |
| 语音（TTS） | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | 约 45 秒 |
| 推理智能体 | `deep-research-preview`, `deep-research-max` | agent | 2–5 分钟 |
| 实时语音 | `gemini-3.1-flash-live` | premium | 约 80 秒 |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 秒 |
| 上游已屏蔽 | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | 返回错误 —— 该层级不支持 |

免费层级模型不消耗付费配额。Pro、高级与智能体模型会使用已登录账户的配额；当 Google 拒绝时，您会收到一个诚实的 HTTP 429，并携带 Google 自身的提示信息。

## 7. 媒体结果

会产出媒体内容的模型，将其以 `data:` URI 的形式返回在 `choices[0].message.media` 中——可直接渲染或保存。

| 模型家族 | `media[0]` 前缀 | 说明 |
|---|---|---|
| 图像 | `data:image/jpeg;base64,` | 同一张图也会以 markdown 形式内联出现在 `content` 中 |
| 音乐 | `data:audio/mpeg;base64,` | MP3 |
| 语音（TTS） | `data:audio/wav;base64,` | 24 kHz 单声道 WAV；时长在 `content` 中给出 |
| 实时语音 | `data:audio/wav;base64,` | 纯语音回复的 `content` 基本为空 |
| 深度研究 | `data:image/png;base64,` | 图表产物；报告正文在 `content`，研究计划在 `reasoning_content`，引用来源在 `message.sources` |

### 选择 TTS 音色

在请求体中添加可选的 `voice` 字段。音色名称可取自 AI Studio 提供的 70 种音色——例如 `Fola`（UI 默认）、`Puck`、`Lumi`、`Kore`、`Zephyr`、`Aoede`、`Charon`。

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. 运行限制

- **同一时间只处理一个请求。** 浏览器一次只处理一个请求；第二个请求最多等待正在运行的请求 90 秒（`AIS2A_LOCK_WAIT`），随后以 `503 farmer_busy` 失败。
- **客户端超时。** 对话约 20–30 秒，图像约 30 秒，TTS 约 45 秒，实时语音约 80 秒，深度研究 2–5 分钟。用于智能体时，请将客户端超时设置得足够宽裕（600 秒或更长）。
- **本地无每日上限。** 账本仅按模型统计每日请求数，不做任何拦截。Google 自身的限制才是真正的限制，并以 HTTP 429 的形式返回。
- **请保持合理的使用量。** 遵守 AI Studio 服务条款；请勿借此滥用免费层级。

## 9. 环境变量

| 变量 | 默认值 | 含义 |
|---|---|---|
| `AIS2A_PORT` | `8788` | API 端口 |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools (CDP) 端口 |
| `AIS2A_CHROME_BIN` | 自动检测 | Chrome/Chromium/Edge 可执行文件的路径 |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | 专用浏览器配置文件（本项目私有） |
| `AIS2A_LOCK_WAIT` | `90` | 排队请求等待浏览器的秒数 |
| `AIS2A_AGENT_TIMEOUT` | `1500` | 智能体模型（deep-research）的服务端超时 |
| `AIS2A_TTS_TIMEOUT` | `120` | 语音模型的服务端超时 |
| `AIS2A_LIVE_TIMEOUT` | `120` | 实时语音的服务端超时 |
| `AIS2A_VIDEO_TIMEOUT` | `600` | 视频任务的服务端超时 |

## 10. 故障排查

| 现象 | 原因 | 处理方式 |
|---|---|---|
| 端口 8788 上出现 `Connection refused` | API 未运行 | 运行 `python start.py` |
| `/health` 显示 `degraded`，或错误信息中出现 `farmer CDP port not reachable` | Chrome 窗口已被关闭或崩溃 | 再次运行 `python launch_chrome.py`，如被要求则重新登录 |
| `503 farmer_busy` | 另一个请求仍在运行 | 等待其完成，或调高 `AIS2A_LOCK_WAIT` |
| API 返回 `429` | Google 对该模型自身的配额/限制 | 稍后重试，或改用免费层级模型 |
| `502`，响应体为空或无法解析 | AI Studio 更改了其内部协议 | 保留原始响应体，用 `tools/capture_run.py` 重新抓取，并更新 `src/lib/extract*.py` |
| `content` 为空，但存在 `media` | 对图像、音乐与语音模型而言属正常现象 | 读取 `choices[0].message.media` |
| Chrome 显示 "No API key selected" | UI 中选定的模型属于付费锁定 | 驱动会自动重新导航至免费主机；若问题持续，请在 AI Studio 模型选择器中手动选择一个免费模型 |
| `/v1/models` 中缺少某个模型 | 它不在注册表中 | 将其加入 `src/facade/registry.py` |
| `antigravity` 或 `veo-*` 报错 | 在 Google 的层级被上游屏蔽 | 无法通过本项目使用——参见 `docs/protocol-notebook.md` §15 |
| 返回的答案看起来像是上一个问题的答案 | 请求在浏览器锁定期间被吞掉 | 检查 `/health` 中的 `busy`，然后重试 |

## 11. 日常维护

- 修改 `src/` 下的任何内容后，请重启 `start.py`。
- 若 AI Studio 会话过期（该窗口出现登录页），请重新运行 `python launch_chrome.py`。
- 若响应突然集中出现 `403` 失败，说明会话或每请求令牌在上游已发生变更：请在 Chrome 窗口中重新登录，然后再次检查 `/health`。

## 12. 深入阅读

- `docs/protocol-notebook.md` —— 完整的逆向工程笔记：载荷形态、协议族、各模型说明，以及模型审计（§15）。
- `tools/capture_run.py` —— 真值抓取工具（网络响应体、DOM、WebSocket 帧），用于对变更后的协议重新进行逆向。
