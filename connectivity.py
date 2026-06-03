"""Connectivity supervisor for the cloud Voice Live endpoint.

Periodically probes ``AZURE_AI_ENDPOINT`` and tracks online/offline state. The
session router consults ``is_cloud_reachable()`` at session start to decide
whether to route a new session through the cloud handler or the local handler.

We probe over plain HTTPS rather than opening a real Voice Live WebSocket
because (a) it's cheap, (b) we don't burn quota, and (c) DNS / route /
firewall failures bubble up the same way they would for the real connection.

Probe target is the Foundry account's root, which always responds with a
TLS handshake and either a 200, 401, or 404 — anything that does NOT raise a
transport error counts as "reachable".
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class ConnectivitySupervisor:
    def __init__(
        self,
        endpoint: str,
        interval_s: float = 15.0,
        timeout_s: float = 3.0,
        failure_threshold: int = 2,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.interval_s = interval_s
        self.timeout_s = timeout_s
        self.failure_threshold = max(1, failure_threshold)

        self._reachable: bool = True   # optimistic start — first probe corrects this fast
        self._consecutive_failures: int = 0
        self._last_check_ts: float = 0.0
        self._last_error: Optional[str] = None

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    # ── Public API ───────────────────────────────────────────────────────

    def is_cloud_reachable(self) -> bool:
        """Best-effort answer based on the most recent probe."""
        return self._reachable

    def status(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "reachable": self._reachable,
            "consecutiveFailures": self._consecutive_failures,
            "lastCheckTs": self._last_check_ts,
            "lastError": self._last_error,
        }

    async def start(self) -> None:
        """Begin background probing."""
        if self._task is not None:
            return
        if not self.endpoint:
            logger.warning("ConnectivitySupervisor disabled — empty endpoint.")
            self._reachable = False
            self._last_error = "no endpoint configured"
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop(), name="connectivity-supervisor")
        # Kick off an immediate probe so the first session has a fresh answer.
        await self.probe_once()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def probe_once(self) -> bool:
        """Issue a single probe synchronously and update internal state."""
        ok, err = await self._probe()
        self._last_check_ts = time.time()
        if ok:
            if not self._reachable:
                logger.info("Cloud reachability restored.")
            self._reachable = True
            self._consecutive_failures = 0
            self._last_error = None
        else:
            self._consecutive_failures += 1
            self._last_error = err
            if (
                self._reachable
                and self._consecutive_failures >= self.failure_threshold
            ):
                logger.warning(
                    "Cloud unreachable after %d consecutive failures: %s",
                    self._consecutive_failures,
                    err,
                )
                self._reachable = False
        return self._reachable

    # ── Internals ────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval_s
                    )
                    return  # stop event fired
                except asyncio.TimeoutError:
                    pass  # normal — time to probe
                try:
                    await self.probe_once()
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Supervisor probe crashed: %s", exc)
        except asyncio.CancelledError:
            return

    async def _probe(self) -> tuple[bool, Optional[str]]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.get(self.endpoint)
            # Any response — even 401/404 — means the network path is healthy.
            return True, None
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            return False, f"connect: {exc.__class__.__name__}: {exc}"
        except httpx.ReadTimeout as exc:
            return False, f"read-timeout: {exc}"
        except httpx.TransportError as exc:
            return False, f"transport: {exc.__class__.__name__}: {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"unexpected: {exc.__class__.__name__}: {exc}"
