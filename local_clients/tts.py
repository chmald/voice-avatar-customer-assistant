"""Local TTS client — Azure Speech `neural-text-to-speech` Docker container.

The container exposes the same REST endpoint as cloud Speech TTS:

    POST {endpoint}/cognitiveservices/v1
    Content-Type: application/ssml+xml
    X-Microsoft-OutputFormat: raw-24khz-16bit-mono-pcm
    body: <SSML document>

We request raw PCM directly (no WAV header) so the bytes can be base64-encoded
and shipped to the browser's existing playback path unchanged.

The container only ships standard neural voices — HD/Dragon voices are
cloud-only. The container tag determines which voice is loaded
(e.g. ``3.11.0-amd64-en-us-jennyneural``).
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional
from xml.sax.saxutils import escape as xml_escape

import httpx

logger = logging.getLogger(__name__)

_OUTPUT_FORMAT = "raw-24khz-16bit-mono-pcm"
_USER_AGENT = "ai-voice-live-avatar-hybrid/1.0"


def _build_ssml(text: str, voice: str, locale: str) -> str:
    """Build a minimal SSML doc for the local NTTS container."""
    return (
        f'<speak version="1.0" xml:lang="{locale}" '
        f'xmlns="http://www.w3.org/2001/10/synthesis">'
        f'<voice name="{voice}">{xml_escape(text)}</voice>'
        f'</speak>'
    )


class LocalTTSClient:
    """Synthesize text into raw 24 kHz PCM16 chunks via the on-prem NTTS container."""

    # Stream chunk size used to break the response into browser-friendly frames
    # (~100 ms @ 24 kHz mono PCM16 = 4800 bytes).
    CHUNK_SIZE = 4800

    def __init__(
        self,
        endpoint: str,
        voice: str = "en-US-JennyNeural",
        timeout_s: float = 30.0,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.voice = voice
        # Derive locale from voice name (e.g. en-US-JennyNeural -> en-US).
        parts = voice.split("-")
        self.locale = "-".join(parts[:2]) if len(parts) >= 2 else "en-US"
        self.timeout_s = timeout_s
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Yield raw PCM16 mono @ 24 kHz chunks for ``text``.

        Use ``async for chunk in client.synthesize(...)`` to stream the audio
        back to the browser.
        """
        if not text.strip():
            return

        url = f"{self.endpoint}/cognitiveservices/v1"
        headers = {
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
            "User-Agent": _USER_AGENT,
        }
        body = _build_ssml(text, self.voice, self.locale).encode("utf-8")

        client = await self._ensure_client()
        try:
            async with client.stream("POST", url, content=body, headers=headers) as resp:
                resp.raise_for_status()
                buffer = bytearray()
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    while len(buffer) >= self.CHUNK_SIZE:
                        out = bytes(buffer[: self.CHUNK_SIZE])
                        del buffer[: self.CHUNK_SIZE]
                        yield out
                if buffer:
                    yield bytes(buffer)
        except httpx.HTTPError as exc:
            logger.error("NTTS container request failed: %s", exc)
            raise

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
