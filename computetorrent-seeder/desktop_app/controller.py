"""
Application Controller — APP-6 enforcement point

Glues networking_client ↔ webtorrent_sync ↔ sandbox_runtime together and
keeps the UI state in sync. Runs in a background asyncio loop so the GUI
thread stays responsive.

APP-6 hard invariant: self._sandbox_active must be True before any task
is accepted. The controller checks this immediately when a task_assign
arrives and refuses with status="failed" if the sandbox is not ready.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("computetorrent.desktop_app.controller")


# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

class AppState:
    """Observable state bag — UI screens read from this."""

    def __init__(self) -> None:
        self.connected: bool = False
        self.paused: bool = False
        self.current_task_id: Optional[str] = None
        self.current_task_state: Optional[str] = None   # queued/downloading/running/completed/failed
        self.tasks_completed: int = 0
        self.credits_earned: float = 0.0
        self._listeners: list[Callable[["AppState"], None]] = []

    def add_listener(self, fn: Callable[["AppState"], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in self._listeners:
            try:
                fn(self)
            except Exception as exc:
                logger.warning("State listener raised: %s", exc)

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
        self._notify()


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class AppController:
    """
    Orchestrates the four backend modules.

    Lifecycle:
        controller = AppController(profiler, sandbox_runner, networking_client, wt_bridge)
        controller.start()   # spawns background thread running asyncio loop
        # ... UI runs ...
        controller.stop()
    """

    def __init__(
        self,
        profiler,               # hardware_profiling.HardwareProfiler
        sandbox_runner,         # sandbox_runtime.SandboxRunner
        networking_client,      # networking_client.NetworkingClient
        wt_bridge,              # webtorrent_sync.WebtorrentBridge (or None)
        state: Optional[AppState] = None,
    ):
        self._profiler = profiler
        self._runner = sandbox_runner
        self._net = networking_client
        self._wt = wt_bridge
        self.state = state or AppState()

        # APP-6: sandbox must be healthy before any task runs
        self._sandbox_active: bool = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, sandbox_ok: bool = True) -> None:
        """
        Start the background event loop.

        `sandbox_ok` should come from `docker_preflight.run_preflight().ok`.
        If False, seeding is blocked (APP-6).
        """
        self._sandbox_active = sandbox_ok
        if not sandbox_ok:
            logger.warning("APP-6: Docker not available — seeding disabled.")
            self.state.update(connected=False)

        # Wire up the networking client callback
        self._net.on_task_assign = self._on_task_assign_sync

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("AppController started (sandbox_active=%s)", self._sandbox_active)

    def stop(self) -> None:
        """Signal the event loop to exit."""
        self._net.stop()
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        if self._wt:
            try:
                self._wt.stop()
            except Exception:
                pass
        logger.info("AppController stopped.")

    def pause(self) -> None:
        """APP-4: Pause seeding — no new tasks accepted until resumed."""
        self.state.update(paused=True)
        logger.info("Seeding paused.")

    def resume(self) -> None:
        """APP-4: Resume seeding after pause."""
        self.state.update(paused=False)
        logger.info("Seeding resumed.")

    # ------------------------------------------------------------------
    # Task flow
    # ------------------------------------------------------------------

    def _on_task_assign_sync(self, msg: dict) -> None:
        """Called from the networking_client asyncio context — schedules the task."""
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._handle_task(msg), self._loop)

    async def _handle_task(self, msg: dict) -> None:
        task_id = msg.get("task_id", "unknown")
        chunk_ids: list[int] = msg.get("chunk_ids", [])

        # APP-6: refuse if sandbox is not ready
        if not self._sandbox_active:
            logger.error("APP-6: sandbox not active — refusing task %s", task_id)
            await self._net.send_status(task_id, "failed")
            return

        # APP-4: refuse if paused
        if self.state.paused:
            logger.info("Paused — declining task %s", task_id)
            await self._net.send_status(task_id, "failed")
            return

        self.state.update(current_task_id=task_id, current_task_state="queued")

        # --- Download phase (via webtorrent_sync if available) ---
        chunk_path = Path(
            msg.get("chunk_file_path", "/tmp/mock_chunk.bin")
        )

        if self._wt and msg.get("swarm_id") and msg.get("model_ref"):
            await self._net.send_status(task_id, "downloading")
            self.state.update(current_task_state="downloading")
            try:
                magnet = msg.get("magnet_uri", "")
                chunk_path = Path(self._wt.join_swarm(msg["swarm_id"], magnet))
            except Exception as exc:
                logger.error("Download failed for task %s: %s", task_id, exc)
                await self._net.send_status(task_id, "failed")
                self.state.update(current_task_state="failed")
                return

        # --- Execution phase (sandbox_runtime) ---
        await self._net.send_status(task_id, "running")
        self.state.update(current_task_state="running")

        try:
            from sandbox_runtime.runner import TaskAssignment  # package import
        except ModuleNotFoundError:
            from runner import TaskAssignment  # flat sibling import
        task_assignment = TaskAssignment(
            task_id=task_id,
            chunk_ids=chunk_ids,
            swarm_id=msg.get("swarm_id", ""),
            model_ref=msg.get("model_ref", ""),
            task_kind=msg.get("task_kind", "inference"),
            chunk_file_path=chunk_path,
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, self._runner.run, task_assignment, chunk_ids[0] if chunk_ids else 0
        )

        # --- Result submission ---
        if result.status == "completed":
            if result.output_ref:
                await self._net.send_result(task_id, result.chunk_id, result.output_ref)
            await self._net.send_status(task_id, "completed")
            self.state.update(
                current_task_state="completed",
                tasks_completed=self.state.tasks_completed + 1,
                credits_earned=self.state.credits_earned + 1.0,
            )
            # WT-4: leave swarm after submission
            if self._wt and msg.get("swarm_id"):
                try:
                    self._wt.leave_swarm(msg["swarm_id"])
                except Exception:
                    pass
        else:
            await self._net.send_status(task_id, "failed")
            self.state.update(current_task_state="failed")

        self.state.update(current_task_id=None)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        # Always connect to the tracker so the UI shows connection status.
        # APP-6 is enforced at task-dispatch time, not at connection time.
        try:
            self._loop.run_until_complete(self._net.connect_and_run())
        except Exception as exc:
            logger.error("Networking loop exited: %s", exc)
        self._loop.close()
