"""Speech-to-text clients and provider factory.

Two providers are supported, both exposing the same one-shot
``transcribe(wav_bytes) -> str`` interface:

* **OpenRouter** (:class:`Transcriber`) — a single synchronous POST. The
  model is configurable by slug; the endpoint accepts any compatible model.
* **Gladia** (:class:`~dictapi.gladia.GladiaTranscriber`) — an asynchronous
  pre-recorded job (upload → create → poll) hidden behind the same call.

:func:`make_transcriber` selects the client from ``[api].provider``.
"""

import base64
import logging
from typing import Optional

import requests

from dictapi.gladia import GladiaTranscriber

log = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/audio/transcriptions"


class Transcriber:
    """Send a complete WAV recording to OpenRouter and return its text.

    This is a one-shot transcription request, not a realtime audio stream.
    """

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


def make_transcriber(cfg: dict) -> "Transcriber | GladiaTranscriber":
    """Build the transcriber selected by ``[api].provider``.

    ``provider = "gladia"`` returns a :class:`GladiaTranscriber`; anything
    else (default ``"openrouter"``) returns the OpenRouter :class:`Transcriber`.
    Both expose the same ``transcribe(wav_bytes) -> str`` interface, so the
    daemon never needs to know which one is active.

    Raises ``RuntimeError`` if the selected provider has no API key.
    """
    api = cfg["api"]
    provider = (api.get("provider") or "openrouter").strip().lower()

    if provider == "gladia":
        api_key = api.get("gladia_api_key")
        if not api_key:
            raise RuntimeError(
                "Missing Gladia API key. "
                "Set GLADIA_API_KEY env var or api.gladia_api_key in config.toml"
            )
        return GladiaTranscriber(
            api_key=api_key,
            model=api.get("gladia_model") or "solaria-1",
            language=api["language"],
            timeout=api["timeout"],
        )

    # Default: OpenRouter
    api_key = api.get("api_key")
    if not api_key:
        raise RuntimeError(
            "Missing OpenRouter API key. "
            "Set OPENROUTER_API_KEY env var or api.api_key in config.toml"
        )
    return Transcriber(
        api_key=api_key,
        model=api["model"],
        language=api["language"],
        timeout=api["timeout"],
    )
