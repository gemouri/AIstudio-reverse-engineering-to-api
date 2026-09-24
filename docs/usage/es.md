# Guía de uso — Google AI Studio → API compatible con OpenAI

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Este proyecto controla una ventana real de Chrome que tiene iniciada sesión en
**su propia** cuenta de Google AI Studio, y vuelve a exponer esa sesión como una
API estándar compatible con OpenAI en `http://127.0.0.1:8788/v1`. No hay clave
de API de Google ni facturación alguna: utiliza el acceso a AI Studio que su
cuenta ya posee.

---

## 1. Requisitos

| Elemento | Notas |
|---|---|
| Sistema operativo | Windows, macOS o Linux — **escritorio con pantalla** (Chrome se ejecuta como una ventana real y visible) |
| Python | 3.10 o superior |
| Navegador | Google Chrome (Chromium o Edge también funcionan) |
| Cuenta de Google | Cualquier cuenta capaz de abrir `aistudio.google.com` y enviar un prompt |
| Memoria | ~2 GB de RAM libre mientras Chrome y la API están en ejecución |

## 2. Instalación

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Solo se necesitan dos dependencias: `flask` y `websocket-client`.

## 3. Primera ejecución

### Paso 1 — iniciar el navegador dedicado

```bash
python launch_chrome.py
```

Se abre una ventana de Chrome en `aistudio.google.com` usando su **propio
perfil** (separado del navegador que usted utiliza a diario). Inicie sesión con
su cuenta de Google: esto solo es necesario la primera vez; la sesión se
conserva en ese perfil.

> **Mantenga esta ventana abierta.** Es el componente que genera un token por
> petición a partir de la página. Si la cierra, la API se detiene.

### Paso 2 — iniciar la API (nueva terminal)

```bash
python start.py
```

Línea esperada: `Running on http://127.0.0.1:8788`.

## 4. Verificar que funciona

Tres comprobaciones, de la más rápida a la más completa:

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

Cómo interpretar `/health`:

| Campo | Significado |
|---|---|
| `status` | `ok` = tanto la API como el navegador son accesibles. `degraded` = la API está activa pero el navegador/CDP no — reinicie el paso 1 |
| `hook` | `true` = el hook de parcheo de peticiones está instalado en la página (normal) |
| `busy` / `running_model` / `running_for_s` | hay una petición en ejecución y, en su caso, desde hace cuánto tiempo |

## 5. Uso de la API desde sus herramientas

Cualquier cliente compatible con OpenAI funciona. Configure la URL base como
`http://127.0.0.1:8788/v1` y use cualquier cadena no vacía como clave de API.

### Python (SDK de OpenAI)

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

### Llamada a funciones (tools)

Los `tools` al estilo de OpenAI se traducen al esquema de Gemini y las respuestas
vuelven como `tool_calls` estándar:

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

### Multiturno

Envíe la transcripción completa cada vez, exactamente igual que con cualquier API
compatible con OpenAI:

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Otros clientes

Apunte cualquier herramienta que hable la API de OpenAI a la misma URL base:
OpenWebUI, LobeChat, LangChain, LlamaIndex, la CLI de OpenAI, sus propios
scripts. Para los clientes que exigen una clave de API, use cualquier cadena de
relleno.

## 6. Modelos

`GET /v1/models` es la fuente de verdad en vivo. Grupos y uso típico:

| Grupo | Modelos | Nivel | Tiempo típico |
|---|---|---|---|
| Chat gratuito | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Chat Pro | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Imágenes | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Música | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Voz (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Agentes de razonamiento | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Voz en vivo | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Bloqueados en origen | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | devuelve un error — no compatible en este nivel |

Los modelos de nivel gratuito no consumen cuota de pago. Los modelos pro, premium
y de agente utilizan la cuota de la cuenta con la que se ha iniciado sesión;
cuando Google la rechaza, usted recibe un honesto HTTP 429 con el propio mensaje
de Google.

## 7. Resultados multimedia

Los modelos que producen contenido multimedia lo devuelven en
`choices[0].message.media` como URI `data:` — represéntelos o guárdelos
directamente.

| Familia de modelo | `media[0]` comienza por | Notas |
|---|---|---|
| Imágenes | `data:image/jpeg;base64,` | la misma imagen también aparece insertada en `content` como markdown |
| Música | `data:audio/mpeg;base64,` | MP3 |
| Voz (TTS) | `data:audio/wav;base64,` | WAV mono a 24 kHz; la duración se indica en `content` |
| Voz en vivo | `data:audio/wav;base64,` | las respuestas solo de voz tienen un `content` prácticamente vacío |
| Deep research | `data:image/png;base64,` | artefactos gráficos; el informe en sí está en `content`, el plan de investigación en `reasoning_content` y las citas en `message.sources` |

### Elegir una voz de TTS

Añada un campo opcional `voice` al cuerpo de la petición. El nombre de la voz es
cualquiera de las 70 voces que ofrece AI Studio — por ejemplo `Fola` (la
predeterminada en la interfaz), `Puck`, `Lumi`, `Kore`, `Zephyr`, `Aoede`,
`Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Límites operativos

- **Una petición a la vez.** El navegador atiende una sola petición; una segunda
  petición espera a la que está en curso hasta 90 segundos (`AIS2A_LOCK_WAIT`) y
  después falla con `503 farmer_busy`.
- **Tiempos de espera del cliente.** Chat ~20–30 s, imágenes ~30 s, TTS ~45 s,
  Live ~80 s, deep-research 2–5 minutos. Configure el tiempo de espera de su
  cliente con holgura para los agentes (600 s o más).
- **Sin tope diario local.** El registro solo cuenta las peticiones por modelo y
  día; no bloquea nada. El límite real es el de Google y se manifiesta como
  HTTP 429.
- **Mantenga un volumen humano.** Respete las condiciones de servicio de AI
  Studio; no utilice esto para abusar de los niveles gratuitos.

## 9. Variables de entorno

| Variable | Valor predeterminado | Significado |
|---|---|---|
| `AIS2A_PORT` | `8788` | Puerto de la API |
| `AIS2A_CDP_PORT` | `9333` | Puerto de Chrome DevTools (CDP) |
| `AIS2A_CHROME_BIN` | detectado automáticamente | Ruta al binario de Chrome/Chromium/Edge |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Perfil de navegador dedicado (privado para este proyecto) |
| `AIS2A_LOCK_WAIT` | `90` | Segundos que una petición en cola espera al navegador |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Tiempo de espera en el servidor para los modelos de agente (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Tiempo de espera en el servidor para los modelos de voz |
| `AIS2A_LIVE_TIMEOUT` | `120` | Tiempo de espera en el servidor para la voz en vivo |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Tiempo de espera en el servidor para los trabajos de vídeo |

## 10. Resolución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `Connection refused` en el puerto 8788 | la API no está en ejecución | `python start.py` |
| `/health` indica `degraded`, o los errores mencionan `farmer CDP port not reachable` | la ventana de Chrome se cerró o se bloqueó | ejecute de nuevo `python launch_chrome.py` e inicie sesión si se le solicita |
| `503 farmer_busy` | hay otra petición aún en ejecución | espere a que termine o aumente `AIS2A_LOCK_WAIT` |
| `429` de la API | la cuota o el límite propios de Google para ese modelo | espere o cambie a un modelo de nivel gratuito |
| `502` con un cuerpo vacío o no analizable | AI Studio cambió algo en su protocolo interno | conserve el cuerpo sin procesar, vuelva a capturarlo con `tools/capture_run.py` y actualice `src/lib/extract*.py` |
| `content` vacío pero `media` presente | es normal en los modelos de imagen, música y voz | lea `choices[0].message.media` |
| Chrome muestra "No API key selected" | el modelo seleccionado en la interfaz está bloqueado por ser de pago | el controlador vuelve a navegar automáticamente a un host gratuito; si persiste, elija una vez un modelo gratuito en el selector de modelos de AI Studio |
| Un modelo no aparece en `/v1/models` | no está en el registro | añádalo a `src/facade/registry.py` |
| `antigravity` o `veo-*` dan error | bloqueados en origen en el nivel de Google | no son utilizables a través de este proyecto — véase `docs/protocol-notebook.md` §15 |
| La respuesta parece la de una pregunta anterior | la petición se perdió mientras el navegador estaba bloqueado | compruebe `busy` en `/health` y vuelva a intentarlo |

## 11. Mantenimiento

- Reinicie `start.py` después de cambiar cualquier cosa bajo `src/`.
- Vuelva a ejecutar `python launch_chrome.py` si la sesión de AI Studio caduca
  (aparece una página de inicio de sesión en esa ventana).
- Si las respuestas empiezan a fallar de inmediato con `403`, la sesión o el
  token por petición cambiaron en origen: inicie sesión de nuevo en la ventana de
  Chrome y vuelva a comprobar `/health`.

## 12. Para profundizar

- `docs/protocol-notebook.md` — el cuaderno completo de ingeniería inversa:
  formas de los payloads, familias de protocolo, notas por modelo y la auditoría
  de modelos (§15).
- `tools/capture_run.py` — herramienta de captura de verdad de base (cuerpos de
  red, DOM, tramas de WebSocket) empleada para volver a hacer ingeniería inversa
  sobre un protocolo que haya cambiado.
