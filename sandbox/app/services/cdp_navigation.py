"""
CDP Navigation service for browser history/reload controls.

Provides lightweight page-target CDP commands used by takeover controls:
- back / forward via Page.getNavigationHistory + Page.navigateToHistoryEntry
- reload via Page.reload
- stop loading via Page.stopLoading
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_NAV_COMMAND_TIMEOUT = 5.0


class CDPNavigationService:
    """CDP page-navigation command helper."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self.session: aiohttp.ClientSession | None = None
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self._connected = False
        self._msg_counter = 0
        self._command_lock = asyncio.Lock()

    async def connect(self) -> bool:
        """Connect to an active page-level CDP websocket."""
        try:
            if self.session is None:
                self.session = aiohttp.ClientSession()

            async with self.session.get(
                f"{self.cdp_url}/json",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    logger.error("CDP /json endpoint returned %s", resp.status)
                    return False
                pages = await resp.json()

            ws_url = None
            for target in pages:
                if target.get("type") == "page":
                    ws_url = target.get("webSocketDebuggerUrl")
                    break

            if not ws_url:
                logger.error("No page target available for CDP navigation")
                return False

            self.ws = await self.session.ws_connect(
                ws_url,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            self._connected = True
            return True
        except Exception as e:
            logger.error(
                "Failed to connect CDP navigation service: %s", e, exc_info=True
            )
            return False

    async def disconnect(self) -> None:
        self._connected = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.debug("Ignoring CDP navigation websocket close error: %s", e)
            self.ws = None
        if self.session:
            try:
                await self.session.close()
            except Exception as e:
                logger.debug("Ignoring CDP navigation session close error: %s", e)
            self.session = None

    async def _send_command(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = _NAV_COMMAND_TIMEOUT,
    ) -> dict[str, Any]:
        if not self._connected or not self.ws:
            raise RuntimeError("CDP navigation service not connected")

        async with self._command_lock:
            if not self.ws or self.ws.closed:
                self._connected = False
                raise RuntimeError("CDP websocket closed")

            self._msg_counter += 1
            msg_id = self._msg_counter
            payload: dict[str, Any] = {"id": msg_id, "method": method}
            if params:
                payload["params"] = params

            await self.ws.send_json(payload)

            started = asyncio.get_event_loop().time()
            while True:
                remaining = timeout - (asyncio.get_event_loop().time() - started)
                if remaining <= 0:
                    raise RuntimeError(f"CDP command timed out: {method}")

                try:
                    ws_msg = await asyncio.wait_for(
                        self.ws.receive(), timeout=remaining
                    )
                except asyncio.TimeoutError as e:
                    raise RuntimeError(
                        f"CDP command timed out waiting response: {method}"
                    ) from e

                if ws_msg.type == aiohttp.WSMsgType.TEXT:
                    data = ws_msg.json()
                    if data.get("id") == msg_id:
                        if "error" in data:
                            raise RuntimeError(f"CDP command failed: {data['error']}")
                        result = data.get("result")
                        return result if isinstance(result, dict) else {}
                elif ws_msg.type == aiohttp.WSMsgType.ERROR:
                    raise RuntimeError(f"CDP websocket error: {ws_msg.data}")
                elif ws_msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                    self._connected = False
                    raise RuntimeError("CDP websocket closed before response")

    async def get_navigation_history(self) -> dict[str, Any]:
        history = await self._send_command("Page.getNavigationHistory")
        current_index = int(history.get("currentIndex", 0))
        entries_payload = history.get("entries", [])
        entries = []
        if isinstance(entries_payload, list):
            for entry in entries_payload:
                if not isinstance(entry, dict):
                    continue
                entries.append(
                    {
                        "id": int(entry.get("id", -1)),
                        "url": str(entry.get("url", "")),
                        "title": str(entry.get("title", "")),
                    }
                )
        return {"current_index": current_index, "entries": entries}

    async def go_back(self) -> tuple[bool, str]:
        history = await self.get_navigation_history()
        current_index = history["current_index"]
        entries = history["entries"]
        if current_index <= 0 or current_index >= len(entries):
            return False, "No previous history entry"
        target = entries[current_index - 1]
        await self._send_command(
            "Page.navigateToHistoryEntry", {"entryId": int(target["id"])}
        )
        return True, "Navigated back"

    async def go_forward(self) -> tuple[bool, str]:
        history = await self.get_navigation_history()
        current_index = history["current_index"]
        entries = history["entries"]
        if current_index < 0 or current_index >= len(entries) - 1:
            return False, "No forward history entry"
        target = entries[current_index + 1]
        await self._send_command(
            "Page.navigateToHistoryEntry", {"entryId": int(target["id"])}
        )
        return True, "Navigated forward"

    async def reload(self) -> tuple[bool, str]:
        await self._send_command("Page.reload")
        return True, "Reload triggered"

    async def stop_loading(self) -> tuple[bool, str]:
        await self._send_command("Page.stopLoading")
        return True, "Stop loading triggered"
