"""Audio recording via sounddevice (PortAudio)."""

import io
import wave
from typing import Optional

import sounddevice as sd
import numpy as np


class Recorder:
    """Records audio from the default microphone to a WAV buffer.

    Usage::

        rec = Recorder(samplerate=16000, channels=1)
        rec.start()
        # … hold key …
        wav_bytes = rec.stop()   # returns bytes (WAV)
    """

    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        device: Optional[int] = None,
    ) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self.device = device
        self._frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None

    def start(self) -> None:
        """Open the input stream and begin buffering."""
        if self._stream is not None:
            return  # already recording

        self._frames = []
        stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            device=self.device,
            callback=self._callback,
        )
        stream.start()
        self._stream = stream

    def stop(self) -> bytes:
        """Stop recording and return the accumulated audio as WAV bytes."""
        if self._stream is None:
            return b""

        self._stream.stop()
        self._stream.close()
        self._stream = None

        if not self._frames:
            return b""

        audio = np.concatenate(self._frames, axis=0)

        # Normalize float32 → int16 (WAV standard)
        audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.samplerate)
            wf.writeframes(audio_int16.tobytes())

        return buf.getvalue()

    @property
    def is_recording(self) -> bool:
        return self._stream is not None and self._stream.active

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags,
    ) -> None:
        """Called by PortAudio for each buffer chunk."""
        if status:
            # Log non-critical underflow/overflow but keep going
            import logging

            logging.getLogger(__name__).warning("Audio callback status: %s", status)
        self._frames.append(indata.copy())
