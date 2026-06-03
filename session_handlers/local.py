"""Local voice session handler.

Used when the cloud Voice Live endpoint is unreachable. Wires together:

    browser mic (PCM16 @ 24 kHz)
        ↓  energy-based VAD
    Local STT container  ───→  user transcript
        ↓
    Foundry Local LLM    ───→  assistant text
        ↓
    Local NTTS container ───→  PCM16 audio
        ↓
    browser playback (existing audio_data path)

The handler emits the same browser-facing event protocol as
``CloudVoiceLiveSessionHandler`` so the front-end does not branch on mode for
anything other than the avatar / mode-badge visuals.

Hard constraints (documented in IMPLEMENTATION-PLAN.md):
- No avatar. ``send_avatar_sdp_offer`` is a no-op.
- No semantic VAD; no HD/Dragon voices; no tool calling.
- Single-utterance STT via the REST short-audio endpoint (≤20 s default).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from typing import Callable, Optional

from config import settings
from local_clients import LocalLLMClient, LocalSTTClient, LocalTTSClient

logger = logging.getLogger(__name__)

# Browser captures mono PCM16 @ 24 kHz. 100 ms = 4800 bytes.
_BROWSER_SAMPLE_RATE = 24000
_BYTES_PER_SAMPLE = 2
_BYTES_PER_MS = (_BROWSER_SAMPLE_RATE * _BYTES_PER_SAMPLE) // 1000  # = 48


def _rms_pcm16(pcm16: bytes) -> int:
    """Cheap RMS computation over a PCM16 byte buffer (no numpy dep)."""
    if not pcm16:
        return 0
    samples = memoryview(pcm16).cast("h")
    n = len(samples)
    if n == 0:
        return 0
    acc = 0
    for s in samples:
        acc += s * s
    return int((acc // n) ** 0.5)


class LocalSessionHandler:
    """Voice-only session backed by local Speech containers + Foundry Local."""

    def __init__(
        self,
        client_id: str,
        send_message: Callable,
        config: dict,
        *,
        stt_client: Optional[LocalSTTClient] = None,
        tts_client: Optional[LocalTTSClient] = None,
        llm_client: Optional[LocalLLMClient] = None,
        fallback_reason: Optional[str] = None,
    ):
        self.client_id = client_id
        self.send_message = send_message
        self.config = config or {}
        self.fallback_reason = fallback_reason

        # Force voice-only — avatar is not supported in local mode.
        self._avatar_enabled = False

        # Lazily constructed clients (allows DI for tests).
        self.stt = stt_client or LocalSTTClient(
            endpoint=settings.LOCAL_STT_ENDPOINT,
            language=settings.LOCAL_STT_LANGUAGE,
        )
        self.tts = tts_client or LocalTTSClient(
            endpoint=settings.LOCAL_TTS_ENDPOINT,
            voice=settings.LOCAL_TTS_VOICE,
        )
        self.llm = llm_client or LocalLLMClient(
            endpoint=settings.LOCAL_LLM_ENDPOINT,
            model=settings.LOCAL_LLM_MODEL,
            api_key=settings.LOCAL_LLM_API_KEY,
            timeout_s=settings.LOCAL_LLM_TIMEOUT_S,
            max_tokens=settings.LOCAL_LLM_MAX_TOKENS,
        )

        # Conversation history (capped to last N turns to keep prompts small).
        self._max_history_turns = 8
        instructions = (self.config.get("instructions") or settings.SYSTEM_PROMPT).strip()
        self._history: list[dict] = [{"role": "system", "content": instructions}]

        # VAD state
        self._mic_buffer = bytearray()
        self._utterance_buffer = bytearray()
        self._in_speech = False
        self._last_voiced_ts = 0.0
        self._utterance_started_ts = 0.0

        # Concurrency / lifecycle
        self.is_running = False
        self._lock = asyncio.Lock()
        self._speak_task: Optional[asyncio.Task] = None
        self._interrupt_requested = False

    # ── Lifecycle (SessionHandler protocol) ──────────────────────────────

    async def start(self) -> None:
        """Open the local session and emit ``session_started``."""
        self.is_running = True
        session_id = f"local-{uuid.uuid4().hex[:12]}"
        logger.info("Local session %s starting for client %s", session_id, self.client_id)

        await self.send_message({
            "type": "session_started",
            "status": "success",
            "sessionId": session_id,
            "avatarEnabled": False,
            "mode": "local",
        })
        if self.fallback_reason:
            await self.send_message({
                "type": "mode_notice",
                "mode": "local",
                "reason": self.fallback_reason,
            })

        await self._send_proactive_greeting()

        # The handler doesn't own a long-running recv loop the way the cloud
        # handler does — the asyncio event loop is driven by inbound messages
        # from app.py. We keep the coroutine alive until stop() is called so
        # the existing task plumbing works unchanged.
        try:
            while self.is_running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("Local session %s cancelled", session_id)
            raise
        finally:
            self.is_running = False
            await self._aclose_clients()

    async def stop(self) -> None:
        self.is_running = False
        if self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()
        await self._aclose_clients()

    # ── Inbound from browser ─────────────────────────────────────────────

    async def send_audio(self, audio_base64: str) -> None:
        if not self.is_running or not audio_base64:
            return
        try:
            chunk = base64.b64decode(audio_base64)
        except (ValueError, TypeError):
            logger.warning("Bad audio chunk from client %s", self.client_id)
            return

        # Feed VAD; emit speech_started / speech_stopped to drive existing UI.
        triggered_utterance = await self._consume_audio(chunk)
        if triggered_utterance is not None:
            asyncio.create_task(self._handle_utterance(triggered_utterance))

    async def send_text_message(self, text: str) -> None:
        text = (text or "").strip()
        if not text or not self.is_running:
            return
        # Mirror what cloud does: surface user transcript, then respond.
        await self.send_message({
            "type": "transcript_done",
            "role": "user",
            "transcript": text,
        })
        asyncio.create_task(self._respond_to_user(text))

    async def send_avatar_sdp_offer(self, client_sdp: str) -> None:  # noqa: ARG002
        # Local mode never opens a WebRTC peer connection.
        logger.debug("Ignoring avatar SDP offer in local mode")

    async def interrupt(self) -> None:
        self._interrupt_requested = True
        if self._speak_task and not self._speak_task.done():
            self._speak_task.cancel()
        await self.send_message({"type": "stop_playback", "reason": "manual_interrupt"})

    # ── VAD ──────────────────────────────────────────────────────────────

    async def _consume_audio(self, chunk: bytes) -> Optional[bytes]:
        """Feed a 24 kHz PCM16 chunk to the energy VAD.

        Returns the captured utterance bytes when end-of-speech is detected,
        otherwise None.
        """
        if not chunk:
            return None

        # Operate in 20 ms frames for cheap RMS scoring.
        frame_bytes = 20 * _BYTES_PER_MS
        self._mic_buffer.extend(chunk)

        utterance_to_process: Optional[bytes] = None
        now = time.time()

        while len(self._mic_buffer) >= frame_bytes:
            frame = bytes(self._mic_buffer[:frame_bytes])
            del self._mic_buffer[:frame_bytes]
            rms = _rms_pcm16(frame)
            voiced = rms >= settings.LOCAL_VAD_RMS_THRESHOLD

            if voiced:
                if not self._in_speech:
                    self._in_speech = True
                    self._utterance_started_ts = now
                    self._utterance_buffer.clear()
                    await self.send_message({"type": "speech_started", "itemId": ""})
                    # Barge-in semantics — kill any speaking task.
                    if self._speak_task and not self._speak_task.done():
                        self._interrupt_requested = True
                        self._speak_task.cancel()
                        await self.send_message({"type": "stop_playback", "reason": "barge_in"})
                self._last_voiced_ts = now
                self._utterance_buffer.extend(frame)
            elif self._in_speech:
                self._utterance_buffer.extend(frame)
                silence_ms = (now - self._last_voiced_ts) * 1000
                speech_ms = (now - self._utterance_started_ts) * 1000
                hit_max = speech_ms >= settings.LOCAL_VAD_MAX_UTTERANCE_MS
                hit_silence = silence_ms >= settings.LOCAL_VAD_SILENCE_MS
                if (hit_silence and speech_ms >= settings.LOCAL_VAD_MIN_SPEECH_MS) or hit_max:
                    utterance_to_process = bytes(self._utterance_buffer)
                    self._utterance_buffer.clear()
                    self._in_speech = False
                    await self.send_message({"type": "speech_stopped"})
                    # Only one utterance per chunk — leftover audio stays in
                    # _mic_buffer for the next call.
                    break

        return utterance_to_process

    # ── Pipeline (STT → LLM → TTS) ───────────────────────────────────────

    async def _handle_utterance(self, pcm16: bytes) -> None:
        """Transcribe an utterance and respond."""
        try:
            transcript = await self.stt.recognize(pcm16)
        except Exception as exc:
            await self._emit_error(f"local-stt failed: {exc}")
            return

        transcript = (transcript or "").strip()
        if not transcript:
            logger.info("Local STT produced empty transcript; ignoring utterance")
            return

        await self.send_message({
            "type": "transcript_done",
            "role": "user",
            "transcript": transcript,
        })
        await self._respond_to_user(transcript)

    async def _respond_to_user(self, user_text: str) -> None:
        """Run the LLM, then stream TTS audio back to the browser."""
        async with self._lock:
            self._history.append({"role": "user", "content": user_text})
            self._history = self._truncate_history(self._history)

            await self.send_message({"type": "response_created", "responseId": uuid.uuid4().hex})
            try:
                reply = await self.llm.chat(self._history)
            except Exception as exc:
                await self._emit_error(f"local-llm failed: {exc}")
                await self.send_message({"type": "response_done"})
                return

            reply = (reply or "").strip()
            if not reply:
                reply = "I'm sorry, I didn't catch that."

            self._history.append({"role": "assistant", "content": reply})

            # Mimic the cloud transcript stream by surfacing the full assistant
            # text as a single delta + done.
            await self.send_message({"type": "transcript_delta", "role": "assistant", "delta": reply})
            await self.send_message({"type": "transcript_done", "role": "assistant", "transcript": reply})

            self._interrupt_requested = False
            self._speak_task = asyncio.create_task(self._speak(reply))
            try:
                await self._speak_task
            except asyncio.CancelledError:
                logger.info("TTS playback cancelled (barge-in or stop)")
            finally:
                self._speak_task = None
                await self.send_message({"type": "response_done"})

    async def _speak(self, text: str) -> None:
        """Stream synthesized audio to the browser."""
        try:
            async for chunk in self.tts.synthesize(text):
                if self._interrupt_requested or not self.is_running:
                    break
                await self.send_message({
                    "type": "audio_data",
                    "data": base64.b64encode(chunk).decode(),
                    "format": "pcm16",
                    "sampleRate": _BROWSER_SAMPLE_RATE,
                })
            await self.send_message({"type": "audio_done"})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._emit_error(f"local-tts failed: {exc}")

    async def _send_proactive_greeting(self) -> None:
        try:
            greeting = await self.llm.chat(self._history + [
                {"role": "user", "content": "Greet me briefly in one short sentence."}
            ])
            greeting = (greeting or "").strip() or "Hi! I'm running in local fallback mode."
            self._history.append({"role": "assistant", "content": greeting})
        except Exception as exc:
            logger.warning("Local greeting LLM call failed: %s — using canned greeting", exc)
            greeting = "Hi! I'm running in local fallback mode. How can I help?"
            self._history.append({"role": "assistant", "content": greeting})

        await self.send_message({"type": "response_created", "responseId": uuid.uuid4().hex})
        await self.send_message({"type": "transcript_delta", "role": "assistant", "delta": greeting})
        await self.send_message({"type": "transcript_done", "role": "assistant", "transcript": greeting})
        self._speak_task = asyncio.create_task(self._speak(greeting))
        try:
            await self._speak_task
        except asyncio.CancelledError:
            pass
        finally:
            self._speak_task = None
        await self.send_message({"type": "response_done"})

    # ── Helpers ──────────────────────────────────────────────────────────

    def _truncate_history(self, history: list[dict]) -> list[dict]:
        """Keep the system prompt + last N user/assistant turns."""
        if not history:
            return history
        sys_msgs = [m for m in history if m.get("role") == "system"]
        turns = [m for m in history if m.get("role") != "system"]
        keep = self._max_history_turns * 2  # user + assistant
        if len(turns) > keep:
            turns = turns[-keep:]
        return sys_msgs + turns

    async def _emit_error(self, message: str) -> None:
        logger.error("Local session error: %s", message)
        await self.send_message({"type": "error", "error": message})

    async def _aclose_clients(self) -> None:
        for c in (self.stt, self.tts, self.llm):
            try:
                await c.aclose()
            except Exception:  # pragma: no cover - defensive cleanup
                pass
