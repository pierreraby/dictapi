"""Double-tap detection via evdev for dictapi."""

import logging
import threading
import time

log = logging.getLogger(__name__)


def find_keyboard() -> str | None:
    """Auto-detect the first keyboard device."""
    from evdev import InputDevice, ecodes, list_devices
    for path in list_devices():
        try:
            d = InputDevice(path)
            caps = d.capabilities()
            if ecodes.EV_KEY in caps and ecodes.KEY_A in caps[ecodes.EV_KEY]:
                return path
        except Exception:
            pass
    return None


class KeyWatcher:
    """Listens on a keyboard device for a double-tap to invoke a callback."""

    def __init__(
        self,
        device_path: str | None = None,
        key_name: str = "KEY_RIGHTALT",
        tap_window_ms: int = 400,
        on_toggle=None,
    ):
        self._device_path = device_path
        self._key_name = key_name
        self._tap_window = tap_window_ms / 1000.0
        self._on_toggle = on_toggle
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_press: float = 0

    def start(self) -> None:
        path = self._device_path or find_keyboard()
        if not path:
            log.warning("No keyboard device found - double-tap disabled")
            return
        try:
            from evdev import InputDevice, ecodes
            self._key_code = getattr(ecodes, self._key_name, None)
            if self._key_code is None:
                log.warning("Unknown key %s - double-tap disabled", self._key_name)
                return
            self._device = InputDevice(path)
        except Exception as exc:
            log.warning("Cannot open keyboard %s: %s", path, exc)
            return
        log.info("Double-tap on %s (device: %s)", self._key_name, path)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if hasattr(self, '_device'):
            try:
                self._device.close()
            except Exception:
                pass

    def _run(self) -> None:
        from evdev import ecodes
        for event in self._device.read_loop():
            if not self._running:
                break
            if event.type != ecodes.EV_KEY or event.code != self._key_code:
                continue
            if event.value == 2:
                continue
            if event.value == 1:
                now = time.monotonic()
                if now - self._last_press < self._tap_window:
                    log.info("Double-tap detected")
                    if self._on_toggle:
                        self._on_toggle()
                    self._last_press = 0
                else:
                    self._last_press = now
