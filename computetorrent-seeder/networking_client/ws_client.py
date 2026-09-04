"""
Networking Client — NC-1 to NC-6
WebSocket client that connects to Partner 1's Tracker/Relay, registers the
node, listens for task assignments, sends status updates, and handles
reconnection with exponential back-off.

NC-1  Connect on launch and send `register` with hardware profile + tier.
NC-2  Persistent heartbeat loop while idle.
NC-3  Listen for `task_assign`; parse chunk ID, model ref, swarm ID, task kind.
NC-4  Attempt STUN upgrade; fall back to relay silently on failure.
NC-5  Push `status_update` messages (queued/downloading/running/completed/failed).
NC-6  Reconnect with back-off; attempt to resume dropped task; re-register on failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable, Optional

from webrtc_upgrade import attempt_stun_upgrade

logger = logging.getLogger("computetorrent.networking_client")

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

HEARTBEAT_INTERVAL_S = 15
RECONNECT_BASE_S = 2
RECONNECT_MAX_S = 60
RECONNECT_FACTOR = 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class NetworkingClient:
    """
    Manages the WebSocket connection to the Tracker/Relay.

    Usage (async):
        client = NetworkingClient(
            tracker_url="ws://tracker:8080",
            registration_payload=profiler.registration_payload(),
            on_task_assign=handle_task,
        )
        await client.connect_and_run()   # runs until stopped

    Callbacks:
        on_task_assign(msg: dict) — called when a task_assign arrives (NC-3)
    """

    def __init__(
        self,
        tracker_url: str,
        registration_payload: dict,
        on_task_assign: Optional[Callable[[dict], None]] = None,
        enable_stun: bool = True,
    ):
        self.tracker_url = tracker_url
        self.registration_payload = registration_payload
        self.on_task_assign = on_task_assign
        self.enable_stun = enable_stun

        self._ws = None
        self._running = False
        self._current_task_id: Optional[str] = None
        self._reconnect_delay = RECONNECT_BASE_S
        self._send_lock: Optional[asyncio.Lock] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect_and_run(self) -> None:
        """Main loop: connect → register → listen. Reconnects on drop (NC-6)."""
        self._running = True
        while self._running:
            try:
                await self._connect_once()
                self._reconnect_delay = RECONNECT_BASE_S  # reset on clean connect
            except Exception as exc:
                logger.warning("Connection lost: %s. Retrying in %ss…", exc, self._reconnect_delay)
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * RECONNECT_FACTOR, RECONNECT_MAX_S)

    def stop(self) -> None:
        """Signal the run loop to exit cleanly."""
        self._running = False

    # ------------------------------------------------------------------
    # NC-5: Status updates
    # ------------------------------------------------------------------

    async def send_status(self, task_id: str, state: str) -> None:
        """Push a status_update message (NC-5).
        state: "queued" | "downloading" | "running" | "completed" | "failed"
        """
        await self._send({"type": "status_update", "task_id": task_id, "state": state})

    async def send_result(self, task_id: str, chunk_id: int, output_ref: str) -> None:
        """Push a result_submit message after a chunk completes."""
        await self._send({
            "type": "result_submit",
            "task_id": task_id,
            "chunk_id": chunk_id,
            "output_ref": output_ref,
        })

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _connect_once(self) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("websockets package not installed — pip install websockets") from exc

        # NC-4: STUN probe (fire-and-forget; failure doesn't block connection)
        if self.enable_stun:
            stun_ok = await asyncio.get_event_loop().run_in_executor(
                None, attempt_stun_upgrade
            )
            logger.info("STUN probe: %s", "direct path" if stun_ok else "using relay")

        async with websockets.connect(self.tracker_url) as ws:
            self._ws = ws
            self._send_lock = asyncio.Lock()
            logger.info("Connected to tracker: %s", self.tracker_url)

            # NC-1: Register immediately on connect
            await self._register()

            # NC-6: If we dropped mid-task, notify resumed state
            if self._current_task_id:
                logger.info("Resuming task %s after reconnect", self._current_task_id)
                await self.send_status(self._current_task_id, "running")

            # Run heartbeat + message listener concurrently
            try:
                await asyncio.gather(
                    self._heartbeat_loop(),
                    self._listen_loop(),
                )
            finally:
                self._ws = None

    async def _register(self) -> None:
        """NC-1: Send registration payload."""
        msg = {"type": "register", **self.registration_payload}
        await self._send(msg)
        logger.info("Sent register: tier=%s", self.registration_payload.get("tier"))

    async def _heartbeat_loop(self) -> None:
        """NC-2: Send periodic heartbeat while connected."""
        while self._running:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            if self._ws is not None:
                await self._send({"type": "heartbeat"})
                logger.debug("Heartbeat sent")

    async def _listen_loop(self) -> None:
        """NC-3: Receive and dispatch incoming messages."""
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Non-JSON message received: %r", raw)
                continue

            msg_type = msg.get("type")
            logger.debug("Received: %s", msg_type)

            if msg_type == "task_assign":
                await self._handle_task_assign(msg)
            elif msg_type == "ping":
                await self._send({"type": "pong"})
            elif msg_type in ("registered", "ack", "pong"):
                pass  # expected acknowledgements
            else:
                logger.info("Unhandled message type: %s", msg_type)

    async def _handle_task_assign(self, msg: dict) -> None:
        """NC-3: Parse and dispatch a task_assign message."""
        task_id = msg.get("task_id")
        self._current_task_id = task_id
        logger.info(
            "Task assigned: id=%s chunks=%s model=%s kind=%s",
            task_id, msg.get("chunk_ids"), msg.get("model_ref"), msg.get("task_kind")
        )
        await self.send_status(task_id, "queued")
        if self.on_task_assign:
            self.on_task_assign(msg)

    async def _send(self, msg: dict) -> None:
        """Send a JSON message; silently drop if not connected."""
        if self._ws is None:
            logger.warning("Cannot send — not connected. Message dropped: %s", msg.get("type"))
            return
        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        async with self._send_lock:
            try:
                await self._ws.send(json.dumps(msg))
            except Exception as exc:
                logger.warning("Send failed (%s) — message dropped: %s", exc, msg.get("type"))
