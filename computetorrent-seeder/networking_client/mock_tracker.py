"""
Mock Tracker Server — local WebSocket stand-in for Partner 1's Tracker/Relay.

Used exclusively for testing ws_client.py (NC-1 to NC-6) without a real
network. Runs in a background thread so tests can start/stop it inline.

Behaviour:
  - On receiving { "type": "register" } → replies { "type": "registered", "ok": true }
  - Sends one { "type": "task_assign", ... } after registration
  - Echoes { "type": "status_update" } and { "type": "result_submit" } back as ack
  - Sends periodic { "type": "ping" } so the client's heartbeat can be tested
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Optional

logger = logging.getLogger("computetorrent.mock_tracker")

# Optional dependency — only needed for testing.
try:
    import websockets
    import asyncio
    _WEBSOCKETS_AVAILABLE = True
except ImportError:
    _WEBSOCKETS_AVAILABLE = False

SAMPLE_TASK = {
    "type": "task_assign",
    "task_id": "mock_task_001",
    "chunk_ids": [0, 1],
    "swarm_id": "swarm_mock",
    "model_ref": "phi-3-gguf",
    "task_kind": "inference",
}


class MockTrackerServer:
    """
    Tiny asyncio WebSocket server that mimics the Tracker's message flow.

    Usage (in tests):
        server = MockTrackerServer(port=18765)
        server.start()
        # ... run client code ...
        server.stop()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 18765):
        self.host = host
        self.port = port
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional["asyncio.AbstractEventLoop"] = None
        self._server = None
        self.received_messages: list[dict] = []

    def start(self) -> None:
        if not _WEBSOCKETS_AVAILABLE:
            raise RuntimeError("websockets package not installed — run: pip install websockets")
        ready = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
        self._thread.start()
        ready.wait(timeout=5)

    def stop(self) -> None:
        if self._loop and self._server:
            self._loop.call_soon_threadsafe(self._server.close)
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self, ready: threading.Event) -> None:
        import asyncio as _asyncio
        import websockets as _ws

        self._loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(self._loop)

        async def handler(websocket):
            async for raw in websocket:
                msg = json.loads(raw)
                self.received_messages.append(msg)

                if msg.get("type") == "register":
                    await websocket.send(json.dumps({"type": "registered", "ok": True}))
                    await websocket.send(json.dumps(SAMPLE_TASK))

                elif msg.get("type") in ("status_update", "result_submit", "heartbeat"):
                    await websocket.send(json.dumps({"type": "ack", "ref": msg.get("type")}))

        async def serve():
            self._server = await _ws.serve(handler, self.host, self.port)
            ready.set()
            await self._server.wait_closed()

        self._loop.run_until_complete(serve())
