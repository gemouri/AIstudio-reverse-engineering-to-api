# 使用ガイド — Google AI Studio → OpenAI 互換 API

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

本プロジェクトは、**お客様ご自身**の Google AI Studio セッションにサインイン済みの実際の
Chrome ウィンドウを操作し、そのセッションを `http://127.0.0.1:8788/v1` 上の標準的な
OpenAI 互換 API として再公開します。Google の API キーも課金も不要です。
アカウントがすでにお持ちの AI Studio へのアクセスをそのまま利用します。

---

## 1. 動作要件

| 項目 | 備考 |
|---|---|
| オペレーティングシステム | Windows、macOS または Linux — **ディスプレイのあるデスクトップ環境**(Chrome は実際に表示されるウィンドウとして動作します) |
| Python | 3.10 以上 |
| ブラウザー | Google Chrome(Chromium や Edge でも動作します) |
| Google アカウント | `aistudio.google.com` を開いてプロンプトを送信できる任意のアカウント |
| メモリ | Chrome と API の実行中に約 2 GB の空き RAM |

## 2. インストール

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

必要な依存関係は `flask` と `websocket-client` の 2 つだけです。

## 3. 初回起動

### ステップ 1 — 専用ブラウザーを起動する

```bash
python launch_chrome.py
```

Chrome ウィンドウが **独自のプロファイル** で `aistudio.google.com` を開きます
(日常的に使用しているブラウザーとは別のプロファイルです)。Google アカウントで
サインインしてください。これが必要なのは初回のみで、セッションはそのプロファイルに
保持されます。

> **このウィンドウは開いたままにしてください。** このウィンドウが、ページから
> リクエストごとのトークンを発行するコンポーネントです。閉じると API は停止します。

### ステップ 2 — API を起動する(新しいターミナル)

```bash
python start.py
```

次の行が表示されれば正常です: `Running on http://127.0.0.1:8788`。

## 4. 動作確認

確認は 3 つ、簡単なものから完全なものへと順に示します:

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

`/health` の読み方:

| フィールド | 意味 |
|---|---|
| `status` | `ok` = API とブラウザーの両方に到達可能です。`degraded` = API は起動していますがブラウザー/CDP に到達できません — ステップ 1 を再起動してください |
| `hook` | `true` = リクエスト改変フックがページにインストールされています(正常) |
| `busy` / `running_model` / `running_for_s` | 現在リクエストが実行中であるかどうか、およびその実行時間 |

## 5. 各種ツールから API を使う

OpenAI 互換のクライアントであればどれでも利用できます。ベース URL を
`http://127.0.0.1:8788/v1` に、API キーには任意の空でない文字列を設定してください。

### Python(OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### ストリーミング

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### 関数呼び出し(ツール)

OpenAI 形式の `tools` は Gemini のスキーマに変換され、応答は標準の `tool_calls` として
返されます:

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

### マルチターン

OpenAI 互換 API と同様に、毎回すべての会話履歴を送信してください:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### その他のクライアント

OpenAI API に対応するツールであれば、同じベース URL を指定して利用できます:
OpenWebUI、LobeChat、LangChain、LlamaIndex、OpenAI CLI、独自のスクリプトなどです。
API キーを必須とするクライアントでは、任意のプレースホルダー文字列を使用してください。

## 6. モデル

`GET /v1/models` が最新の正しい情報源です。グループと一般的な用途は次のとおりです:

| グループ | モデル | ティア | 標準的な所要時間 |
|---|---|---|---|
| 無料チャット | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20〜30 秒 |
| Pro チャット | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20〜30 秒 |
| 画像 | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25〜35 秒 |
| 音楽 | `lyria-3.5`, `lyria-3-pro` | premium | 45〜60 秒 |
| 音声(TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | 約 45 秒 |
| 推論エージェント | `deep-research-preview`, `deep-research-max` | agent | 2〜5 分 |
| ライブ音声 | `gemini-3.1-flash-live` | premium | 約 80 秒 |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20〜30 秒 |
| 上流でブロック | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | エラーを返します — このティアでは未対応です |

無料ティアのモデルは有料クォータを消費しません。Pro、premium、agent の各モデルは
サインイン中のアカウントのクォータを使用します。Google が拒否した場合は、Google 自身の
メッセージを含む HTTP 429 がそのまま返されます。

## 7. メディア結果

メディアを生成するモデルは、結果を `choices[0].message.media` に `data:` URI として
返します — そのままレンダリングするか保存してください。

| モデルファミリー | `media[0]` の先頭 | 備考 |
|---|---|---|
| 画像 | `data:image/jpeg;base64,` | 同じ画像は `content` 内にも markdown としてインライン表示されます |
| 音楽 | `data:audio/mpeg;base64,` | MP3 |
| 音声(TTS) | `data:audio/wav;base64,` | 24 kHz モノラル WAV。長さは `content` に報告されます |
| ライブ音声 | `data:audio/wav;base64,` | 音声のみの応答では `content` はほぼ空になります |
| ディープリサーチ | `data:image/png;base64,` | グラフの成果物です。レポート本体は `content`、リサーチプランは `reasoning_content`、引用は `message.sources` にあります |

### TTS の音声を選ぶ

リクエストボディに任意の `voice` フィールドを追加できます。音声名には AI Studio が提供する
70 種類の音声のいずれかを指定します — たとえば `Fola`(UI の既定値)、`Puck`、
`Lumi`、`Kore`、`Zephyr`、`Aoede`、`Charon` などです。

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. 運用上の制限

- **同時に処理できるのは 1 リクエストのみ。** ブラウザーは 1 件ずつしか処理しません。
  2 件目のリクエストは実行中の処理を最大 90 秒間(`AIS2A_LOCK_WAIT`)待機し、
  その後 `503 farmer_busy` で失敗します。
- **クライアントのタイムアウト。** チャットは約 20〜30 秒、画像は約 30 秒、TTS は約 45 秒、
  ライブは約 80 秒、ディープリサーチは 2〜5 分です。エージェントを利用する場合は、
  クライアント側のタイムアウトを十分に長く(600 秒以上)設定してください。
- **ローカルの 1 日あたり上限はありません。** 台帳はモデルごと・日ごとのリクエスト数を
  記録するだけで、何もブロックしません。実際の上限は Google 側の制限であり、
  HTTP 429 として現れます。
- **利用量は常識的な範囲に。** AI Studio の利用規約を遵守してください。無料ティアを
  悪用する目的で本プロジェクトを使用しないでください。

## 9. 環境変数

| 変数 | 既定値 | 意味 |
|---|---|---|
| `AIS2A_PORT` | `8788` | API のポート |
| `AIS2A_CDP_PORT` | `9333` | Chrome DevTools(CDP)のポート |
| `AIS2A_CHROME_BIN` | 自動検出 | Chrome / Chromium / Edge のバイナリへのパス |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | 専用ブラウザープロファイル(本プロジェクト専用) |
| `AIS2A_LOCK_WAIT` | `90` | 待機中のリクエストがブラウザーを待つ秒数 |
| `AIS2A_AGENT_TIMEOUT` | `1500` | エージェントモデル(deep-research)のサーバー側タイムアウト |
| `AIS2A_TTS_TIMEOUT` | `120` | 音声モデルのサーバー側タイムアウト |
| `AIS2A_LIVE_TIMEOUT` | `120` | ライブ音声のサーバー側タイムアウト |
| `AIS2A_VIDEO_TIMEOUT` | `600` | 動画ジョブのサーバー側タイムアウト |

## 10. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| ポート 8788 で `Connection refused` | API が起動していない | `python start.py` |
| `/health` が `degraded` を示す、またはエラーに `farmer CDP port not reachable` が含まれる | Chrome ウィンドウが閉じられたかクラッシュした | 再度 `python launch_chrome.py` を実行し、求められたらサインインする |
| `503 farmer_busy` | 別のリクエストがまだ実行中 | 完了を待つか、`AIS2A_LOCK_WAIT` を大きくする |
| API から `429` | そのモデルに対する Google 側のクォータ/制限 | 待つか、無料ティアのモデルに切り替える |
| 空または解析不能なボディを伴う `502` | AI Studio が内部プロトコルを変更した | 生のボディを保存し、`tools/capture_run.py` で再取得して `src/lib/extract*.py` を更新する |
| `content` が空だが `media` が存在する | 画像・音楽・音声モデルでは正常な動作 | `choices[0].message.media` を参照する |
| Chrome に "No API key selected" と表示される | UI で選択中のモデルが有料ロックされている | ドライバーは自動的に無料ホストへ再遷移します。改善しない場合は AI Studio のモデルピッカーで無料モデルを一度選択してください |
| `/v1/models` にモデルが表示されない | レジストリに登録されていない | `src/facade/registry.py` に追加する |
| `antigravity` や `veo-*` がエラーになる | Google のティアで上流からブロックされている | 本プロジェクト経由では使用できません — `docs/protocol-notebook.md` §15 を参照してください |
| 応答が前の質問への回答のように見える | ブラウザーがロックされている間にリクエストが飲み込まれた | `/health` で `busy` を確認してから再試行する |

## 11. メンテナンス

- `src/` 以下のファイルを変更した後は `start.py` を再起動してください。
- AI Studio のセッションが切れた場合(そのウィンドウにサインインページが表示されます)は、
  `python launch_chrome.py` を再度実行してください。
- 応答が突然まとめて `403` で失敗し始めた場合は、セッションまたはリクエストごとの
  トークンが上流で変更されています。Chrome ウィンドウで再度サインインし、
  `/health` を再確認してください。

## 12. より深く知るには

- `docs/protocol-notebook.md` — リバースエンジニアリングの全記録です。ペイロードの
  形式、プロトコルファミリー、モデルごとのメモ、モデル監査(§15)を収録しています。
- `tools/capture_run.py` — 変更されたプロトコルを再解析するためのグラウンドトゥルース
  取得ツールです(ネットワークボディ、DOM、WebSocket フレーム)。
