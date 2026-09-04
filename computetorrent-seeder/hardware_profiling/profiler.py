"""
Hardware Profiling Module — ComputeTorrent Provider (Seeder) Desktop App
Implements requirements HP-1 through HP-5 from the Partner 2 requirements doc.

Responsibilities:
  HP-1: Detect GPU model, VRAM size, CUDA availability, CPU core count, total RAM.
  HP-2: Build a `Node Profile` JSON object: { GPU, VRAM, CUDA, RAM }.
  HP-3: Assign a capability tier locally (Tier-1 if VRAM >= 8GB, else Tier-2).
  HP-4: Support re-checking the profile (on app restart, or a manual refresh).
  HP-5: Produce a plain-language description of the profile + tier for the UI.

Tech: pynvml (NVIDIA GPU stats), psutil (CPU/RAM stats).

This module is intentionally standalone — it has no dependency on the
Networking Client, Docker Sandbox, or WebTorrent modules, so it can be
built and unit-tested first, per the MVP Build Order (section 8, step 1).
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Optional

import psutil

logger = logging.getLogger("computetorrent.hardware_profiling")

# --- Tuning constants -------------------------------------------------------

TIER_1_MIN_VRAM_GB = 8  # HP-3: VRAM >= 8GB -> Tier-1

BYTES_PER_GB = 1024 ** 3


# --- Data model --------------------------------------------------------------

@dataclasses.dataclass
class NodeProfile:
    """Matches the exact JSON shape required by HP-2: { GPU, VRAM, CUDA, RAM }."""

    GPU: Optional[str]
    VRAM: float  # GB
    CUDA: bool
    RAM: float  # GB

    def to_json(self) -> dict:
        return {
            "GPU": self.GPU,
            "VRAM": self.VRAM,
            "CUDA": self.CUDA,
            "RAM": self.RAM,
        }

    def to_json_str(self) -> str:
        return json.dumps(self.to_json())


TIER_1 = 1
TIER_2 = 2

TIER_LABELS = {
    TIER_1: "Tier 1 — eligible for AI Inference & LoRA tasks",
    TIER_2: "Tier 2 — eligible for Preprocessing / light training",
}


# --- GPU / CPU / RAM detection ------------------------------------------------

def _detect_gpu() -> tuple[Optional[str], float, bool]:
    """Returns (gpu_name, vram_gb, cuda_available).

    Falls back to (None, 0.0, False) on any machine without an NVIDIA GPU,
    without a driver installed, or without pynvml available — this keeps
    HP-1 from crashing the app on non-NVIDIA / CPU-only machines, which
    matters for NFR-3 (degrade gracefully).
    """
    try:
        import pynvml  # imported lazily: not every dev machine has it installed
    except ImportError:
        logger.info("pynvml not installed — treating node as GPU-less.")
        return None, 0.0, False

    try:
        pynvml.nvmlInit()
    except Exception as exc:  # covers NVMLError_LibraryNotFound, driver issues, etc.
        logger.info("NVML init failed (%s) — treating node as GPU-less.", exc)
        return None, 0.0, False

    try:
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count == 0:
            return None, 0.0, False

        # MVP scope: profile the first GPU. Multi-GPU nodes are out of scope.
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8")

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        vram_gb = round(mem_info.total / BYTES_PER_GB, 1)

        # If NVML enumerates a device at all, the driver stack backing it
        # is CUDA-capable for our purposes (MVP-level check, not a full
        # CUDA toolkit / compute-capability query).
        cuda_available = True

        return name, vram_gb, cuda_available
    except Exception as exc:
        logger.warning("Error reading GPU details: %s", exc)
        return None, 0.0, False
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def _detect_cpu_and_ram() -> tuple[int, float]:
    """Returns (logical_cpu_count, total_ram_gb)."""
    cpu_count = psutil.cpu_count(logical=True) or 1
    total_ram_gb = round(psutil.virtual_memory().total / BYTES_PER_GB, 1)
    return cpu_count, total_ram_gb


# --- Tier assignment (HP-3) ---------------------------------------------------

def assign_tier(profile: NodeProfile) -> int:
    """Tier-1 if VRAM >= 8GB (LLM Inference / LoRA eligible), else Tier-2."""
    if profile.VRAM >= TIER_1_MIN_VRAM_GB:
        return TIER_1
    return TIER_2


# --- Human-readable summary (HP-5) --------------------------------------------

def format_profile_message(profile: NodeProfile, tier: int, cpu_count: int) -> str:
    """Plain-language profile + tier description for the app UI.

    e.g. "Your PC: RTX 3060, 12.0GB VRAM -> Tier 1 - eligible for AI
    Inference & LoRA tasks"
    """
    gpu_label = profile.GPU if profile.GPU else "No dedicated GPU detected"
    tier_label = TIER_LABELS[tier]
    return (
        f"Your PC: {gpu_label}, {profile.VRAM}GB VRAM, {cpu_count} CPU cores, "
        f"{profile.RAM}GB RAM -> {tier_label}"
    )


# --- Public entry point --------------------------------------------------------

class HardwareProfiler:
    """Owns the current Node Profile and knows how to (re)build it.

    Usage:
        profiler = HardwareProfiler()      # HP-1: runs on construction (app launch)
        profiler.profile.to_json()         # HP-2
        profiler.tier                      # HP-3
        profiler.refresh()                 # HP-4: app restart or manual "Refresh"
        profiler.summary()                 # HP-5
    """

    def __init__(self, auto_profile: bool = True):
        self.profile: Optional[NodeProfile] = None
        self.tier: Optional[int] = None
        self.cpu_count: Optional[int] = None
        if auto_profile:
            self.refresh()

    def refresh(self) -> NodeProfile:
        """Re-run detection. Called on app launch (HP-1) and on restart /
        manual refresh (HP-4)."""
        gpu_name, vram_gb, cuda = _detect_gpu()
        cpu_count, ram_gb = _detect_cpu_and_ram()

        self.profile = NodeProfile(GPU=gpu_name, VRAM=vram_gb, CUDA=cuda, RAM=ram_gb)
        self.cpu_count = cpu_count
        self.tier = assign_tier(self.profile)

        logger.info(
            "Hardware profile refreshed: %s (tier %s)",
            self.profile.to_json(),
            self.tier,
        )
        return self.profile

    def summary(self) -> str:
        if self.profile is None or self.tier is None or self.cpu_count is None:
            raise RuntimeError("Profiler has not run yet — call refresh() first.")
        return format_profile_message(self.profile, self.tier, self.cpu_count)

    def registration_payload(self) -> dict:
        """Shape expected by the Networking Client for the `register` message
        (see requirements doc section 7) — { profile, tier }."""
        if self.profile is None or self.tier is None:
            raise RuntimeError("Profiler has not run yet — call refresh() first.")
        return {"profile": self.profile.to_json(), "tier": self.tier}
