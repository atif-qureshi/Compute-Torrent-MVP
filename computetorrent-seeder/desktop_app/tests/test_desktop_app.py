"""
Tests for the Desktop App modules (APP-1 to APP-6).

All tests are pure unit tests — no GUI toolkit, no Docker, no network.
"""

from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent.parent   # computetorrent-seeder/
for sibling in ("hardware_profiling", "sandbox_runtime", "networking_client", "desktop_app"):
    p = str(ROOT / sibling)
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from docker_preflight import run_preflight, DockerPreflightResult, _check_docker
from onboarding_screen import OnboardingViewModel
from dashboard_screen import DashboardViewModel
from controller import AppController, AppState


# ===========================================================================
# docker_preflight tests
# ===========================================================================

class TestDockerPreflight:

    def test_returns_false_when_docker_not_found(self):
        with patch("docker_preflight.subprocess.run", side_effect=FileNotFoundError):
            result = run_preflight()
        assert result.ok is False
        assert "Docker" in result.message

    def test_returns_false_when_docker_exits_nonzero(self):
        m = MagicMock()
        m.returncode = 1
        m.stderr = "daemon not running"
        with patch("docker_preflight.subprocess.run", return_value=m):
            result = run_preflight()
        assert result.ok is False

    def test_returns_true_when_docker_available(self):
        m = MagicMock()
        m.returncode = 0
        with patch("docker_preflight.subprocess.run", return_value=m):
            result = run_preflight()
        assert result.ok is True

    def test_never_raises(self):
        with patch("docker_preflight.subprocess.run", side_effect=RuntimeError("boom")):
            result = run_preflight()
        assert isinstance(result.ok, bool)

    def test_docker_preflight_result_bool(self):
        assert bool(DockerPreflightResult(ok=True, message="ok")) is True
        assert bool(DockerPreflightResult(ok=False, message="no")) is False

    def test_nvidia_check_skipped_by_default(self):
        m = MagicMock()
        m.returncode = 0
        with patch("docker_preflight.subprocess.run", return_value=m):
            result = run_preflight(check_nvidia=False)
        assert result.nvidia_ok is None

    def test_timeout_returns_false(self):
        import subprocess
        with patch("docker_preflight.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("docker", 10)):
            result = run_preflight()
        assert result.ok is False


# ===========================================================================
# OnboardingViewModel (APP-2) tests
# ===========================================================================

def _make_mock_profiler(tier: int = 2):
    import types
    profiler = MagicMock()
    # Simulate HardwareProfiler attributes directly
    mock_profile = MagicMock()
    mock_profile.GPU = None
    mock_profile.VRAM = 0
    mock_profile.CUDA = False
    mock_profile.RAM = 16.0
    profiler.profile = mock_profile
    profiler.tier = tier
    profiler.cpu_count = 8
    profiler.refresh = MagicMock()
    profiler.registration_payload.return_value = {
        "profile": {"GPU": None, "VRAM": 0, "CUDA": False, "RAM": 16.0},
        "tier": tier,
    }
    return profiler


class TestOnboardingViewModel:

    def test_run_profiling_sets_tier(self):
        vm = OnboardingViewModel(_make_mock_profiler(tier=1))
        vm.run_profiling()
        assert vm.tier == 1

    def test_run_profiling_sets_hardware_summary(self):
        vm = OnboardingViewModel(_make_mock_profiler())
        vm.run_profiling()
        assert "GPU" in vm.hardware_summary
        assert "RAM" in vm.hardware_summary

    def test_run_profiling_sets_registration_payload(self):
        vm = OnboardingViewModel(_make_mock_profiler())
        vm.run_profiling()
        assert "profile" in vm.registration_payload
        assert "tier" in vm.registration_payload

    def test_tier_label_tier1(self):
        vm = OnboardingViewModel(_make_mock_profiler(tier=1))
        vm.run_profiling()
        assert "Tier 1" in vm.tier_label()
        assert "GPU" in vm.tier_label()

    def test_tier_label_tier2(self):
        vm = OnboardingViewModel(_make_mock_profiler(tier=2))
        vm.run_profiling()
        assert "Tier 2" in vm.tier_label()

    def test_profiling_error_captured(self):
        profiler = MagicMock()
        profiler.refresh.side_effect = RuntimeError("hardware error")
        vm = OnboardingViewModel(profiler)
        vm.run_profiling()
        assert vm.error is not None
        assert vm.profiling_done is False

    def test_start_seeding_fires_callback(self):
        called = []
        vm = OnboardingViewModel(_make_mock_profiler(), on_start_seeding=lambda: called.append(1))
        vm.run_profiling()
        vm.start_seeding()
        assert called == [1]

    def test_start_seeding_noop_before_profiling(self):
        called = []
        vm = OnboardingViewModel(_make_mock_profiler(), on_start_seeding=lambda: called.append(1))
        vm.start_seeding()  # profiling not done yet
        assert called == []


# ===========================================================================
# AppState tests
# ===========================================================================

class TestAppState:

    def test_update_notifies_listeners(self):
        state = AppState()
        received = []
        state.add_listener(lambda s: received.append(s.connected))
        state.update(connected=True)
        assert received == [True]

    def test_multiple_listeners_all_called(self):
        state = AppState()
        a, b = [], []
        state.add_listener(lambda s: a.append(1))
        state.add_listener(lambda s: b.append(1))
        state.update(paused=True)
        assert a == [1]
        assert b == [1]

    def test_listener_exception_does_not_propagate(self):
        state = AppState()
        state.add_listener(lambda s: (_ for _ in ()).throw(RuntimeError("bad")))
        # Should not raise
        state.update(tasks_completed=5)
        assert state.tasks_completed == 5


# ===========================================================================
# DashboardViewModel (APP-3 / APP-4) tests
# ===========================================================================

def _make_dashboard():
    state = AppState()
    controller = MagicMock()
    db = DashboardViewModel(state=state, controller=controller)
    return db, state, controller


class TestDashboardViewModel:

    def test_connection_status_connected(self):
        db, state, _ = _make_dashboard()
        state.update(connected=True)
        assert db.connection_status == "Connected"

    def test_connection_status_connecting(self):
        db, state, _ = _make_dashboard()
        state.update(connected=False)
        assert "Connecting" in db.connection_status

    def test_connection_status_paused(self):
        db, state, _ = _make_dashboard()
        state.update(paused=True)
        assert db.connection_status == "Paused"

    def test_current_task_idle(self):
        db, _, _ = _make_dashboard()
        assert db.current_task == "Idle"

    def test_current_task_with_id(self):
        db, state, _ = _make_dashboard()
        state.update(current_task_id="task_001", current_task_state="running")
        assert "task_001" in db.current_task
        assert "running" in db.current_task

    def test_tasks_completed_string(self):
        db, state, _ = _make_dashboard()
        state.update(tasks_completed=7)
        assert db.tasks_completed == "7"

    def test_credits_earned_string(self):
        db, state, _ = _make_dashboard()
        state.update(credits_earned=3.5)
        assert db.credits_earned == "3.50"

    def test_pause_delegates_to_controller(self):
        db, _, ctrl = _make_dashboard()
        db.pause()
        ctrl.pause.assert_called_once()

    def test_resume_delegates_to_controller(self):
        db, _, ctrl = _make_dashboard()
        db.resume()
        ctrl.resume.assert_called_once()

    def test_is_paused_reflects_state(self):
        db, state, _ = _make_dashboard()
        assert db.is_paused is False
        state.update(paused=True)
        assert db.is_paused is True

    def test_on_change_callback_fires(self):
        db, state, _ = _make_dashboard()
        calls = []
        db.set_on_change(lambda: calls.append(1))
        state.update(tasks_completed=1)
        assert calls == [1]


# ===========================================================================
# AppController (APP-4 / APP-6) tests
# ===========================================================================

def _make_controller(sandbox_ok=True):
    profiler = _make_mock_profiler()
    sandbox = MagicMock()
    net = MagicMock()
    net.send_status = AsyncMock()
    net.send_result = AsyncMock()
    net.connect_and_run = AsyncMock()
    net.stop = MagicMock()
    state = AppState()
    ctrl = AppController(
        profiler=profiler,
        sandbox_runner=sandbox,
        networking_client=net,
        wt_bridge=None,
        state=state,
    )
    return ctrl, state, net, sandbox


class TestAppController:

    def test_pause_sets_state(self):
        ctrl, state, _, __ = _make_controller()
        ctrl.pause()
        assert state.paused is True

    def test_resume_clears_state(self):
        ctrl, state, _, __ = _make_controller()
        ctrl.pause()
        ctrl.resume()
        assert state.paused is False

    @pytest.mark.asyncio
    async def test_app6_blocks_task_when_sandbox_inactive(self):
        ctrl, state, net, sandbox = _make_controller()
        ctrl._sandbox_active = False

        msg = {
            "task_id": "t1",
            "chunk_ids": [0],
            "swarm_id": "s1",
            "model_ref": "phi-3",
            "task_kind": "inference",
        }
        await ctrl._handle_task(msg)
        net.send_status.assert_awaited_with("t1", "failed")
        sandbox.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_app4_blocks_task_when_paused(self):
        ctrl, state, net, sandbox = _make_controller()
        ctrl._sandbox_active = True
        ctrl.pause()

        msg = {
            "task_id": "t2",
            "chunk_ids": [0],
            "swarm_id": "s2",
            "model_ref": "phi-3",
            "task_kind": "inference",
        }
        await ctrl._handle_task(msg)
        net.send_status.assert_awaited_with("t2", "failed")
        sandbox.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_task_increments_totals(self):
        ctrl, state, net, sandbox = _make_controller()
        ctrl._sandbox_active = True
        ctrl._loop = asyncio.get_event_loop()

        # Mock sandbox returning completed result
        from runner import SandboxResult
        sandbox.run.return_value = SandboxResult(
            task_id="t3", chunk_id=0, status="completed",
            output_ref="result.json", error=None, duration_s=1.0
        )

        msg = {
            "task_id": "t3",
            "chunk_ids": [0],
            "swarm_id": "s3",
            "model_ref": "phi-3",
            "task_kind": "inference",
            "chunk_file_path": "/tmp/chunk.bin",
        }
        await ctrl._handle_task(msg)

        assert state.tasks_completed == 1
        assert state.credits_earned == 1.0
        net.send_status.assert_any_await("t3", "completed")

    @pytest.mark.asyncio
    async def test_failed_sandbox_sends_failed_status(self):
        ctrl, state, net, sandbox = _make_controller()
        ctrl._sandbox_active = True
        ctrl._loop = asyncio.get_event_loop()

        from runner import SandboxResult
        sandbox.run.return_value = SandboxResult(
            task_id="t4", chunk_id=0, status="failed",
            output_ref=None, error="OOM", duration_s=0.0
        )

        msg = {
            "task_id": "t4",
            "chunk_ids": [0],
            "swarm_id": "s4",
            "model_ref": "phi-3",
            "task_kind": "inference",
            "chunk_file_path": "/tmp/chunk.bin",
        }
        await ctrl._handle_task(msg)

        assert state.tasks_completed == 0
        net.send_status.assert_any_await("t4", "failed")
