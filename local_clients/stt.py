"""Local STT client — Azure Speech `speech-to-text` Docker container.

The container exposes the same REST surface as the cloud Speech endpoint.
For MVP we use the short-audio recognition endpoint:

    POST {endpoint}/speech/recognition/conversation/cognitiveservices/v1
        ?language=<locale>&format=detailed
    Content-Type: audio/wav; codecs=audio/pcm; samplerate=16000
    body: <RIFF/WAV bytes, single utterance, ≤60 s>

Returns JSON like:
    {"RecognitionStatus":"Success","DisplayText":"hello world", ...}

Streaming via the Speech SDK is out of scope for MVP (see IMPLEMENTATION-PLAN.md).
"""

from __future__ import annotations

import io
import logging
import struct
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


# The Speech REST endpoint accepts 16 kHz mono PCM most reliably; the browser
# captures at 24 kHz. We downsample on the fly with a simple stride before
# wrapping in WAV.
_BROWSER_SAMPLE_RATE = 24000
_STT_SAMPLE_RATE = 16000
_BYTES_PER_SAMPLE = 2


def _downsample_24k_to_16k(pcm16: bytes) -> bytes:
    """Cheap 24 kHz → 16 kHz mono PCM16 downsampler (averaging 3 → 2 samples)."""
    if not pcm16:
        return b""
    # Interpret as int16
    samples = memoryview(pcm16).cast("h")  # signed 16-bit
    n = len(samples)
    out = bytearray()
    # 3:2 ratio. Take frames of 3 samples and produce 2.
    i = 0
    while i + 3 <= n:
        a, b, c = samples[i], samples[i + 1], samples[i + 2]
        s1 = (a + b) // 2
        s2 = (b + c) // 2
        out.extend(struct.pack("<hh", s1, s2))
        i += 3
    # Tail: drop the trailing partial frame (≤ 2 samples). Inaudible.
    return bytes(out)


def _wrap_pcm_as_wav(pcm16: bytes, sample_rate: int) -> bytes:
    """Wrap raw PCM16 mono bytes in a minimal RIFF/WAV container."""
    byte_rate = sample_rate * _BYTES_PER_SAMPLE
    block_align = _BYTES_PER_SAMPLE
    bits_per_sample = 16
    data_size = len(pcm16)
    header = io.BytesIO()
    header.write(b"RIFF")
    header.write(struct.pack("<I", 36 + data_size))
    header.write(b"WAVE")
    header.write(b"fmt ")
    header.write(struct.pack("<I", 16))                    # subchunk1 size (PCM)
    header.write(struct.pack("<H", 1))                     # audio format = PCM
    header.write(struct.pack("<H", 1))                     # channels = mono
    header.write(struct.pack("<I", sample_rate))
    header.write(struct.pack("<I", byte_rate))
    header.write(struct.pack("<H", block_align))
    header.write(struct.pack("<H", bits_per_sample))
    header.write(b"data")
    header.write(struct.pack("<I", data_size))
    return header.getvalue() + pcm16


class LocalSTTClient:
    """Thin wrapper around the Azure `speech-to-text` container REST endpoint."""

    def __init__(
        self,
        endpoint: str,
        language: str = "en-US",
        timeout_s: float = 15.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.language = language
        self.timeout_s = timeout_s
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def recognize(self, pcm16_browser: bytes) -> str:
        """Transcribe a single utterance.

        Args:
            pcm16_browser: raw PCM16 mono audio captured by the browser at 24 kHz.

        Returns:
            The recognized text, or "" if nothing was recognized.
        """
        if not pcm16_browser:
            return ""

        pcm16_16k = _downsample_24k_to_16k(pcm16_browser)
        wav = _wrap_pcm_as_wav(pcm16_16k, _STT_SAMPLE_RATE)

        url = (
            f"{self.endpoint}/speech/recognition/conversation/cognitiveservices/v1"
            f"?language={self.language}&format=simple"
        )
        headers = {
            "Content-Type": f"audio/wav; codecs=audio/pcm; samplerate={_STT_SAMPLE_RATE}",
            "Accept": "application/json",
        }

        client = await self._ensure_client()
        try:
            resp = await client.post(url, content=wav, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            logger.error("STT container request failed: %s", exc)
            raise

        status = body.get("RecognitionStatus", "")
        if status != "Success":
            logger.info("STT non-success status=%s body=%s", status, body)
            return ""
        return body.get("DisplayText", "") or ""

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
