"""Session handlers for the Azure AI Voice Live API with Avatar app.

A session handler owns a single conversation between a browser client and a
back-end voice pipeline. Today there are two implementations:

- ``CloudVoiceLiveSessionHandler`` — talks to Azure AI Voice Live (default).
- ``LocalSessionHandler``         — runs a fully local STT → LLM → TTS pipeline
                                     against on-prem Speech containers and a
                                     Foundry Local model. Used as a fallback
                                     when the Azure endpoint is unreachable.

Both implementations expose the same shape (see :class:`SessionHandler`) so the
WebSocket router in :mod:`app` does not need to care which one is in use.
"""

from .base import SessionHandler
from .cloud import CloudVoiceLiveSessionHandler
from .local import LocalSessionHandler

__all__ = ["SessionHandler", "CloudVoiceLiveSessionHandler", "LocalSessionHandler"]
