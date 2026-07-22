# dictapi — Dictation Agent for Linux

Push-to-talk speech-to-text on any Linux desktop.

**Two ways to dictate:**

1. **Double-tap** Right Alt → speak → double-tap Right Alt again (no GNOME shortcut needed)
2. **Keyboard shortcut** (GNOME / custom) → `dictapi toggle` to start/stop

In both cases, the daemon sends your audio to **OpenRouter** (Mistral Transcribe) and the transcribed text is typed wherever your cursor is via **dotool**.

---

## Requirements

| What | How |
| --- | --- |
| Python | ≥ 3.11 |
| `uv` | [astral-sh/uv](https://docs.astral.sh/uv/) |
| PortAudio | `sudo apt install libportaudio2` |
| dotool | [geb/dotool](https://git.sr.ht/~geb/dotool) — already installed at `/usr/local/bin/dotool` |
| evdev | `sudo apt install python3-evdev` (for double-tap) |
| GNOME tray | Install the **AppIndicator and KStatusNotifierItem Support** GNOME Shell extension |

**Optional:** an OpenRouter API key.

---

## Installation

```bash
cd dictapi
uv sync
```

Set your API key (pick one):

```bash
# environment variable
export OPENROUTER_API_KEY="sk-or-v1-..."

# or in ~/.config/dictapi/config.toml under [api]
# api_key = "sk-or-v1-..."
```

---

## Configuration

Copy the default config and edit it:

```bash
mkdir -p ~/.config/dictapi
cp config.toml ~/.config/dictapi/config.toml
```

Readable settings:

```toml
[api]
model = "mistralai/voxtral-mini-transcribe"
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

---

## Usage

### 1. Start the daemon

```bash
dictapi daemon
```

Leave this terminal open (or add it to your Startup Applications).

You should see a green microphone icon in the system tray.

### 2. Dictate — choose your method

#### Option A — Double-tap (recommended)

Double-tap **Right Alt** to start recording, double-tap again to stop.

The daemon transcribes the audio and types the text at your cursor. No GNOME shortcut needed.

#### Option B — Keyboard shortcut

Set up a GNOME custom shortcut:

- **GNOME**: Settings → Keyboard → View & Customize Shortcuts → Custom Shortcuts → **+**
  - Name: `Dictée`
  - Command: `dictapi toggle`
  - Shortcut: e.g. **Ctrl+Shift+D**

If using `uv`, a wrapper script is available at `~/.local/bin/dictapi-toggle`:

```bash
#!/bin/bash
set -e
exec /home/pierre/.local/bin/uv run \
  --directory /home/pierre/Code/AI-test/pi-test/dictapi \
  dictapi toggle
```

Point your GNOME shortcut to this script instead.

### 3. Test manually

In another terminal:

```bash
dictapi status          # → OK idle
dictapi toggle          # → OK recording
# … speak now …
dictapi toggle          # → OK idle  (text is typed!)
```

### 4. Debug — find key codes

```bash
dictapi listen
```

Press any key to see its `evdev` key code. Use this to find the right value for `[keys] key` in your config (e.g. `KEY_LEFTCTRL`, `KEY_RIGHTALT`). Press **Ctrl+C** to exit.

### 5. Tray icon

Right-click the microphone icon for:

- **Démarrer / Arrêter la dictée** — same as double-tap or keyboard shortcut
- **Quitter** — graceful shutdown

Colours:

- 🟢 **green** = ready
- 🔴 **red** = recording
- 🟠 **orange** = transcribing
- 🔵 **blue** = typing
- ⚫ **grey** = error (auto-resets after 1 s)

---

## Architecture

```
GNOME shortcut  ─┐
                  ├──▶ dictapi toggle ── Unix socket ──▶ dictapi daemon
Double-tap Alt ───┘                                           │
                                                  ┌──────────┼──────────┐
                                                  ▼          ▼          ▼
                                             Recorder   Transcriber   Typer
                                           (sounddevice) (OpenRouter)  (dotool)

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
| `ModuleNotFoundError: sounddevice` | `uv sync` or `pip install sounddevice numpy` |
| `ModuleNotFoundError: evdev` | `sudo apt install python3-evdev` or `pip install evdev` |
| `dotool not found` | `which dotool` — install from the source repo |
| Tray icon doesn't appear | Install the GNOME AppIndicator extension |
| `Missing OpenRouter API key` | `export OPENROUTER_API_KEY=sk-or-v1-...` |
| `Connection refused` on `dictapi toggle` | Start `dictapi daemon` first |
| Double-tap not working | Check `[keys] provider = "evdev"` in config; run `dictapi listen` to verify the key code |
