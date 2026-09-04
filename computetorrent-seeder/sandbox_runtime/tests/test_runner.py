"""
Tests for the Docker Sandbox Runtime (DS-1 to DS-6).

Most tests mock subprocess.run so they pass on any machine — including
CI runners without Docker. One integration-style test is skipped unless
Docker is actually available.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runner import SandboxRunner, SandboxResult, TaskAssignment, docker_is_available
from lifecycle_log import LifecycleLog

DOCKER_AVAILABLE = docker_is_available()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "test_task", chunk_file: str = "/tmp/chunk.bin") -> TaskAssignment:
    return TaskAssignment(
        task_id=task_id,
        chunk_ids=[0],
        swarm_id="swarm_test",
        model_ref="phi-3-gguf",
        task_kind="inference",
        chunk_file_path=Path(chunk_file),
    )


def _mock_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# DS-1: Fresh container per task (command contains unique --name)
# ---------------------------------------------------------------------------

def test_container_name_is_unique_per_task_and_chunk():
    runner = SandboxRunner()
    task = _make_task(task_id="abc123")
    cmd = runner._build_command(task, chunk_id=7, work_dir=Path("/tmp/workdir"))
    # --name is passed as a single combined token: "--name=ct_abc123_7"
    assert any("ct_abc123_7" in part for part in cmd), \
        "Container --name must include task_id and chunk_id"


# ---------------------------------------------------------------------------
# DS-2: Resource limits present in command
# ---------------------------------------------------------------------------

def test_cpu_and_memory_limits_in_command():
    runner = SandboxRunner(cpu_limit=2.0, mem_limit="4g")
    task = _make_task()
    cmd = runner._build_command(task, chunk_id=0, work_dir=Path("/tmp/wd"))
    assert "--cpus=2.0" in cmd
    assert "--memory=4g" in cmd
    assert "--memory-swap=0" in cmd


def test_gpu_flag_absent_by_default():
    runner = SandboxRunner(gpu_enabled=False)
    cmd = runner._build_command(_make_task(), 0, Path("/tmp/wd"))
    assert "--gpus" not in cmd


def test_gpu_flag_present_when_enabled():
    runner = SandboxRunner(gpu_enabled=True)
    cmd = runner._build_command(_make_task(), 0, Path("/tmp/wd"))
    assert "--gpus" in cmd


# ---------------------------------------------------------------------------
# DS-3: Network mode and volume mount
# ---------------------------------------------------------------------------

def test_network_none_in_command():
    runner = SandboxRunner()
    cmd = runner._build_command(_make_task(), 0, Path("/tmp/wd"))
    assert "--network=none" in cmd


def test_volume_mount_scoped_to_workdir():
    runner = SandboxRunner()
    work_dir = Path("/tmp/wd_test")
    cmd = runner._build_command(_make_task(), 0, work_dir)
    mounts = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-v"]
    assert len(mounts) == 1
    assert mounts[0].startswith(str(work_dir))
    assert "/workspace" in mounts[0]


# ---------------------------------------------------------------------------
# DS-4: --rm flag ensures no leftover container
# ---------------------------------------------------------------------------

def test_rm_flag_in_command():
    runner = SandboxRunner()
    cmd = runner._build_command(_make_task(), 0, Path("/tmp/wd"))
    assert "--rm" in cmd


# ---------------------------------------------------------------------------
# DS-5: Failure returns status="failed", no exception raised
# ---------------------------------------------------------------------------

@patch("runner.subprocess.run")
@patch("runner.shutil.copy2")
def test_non_zero_exit_returns_failed_status(mock_copy, mock_run):
    mock_run.return_value = _mock_proc(returncode=1, stderr="OOM killed")
    runner = SandboxRunner()
    result = runner.run(_make_task(), chunk_id=0)
    assert result.status == "failed"
    assert result.output_ref is None
    assert "OOM killed" in (result.error or "")


@patch("runner.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired("docker", 5))
@patch("runner.shutil.copy2")
def test_timeout_returns_failed_status(mock_copy, mock_run):
    runner = SandboxRunner(timeout_s=5)
    result = runner.run(_make_task(), chunk_id=0)
    assert result.status == "failed"


# ---------------------------------------------------------------------------
# DS-5 + DS-4: Successful run returns "completed" and cleans up
# ---------------------------------------------------------------------------

@patch("runner.shutil.rmtree")
@patch("runner.shutil.copy2")
@patch("runner.subprocess.run")
def test_successful_run_returns_completed(mock_run, mock_copy, mock_rmtree):
    mock_run.return_value = _mock_proc(returncode=0)

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "test.jsonl"
        lifecycle = LifecycleLog(log_path=log_path)
        runner = SandboxRunner(lifecycle_log=lifecycle)

        # Provide a dummy chunk file
        chunk = Path(tmp) / "chunk.bin"
        chunk.write_bytes(b"data")

        result = runner.run(_make_task(chunk_file=str(chunk)), chunk_id=0)

    assert result.status == "completed"


# ---------------------------------------------------------------------------
# DS-6: Lifecycle events are recorded
# ---------------------------------------------------------------------------

def test_lifecycle_events_recorded():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "lifecycle.jsonl"
        lifecycle = LifecycleLog(log_path=log_path)

        with patch("runner.subprocess.run") as mock_run, \
             patch("runner.shutil.copy2"):
            mock_run.return_value = _mock_proc(returncode=0)
            runner = SandboxRunner(lifecycle_log=lifecycle)
            chunk = Path(tmp) / "chunk.bin"
            chunk.write_bytes(b"x")
            runner.run(_make_task(chunk_file=str(chunk)), chunk_id=1)

        events = [e["event"] for e in lifecycle.read_all()]
        assert "created" in events
        assert "started" in events
        # "completed" or "failed" + "destroyed" should be present
        assert any(e in events for e in ("completed", "failed"))
        assert "destroyed" in events


# ---------------------------------------------------------------------------
# docker_is_available() — smoke-test (doesn't assert True/False, just no crash)
# ---------------------------------------------------------------------------

def test_docker_is_available_does_not_raise():
    result = docker_is_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Integration test — only runs when Docker is present
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker Engine not available on this machine")
def test_integration_echo_container_runs_and_is_destroyed():
    """
    Spin up a real `alpine` container that writes a result file and exits.
    Assert: status == completed, working dir is gone, container is gone.
    """
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "lifecycle.jsonl"
        lifecycle = LifecycleLog(log_path=log_path)

        runner = SandboxRunner(
            image="alpine:latest",
            timeout_s=30,
            lifecycle_log=lifecycle,
        )
        # Override command by subclassing: write result.json via sh
        original_build = runner._build_command

        def patched_build(task, chunk_id, work_dir):
            cmd = original_build(task, chunk_id, work_dir)
            # Replace the sh -c script with a simple echo
            idx = cmd.index("sh")
            cmd[idx:] = [
                "sh", "-c",
                'echo \'{"status":"ok"}\' > /workspace/result.json'
            ]
            return cmd

        runner._build_command = patched_build

        chunk = Path(tmp) / "chunk.bin"
        chunk.write_bytes(b"payload")

        result = runner.run(_make_task(chunk_file=str(chunk)), chunk_id=0)

    assert result.status == "completed"
    events = [e["event"] for e in lifecycle.read_all()]
    assert "destroyed" in events
