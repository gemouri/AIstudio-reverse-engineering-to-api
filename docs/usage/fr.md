# Guide d'utilisation — Google AI Studio → API compatible OpenAI

[English](en.md) · [Dansk](da.md) · [Deutsch](de.md) · [Español](es.md) · [Suomi](fi.md) · [Français](fr.md) · [हिन्दी](hi.md) · [Italiano](it.md) · [日本語](ja.md) · [한국어](ko.md) · [Nederlands](nl.md) · [Svenska](sv.md) · [Tiếng Việt](vi.md) · [中文](zh.md)

Ce projet pilote une vraie fenêtre Chrome connectée à **votre propre** session
Google AI Studio, puis réexpose cette session sous la forme d'une API standard
compatible OpenAI sur `http://127.0.0.1:8788/v1`. Aucune clé API Google, aucune
facturation : le projet s'appuie sur l'accès AI Studio dont votre compte
dispose déjà.

---

## 1. Prérequis

| Élément | Remarques |
|---|---|
| Système d'exploitation | Windows, macOS ou Linux — **poste de travail avec affichage** (Chrome s'exécute dans une fenêtre réelle et visible) |
| Python | 3.10 ou version ultérieure |
| Navigateur | Google Chrome (Chromium ou Edge fonctionnent également) |
| Compte Google | Tout compte capable d'ouvrir `aistudio.google.com` et d'envoyer une requête |
| Mémoire | ~2 Go de RAM libre pendant l'exécution de Chrome et de l'API |

## 2. Installation

```bash
git clone https://github.com/gemouri/AIstudio-reverse-engineering-to-api
cd AIstudio-reverse-engineering-to-api
pip install -r requirements.txt
```

Deux dépendances seulement sont nécessaires : `flask` et `websocket-client`.

## 3. Premier lancement

### Étape 1 — démarrer le navigateur dédié

```bash
python launch_chrome.py
```

Une fenêtre Chrome s'ouvre sur `aistudio.google.com` avec son **profil propre**
(distinct de celui du navigateur que vous utilisez au quotidien). Connectez-vous
avec votre compte Google — cette opération n'est nécessaire que la première
fois ; la session est conservée dans ce profil.

> **Gardez cette fenêtre ouverte.** C'est le composant qui génère un jeton par
> requête depuis la page. Sa fermeture arrête l'API.

### Étape 2 — démarrer l'API (nouveau terminal)

```bash
python start.py
```

Ligne attendue : `Running on http://127.0.0.1:8788`.

## 4. Vérifier que tout fonctionne

Trois contrôles, du plus rapide au plus complet :

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

Comment lire `/health` :

| Champ | Signification |
|---|---|
| `status` | `ok` = l'API et le navigateur sont tous deux joignables. `degraded` = l'API est active mais le navigateur/CDP ne l'est pas — redémarrez l'étape 1 |
| `hook` | `true` = le hook de réécriture des requêtes est installé dans la page (situation normale) |
| `busy` / `running_model` / `running_for_s` | une requête est en cours d'exécution, et depuis combien de temps |

## 5. Utiliser l'API depuis vos outils

Tout client compatible OpenAI fonctionne. Indiquez
`http://127.0.0.1:8788/v1` comme URL de base et n'importe quelle chaîne non vide
comme clé API.

### Python (SDK OpenAI)

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8788/v1", api_key="none")

print(client.chat.completions.create(
    model="gemini-3.1-flash-lite",
    messages=[{"role": "user", "content": "Hello!"}],
).choices[0].message.content)
```

### Diffusion en continu (streaming)

```python
stream = client.chat.completions.create(
    model="gemini-3.5-flash",
    messages=[{"role": "user", "content": "Write a short paragraph about rain."}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

### Appel de fonctions (tools)

Les `tools` au format OpenAI sont traduits vers le schéma Gemini et les réponses
reviennent sous forme de `tool_calls` standard :

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

### Conversation multi-tours

Envoyez la transcription complète à chaque appel, exactement comme avec
n'importe quelle API compatible OpenAI :

```python
messages = [
    {"role": "user", "content": "My name is Linh."},
    {"role": "assistant", "content": "Nice to meet you, Linh."},
    {"role": "user", "content": "What is my name?"},
]
```

### Autres clients

Pointez vers la même URL de base tout outil qui parle l'API OpenAI : OpenWebUI,
LobeChat, LangChain, LlamaIndex, la CLI OpenAI, vos propres scripts. Pour les
clients qui exigent une clé API, utilisez n'importe quelle chaîne de
remplacement.

## 6. Modèles

`GET /v1/models` est la source de vérité en temps réel. Groupes et usages
typiques :

| Groupe | Modèles | Niveau | Temps typique |
|---|---|---|---|
| Free chat | `gemini-3.1-flash-lite`, `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` | free | 20–30 s |
| Pro chat | `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.1-pro`, `gemini-flash-latest`, `gemini-pro-latest` | pro | 20–30 s |
| Images | `gemini-3-pro-image`, `gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image` | premium | 25–35 s |
| Musique | `lyria-3.5`, `lyria-3-pro` | premium | 45–60 s |
| Parole (TTS) | `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts` | premium | ~45 s |
| Agents de raisonnement | `deep-research-preview`, `deep-research-max` | agent | 2–5 min |
| Voix en direct | `gemini-3.1-flash-live` | premium | ~80 s |
| Omni | `gemini-omni-1.1-flash`, `gemini-omni-flash-preview` | pro | 20–30 s |
| Bloqués en amont | `antigravity`, `veo-3.1-generate`, `veo-3.1-fast-generate`, `veo-3.1-lite-generate` | — | renvoie une erreur — non pris en charge à ce niveau |

Les modèles de niveau gratuit ne consomment aucun quota payant. Les modèles pro,
premium et agent utilisent le quota du compte connecté ; lorsque Google refuse,
vous recevez un HTTP 429 honnête portant le message de Google lui-même.

## 7. Résultats multimédias

Les modèles qui produisent des médias les renvoient dans
`choices[0].message.media` sous forme d'URI `data:` — affichez-les ou
enregistrez-les directement.

| Famille de modèles | `media[0]` commence par | Remarques |
|---|---|---|
| Images | `data:image/jpeg;base64,` | la même image apparaît aussi en ligne dans `content` au format markdown |
| Musique | `data:audio/mpeg;base64,` | MP3 |
| Parole (TTS) | `data:audio/wav;base64,` | WAV mono 24 kHz ; la durée est indiquée dans `content` |
| Voix en direct | `data:audio/wav;base64,` | les réponses uniquement vocales ont un `content` quasiment vide |
| Deep research | `data:image/png;base64,` | artefacts de graphiques ; le rapport lui-même est dans `content`, le plan de recherche dans `reasoning_content`, les citations dans `message.sources` |

### Choisir une voix TTS

Ajoutez un champ facultatif `voice` au corps de la requête. Le nom de la voix
est l'un des 70 voix proposées par AI Studio — par exemple `Fola` (la valeur par
défaut de l'interface), `Puck`, `Lumi`, `Kore`, `Zephyr`, `Aoede`, `Charon`.

```bash
curl http://127.0.0.1:8788/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-3.8-flash-tts","voice":"Puck",
       "messages":[{"role":"user","content":"Good morning, this is a test."}]}'
```

## 8. Limites opérationnelles

- **Une requête à la fois.** Le navigateur traite une seule requête ; une
  seconde requête attend l'exécution en cours jusqu'à 90 secondes
  (`AIS2A_LOCK_WAIT`), puis échoue avec `503 farmer_busy`.
- **Délais d'attente côté client.** Chat ~20–30 s, images ~30 s, TTS ~45 s,
  Live ~80 s, deep-research 2–5 minutes. Réglez le délai d'attente de votre
  client avec largesse pour les agents (600 s ou plus).
- **Aucun plafond quotidien local.** Le registre ne fait que compter les
  requêtes par modèle et par jour ; il ne bloque rien. La limite réelle est
  celle de Google, qui se manifeste par un HTTP 429.
- **Gardez un volume humain.** Respectez les conditions d'utilisation d'AI
  Studio ; n'utilisez pas cet outil pour abuser des niveaux gratuits.

## 9. Variables d'environnement

| Variable | Valeur par défaut | Signification |
|---|---|---|
| `AIS2A_PORT` | `8788` | Port de l'API |
| `AIS2A_CDP_PORT` | `9333` | Port Chrome DevTools (CDP) |
| `AIS2A_CHROME_BIN` | détection automatique | Chemin vers le binaire Chrome/Chromium/Edge |
| `AIS2A_PROFILE_DIR` | `~/.ais2api/chrome-profile` | Profil de navigateur dédié (privé, propre à ce projet) |
| `AIS2A_LOCK_WAIT` | `90` | Secondes pendant lesquelles une requête en file attend le navigateur |
| `AIS2A_AGENT_TIMEOUT` | `1500` | Délai d'attente côté serveur pour les modèles agent (deep-research) |
| `AIS2A_TTS_TIMEOUT` | `120` | Délai d'attente côté serveur pour les modèles de parole |
| `AIS2A_LIVE_TIMEOUT` | `120` | Délai d'attente côté serveur pour la voix en direct |
| `AIS2A_VIDEO_TIMEOUT` | `600` | Délai d'attente côté serveur pour les tâches vidéo |

## 10. Dépannage

| Symptôme | Cause | Correction |
|---|---|---|
| `Connection refused` sur le port 8788 | l'API n'est pas en cours d'exécution | `python start.py` |
| `/health` indique `degraded`, ou les erreurs mentionnent `farmer CDP port not reachable` | la fenêtre Chrome a été fermée ou a planté | relancez `python launch_chrome.py` et connectez-vous si demandé |
| `503 farmer_busy` | une autre requête est toujours en cours | attendez qu'elle se termine, ou augmentez `AIS2A_LOCK_WAIT` |
| `429` renvoyé par l'API | quota ou limite de Google pour ce modèle | attendez, ou basculez vers un modèle de niveau gratuit |
| `502` avec un corps vide ou illisible | AI Studio a modifié quelque chose dans son protocole interne | conservez le corps brut, refaites une capture avec `tools/capture_run.py`, mettez à jour `src/lib/extract*.py` |
| `content` vide mais `media` présent | normal pour les modèles d'image, de musique et de parole | lisez `choices[0].message.media` |
| Chrome affiche « No API key selected » | le modèle sélectionné dans l'interface est verrouillé en payant | le pilote revient automatiquement vers un hôte gratuit ; si le problème persiste, choisissez une fois un modèle gratuit dans le sélecteur de modèles d'AI Studio |
| Modèle absent de `/v1/models` | il n'est pas dans le registre | ajoutez-le à `src/facade/registry.py` |
| `antigravity` ou `veo-*` renvoient une erreur | bloqués en amont au niveau de Google | inutilisables via ce projet — voir `docs/protocol-notebook.md` §15 |
| La réponse ressemble à celle d'une question précédente | la requête a été absorbée pendant que le navigateur était verrouillé | vérifiez `busy` dans `/health`, puis réessayez |

## 11. Maintenance

- Redémarrez `start.py` après toute modification sous `src/`.
- Relancez `python launch_chrome.py` si la session AI Studio expire (une page de
  connexion apparaît dans cette fenêtre).
- Si les réponses se mettent soudainement à échouer avec `403`, la session ou le
  jeton par requête a changé en amont : reconnectez-vous dans la fenêtre Chrome,
  puis revérifiez `/health`.

## 12. Pour aller plus loin

- `docs/protocol-notebook.md` — le carnet complet de rétro-ingénierie : formes
  des charges utiles, familles de protocoles, notes par modèle et audit des
  modèles (§15).
- `tools/capture_run.py` — outil de capture de vérité terrain (corps réseau,
  DOM, trames WebSocket) utilisé pour refaire la rétro-ingénierie d'un protocole
  modifié.
