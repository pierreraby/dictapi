# dictapi — Contexte complet du projet

> Généré le 2025-07-17 par le context-builder subagent

---

## 1. Présentation du projet

**dictapi** est un agent de dictée push-to-talk pour Linux. Il capture l'audio du micro, l'envoie à OpenRouter (Mistral Transcribe) pour transcription, puis tape le texte résultant via **dotool** à l'endroit où se trouve le curseur.

Il fonctionne sur **X11 et Wayland**, sans dépendre d'une API de accessibilité spécifique (AT-SPI, etc.), grâce à dotool qui simule le clavier via `/dev/uinput`.

### Cas d'usage typique

1. L'utilisateur presse **Ctrl+Shift+D** (ou son propre raccourci GNOME)
2. Il parle pendant quelques secondes
3. Il represse le même raccourci
4. Le texte transcrit apparaît automatiquement dans l'éditeur, terminal, navigateur, etc.

---

## 2. Architecture

### Arborescence

```
dictapi/
├── dictapi/
│   ├── __init__.py        # Version string
│   ├── __main__.py        # CLI entry point (argparse, socket IPC client)
│   ├── config.py          # Configuration loader (TOML + env vars)
│   ├── daemon.py          # Orchestrateur : socket IPC, state machine, tray
│   ├── recorder.py        # Capture audio via sounddevice → WAV bytes
│   ├── transcriber.py     # Appel API OpenRouter (Mistral Transcribe)
│   ├── typer.py           # Wrapper dotool pour simuler le clavier
│   ├── tray.py            # Icône système pystray (Pillow)
│   └── keywatcher.py      # Double-tap evdev (optionnel)
├── config.toml            # Configuration par défaut du projet
├── pyproject.toml         # Métadonnées et dépendances pip
├── README.md              # Documentation utilisateur
├── keyboard_shortcuts.py  # Module legacy (Vocalinux) — non utilisé par dictapi
├── uv.lock                # Lock file uv/pip
└── .pi-subagents/         # Artéfacts des sessions Pi précédentes
```

### Dépendances (pyproject.toml)

| Dépendance | Rôle |
| --- | --- |
| `sounddevice>=0.5.0` | Capture audio via PortAudio |
| `pystray>=0.19.0` | Icône système (StatusNotifierItem) |
| `Pillow>=10.0.0` | Génération d'icône microphone en mémoire |
| `requests>=2.31.0` | Appel API REST OpenRouter |
| `numpy>=1.24.0` | Normalisation audio float32 → int16 |
| *(optionnel)* `evdev` | Double-tap hardware (alternative au raccourci GNOME) |

**Entry point CLI** : `dictapi = "dictapi.__main__:cli"`

### Flux de données

```
GNOME Shortcut (Ctrl+Shift+D)  ou  double-tap Alt droit  ou  clic tray
                          │
                          ▼
              dictapi toggle ──── Unix Socket ────▶ dictapi daemon (foreground)
                    IPC           (STREAM)            │
                                                     ├── pystray tray icon (thread dédié)
                                                     ├── Recorder    (sounddevice)
                                                     ├── Transcriber (OpenRouter REST)
                                                     └── DotoolTyper (dotool subprocess)
```

### Machine à états

```
  IDLE ──toggle──▶ RECORDING ──toggle──▶ TRANSCRIBING ──(auto)──▶ TYPING ──(auto)──▶ IDLE
   ▲                  │                      │                       │
   │                  │ (error)              │ (error)               │ (error)
   │                  ▼                      ▼                       ▼
   └──────────────── ERROR ──(2s auto-reset)──────────────────────────┘
```

### Diagramme de séquence (cycle complet)

```
CLI              Daemon            Recorder         Transcriber    Typer       Tray
 │                 │                  │                 │            │           │
 │── toggle ──────▶│                  │                 │            │           │──▶ 🔴
 │                 │── start() ──────▶│                 │            │           │
 │                 │ state=RECORDING  │[buffering]      │            │           │
 │                 │                  │                 │            │           │
 │── toggle ──────▶│                  │                 │            │           │
 │                 │── stop() ───────▶│── WAV bytes ──▶ │            │           │──▶ 🟠
 │                 │ state=TRANSCRIBING                 │            │           │
 │                 │                                   │── text ──▶ │           │
 │                 │ state=TYPING                      │            │── type()──▶│──▶ 🔵
 │                 │ state=IDLE                        │            │           │──▶ 🟢
 │◀── OK idle ─────│                  │                 │            │           │
```

---

## 3. Décisions clés et leur justification

### 3.1 Python plutôt que JavaScript

- **Pourquoi** : Le projet original (Vocalinux) avait un proxy TypeScript/Hono pour l'API OpenRouter. La version dictapi réimplémente tout en Python.
- **Avantages** : Pas de runtime Node.js requis, gestion directe de PortAudio (sounddevice), code unifié pour la capture + transcription + typing.
- **Conséquence** : Le proxy TS (`index.ts` dans l'historique) est désormais legacy et pourrait être supprimé.

### 3.2 dotool pour le typing

- **Pourquoi** : `dotool` (successeur de `ydotool`) fonctionne sur Wayland ET X11 en injectant des événements input via `/dev/uinput`. Pas de dépendance à `xdotool`, `xte`, ou `wtype`.
- **Contrainte** : Nécessite que l'utilisateur ait installé dotool (`/usr/local/bin/dotool` typiquement).
- **Layout clavier** : Via variable d'environnement `DOTOOL_XKB_LAYOUT` (ex: `fr` pour AZERTY).

### 3.3 evdev pour le double-tap

- **Pourquoi** : Alternative au raccourci GNOME. Capture directement les événements clavier hardware via evdev. Fonctionne même si GNOME n'est pas au premier plan.
- **Contrainte** : L'utilisateur doit être dans le groupe `input` pour lire `/dev/input/event*`.
- **Configuration** : Touche configurable (`KEY_RIGHTALT` par défaut), fenêtre de double-tap 400 ms.

### 3.4 Socket IPC Unix (SOCK_STREAM)

- **Pourquoi** : Simple, pas de serveur HTTP, pas de filesystem partagé. Le daemon écoute sur un socket Unix, le CLI s'y connecte, envoie une commande texte, reçoit une réponse, ferme.
- **Avantage** : Pas de port réseau ouvert, sécurité par permissions fichier (`0o600`).

### 3.5 pystray pour l'icône système

- **Pourquoi** : Fonctionne via StatusNotifierItem (SNI), compatible avec GNOME (via extension AppIndicator) et KDE.
- **Contrainte** : GNOME ≥ 40 ne supporte pas SNI nativement. L'extension "AppIndicator and KStatusNotifierItem Support" est indispensable.
- **Mode headless** : Si pystray n'est pas installé, le daemon fonctionne sans icône (log warning).

---

## 4. État actuel

### ✅ Ce qui marche

| Fonctionnalité | Statut | Détails |
| --- | --- | --- |
| Capture audio | ✅ | `sounddevice` → buffer numpy → WAV int16 |
| Transcription API | ✅ | OpenRouter Mistral Transcribe, base64/WAV |
| Typage dotool | ✅ | Simple lines, multi-line séparé par `key Return` |
| Icône système | ✅ | 5 couleurs (vert/rouge/orange/bleu/gris) |
| Socket IPC | ✅ | `toggle`, `status`, `quit` |
| Machine à états | ✅ | IDLE→RECORDING→TRANSCRIBING→TYPING→IDLE |
| Double-tap evdev | ✅ | `keywatcher.py` avec callback thread-safe |
| CLI `listen` debug | ✅ | Affiche les keycodes des touches pressées |
| Gestion erreur API | ✅ | → ERROR state, auto-reset after 2s |
| Gestion dotool absent | ✅ | Warning au démarrage |
| Config TOML + env vars | ✅ | Merge hiérarchique |

### 🟡 Ce qui fonctionne avec réserves

| Problème | Sévérité | Détail |
| --- | --- | --- |
| **Multi-line dotool** | **BLOCKER** | Voir section 6.2 |
| **Timeout CLI** | **HIGH** | 3s de timeout socket, mais API peut prendre 30s |
| **Race tray+dispatch** | **HIGH** | Voir section 6.3 |
| **listen(1) backlog** | **MEDIUM** | `listen(1)` = 1 connexion en attente max |
| **Error state sleep** | **MEDIUM** | ~~`time.sleep(1)`~~ **RÉSOLU** — maintenant utilise `_error_until` timestamp |

### 🔴 Ce qui reste à faire / améliorations

| Priorité | Tâche |
| --- | --- |
| **HIGH** | Fixer le multi-line dotool (typer.py:32-33) |
| **HIGH** | Synchroniser l'appel `_on_tray_toggle()` avec `_state_lock` |
| **MEDIUM** | Augmenter `listen(1)` → `listen(5)` |
| **LOW** | Détection VAD (Voice Activity Detection) pour arrêt automatique |
| **LOW** | Notification desktop (`notify-send`) en fin de transcription |
| **LOW** | Menu tray pour changer de langue/modèle |
| **LOW** | Vérifier RMS avant envoi API (éviter silence → API call gaspillé) |
| **LOW** | Supprimer/moderniser `keyboard_shortcuts.py` (legacy Vocalinux) |

---

## 5. Configuration

### 5.1 Fichier `config.toml`

Emplacement : `~/.config/dictapi/config.toml` (ou `./config.toml` dans le projet)

```toml
[api]
# api_key = "sk-or-v1-..."          # ou via env OPENROUTER_API_KEY
model = "mistralai/voxtral-mini-transcribe"
language = "fr"                      # ISO 639-1
timeout = 30                         # timeout requête en secondes

[audio]
samplerate = 16000                   # 16 kHz recommandé STT
channels = 1                         # mono
# device = 0                         # index périphérique (défaut = syst.)

[dotool]
binary = "dotool"
typedelay = 0                        # ms entre frappes
xkb_layout = "fr"                    # DOTOOL_XKB_LAYOUT (AZERTY)
# xkb_variant = "latin9"

[daemon]
socket_path = "~/.local/share/dictapi/dictapi.sock"

[keys]
provider = "evdev"                   # "evdev" ou None
key = "KEY_RIGHTALT"
tap_window_ms = 400                  # fenêtre double-tap
# device = "/dev/input/event4"       # forcer un périphérique
```

### 5.2 Ordre de résolution (priorité croissante)

1. **Valeurs par défaut** (dans `config.py:DEFAULT`)
2. **`~/.config/dictapi/config.toml`** (user config)
3. **`./config.toml`** (projet local — surcharge le user)
4. **Argument `path`** de `load()` (explicite)
5. **Variable d'environnement `OPENROUTER_API_KEY`** (surcharge `api.api_key`)

### 5.3 Variables d'environnement

| Variable | Rôle |
| --- | --- |
| `OPENROUTER_API_KEY` | Clé API OpenRouter (priorité max) |
| `DOTOOL_XKB_LAYOUT` | Layout clavier pour dotool (ex: `fr`, `us`) |
| `DOTOOL_XKB_VARIANT` | Variant (ex: `latin9`, `oss`) |

---

## 6. Problèmes résolus (et leçons apprises)

### 6.1 AZERTY / QWERTY (RÉSOLU)

**Problème** : dotool tape en QWERTY par défaut, même si le système est en AZERTY.
**Solution** : Passer `DOTOOL_XKB_LAYOUT=fr` dans l'environnement du subprocess dotool.
**Fichier** : `typer.py:25-27`

```python
self._env = os.environ.copy()
if xkb_layout:
    self._env["DOTOOL_XKB_LAYOUT"] = xkb_layout
```

### 6.2 Multi-line dotool (RÉSOLU dans typer.py, mais vérifier)

**Problème** : Si la transcription contient des retours à la ligne (fréquent en dictée),
  `dotool` interprète chaque ligne comme une commande, pas comme du texte à taper.
  
  Exemple: la transcription "Bonjour\nComment ça va ?" envoie :

  ```
  type Bonjour
  Comment ça va ?      ← dotool interprète "Comment" comme une commande inconnue → erreur
  ```

**Solution actuelle** (`typer.py:30-39`) : Splitter le texte sur `\n`, envoyer
  `type {ligne}` pour chaque paragraphe, séparé par `key Return`.

```python
paragraphs = text.split("\n")
for i, para in enumerate(paragraphs):
    lines.append(f"type {para}")
    if i < len(paragraphs) - 1:
        lines.append("key Return")
```

**⚠️ Résidu** : Si `dotool` reçoit un texte commençant par un mot-clé dotool
  (`type`, `key`, `mousemove`, etc.), il peut l'interpréter comme commande.
  Solution idéale : utiliser un mode littéral si dotool le supporte, ou
  échapper les lignes. Risque faible en pratique.

### 6.3 Race conditions dans la machine à états (RÉSOLU)

**Problème** : Les callbacks viennent de 3 threads différents :

- Thread principal (socket dispatch)
- Thread tray (clic menu)
- Thread keywatcher (double-tap evdev)

**Solution** : `_state_lock = threading.Lock()` protège tous les appels à
  `_handle_toggle()` via des wrappers :
  
- `_on_toggle_wrapper()` (daemon.py:144-147) — lock avant `_handle_toggle()`
- `_on_tray_toggle()` (daemon.py:137-142) — lock avant `_handle_toggle()`
- `_dispatch("toggle")` (daemon.py:183) — lock avant `_handle_toggle()`

**Fichier** : `daemon.py:49`, `daemon.py:137-147`, `daemon.py:183`

### 6.4 Error state non-bloquant (RÉSOLU)

**Problème** : Anciennement `time.sleep(1)` dans la boucle select bloquait tout.
**Solution** : `_error_until` timestamp (monotonic). La boucle principale vérifie
  `time.monotonic() >= self._error_until` à chaque itération et reset l'état
  automatiquement sans bloquer.

**Fichier** : `daemon.py:50`, `daemon.py:161-166`

### 6.5 Stale socket (RÉSOLU)

**Problème** : Si le daemon crashe, le fichier socket persiste et bloque le redémarrage.
**Solution** : `os.unlink()` au démarrage (`daemon.py:97`) et à l'arrêt (`daemon.py:216`).

### 6.6 Python 3.11+ only (assumé)

**Pourquoi** : Utilisation de `tomllib` (standard library depuis 3.11) pour parser le TOML.
  Également `str | None` syntax, `list[...]` generics.

---

## 7. Meta-prompt pour reprise du travail

```markdown
## Goal
Complete dictapi — Linux push-to-talk dictation agent. The project is at
`/home/pierre/Code/AI-test/pi-test/dictapi/`.

## Current state
All core features are implemented:
- Audio capture (sounddevice → WAV)
- Transcription (OpenRouter Mistral Transcribe)
- Typing (dotool)
- Tray icon (pystray, 5 states)
- Socket IPC (Unix STREAM, text protocol)
- evdev double-tap (optional)
- CLI (`dictapi daemon|toggle|status|quit|listen`)
- Config (TOML + env vars)
- Error handling (auto-reset after 2s)

## Known issues (from review)
1. **BLOCKER**: Multi-line transcription — `typer.py` splits lines correctly
   but dotool may still interpret text starting with dotool keywords as commands.
   Validate the current fix works end to end.
2. **HIGH**: CLI timeout — `__main__.py` socket timeout is 35s (configurable),
   verify against API timeout=30s. The timeout was increased from 3s to 35s.
3. **HIGH**: Race condition — verify `_on_tray_toggle()` and `_on_toggle_wrapper()`
   both hold `_state_lock` before calling `_handle_toggle()`.
4. **MEDIUM**: `listen(1)` backlog — consider increasing to `listen(5)`.
5. **LOW**: Legacy `keyboard_shortcuts.py` — not imported by dictapi, safe to remove.
6. **LOW**: No silence detection before API call.

## Key file locations
- `dictapi/__main__.py` — CLI, socket timeout at line 37
- `dictapi/config.py` — DEFAULT dict, merge logic
- `dictapi/daemon.py` — Daemon class, state machine, locking
- `dictapi/recorder.py` — Recorder class (sounddevice)
- `dictapi/transcriber.py` — Transcriber class (OpenRouter)
- `dictapi/typer.py` — DotoolTyper, multi-line handling at lines 30-39
- `dictapi/tray.py` — TrayController, 5 icon states
- `dictapi/keywatcher.py` — KeyWatcher, evdev double-tap
- `config.toml` — config template
- `pyproject.toml` — dependencies

## Architecture invariants
- Python ≥ 3.11 only (tomllib, type syntax)
- State machine: IDLE→RECORDING→TRANSCRIBING→TYPING→IDLE (with ERROR)
- Socket protocol: one text command per TCP-style connection
- Tray in daemon thread, accessed thread-safely via set_state()
- _state_lock protects all state transitions from any thread
- dotool subprocess with DOTOOL_XKB_LAYOUT env var for AZERTY/QWERTY
- No tests exist yet — add pytest tests

## Validation
- `python3 -c "from dictapi.config import load; cfg=load(); print('OK')"`
- `python3 -m dictapi daemon` (starts, prints "Listening on ...")
- In another terminal: `python3 -m dictapi status` → "OK idle"
- `python3 -m dictapi toggle` → "OK recording" / "OK idle"
- `python3 -c "import tomllib; tomllib.load(open('config.toml','rb'))"`
- `python3 -c "import dictapi.recorder, dictapi.transcriber, dictapi.typer, dictapi.tray, dictapi.daemon, dictapi.keywatcher; print('OK')"`

## Hard constraints
- Do not remove evdev dependency — keywatcher imports it at runtime
- Do not change socket protocol format (OK/ERROR prefix)
- Do not add new dependencies without justification
- Do not modify config.py DEFAULT structure without updating load()
- Do not break headless mode (no pystray = no crash)
```

---

## 8. Fichier par fichier — résumé technique

### `dictapi/__init__.py`

- Juste `__version__ = "0.1.0"` et docstring.

### `dictapi/__main__.py`

- **Rôle** : CLI argparse avec 5 sous-commandes : `daemon`, `toggle`, `status`, `quit`, `listen`.
- **Socket timeout** : 35s (30s API + 5s marge) — **attention** : le timeout était de 3s dans la revue, maintenant 35s.
- **Erreurs gérées** : `ConnectionRefusedError`, `FileNotFoundError`, `socket.timeout`, `OSError`.
- **listen** : Mode debug qui affiche les keycodes evdev (utile pour configurer le double-tap).

### `dictapi/config.py`

- **Rôle** : Charge la configuration TOML avec merge profond.
- **Points clés** : `_merge()` récursif, shallow copy des defaults pour éviter la mutation, `tomllib` (stdlib 3.11+).
- **Ordre** : defaults → `~/.config/dictapi/config.toml` → `./config.toml` → path argument → env var.
- **Noms de sections** : `api`, `audio`, `dotool`, `daemon`, `keys`.

### `dictapi/daemon.py`

- **Rôle** : Orchestrateur principal — socket Unix + state machine + tray.
- **~280 lignes**.
- **State machine** : `_handle_toggle()` (ligne ~199) — gère IDLE→RECORDING, RECORDING→TRANSCRIBING→TYPING→IDLE, et ERROR.
- **Thread safety** : `_state_lock` (threading.Lock) protège tous les accès à `_state`.
- **Error handling** : `_error_until` timestamp, pas de `time.sleep()`.
- **Tray** : Thread dédié daemon. Import conditionnel : si pystray manque, mode headless.
- **Signaux** : SIGINT/SIGTERM → `_running = False`.
- **Nettoyage** : Unlink socket, close socket, stop tray, stop keywatcher.

### `dictapi/recorder.py`

- **Rôle** : Capture audio via `sounddevice.InputStream` → buffer numpy → WAV bytes.
- **Format** : 16 kHz, mono, 16-bit int16 WAV.
- **Callback** : Copie `indata.copy()` pour éviter les mutations.
- **Normalisation** : `np.clip(audio * 32767, -32768, 32767).astype(np.int16)`.
- **Propriétés** : `is_recording` (bool).

### `dictapi/transcriber.py`

- **Rôle** : Envoie le WAV à OpenRouter API `/v1/audio/transcriptions`.
- **Format** : Base64 dans `input_audio.data`, format `"wav"`.
- **Headers** : `Authorization: Bearer {api_key}`, `Content-Type: application/json`.
- **Gestion erreur** : `raise RuntimeError` si statut ≠ 2xx, texte vide si réponse vide.

### `dictapi/typer.py`

- **Rôle** : Wrapper dotool — envoie des commandes texte via stdin.
- **Layout** : `DOTOOL_XKB_LAYOUT` / `DOTOOL_XKB_VARIANT` dans l'environnement du subprocess.
- **Multi-line** : Split sur `\n`, chaque paragraphe en `type {para}`, séparé par `key Return`.
- **`key(chord)`** : Envoie `key {chord}\n` pour les combinaisons (ex: `ctrl+shift+v`).

### `dictapi/tray.py`

- **Rôle** : Icône système pystray/Pillow avec 5 états + 2 entrées menu.
- **Icône** : 64×64 RGBA, cercle coloré + silhouette microphone blanche.
- **États** : `idle` (vert #2EA043), `recording` (rouge #DC322F), `transcribing` (orange #FF9900), `typing` (bleu #1E90FF), `error` (gris #808080).
- **Thread-safe** : `set_state()` avec lock, mise à jour via `icon.icon` et `icon.title`.
- **Menu** : "Démarrer / Arrêter la dictée" (callback `on_toggle`), "Quitter" (callback `on_quit`).

### `dictapi/keywatcher.py`

- **Rôle** : Double-tap evdev — écoute un périphérique clavier pour détecter un double-appui.
- **Détection auto** : `find_keyboard()` cherche le premier périphérique avec `KEY_A`.
- **Fenêtre** : `tap_window_ms` (défaut 400 ms) entre deux pressions.
- **Callback** : Appelle `on_toggle()` sur détection de double-tap.
- **Thread** : Boucle évènements dans un thread daemon.

### `config.toml`

- Fichier de configuration par défaut du projet, copié vers `~/.config/dictapi/config.toml`.
- Sections : `[api]`, `[audio]`, `[dotool]`, `[daemon]`, `[keys]`.
- **Remarque** : Format TOML valide (plus de `null` ou doubles clés).

### `pyproject.toml`

- Build system : `setuptools>=64`.
- Entry point : `dictapi = "dictapi.__main__:cli"`.

---

## 9. Résumé des risques résiduels

| Risque | Sévérité | Description |
| --- | --- | --- |
| Dotool multi-line edge case | Medium | Si le texte transcrit commence par un mot-clé dotool (`type`, `key`, etc.), il sera interprété comme commande. |
| Pas de VAD | Low | Un silence enregistré consomme un appel API pour rien. |
| Pas de tests | Medium | Aucun test unitaire ou d'intégration. La moindre régression est manuelle. |
| Tray dépend de l'extension GNOME | Medium | Sans l'extension AppIndicator, pas d'icône (mais mode headless fonctionne). |
| PortAudio pas installé par défaut | Low | `sudo apt install libportaudio2` nécessaire. |
| Dotool pas inclus | Medium | L'utilisateur doit builder dotool depuis les sources. |
| Pas de mutex sur `_running` | Low | Booléen partagé entre threads sans verrou (GIL-safe en pratique). |

---

## 10. Fichiers legacy / non utilisés

| Fichier | Raison |
| --- | --- |
| `keyboard_shortcuts.py` | Ancien module Vocalinux avec backends pynput/evdev. Remplacé par `keywatcher.py`. |
| `dictapi/keyboard_backends.py` | (non listé, mais importé par `keyboard_shortcuts.py`) — même legacy. |
| `.pi-subagents/` | Artéfacts de sessions Pi précédentes (DeepSeek research, plans, reviews). |
| `uv.lock` | Lock file généré par uv (optionnel, pip fonctionne aussi). |
