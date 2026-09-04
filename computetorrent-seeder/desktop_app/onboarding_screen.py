"""
Onboarding Screen — APP-2

Runs hardware_profiling.HardwareProfiler on first launch, displays the
detected tier and hardware summary, and presents a "Start Seeding" button.

This module is pure logic — no real GUI toolkit dependency so it is
independently testable. A real UI layer (CustomTkinter / PyQt) would
import OnboardingViewModel and bind its properties to widgets.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("computetorrent.desktop_app.onboarding")


class OnboardingViewModel:
    """
    Drives the onboarding screen.

    Attributes set after `run_profiling()`:
        tier            int  — 1 (GPU) / 2 (CPU-only) / 3 (minimal)
        hardware_summary dict — subset of HardwareProfiler.full_profile()
        registration_payload dict — ready to hand to NetworkingClient
        error           str | None — if profiling failed
    """

    def __init__(self, profiler, on_start_seeding: Optional[Callable[[], None]] = None):
        """
        :param profiler: hardware_profiling.HardwareProfiler instance.
        :param on_start_seeding: callback invoked when user clicks "Start Seeding".
        """
        self._profiler = profiler
        self._on_start_seeding = on_start_seeding

        self.tier: Optional[int] = None
        self.hardware_summary: dict = {}
        self.registration_payload: dict = {}
        self.error: Optional[str] = None
        self.profiling_done: bool = False

    # ------------------------------------------------------------------
    # APP-2: Run hardware detection
    # ------------------------------------------------------------------

    def run_profiling(self) -> None:
        """
        Invoke the profiler and populate view-model fields.
        Errors are captured into self.error — never raised to the caller.
        """
        try:
            # HardwareProfiler exposes .profile, .tier, .cpu_count directly
            self._profiler.refresh()
            p = self._profiler.profile
            self.tier = self._profiler.tier
            self.hardware_summary = {
                "GPU":   p.GPU,
                "VRAM":  p.VRAM,
                "CUDA":  p.CUDA,
                "RAM":   p.RAM,
                "CPU":   f"{self._profiler.cpu_count} cores",
                "Cores": self._profiler.cpu_count,
            }
            self.registration_payload = self._profiler.registration_payload()
            self.profiling_done = True
            logger.info(
                "Onboarding profiling complete: tier=%s GPU=%s RAM=%s",
                self.tier,
                self.hardware_summary.get("GPU"),
                self.hardware_summary.get("RAM"),
            )
        except Exception as exc:
            self.error = str(exc)
            logger.error("Hardware profiling failed: %s", exc)

    def tier_label(self) -> str:
        """Human-readable tier description for the UI."""
        labels = {
            1: "Tier 1 — GPU accelerated (CUDA)",
            2: "Tier 2 — CPU only",
            3: "Tier 3 — Minimal / fallback",
        }
        return labels.get(self.tier or 3, "Unknown tier")

    # ------------------------------------------------------------------
    # APP-2: "Start Seeding" action
    # ------------------------------------------------------------------

    def start_seeding(self) -> None:
        """Called when the user clicks Start Seeding."""
        if not self.profiling_done:
            logger.warning("start_seeding() called before profiling finished.")
            return
        if self._on_start_seeding:
            self._on_start_seeding()
