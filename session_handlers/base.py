"""SessionHandler protocol — common shape for cloud and local handlers."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class SessionHandler(Protocol):
    """Contract every session handler must satisfy.

    The methods mirror the messages the browser can send via the WebSocket
    router in ``app.py``. Handlers are responsible for emitting the
    browser-facing event protocol (``session_started``, ``transcript_delta``,
    ``audio_data``, etc.) via the ``send_message`` callback they were
    constructed with.
    """

    client_id: str
    is_running: bool

    async def start(self) -> None:
        """Open the session and run the event loop until ``stop()`` is called."""
        ...

    async def stop(self) -> None:
        """Signal the session to tear down. Idempotent."""
        ...

    async def send_audio(self, audio_base64: str) -> None:
        """Forward a chunk of mic audio (base64-encoded PCM16 @ 24 kHz) from the browser."""
        ...

    async def send_text_message(self, text: str) -> None:
        """Inject a typed user message into the session."""
        ...

    async def send_avatar_sdp_offer(self, client_sdp: str) -> None:
        """Forward the browser's WebRTC offer (avatar mode only). Local handler may no-op."""
        ...

    async def interrupt(self) -> None:
        """Cancel the in-flight assistant response (barge-in)."""
        ...
