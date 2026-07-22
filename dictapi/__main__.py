"""dictapi CLI entry point.

Usage::

    dictapi daemon     start the background daemon (foreground process)
    dictapi toggle     start / stop recording (via Unix socket)
    dictapi status     query daemon state
    dictapi quit       graceful shutdown

Set up a GNOME custom shortcut pointing to ``dictapi toggle`` for push-to-talk.
"""

import argparse
import logging
import socket
import sys
from pathlib import Path

from dictapi.config import load as load_config

# Default socket path — keep in sync with config.toml
_SOCK_PATH = "~/.local/share/dictapi/dictapi.sock"


# ── helpers ──────────────────────────────────────────────────────

def _send_command(cmd: str, sock_path: str = _SOCK_PATH) -> str:
    """Connect to the daemon, send *cmd*, and return the response line."""
    path = str(Path(sock_path).expanduser())
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(35)  # 30s API timeout + 5s marge
        sock.connect(path)
        sock.sendall(f"{cmd}\n".encode("utf-8"))
        data = sock.recv(4096)
        sock.close()
        return data.decode("utf-8").strip()
    except ConnectionRefusedError:
        return "ERROR: daemon not running (connection refused)"
    except FileNotFoundError:
        return "ERROR: daemon not running (socket not found)"
    except socket.timeout:  # ast-grep-ignore — specific exception, not bare
        return "ERROR: daemon not responding (timeout)"
    except OSError as exc:
        return f"ERROR: {exc}"


# ── CLI ──────────────────────────────────────────────────────────

def _cmd_listen(_args: argparse.Namespace) -> int:
    """Debug: listen for key events and print key codes."""
    from dictapi.keywatcher import find_keyboard
    from evdev import InputDevice, ecodes, categorize
    from evdev.events import KeyEvent
    path = find_keyboard()
    if not path:
        print("No keyboard found")
        return 1
    print(f"Listening on {path} - press a key, Ctrl+C to quit")
    device = InputDevice(path)
    try:
        for event in device.read_loop():
            if event.type == ecodes.EV_KEY and event.value == 1:
                kev = categorize(event)
                assert isinstance(kev, KeyEvent)
                print(f"  {kev.keycode}  (code={event.code})")
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_daemon(_args: argparse.Namespace) -> int:
    """Start the daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config()

    from dictapi.daemon import Daemon

    daemon = Daemon(config)
    daemon.start()
    return 0


def _cmd_toggle(_args: argparse.Namespace) -> int:
    resp = _send_command("toggle")
    print(resp)
    return 0 if resp.startswith("OK") else 1


def _cmd_status(_args: argparse.Namespace) -> int:
    resp = _send_command("status")
    print(resp)
    return 0 if resp.startswith("OK") else 1


def _cmd_quit(_args: argparse.Namespace) -> int:
    resp = _send_command("quit")
    print(resp)
    return 0


def cli() -> None:
    """Main CLI dispatch (entry point from pyproject.toml)."""
    parser = argparse.ArgumentParser(
        prog="dictapi",
        description="Push-to-talk dictation for Linux — STT via OpenRouter + dotool.",
    )
    sub = parser.add_subparsers(dest="command", title="commands")
    sub.required = True

    sub.add_parser("daemon", help="Start the background daemon")
    sub.add_parser("toggle", help="Start or stop recording")
    sub.add_parser("status", help="Query daemon state")
    sub.add_parser("quit", help="Graceful shutdown")
    sub.add_parser("listen", help="Debug: show pressed key codes")

    args = parser.parse_args()

    handlers = {
        "daemon": _cmd_daemon,
        "toggle": _cmd_toggle,
        "status": _cmd_status,
        "quit": _cmd_quit,
        "listen": _cmd_listen,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))
