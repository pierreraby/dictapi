# dictapi — Dictation Agent for Linux

Push-to-talk speech-to-text on any Linux desktop.

**Two ways to dictate:**

1. **Double-tap** Right Alt → speak → double-tap Right Alt again (no GNOME shortcut needed)
2. **Keyboard shortcut** (GNOME / custom) → `dictapi toggle` to start/stop

In both cases, the daemon sends your audio to an **STT provider** — **OpenRouter** (default) or **Gladia** — and the transcribed text is typed wherever your cursor is via **dotool**.

---

## Requirements

| What | How |
| --- | --- |
| Python | ≥ 3.11 |
| `uv` | [astral-sh/uv](https://docs.astral.sh/uv/) |
| PortAudio | `sudo apt install libportaudio2` |
| dotool | [geb/dotool](https://git.sr.ht/~geb/dotool) — installed at `/usr/local/bin/dotool` |
| evdev | `sudo apt install python3-evdev` (for double-tap) |
| secret-tool | `sudo apt install libsecret-tools` (for secure API key storage) |
| GNOME tray | Install the **AppIndicator and KStatusNotifierItem Support** extension |

---

## Installation

```bash
cd dictapi
uv sync
```

### Store your OpenRouter API key securely

```bash
secret-tool store --label="OpenRouter API Key" key OpenrouterApiKey
```

This stores the key in your GNOME Keyring — no plaintext in config files, no env vars to remember.

All launcher scripts (`dictapi-start`, `dictapi-toggle`) load it automatically. If `secret-tool` is not found, you can fall back to:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
```

---

## Configuration

Copy the default config and edit it:

```bash
mkdir -p ~/.config/dictapi
cp config.toml ~/.config/dictapi/config.toml
```

Full reference:

```toml
[api]
provider = "openrouter"  # "openrouter" | "gladia"
model = "mistralai/voxtral-mini-transcribe"  # OpenRouter slug
gladia_model = "solaria-1"                   # used when provider = "gladia"
language = "fr"          # ISO 639‑1
timeout = 30

[audio]
samplerate = 16000       # 16 kHz recommended for STT
channels = 1             # mono

[dotool]
binary = "dotool"
typedelay = 0            # ms between keystrokes
xkb_layout = "fr"        # Wayland layout; leave commented to skip

[daemon]
socket_path = "~/.local/share/dictapi/dictapi.sock"

[keys]
provider = "evdev"       # enable double-tap, or "" to disable
key = "KEY_RIGHTALT"     # key to double-tap
tap_window_ms = 400      # max ms between two taps
```

### Choisir le fournisseur : OpenRouter ou Gladia

Le champ `[api].provider` sélectionne le moteur de transcription :

- `provider = "openrouter"` (défaut) — utilise `OPENROUTER_API_KEY` et le
  slug `[api].model`. Comportement historique, inchangé.
- `provider = "gladia"` — utilise `GLADIA_API_KEY` et le modèle
  `[api].gladia_model`.

### Fournisseur Gladia

[Gladia](https://www.gladia.io/) est utilisé **en direct** (pas via
OpenRouter). Son API *pre-recorded* (v2) est **asynchrone** :
upload → création d'un job → polling jusqu'à `status = "done"`. Le daemon
gère ce cycle de façon transparente et attend le résultat (icône 🟠 orange
pendant l'attente), exactement comme le flux batch/push-to-talk existant.

```bash
# Clé à exporter au démarrage (déjà chargé par dictapi-start si elle est
# dans le trousseau) :
export GLADIA_API_KEY="..."
# ou, de façon sûre :
secret-tool store --label="Gladia API Key" key GladiaApiKey
```

```toml
[api]
provider = "gladia"
gladia_model = "solaria-1"   # ou "solaria-3" (optimisé FR/EN/DE/ES/IT)
language = "fr"
```

Modèles Gladia : `solaria-1` (généraliste, défaut) et `solaria-3` (dernier
modèle, une seule langue à la fois). Le WAV 16 kHz mono enregistré par
dictapi est exactement le format cible de Gladia (aucune conversion).

> ⚠️ Le polling est borné par `[api].timeout` (défaut 30 s). Le client CLI
> attend 35 s. Pour de très longs enregistrements, augmente `timeout`.

### STT models OpenRouter

Le modèle est choisi uniquement avec son *slug* dans `[api].model`. Le
transcriber utilise l'endpoint OpenRouter commun
[`/api/v1/audio/transcriptions`](https://openrouter.ai/docs/guides/overview/multimodal/stt),
donc ces modèles ne demandent pas de modification du code :

| Fournisseur | Slug OpenRouter |
| --- | --- |
| Mistral | `mistralai/voxtral-mini-transcribe` |
| xAI | `x-ai/grok-stt-1.0` |
| Deepgram | `deepgram/nova-3` |
| Microsoft | `microsoft/mai-transcribe-1.5` |
| Qwen | `qwen/qwen3-asr-flash-2026-02-10` |

Pour changer de modèle, modifie la ligne `model`, puis redémarre le daemon.
Le fonctionnement actuel est **batch / push-to-talk** : l'enregistrement WAV
complet est envoyé après le second appui. Il ne s'agit pas d'un flux audio
realtime (WebSocket ou transcription partielle pendant la capture).

---

## Usage

### 1. Start the daemon

```bash
dictapi-start          # launches in foreground — leave the terminal open
```

Or add it to your GNOME Startup Applications for zero-friction launch on login.

You should see a green microphone icon in the system tray.

### 2. Stop the daemon

```bash
dictapi-stop           # graceful shutdown via socket
```

Or right-click the tray icon → **Quitter**.

### 3. Dictate — choose your method

#### Option A — Double-tap (recommended)

Double-tap **Right Alt** to start recording, double-tap again to stop.

The daemon transcribes the audio and types the text at your cursor. No GNOME shortcut needed.

#### Option B — Keyboard shortcut

Set up a GNOME custom shortcut:

- **GNOME**: Settings → Keyboard → View & Customize Shortcuts → Custom Shortcuts → **+**
  - Name: `Dictée`
  - Command: `dictapi-toggle`
  - Shortcut: e.g. **Ctrl+Shift+D**

### 4. Test manually

```bash
dictapi status          # → OK idle
dictapi toggle          # → OK recording
# … speak now …
dictapi toggle          # → OK idle  (text is typed!)
```

### 5. Debug — find key codes

```bash
dictapi listen
```

Press any key to see its `evdev` key code. Use this to pick the right value for `[keys] key` in your config (e.g. `KEY_LEFTCTRL`, `KEY_RIGHTALT`). Press **Ctrl+C** to exit.

### 6. Tray icon

Right-click the microphone icon for:

- **Démarrer / Arrêter la dictée** — same as double-tap or toggle
- **Quitter** — graceful shutdown

Colours:

- 🟢 **green** = ready
- 🔴 **red** = recording
- 🟠 **orange** = transcribing
- 🔵 **blue** = typing
- ⚫ **grey** = error (auto-resets after 1 s)

---

## Launcher scripts

Three convenience scripts live in `~/.local/bin/`:

| Script | Purpose |
| --- | --- |
| `dictapi-start` | Start the daemon (loads API key from GNOME Keyring) |
| `dictapi-stop` | Graceful shutdown via Unix socket |
| `dictapi-toggle` | Push-to-talk toggle — used by the GNOME shortcut |

All three auto-load `OPENROUTER_API_KEY` from `secret-tool` if available.

---

## Architecture

```text
GNOME shortcut  ─┐
                  ├──▶ dictapi-toggle ── Unix socket ──▶ dictapi daemon
Double-tap Alt ───┘                                        │
                                              ┌──────────┼──────────┐
                                              ▼          ▼          ▼
                                         Recorder   Transcriber        Typer
                                       (sounddevice) (OpenRouter/Gladia) (dotool)

State machine:  IDLE → RECORDING → TRANSCRIBING → TYPING → IDLE
```

---

## Socket Protocol

One text command per TCP-style connection:

| Client sends | Server responds |
| --- | --- |
| `toggle\n` | `OK idle\|recording\|transcribing\|typing\n` |
| `status\n` | `OK idle\n` |
| `quit\n` | `OK bye\n` |
| *(garbage)* | `ERROR unknown command\n` |

---

## Troubleshooting

| Symptom | Likely fix |
| --- | --- |
| `ModuleNotFoundError: sounddevice` | `uv sync` |
| `ModuleNotFoundError: evdev` | `sudo apt install python3-evdev` or `pip install evdev` |
| `secret-tool: command not found` | `sudo apt install libsecret-tools` |
| Key not found by secret-tool | Use the exact command: `secret-tool lookup key OpenrouterApiKey` |
| `dotool not found` | `which dotool` — install from the source repo |
| Tray icon doesn't appear | Install the GNOME AppIndicator extension |
| `Missing OpenRouter API key` | Run `secret-tool store --label="OpenRouter API Key" key OpenrouterApiKey` |
| `Missing Gladia API key` | Set `provider = "gladia"` needs `GLADIA_API_KEY` — run `secret-tool store --label="Gladia API Key" key GladiaApiKey` |
| Gladia transcription slow / timeout | Gladia is async (polling); raise `[api].timeout` for long recordings |
| `Connection refused` on `dictapi toggle` | Start the daemon with `dictapi-start` |
| Double-tap not working | Check `[keys] provider = "evdev"` in config; run `dictapi listen` to verify key codes |
| `dictapi-start` / `dictapi-toggle` not found | Make sure `~/.local/bin/` is in your `$PATH` |
