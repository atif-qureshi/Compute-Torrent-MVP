"""
Dashboard Screen — APP-3 / APP-4

Displays:
  - Connection status (connected / connecting / paused)
  - Current task ID + progress state
  - Total tasks completed
  - Credits earned

Provides pause/resume controls (APP-4).

Again, pure logic — no GUI dependency, bindable by any widget toolkit.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("computetorrent.desktop_app.dashboard")


class DashboardViewModel:
    """
    Drives the main dashboard screen.

    Reads from AppState and exposes formatted strings for the UI to bind.
    Also exposes pause() / resume() which delegate to AppController.
    """

    def __init__(self, state, controller):
        """
        :param state: desktop_app.controller.AppState
        :param controller: desktop_app.controller.AppController
        """
        self._state = state
        self._controller = controller
        # Register for state changes so the UI can re-render
        self._state.add_listener(self._on_state_change)
        self._on_change_callback: Optional[Callable[[], None]] = None

    def set_on_change(self, fn: Callable[[], None]) -> None:
        """Register a callback that fires whenever state changes (for UI refresh)."""
        self._on_change_callback = fn

    def _on_state_change(self, state) -> None:
        if self._on_change_callback:
            self._on_change_callback()

    # ------------------------------------------------------------------
    # APP-3: Formatted display properties
    # ------------------------------------------------------------------

    @property
    def connection_status(self) -> str:
        if self._state.paused:
            return "Paused"
        return "Connected" if self._state.connected else "Connecting…"

    @property
    def current_task(self) -> str:
        if not self._state.current_task_id:
            return "Idle"
        state_label = self._state.current_task_state or "unknown"
        return f"{self._state.current_task_id} — {state_label}"

    @property
    def tasks_completed(self) -> str:
        return str(self._state.tasks_completed)

    @property
    def credits_earned(self) -> str:
        return f"{self._state.credits_earned:.2f}"

    # ------------------------------------------------------------------
    # APP-4: Pause / Resume controls
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause seeding — no new tasks accepted."""
        self._controller.pause()

    def resume(self) -> None:
        """Resume seeding after pause."""
        self._controller.resume()

    @property
    def is_paused(self) -> bool:
        return self._state.paused
