"""Local LLM client — Microsoft Foundry Local (OpenAI-compatible).

Foundry Local exposes an OpenAI-compatible REST API on a dynamic local port.
The endpoint base ends in ``/v1`` and ``/v1/chat/completions`` accepts the
familiar OpenAI request body.

We use the official ``openai`` async client pointed at that base URL — Foundry
Local does not require authentication, but the client demands a non-empty key.

References:
- https://learn.microsoft.com/azure/foundry-local/reference/reference-rest
- https://learn.microsoft.com/azure/foundry-local/how-to/how-to-integrate-with-inference-sdks
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LocalLLMClient:
    """Async chat-completion client for a Foundry Local deployment."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str = "not-needed",
        timeout_s: float = 30.0,
        max_tokens: int = 256,
    ):
        # The OpenAI SDK appends paths to base_url, so it must NOT end with /.
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self._client = AsyncOpenAI(
            base_url=self.endpoint,
            api_key=api_key or "not-needed",
            timeout=timeout_s,
        )

    async def chat(
        self,
        messages: Iterable[dict],
        *,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Return the assistant's reply text for the given message history.

        ``messages`` is a list of dicts in OpenAI format:
            [{"role": "system", "content": "..."},
             {"role": "user", "content": "..."}]
        """
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=list(messages),
                temperature=temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=False,
            )
        except Exception as exc:
            logger.error("Foundry Local chat call failed: %s", exc)
            raise

        if not resp.choices:
            return ""
        content = resp.choices[0].message.content or ""
        return content.strip()

    async def aclose(self) -> None:
        try:
            await self._client.close()
        except Exception:
            pass
