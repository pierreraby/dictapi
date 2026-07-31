"""Gladia speech-to-text API client (v2 pre-recorded, asynchronous).

Gladia's v2 pre-recorded API is job-based: you upload the audio, create a
transcription job, then poll until it completes. There is no synchronous
endpoint in v2. This client hides that async flow behind the same one-shot
``transcribe(wav_bytes) -> str`` interface used by the OpenRouter client, so
the daemon does not need to know which provider is active.

Docs: https://docs.gladia.io/api-reference/v2/pre-recorded/init
"""

import logging
import time

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.gladia.io"
UPLOAD_URL = f"{BASE_URL}/v2/upload"
PRERECORDED_URL = f"{BASE_URL}/v2/pre-recorded"

# Polling cadence while waiting for the job to finish. We start fast for
# short dictation clips and back off gently to stay polite to the API.
_POLL_START = 1.0
_POLL_MAX = 3.0


class GladiaTranscriber:
    """Send a complete WAV recording to Gladia and return its text.

    Internally this is asynchronous (upload → create job → poll), but the
    call blocks until the transcript is available, mirroring the one-shot
    behaviour of the OpenRouter transcriber.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "solaria-1",
        language: str = "fr",
        timeout: int = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"x-gladia-key": self._api_key}

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV audio and return the text.

        Raises ``RuntimeError`` on API errors or if the job does not
        complete within the configured timeout.
        """
        if not wav_bytes:
            raise RuntimeError("No audio data to transcribe")

        # Overall budget for the whole async cycle (upload + create + poll).
        deadline = time.monotonic() + self._timeout

        audio_url = self._upload(wav_bytes)
        job_id = self._create_job(audio_url)
        return self._poll(job_id, deadline)

    # ── steps ─────────────────────────────────────────────────

    def _upload(self, wav_bytes: bytes) -> str:
        """Upload the WAV file and return Gladia's hosted ``audio_url``."""
        log.info("Uploading %d bytes to Gladia…", len(wav_bytes))
        resp = requests.post(
            UPLOAD_URL,
            headers=self._headers(),
            files={"audio": ("recording.wav", wav_bytes, "audio/wav")},
            timeout=self._timeout,
        )
        if not resp.ok:
            self._raise("upload", resp)

        audio_url = resp.json().get("audio_url")
        if not audio_url:
            raise RuntimeError("Gladia upload did not return an audio_url")
        return audio_url

    def _create_job(self, audio_url: str) -> str:
        """Create the transcription job and return its id."""
        payload = {
            "audio_url": audio_url,
            "model": self._model,
            "language_config": {"languages": [self._language]},
        }
        resp = requests.post(
            PRERECORDED_URL,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
            timeout=self._timeout,
        )
        if not resp.ok:
            self._raise("create job", resp)

        job_id = resp.json().get("id")
        if not job_id:
            raise RuntimeError("Gladia did not return a transcription job id")
        log.info("Gladia job created: %s (model=%s)", job_id, self._model)
        return job_id

    def _poll(self, job_id: str, deadline: float) -> str:
        """Poll the job until done and return the full transcript."""
        url = f"{PRERECORDED_URL}/{job_id}"
        interval = _POLL_START

        while True:
            resp = requests.get(url, headers=self._headers(), timeout=self._timeout)
            if not resp.ok:
                self._raise("poll", resp)

            data = resp.json()
            status = data.get("status")

            if status == "done":
                text = (
                    data.get("result", {})
                    .get("transcription", {})
                    .get("full_transcript", "")
                    or ""
                )
                text = text.strip()
                log.info("Transcription (%d chars): %s", len(text), text[:100])
                return text

            if status == "error":
                raise RuntimeError(
                    f"Gladia transcription failed: {data.get('error_code')}"
                )

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Gladia transcription timed out after {self._timeout}s "
                    f"(last status: {status})"
                )

            log.debug("Gladia status: %s — polling again in %.1fs", status, interval)
            time.sleep(interval)
            interval = min(interval + 0.5, _POLL_MAX)

    @staticmethod
    def _raise(step: str, resp: requests.Response) -> None:
        detail = resp.text[:500]
        log.error("Gladia %s error %s: %s", step, resp.status_code, detail)
        raise RuntimeError(
            f"Gladia {step} error {resp.status_code}: {resp.reason}"
        )
