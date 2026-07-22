# dictapi — Dictation Agent for Linux

Push-to-talk speech-to-text on any Linux desktop.  

1. Press your shortcut → start speaking
2. Press again → the daemon sends your audio to **OpenRouter** (Mistral Transcribe)
3. The transcribed text is typed wherever your cursor is via **dotool**

---

## Requirements

| What | How |
| --- | --- |
| Python | ≥ 3.11 |
| PortAudio | `sudo apt install libportaudio2` |
| dotool | [geb/dotool](https://git.sr.ht/~geb/dotool) — already installed at `/usr/local/bin/dotool` |
| GNOME tray | Install the **AppIndicator and KStatusNotifierItem Support** GNOME Shell extension |
quel
**Optional**: an OpenRouter API key.

---

## Installation

```bash
cd dictapi//mcp
pip install -e .
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
language = "fr"          # ISO 639‑1

[audio]
samplerate = 16000       # 16 kHz recommended for STT
channels = 1             # mono

[dotool]
binary = "dotool"
typedelay = 0            # ms between keystrokes
```

---

## Usage

### 1. Start the daemon

```bash
dictapi daemon
```

Leave this terminal open (or add it to your Startup Applications).

You should see a green microphone icon in the system tray.

### 2. Test manually

In another terminal:

```bash
dictapi status          # → OK idle
dictapi toggle          # → OK recording
# … speak now …
dictapi toggle          # → OK idle  (text is typed!)
```

### 3. Set up the keyboard shortcut

- **GNOME**: Settings → Keyboard → View & Customize Shortcuts → Custom Shortcuts → **+**
  - Name: `Dictée`
  - Command: `dictapi toggle`
  - Shortcut: e.g. **Ctrl+Shift+D**

Now push-to-talk: press **Ctrl+Shift+D** to start, press again to stop.

### 4. Tray icon

Right-click the microphone icon for:

- **Démarrer / Arrêter la dictée** — same as the keyboard shortcut
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
GNOME shortcut (Ctrl+Shift+D)
    │
    ▼
dictapi toggle ── Unix socket ──▶ dictapi daemon
                                     │
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
| `ModuleNotFoundError: sounddevice` | `pip install sounddevice numpy` |
| `dotool not found` | `which dotool` — install from the source repo |
| Tray icon doesn't appear | Install the GNOME AppIndicator extension |
| `Missing OpenRouter API key` | `export OPENROUTER_API_KEY=sk-or-v1-...` |
| `Connection refused` on `dictapi toggle` | Start `dictapi daemon` first |
