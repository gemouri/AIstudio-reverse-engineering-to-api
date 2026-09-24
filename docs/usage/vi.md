# Hướng dẫn sử dụng — Google AI Studio → API tương thích OpenAI

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Dự án này điều khiển một cửa sổ Chrome thật đang đăng nhập vào phiên Google AI
Studio **của chính bạn**, rồi mở lại phiên đó thành một API chuẩn tương thích
OpenAI tại `http://127.0.0.1:8788/v1`. Không cần API key của Google, không phát
sinh chi phí — nó dùng đúng quyền truy cập AI Studio mà tài khoản bạn đã có.

---

## 1. Yêu cầu

| Hạng mục | Ghi chú |
|---|---|
| Hệ điều hành | Windows, macOS hoặc Linux — **máy tính để bàn có màn hình** (Chrome phải chạy dưới dạng cửa sổ thật, nhìn thấy được) |
| Python | 3.10 trở lên |
| Trình duyệt | Google Chrome (Chromium hoặc Edge cũng chạy được) |
| Tài khoản Google | Bất kỳ tài khoản nào mở được `aistudio.google.com` và gửi được một câu lệnh |
| Bộ nhớ | ~2 GB RAM trống trong lúc Chrome và API cùng chạy |

## 2. Cài đặt

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Chỉ có hai thư viện phụ thuộc: `flask` và `websocket-client`.

## 3. Chạy lần đầu

### Bước 1 — mở trình duyệt dành riêng cho dự án

```bash
python launch_chrome.py
```

Một cửa sổ Chrome mở ra tại `aistudio.google.com` với **profile riêng** (tách
biệt hoàn toàn với trình duyệt bạn dùng hằng ngày). Hãy đăng nhập tài khoản
Google — chỉ cần làm một lần; phiên đăng nhập được giữ lại trong profile đó.

> **Giữ cửa sổ này luôn mở.** Đây là thành phần tạo token cho từng request từ
> chính trang AI Studio. Đóng nó là API dừng hoạt động.

### Bước 2 — khởi động API (mở terminal mới)

```bash
python start.py
```

Dòng báo mong đợi: `Running on http://127.0.0.1:8788`.

## 4. Kiểm tra đã chạy được chưa

Ba bước kiểm tra, từ nhanh nhất tới đầy đủ nhất:

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

Cách đọc `/health`:

| Trường | Ý nghĩa |
|---|---|
| `status` | `ok` = API và trình duyệt đều kết nối được. `degraded` = API còn sống nhưng trình duyệt/CDP không phản hồi — chạy lại bước 1 |
| `hook` | `true` = hook vá request đã được cài vào trang (bình thường) |
| `busy` / `running_model` / `running_for_s` | hiện có request đang chạy, và đã chạy bao lâu |

## 5. Gọi API từ công cụ của bạn

Mọi client tương thích OpenAI đều dùng được. Đặt base URL thành
`http://127.0.0.1:8788/v1` và API key là một chuỗi bất kỳ không rỗng.

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### Truyền dần (streaming)

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### Gọi hàm (tools)

`tools` theo chuẩn OpenAI được chuyển thành schema Gemini, và kết quả trả về
dưới dạng `tool_calls` chuẩn:

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

### Hội thoại nhiều lượt

Gửi lại toàn bộ lịch sử mỗi lần, đúng như mọi API tương thích OpenAI:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Các client khác

Trỏ bất kỳ công cụ nào nói được "OpenAI API" vào cùng base URL đó: OpenWebUI,
LobeChat, LangChain, LlamaIndex, OpenAI CLI, hay script của chính bạn. Với client
bắt buộc phải có API key, dùng một chuỗi giữ chỗ bất kỳ.

## 6. Model

`GET /v1/models` là nguồn dữ liệu sống, luôn đúng nhất. Nhóm và công dụng:

| Nhóm | Model | Tier | Thời gian thường |
|---|---|---|---|
| Chat miễn phí | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 giây |
| Chat Pro | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 giây |
| Hình ảnh | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 giây |
| Nhạc | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 giây |
| Giọng nói (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 giây |
| Agent nghiên cứu | `deep-research-preview`, `deep-research-max` | agent | 2–5 phút |
| Giọng nói trực tiếp | `gemini-3.1-flash-live` | premium | ~80 giây |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 giây |
| Bị chặn từ phía Google | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | trả về lỗi — không dùng được ở tier này |

Model miễn phí không tiêu tốn quota trả phí. Model pro, premium và agent dùng
quota của tài khoản đang đăng nhập; khi Google từ chối, bạn nhận HTTP 429 kèm
đúng thông báo gốc của Google.

## 7. Kết quả dạng media

Các model sinh media trả kết quả trong `choices[0].message.media` dưới dạng URI
`data:` — hiển thị hoặc lưu trực tiếp.

| Nhóm model | `media[0]` bắt đầu bằng | Ghi chú |
|---|---|---|
| Hình ảnh | `data:image/jpeg;base64,` | ảnh cũng xuất hiện trong `content` dưới dạng markdown |
| Nhạc | `data:audio/mpeg;base64,` | MP3 |
| Giọng nói (TTS) | `data:audio/wav;base64,` | WAV 24 kHz mono; thời lượng báo trong `content` |
| Giọng nói trực tiếp | `data:audio/wav;base64,` | câu trả lời chỉ có tiếng thì `content` gần như rỗng |
| Nghiên cứu sâu | `data:image/png;base64,` | biểu đồ sinh kèm; báo cáo nằm trong `content`, dàn ý nghiên cứu trong `reasoning_content`, nguồn trích dẫn trong `message.sources` |

### Chọn giọng đọc cho TTS

Thêm trường `voice` tuỳ chọn vào body request. Tên giọng là bất kỳ giọng nào
trong 70 giọng mà AI Studio cung cấp — ví dụ `Fola` (mặc định của giao diện),
`Puck`, `Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Giới hạn vận hành

- **Mỗi lần một request.** Trình duyệt chỉ xử lý một request; request thứ hai
  sẽ chờ request đang chạy tối đa 90 giây (`AIS2A_LOCK_WAIT`), quá hạn thì trả
  lỗi `503 farmer_busy`.
- **Timeout phía client.** Chat ~20–30 giây, ảnh ~30 giây, TTS ~45 giây, Live
  ~80 giây, nghiên cứu sâu 2–5 phút. Hãy đặt timeout client rộng rãi cho nhóm
  agent (600 giây trở lên).
- **Không có trần cứng theo ngày.** Sổ ghi chỉ đếm số request mỗi model mỗi
  ngày, không chặn gì cả. Giới hạn thật là giới hạn của Google, và nó hiện ra
  dưới dạng HTTP 429.
- **Giữ tần suất ở mức như người dùng thật.** Tôn trọng điều khoản dịch vụ của
  AI Studio; đừng dùng công cụ này để lạm dụng bậc miễn phí.

## 9. Biến môi trường

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AIS2A_PORT` | `8788` | Cổng của API |
| `AIS2A_CDP_PORT` | `9333` | Cổng Chrome DevTools (CDP) |
| `AIS2A_CHROME_BIN` | tự dò | Đường dẫn tới Chrome/Chromium/Edge |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Profile trình duyệt riêng (chỉ dự án này dùng) |
| `AIS2A_LOCK_WAIT` | `90` | Số giây một request xếp hàng chờ trình duyệt |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Timeout phía server cho nhóm agent (nghiên cứu sâu) |
| `AIS2A_TTS_TIMEOUT` | `120` | Timeout phía server cho model giọng nói |
| `AIS2A_LIVE_TIMEOUT` | `120` | Timeout phía server cho Live voice |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Timeout phía server cho tác vụ video |

## 10. Xử lý sự cố

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Connection refused` ở cổng 8788 | API chưa chạy | `python start.py` |
| `/health` báo `degraded`, hoặc lỗi nhắc `farmer CDP port not reachable` | cửa sổ Chrome đã bị đóng hoặc treo | chạy lại `python launch_chrome.py` và đăng nhập nếu được hỏi |
| `503 farmer_busy` | vẫn còn một request đang chạy | chờ nó xong, hoặc tăng `AIS2A_LOCK_WAIT` |
| `429` từ API | quota/giới hạn của chính Google cho model đó | chờ, hoặc chuyển sang model miễn phí |
| `502` với body rỗng hoặc không phân tích được | AI Studio đã đổi giao thức nội bộ | giữ lại body thô, thu thập lại bằng `tools/capture_run.py`, cập nhật `src/lib/extract*.py` |
| `content` rỗng nhưng có `media` | bình thường với model ảnh, nhạc và giọng nói | đọc `choices[0].message.media` |
| Chrome hiện "No API key selected" | model đang chọn trên giao diện bị khoá trả phí | driver tự điều hướng lại về host miễn phí; nếu vẫn còn, chọn một model miễn phí trong bảng chọn model của AI Studio một lần |
| Model không có trong `/v1/models` | chưa được đăng ký | thêm vào `src/facade/registry.py` |
| `antigravity` hoặc `veo-*` báo lỗi | bị chặn từ phía Google ở tier này | không dùng được qua dự án này — xem `docs/protocol-notebook.md` §15 |
| Câu trả lời giống hệt câu hỏi trước đó | request đã bị nuốt trong lúc trình duyệt bị khoá | kiểm tra `busy` ở `/health` rồi thử lại |

## 11. Bảo trì

- Khởi động lại `start.py` sau khi sửa bất cứ thứ gì trong `src/`.
- Chạy lại `python launch_chrome.py` nếu phiên AI Studio hết hạn (cửa sổ đó
  hiện trang đăng nhập).
- Nếu mọi phản hồi bắt đầu lỗi `403` cùng lúc: phiên đăng nhập hoặc token theo
  request đã thay đổi từ phía Google — đăng nhập lại trong cửa sổ Chrome, rồi
  kiểm tra lại `/health`.

## 12. Đi sâu hơn

- `docs/protocol-notebook.md` — sổ tay reverse-engineering đầy đủ: hình dạng
  payload, các họ giao thức, ghi chú từng model, và bản kiểm toán model (§15).
- `tools/capture_run.py` — công cụ thu thập bằng chứng gốc (network body, DOM,
  khung WebSocket) dùng để reverse lại khi giao thức thay đổi.
