"""OpenRouter transcription API client.

Mirrors the existing TS proxy (index.ts) behaviour.
"""

import base64
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/audio/transcriptions"


class Transcriber:
    """Send WAV audio to OpenRouter and return transcribed text."""

    def __init__(
        self,
        api_key: str,
        model: str = "mistralai/voxtral-mini-transcribe",
        language: str = "fr",
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._timeout = timeout

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV audio and return the text.

        Raises ``RuntimeError`` on API errors.
        """
        if not wav_bytes:
            raise RuntimeError("No audio data to transcribe")

        b64 = base64.b64encode(wav_bytes).decode("ascii")

        payload = {
            "model": self._model,
            "language": self._language,
            "input_audio": {
                "data": b64,
                "format": "wav",
            },
            "response_format": "json",
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        log.info("Sending %d bytes to %s …", len(wav_bytes), self._model)
        resp = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=self._timeout,
        )

        if not resp.ok:
            detail = resp.text[:500]
            log.error("OpenRouter error %s: %s", resp.status_code, detail)
            raise RuntimeError(
                f"API error {resp.status_code}: {resp.reason}"
            )

        data = resp.json()
        text: Optional[str] = data.get("text")
        if not text:
            log.warning("Empty transcription response: %s", data)
            return ""

        text = text.strip()
        log.info("Transcription (%d chars): %s", len(text), text[:100])
        return text
