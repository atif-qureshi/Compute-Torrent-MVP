"""
Unit tests for the Hardware Profiling Module (HP-1 to HP-5).

GPU detection is mocked so these tests pass on any machine — including
CI runners and dev laptops with no NVIDIA GPU — while still exercising
the real tier-assignment and formatting logic.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from profiler import (  # noqa: E402
    HardwareProfiler,
    NodeProfile,
    TIER_1,
    TIER_2,
    assign_tier,
    format_profile_message,
)


# --- HP-2: Node Profile JSON shape -------------------------------------------

def test_node_profile_json_shape_matches_spec():
    profile = NodeProfile(GPU="RTX 3060", VRAM=12.0, CUDA=True, RAM=16.0)
    assert profile.to_json() == {
        "GPU": "RTX 3060",
        "VRAM": 12.0,
        "CUDA": True,
        "RAM": 16.0,
    }
    # round-trips through JSON cleanly
    assert json.loads(profile.to_json_str()) == profile.to_json()


# --- HP-3: Tier assignment ----------------------------------------------------

def test_tier_1_when_vram_at_or_above_8gb():
    profile = NodeProfile(GPU="RTX 3060", VRAM=12.0, CUDA=True, RAM=16.0)
    assert assign_tier(profile) == TIER_1

    boundary_profile = NodeProfile(GPU="RTX 3050", VRAM=8.0, CUDA=True, RAM=16.0)
    assert assign_tier(boundary_profile) == TIER_1


def test_tier_2_when_vram_below_8gb_or_no_gpu():
    weak_gpu = NodeProfile(GPU="GTX 1650", VRAM=4.0, CUDA=True, RAM=8.0)
    assert assign_tier(weak_gpu) == TIER_2

    no_gpu = NodeProfile(GPU=None, VRAM=0.0, CUDA=False, RAM=8.0)
    assert assign_tier(no_gpu) == TIER_2


# --- HP-5: Human-readable summary --------------------------------------------

def test_summary_message_mentions_gpu_and_tier():
    profile = NodeProfile(GPU="RTX 3060", VRAM=12.0, CUDA=True, RAM=16.0)
    msg = format_profile_message(profile, TIER_1, cpu_count=8)
    assert "RTX 3060" in msg
    assert "12.0GB VRAM" in msg
    assert "Tier 1" in msg


def test_summary_message_handles_no_gpu_gracefully():
    profile = NodeProfile(GPU=None, VRAM=0.0, CUDA=False, RAM=8.0)
    msg = format_profile_message(profile, TIER_2, cpu_count=4)
    assert "No dedicated GPU detected" in msg
    assert "Tier 2" in msg


# --- HP-1 / HP-4: end-to-end profiler, with GPU detection mocked -------------

@patch("profiler._detect_cpu_and_ram", return_value=(8, 16.0))
@patch("profiler._detect_gpu", return_value=("RTX 3060", 12.0, True))
def test_profiler_runs_on_construction_and_builds_tier1_profile(mock_gpu, mock_cpu):
    profiler = HardwareProfiler()  # HP-1: should auto-profile on init
    assert profiler.profile.to_json() == {
        "GPU": "RTX 3060",
        "VRAM": 12.0,
        "CUDA": True,
        "RAM": 16.0,
    }
    assert profiler.tier == TIER_1
    assert profiler.cpu_count == 8


@patch("profiler._detect_cpu_and_ram", return_value=(4, 8.0))
@patch("profiler._detect_gpu")
def test_refresh_reflects_hardware_changes(mock_gpu, mock_cpu):
    # Simulates a fresh boot detecting a weaker GPU than before (HP-4).
    mock_gpu.return_value = ("RTX 3060", 12.0, True)
    profiler = HardwareProfiler()
    assert profiler.tier == TIER_1

    mock_gpu.return_value = ("GTX 1650", 4.0, True)
    profiler.refresh()
    assert profiler.tier == TIER_2
    assert profiler.profile.GPU == "GTX 1650"


@patch("profiler._detect_cpu_and_ram", return_value=(4, 8.0))
@patch("profiler._detect_gpu", return_value=(None, 0.0, False))
def test_profiler_degrades_gracefully_with_no_gpu(mock_gpu, mock_cpu):
    # NFR-3: should never crash on a machine with no NVIDIA GPU.
    profiler = HardwareProfiler()
    assert profiler.profile.GPU is None
    assert profiler.tier == TIER_2
    assert "No dedicated GPU detected" in profiler.summary()


# --- registration_payload shape, for the Networking Client's `register` msg -

@patch("profiler._detect_cpu_and_ram", return_value=(8, 16.0))
@patch("profiler._detect_gpu", return_value=("RTX 3060", 12.0, True))
def test_registration_payload_matches_section_7_contract(mock_gpu, mock_cpu):
    profiler = HardwareProfiler()
    payload = profiler.registration_payload()
    assert payload == {
        "profile": {"GPU": "RTX 3060", "VRAM": 12.0, "CUDA": True, "RAM": 16.0},
        "tier": TIER_1,
    }
