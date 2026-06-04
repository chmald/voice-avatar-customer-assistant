"""Azure AI Voice Live API with Avatar — FastAPI backend.

Bridges browser WebSocket ↔ a session handler. Two handlers exist:

  - ``CloudVoiceLiveSessionHandler``  (default) — Azure Voice Live API with
    optional WebRTC avatar.
  - ``LocalSessionHandler``           — fully on-prem STT → LLM → TTS pipeline
    used as a fallback when the cloud endpoint is unreachable.

Authentication: DefaultAzureCredential (Azure CLI / managed identity).
Required roles: Cognitive Services User + Azure AI User.
"""

import asyncio
import json
import logging
import time
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from azure.identity.aio import DefaultAzureCredential

from session_handlers import (
    CloudVoiceLiveSessionHandler,
    LocalSessionHandler,
    SessionHandler,
)
from connectivity import ConnectivitySupervisor
from config import settings

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-24s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Active session tracking ──────────────────────────────────────────────────
_sessions: Dict[str, SessionHandler] = {}
_tasks: Dict[str, asyncio.Task] = {}

# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="Azure AI Voice Live API with Avatar")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Connectivity supervisor (created at startup if AZURE_AI_ENDPOINT is set).
_supervisor: ConnectivitySupervisor | None = None


@app.on_event("startup")
async def _startup() -> None:
    global _supervisor
    if settings.AZURE_AI_ENDPOINT and settings.ENABLE_LOCAL_FALLBACK:
        _supervisor = ConnectivitySupervisor(
            endpoint=settings.AZURE_AI_ENDPOINT,
            interval_s=settings.FAILOVER_PROBE_INTERVAL_S,
            timeout_s=settings.FAILOVER_PROBE_TIMEOUT_S,
            failure_threshold=settings.FAILOVER_FAILURE_THRESHOLD,
        )
        await _supervisor.start()
        logger.info("Connectivity supervisor started for %s", settings.AZURE_AI_ENDPOINT)
    else:
        logger.info(
            "Local fallback disabled (ENABLE_LOCAL_FALLBACK=%s, endpoint=%s)",
            settings.ENABLE_LOCAL_FALLBACK,
            bool(settings.AZURE_AI_ENDPOINT),
        )


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _supervisor is not None:
        await _supervisor.stop()


@app.middleware("http")
async def no_cache_static(request: StarletteRequest, call_next):
    """Prevent browser caching of static assets (development convenience)."""
    response: StarletteResponse = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ── HTML page ────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "characters": settings.AVATAR_CHARACTERS,
            "photo_avatars": settings.PHOTO_AVATARS,
            "voices": settings.VOICES,
            "default_video_character": settings.DEFAULT_VIDEO_CHARACTER,
            "default_photo_character": settings.DEFAULT_PHOTO_CHARACTER,
            "default_voice": settings.DEFAULT_VOICE,
            "system_prompt": settings.SYSTEM_PROMPT,
            "cache_bust": str(int(time.time())),
        },
    )


# ── WebSocket endpoint ───────────────────────────────────────────────────────
#
# Custom message protocol between browser and backend:
#
#   Browser → Backend                Backend → Browser
#   ───────────────────              ──────────────────────
#   start_session                    session_started
#   stop_session                     ice_servers
#   audio_chunk                      avatar_sdp_answer
#   send_text                        transcript_delta / transcript_done
#   avatar_sdp_offer                 response_created / response_done
#   interrupt                        speech_started / speech_stopped
#                                    audio_data  (voice-only)
#                                    error / session_error


@app.websocket("/ws/voicelive")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    cid = str(id(ws))
    logger.info(f"Client {cid} connected")

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            await _route_message(cid, msg, ws)
    except WebSocketDisconnect:
        logger.info(f"Client {cid} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for {cid}: {e}")
    finally:
        await _cleanup(cid)


async def _route_message(cid: str, msg: dict, ws: WebSocket):
    """Dispatch a browser message to the appropriate handler method."""
    t = msg.get("type")
    handler = _sessions.get(cid)

    if t == "start_session":
        await _start_session(cid, msg.get("config", {}), ws)
    elif t == "stop_session":
        await _cleanup(cid)
    elif t == "audio_chunk" and handler:
        await handler.send_audio(msg.get("data", ""))
    elif t == "send_text" and handler:
        await handler.send_text_message(msg.get("text", ""))
    elif t == "avatar_sdp_offer" and handler:
        await handler.send_avatar_sdp_offer(msg.get("clientSdp", ""))
    elif t == "interrupt" and handler:
        await handler.interrupt()
    else:
        logger.warning(f"Unknown or unroutable message: {t}")


async def _start_session(cid: str, config: dict, ws: WebSocket):
    """Create a session handler and run it as a background task.

    Picks the cloud handler by default; falls back to the local handler when
    ``ENABLE_LOCAL_FALLBACK`` is on AND either ``FORCE_LOCAL_MODE`` is set or
    the connectivity supervisor reports the cloud endpoint unreachable.
    """
    await _cleanup(cid)

    async def _send(msg: dict):
        try:
            await ws.send_text(json.dumps(msg))
        except Exception as e:
            logger.error(f"Send to {cid} failed: {e}")

    # Decide cloud vs local
    use_local, reason = _decide_local(config)

    if use_local:
        missing = settings.validate_local_fallback()
        if missing:
            await _send({
                "type": "session_error",
                "error": f"local-fallback misconfigured: missing {', '.join(missing)}",
            })
            return
        handler: SessionHandler = LocalSessionHandler(
            client_id=cid,
            send_message=_send,
            config=config,
            fallback_reason=reason,
        )
        logger.info(f"Session {cid} → local (reason={reason})")
    else:
        credential = DefaultAzureCredential()

        # BYOM: when enabled, the BYOM deployment name *replaces* the model query param,
        # and the BYOM profile + (optional) cross-resource override are added as query params.
        use_byom = settings.ENABLE_BYOM_MODE and bool(settings.VOICE_BYOM_MODEL)
        if settings.ENABLE_BYOM_MODE and not settings.VOICE_BYOM_MODEL:
            logger.warning(
                "ENABLE_BYOM_MODE is true but VOICE_BYOM_MODEL is empty — falling back to VOICE_LIVE_MODEL."
            )

        handler = CloudVoiceLiveSessionHandler(
            client_id=cid,
            endpoint=settings.AZURE_AI_ENDPOINT,
            model=settings.VOICE_BYOM_MODEL if use_byom else settings.VOICE_LIVE_MODEL,
            byom_mode=settings.VOICE_BYOM_MODE if use_byom else None,
            foundry_resource_override=settings.VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE or None,
            credential=credential,
            send_message=_send,
            config=config,
        )
        logger.info(f"Session {cid} → cloud")

    _sessions[cid] = handler
    _tasks[cid] = asyncio.create_task(handler.start())
    logger.info(f"Session started for {cid}")


def _decide_local(config: dict) -> tuple[bool, str | None]:
    """Return (use_local, reason).

    Priority order:
      1. Client explicitly requested mode (config["forceMode"] == "local").
      2. Server FORCE_LOCAL_MODE env var.
      3. ENABLE_LOCAL_FALLBACK + supervisor says cloud is unreachable.
      4. Default: cloud.
    """
    requested = (config or {}).get("forceMode", "")
    if requested == "local":
        if not settings.ENABLE_LOCAL_FALLBACK:
            logger.warning("Client requested local mode but ENABLE_LOCAL_FALLBACK=false — denied")
        else:
            return True, "client-requested"

    if not settings.ENABLE_LOCAL_FALLBACK:
        return False, None

    if settings.FORCE_LOCAL_MODE:
        return True, "force-local-env"

    if _supervisor is not None and not _supervisor.is_cloud_reachable():
        last_err = _supervisor.status().get("lastError") or "unknown"
        return True, f"cloud-unreachable: {last_err}"

    return False, None


async def _cleanup(cid: str):
    """Tear down session and cancel its background task."""
    handler = _sessions.pop(cid, None)
    if handler:
        await handler.stop()

    task = _tasks.pop(cid, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


# ── Available avatars ────────────────────────────────────────────────────────
@app.get("/api/avatars")
async def list_avatars():
    """Return all configured avatar characters (video + photo)."""
    return {
        "video": [
            {**c, "type": "video"} for c in settings.AVATAR_CHARACTERS
        ],
        "photo": [
            {**p, "type": "photo", "model": "vasa-1"} for p in settings.PHOTO_AVATARS
        ],
    }


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    missing = settings.validate()
    return {"status": "ok" if not missing else "misconfigured", "missing_keys": missing}


# ── Hybrid supervisor status ─────────────────────────────────────────────────
@app.get("/api/hybrid/status")
async def hybrid_status():
    """Expose the connectivity supervisor state + local-fallback config."""
    return {
        "enableLocalFallback": settings.ENABLE_LOCAL_FALLBACK,
        "forceLocalMode": settings.FORCE_LOCAL_MODE,
        "supervisor": _supervisor.status() if _supervisor is not None else None,
        "localStack": {
            "stt": settings.LOCAL_STT_ENDPOINT,
            "tts": settings.LOCAL_TTS_ENDPOINT,
            "llm": settings.LOCAL_LLM_ENDPOINT,
            "voice": settings.LOCAL_TTS_VOICE,
            "model": settings.LOCAL_LLM_MODEL,
        },
        "missingLocalConfig": settings.validate_local_fallback(),
    }


# ── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    missing = settings.validate()
    if missing:
        print(f"WARNING: Missing env vars: {', '.join(missing)}")

    uvicorn.run("app:app", host="0.0.0.0", port=settings.PORT, reload=True)
