"""Configuration loader — merges defaults, config file, and environment."""

import os
from pathlib import Path
from typing import Any

import tomllib

DEFAULT: dict[str, Any] = {
    "api": {
        "model": "mistralai/voxtral-mini-transcribe",
        "language": "fr",
        "timeout": 30,
        "api_key": None,  # prefer env OPENROUTER_API_KEY
    },
    "audio": {
        "samplerate": 16000,
        "channels": 1,
        "device": None,
    },
    "dotool": {
        "binary": "dotool",
        "typedelay": 0,
        "xkb_layout": None,
        "xkb_variant": None,
    },
    "daemon": {
        "socket_path": "~/.local/share/dictapi/dictapi.sock",
    },
    "keys": {
        "provider": "evdev",
        "key": "KEY_RIGHTALT",
        "tap_window_ms": 400,
        "device": None,
    },
}


def _merge(base: dict, overlay: dict) -> dict:
    """Deep-merge overlay into base (mutates base)."""
    for key, val in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _merge(base[key], val)
        else:
            base[key] = val
    return base


def load(path: str | Path | None = None) -> dict[str, Any]:
    """Load configuration.

    Resolution order (low → high priority):
      1. Hard-coded defaults
      2. ``~/.config/dictapi/config.toml`` (if exists)
      3. *path* argument (if given and exists)
      4. Environment ``OPENROUTER_API_KEY`` (overrides api.api_key)

    Returns a flat-enough dict, nested under ``api`` / ``audio`` / etc.
    """
    cfg = DEFAULT.copy()
    cfg["api"] = DEFAULT["api"].copy()
    cfg["audio"] = DEFAULT["audio"].copy()
    cfg["dotool"] = DEFAULT["dotool"].copy()
    cfg["daemon"] = DEFAULT["daemon"].copy()
    cfg["keys"] = DEFAULT["keys"].copy()

    # User config file (~/.config/dictapi/config.toml)
    user_path = Path.home() / ".config" / "dictapi" / "config.toml"
    if user_path.exists():
        try:
            with open(user_path, "rb") as fh:
                _merge(cfg, tomllib.load(fh))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load %s: %s", user_path, exc
            )

    # Local project config (./config.toml) — overrides user config
    local_path = Path("config.toml")
    if local_path.exists():
        try:
            with open(local_path, "rb") as fh:
                _merge(cfg, tomllib.load(fh))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to load %s: %s", local_path, exc
            )

    # Explicit override
    if path:
        p = Path(path).expanduser()
        if p.exists():
            try:
                with open(p, "rb") as fh:
                    _merge(cfg, tomllib.load(fh))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to load %s: %s", p, exc
                )

    # Environment override
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        cfg["api"]["api_key"] = env_key

    return cfg
