"""Back-compat shim.

The cloud Voice Live session handler now lives in
``session_handlers.cloud.CloudVoiceLiveSessionHandler``. This module preserves
the historical import path used elsewhere in the codebase and in any external
tooling that referenced ``voice_handler.VoiceSessionHandler``.
"""

from session_handlers.cloud import CloudVoiceLiveSessionHandler

VoiceSessionHandler = CloudVoiceLiveSessionHandler

__all__ = ["VoiceSessionHandler", "CloudVoiceLiveSessionHandler"]
