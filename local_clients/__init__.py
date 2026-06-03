"""Clients for the on-prem services used by the local-fallback handler.

These are deliberately thin wrappers — the handler in
``session_handlers.local`` owns the orchestration. Each client is async,
constructs its own ``httpx.AsyncClient`` lazily, and can be closed via
``aclose()``.
"""

from .stt import LocalSTTClient
from .tts import LocalTTSClient
from .llm import LocalLLMClient

__all__ = ["LocalSTTClient", "LocalTTSClient", "LocalLLMClient"]
