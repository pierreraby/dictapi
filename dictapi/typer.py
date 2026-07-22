"""Type text via dotool — works on Wayland, X11, and any Linux desktop."""

import subprocess
import shutil
import os
from typing import Optional


class DotoolTyper:
    """Thin wrapper around ``dotool`` for simulating keyboard input.

    Uses ``DOTOOL_XKB_LAYOUT`` and ``DOTOOL_XKB_VARIANT`` env vars
    to ensure correct keyboard layout (AZERTY, QWERTY, etc.).
    """

    def __init__(
        self,
        binary: str = "dotool",
        typedelay: int = 0,
        xkb_layout: str | None = None,
        xkb_variant: str | None = None,
    ) -> None:
        self._binary = shutil.which(binary) or binary
        self._typedelay = typedelay

        # Build the environment for dotool subprocess (layout + variant)
        self._env = os.environ.copy()
        if xkb_layout:
            self._env["DOTOOL_XKB_LAYOUT"] = xkb_layout
        if xkb_variant:
            self._env["DOTOOL_XKB_VARIANT"] = xkb_variant

    @property
    def available(self) -> bool:
        return shutil.which(self._binary) is not None

    def type(self, text: str) -> None:
        """Type *text* using dotool.

        Handles multi-line text by splitting into per-line ``type``
        commands separated by ``key Return``, preventing newlines from
        being interpreted as dotool commands.
        """
        if not self.available:
            raise RuntimeError(
                f"dotool not found ('{self._binary}'). "
                "Install it from https://git.sr.ht/~geb/dotool"
            )

        lines = []
        if self._typedelay:
            lines.append(f"typedelay {self._typedelay}")

        paragraphs = text.split("\n")
        for i, para in enumerate(paragraphs):
            lines.append(f"type {para}")
            if i < len(paragraphs) - 1:
                lines.append("key Return")

        payload = "\n".join(lines)

        subprocess.run(
            [self._binary],
            input=payload,
            text=True,
            env=self._env,
            check=True,
        )

    def key(self, chord: str) -> None:
        """Send a key chord, e.g. ``ctrl+shift+v``."""
        subprocess.run(
            [self._binary],
            input=f"key {chord}\n",
            text=True,
            env=self._env,
            check=True,
        )
