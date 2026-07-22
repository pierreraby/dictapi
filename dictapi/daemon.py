"""dictapi daemon — Unix-socket IPC + state machine + tray icon.

Starts a background daemon that listens on a Unix socket for commands from
``dictapi toggle`` (the CLI front-end).  Orchestrates audio capture,
OpenRouter transcription, and dotool typing.

Usage:  dictapi daemon

Commands accepted on the socket (text protocol, one command per connection):
    toggle   – start / stop recording
    status   – return current state
    quit     – graceful shutdown
"""

import logging
import os
import select
import signal
import socket
import threading
import time
from pathlib import Path

from dictapi.config import load as load_config
from dictapi.recorder import Recorder
from dictapi.transcriber import Transcriber
from dictapi.typer import DotoolTyper

try:
    from dictapi.tray import TrayController  # type: ignore[import-untyped]
    _HAS_TRAY = True
except ImportError:
    TrayController = None  # type: ignore[assignment,misc]
    _HAS_TRAY = False

log = logging.getLogger(__name__)

# ── state constants ──────────────────────────────────────────────

IDLE = "idle"
RECORDING = "recording"
TRANSCRIBING = "transcribing"
TYPING = "typing"
ERROR = "error"

# ── Daemon ───────────────────────────────────────────────────────


class Daemon:
    """Main orchestrator: socket → state machine → audio → API → dotool."""

    def __init__(self, config: dict) -> None:
        cfg = config

        # ---- audio component ----
        self._recorder = Recorder(
            samplerate=cfg["audio"]["samplerate"],
            channels=cfg["audio"]["channels"],
            device=cfg["audio"].get("device"),
        )

        # ---- API component ----
        api_key = cfg["api"].get("api_key")
        if not api_key:
            raise RuntimeError(
                "Missing OpenRouter API key. "
                "Set OPENROUTER_API_KEY env var or api.api_key in config.toml"
            )
        self._transcriber = Transcriber(
            api_key=api_key,
            model=cfg["api"]["model"],
            language=cfg["api"]["language"],
            timeout=cfg["api"]["timeout"],
        )

        # ---- dotool component ----
        self._typer = DotoolTyper(
            binary=cfg["dotool"]["binary"],
            typedelay=cfg["dotool"]["typedelay"],
            xkb_layout=cfg["dotool"].get("xkb_layout"),
            xkb_variant=cfg["dotool"].get("xkb_variant"),
        )
        if not self._typer.available:
            log.warning("dotool binary not found — dictation will not type text!")

        # ---- socket ----
        self._sock_path = str(
            Path(cfg["daemon"]["socket_path"]).expanduser()
        )
        self._sock: socket.socket | None = None
        self._running = False

        # ---- tray (optional) ----
        if _HAS_TRAY:
            self._tray = TrayController(  # type: ignore[unreachable]
                on_toggle=self._on_tray_toggle,
                on_quit=self._request_quit,
            )
        else:
            self._tray = None
            log.warning("pystray/Pillow not available — running headless")

        # ---- state machine ----
        self._state: str = IDLE
        self._state_lock = threading.Lock()  # guards _state + recorder + tray
        self._error_until: float = 0  # timestamp; main loop skips socket while set

        # ---- key watcher ----
        self._keywatcher = None
        if cfg["keys"].get("provider") == "evdev":
            from dictapi.keywatcher import KeyWatcher
            self._keywatcher = KeyWatcher(
                device_path=cfg["keys"].get("device"),
                key_name=cfg["keys"].get("key", "KEY_RIGHTALT"),
                tap_window_ms=cfg["keys"].get("tap_window_ms", 400),
                on_toggle=self._on_toggle_wrapper,
            )

    # ── socket setup ──────────────────────────────────────────

    def _setup_socket(self) -> None:
        """Create and bind the Unix domain socket."""
        sock_dir = Path(self._sock_path).parent
        sock_dir.mkdir(parents=True, exist_ok=True)

        # Remove stale socket file from a previous crash
        try:
            os.unlink(self._sock_path)
        except FileNotFoundError:
            pass

        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(self._sock_path)
        self._sock.listen(5)
        os.chmod(self._sock_path, 0o600)
        log.info("Listening on %s", self._sock_path)

    # ── lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        """Bind socket, start tray, enter the select() event loop."""
        self._setup_socket()

        # signal handlers — set self._running = False on SIGINT / SIGTERM
        # (only works in the main thread; skipped in threads for test compat)
        def _handle_signal(signum: int, frame: object) -> None:
            log.info("Received signal %d, shutting down…", signum)
            self._running = False

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except ValueError:
            log.debug("Not in main thread — signal handlers not installed")

        # start tray in its own daemon thread
        if self._tray is not None:
            tray_thread = threading.Thread(
                target=self._tray.run,
                name="dictapi-tray",
                daemon=True,
            )
            tray_thread.start()

        if self._keywatcher:
            self._keywatcher.start()

        self._running = True
        log.info("Daemon ready — state: %s", self._state)

        # ── main loop ──────────────────────────────────────────
        assert self._sock is not None
        while self._running:
            # Clear error state after 2 seconds (non-blocking)
            if self._error_until and time.monotonic() >= self._error_until:
                self._error_until = 0
                with self._state_lock:
                    self._state = IDLE
                    self._update_tray(IDLE)

            readable, _, _ = select.select([self._sock], [], [], 1.0)
            if not readable:
                continue

            conn, _addr = self._sock.accept()
            with conn:
                data = conn.recv(1024)
                if not data:
                    continue

                raw = data.decode("utf-8").strip().lower()
                response = self._dispatch(raw)
                try:
                    conn.sendall((response + "\n").encode("utf-8"))
                except OSError:
                    pass

        self._cleanup()

    def _request_quit(self) -> None:
        """Called from tray thread — flags the main loop to exit."""
        self._running = False

    def _on_tray_toggle(self) -> None:
        """Tray toggle callback — same as socket toggle but discards return.

        Protected by ``_state_lock`` to prevent races when a socket
        ``toggle`` arrives from the main thread simultaneously.
        """
        with self._state_lock:
            self._handle_toggle()

    def _on_toggle_wrapper(self) -> None:
        """Thread-safe wrapper for keywatcher callback."""
        with self._state_lock:
            self._handle_toggle()

    def _cleanup(self) -> None:
        """Close socket, unlink file, stop tray."""
        log.info("Cleaning up…")
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        try:
            os.unlink(self._sock_path)
        except (FileNotFoundError, OSError):
            pass
        if self._tray is not None:
            self._tray.stop()
        if self._keywatcher:
            self._keywatcher.stop()
        log.info("Daemon stopped.")

    # ── command dispatch ──────────────────────────────────────

    def _dispatch(self, cmd: str) -> str:
        """Route a command to the right handler; return the response string."""
        # While showing an error state, accept only status and quit
        if self._error_until and cmd not in ("status", "quit"):
            return f"ERROR busy ({self._state})"

        if cmd == "toggle":
            with self._state_lock:
                return self._handle_toggle()
        if cmd == "status":
            return f"OK {self._state}"
        if cmd == "quit":
            self._running = False
            return "OK bye"
        return "ERROR unknown command"

    # ── toggle state machine ──────────────────────────────────

    def _handle_toggle(self) -> str:
        """Run one step of the toggle state machine.

        Caller must hold ``_state_lock`` if called from a concurrent path.
        """
        if self._state == IDLE:
            self._recorder.start()
            self._state = RECORDING
            self._update_tray(RECORDING)
            log.info("Recording started")
            return f"OK {RECORDING}"

        if self._state == RECORDING:
            wav = self._recorder.stop()

            if not wav:
                self._state = IDLE
                self._update_tray(IDLE)
                log.info("Recording stopped — no audio captured")
                return f"OK {IDLE} (empty)"

            self._state = TRANSCRIBING
            self._update_tray(TRANSCRIBING)
            log.info("Transcribing %d bytes…", len(wav))

            try:
                text = self._transcriber.transcribe(wav)
            except Exception as exc:
                log.error("Transcription failed: %s", exc)
                self._state = ERROR
                self._update_tray(ERROR)
                self._error_until = time.monotonic() + 2
                return f"ERROR transcription: {exc}"

            if text:
                self._state = TYPING
                self._update_tray(TYPING)
                log.info("Typing %d chars: %s", len(text), text[:80])
                try:
                    self._typer.type(text)
                except Exception as exc:
                    log.error("dotool failed: %s", exc)
                    self._state = ERROR
                    self._update_tray(ERROR)
                    self._error_until = time.monotonic() + 2
                    return f"ERROR typing: {exc}"

            self._state = IDLE
            self._update_tray(IDLE)
            return f"OK {IDLE}"

        # TRANSCRIBING or TYPING — ignore, still busy
        return f"OK {self._state}"

    # ── helpers ───────────────────────────────────────────────

    def _update_tray(self, state: str) -> None:
        if self._tray is None:
            return
        try:
            self._tray.set_state(state)
        except Exception:
            pass  # tray may be shutting down
