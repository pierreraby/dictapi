"""System tray icon for dictapi using pystray.

Draws a simple microphone-shaped icon on a coloured circle:
  - green  = idle (ready)
  - red    = recording
  - orange = transcribing
  - blue   = typing
  - grey   = error

Thread-safe by design: set_state() may be called from the daemon thread.
"""

import logging
import threading
from typing import Callable

from PIL import Image, ImageDraw

log = logging.getLogger(__name__)

# ── icon geometry constants ──────────────────────────────────────
_SIZE = 64
_MARGIN = 2  # px around the coloured circle

# ── state → (colour tuple, tooltip) ──────────────────────────────
_STATES: dict[str, tuple[tuple[int, int, int], str]] = {
    "idle":         ((46, 160, 67),   "Dictapi - Ready"),
    "recording":    ((220, 50, 47),   "Dictapi - Recording..."),
    "transcribing": ((255, 153, 0),   "Dictapi - Transcribing..."),
    "typing":       ((30, 144, 255),  "Dictapi - Typing..."),
    "error":        ((128, 128, 128), "Dictapi - Error"),
}


def _generate_icon(color: tuple[int, int, int]) -> Image.Image:
    """Return a 64×64 RGBA image: coloured circle + white mic silhouette."""

    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))  # type: ignore[arg-type]
    d = ImageDraw.Draw(img)

    # background circle
    r = _SIZE - 2 * _MARGIN
    d.ellipse([_MARGIN, _MARGIN, _MARGIN + r, _MARGIN + r], fill=color)

    white = (255, 255, 255, 255)

    # microphone capsule body — rounded rectangle
    d.rounded_rectangle([22, 14, 42, 38], radius=8, fill=white)

    # microphone head — ellipse peeking out the top
    d.ellipse([20, 6, 44, 22], fill=white)

    # stand — thin vertical bar
    d.rectangle([28, 36, 36, 50], fill=white)

    # stand base — horizontal arc
    d.arc([22, 40, 42, 58], start=210, end=330, fill=white, width=4)

    return img


# ── TrayController ───────────────────────────────────────────────


class TrayController:
    """System-tray icon driven by pystray.

    Callbacks *on_toggle* and *on_quit* are called from the tray thread
    when the user clicks the corresponding menu item.
    """

    def __init__(
        self,
        on_toggle: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_toggle = on_toggle
        self._on_quit = on_quit
        self._lock = threading.Lock()
        self._state = "idle"
        self._icons: dict[str, Image.Image] = {}
        self._icon: object = None  # pystray.Icon — lazy import

    # ── internal helpers ──────────────────────────────────────

    def _lazy_setup(self) -> None:
        """Build the pystray Icon on first use (imports pystray late)."""
        import pystray  # type: ignore[import-untyped]  # noqa: F811 — late import

        for state_key, (color, _tooltip) in _STATES.items():
            self._icons[state_key] = _generate_icon(color)

        self._icon = pystray.Icon(
            "dictapi-tray",
            self._icons["idle"],
            _STATES["idle"][1],
            menu=pystray.Menu(
                pystray.MenuItem(
                    "Démarrer / Arrêter la dictée",
                    self._on_toggle_cb,
                    default=True,
                ),
                pystray.MenuItem(
                    "Quitter",
                    self._on_quit_cb,
                ),
            ),
        )

    def _on_toggle_cb(self, icon, item) -> None:
        """Menu callback → forward to on_toggle."""
        self._on_toggle()

    def _on_quit_cb(self, icon, item) -> None:
        """Menu callback → forward to on_quit."""
        self._on_quit()

    # ── public API ────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Update icon colour and tooltip. Safe to call from any thread."""
        if state not in self._icons:
            state = "idle"
        with self._lock:
            self._state = state
        if self._icon is not None:
            self._icon.icon = self._icons[state]  # type: ignore[attr-defined]
            self._icon.title = _STATES[state][1]  # type: ignore[attr-defined]

    def run(self) -> None:
        """Enter the tray event-loop (blocking — run in a daemon thread)."""
        if self._icon is None:
            self._lazy_setup()
        if self._icon is not None:
            self._icon.run()  # type: ignore[attr-defined]

    def stop(self) -> None:
        """Request the event-loop to exit. Safe from any thread."""
        if self._icon is not None:
            self._icon.stop()  # type: ignore[attr-defined]
