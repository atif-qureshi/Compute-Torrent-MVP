"""
Docker Sandbox Runtime — DS-1 to DS-6
Implements SandboxRunner: spins up a fresh, disposable container per task,
enforces resource limits, and destroys the container on completion or failure.

DS-1  Fresh container per task — never reused.
DS-2  Hard resource caps: --cpus, --memory, --gpus (NVIDIA toolkit).
DS-3  No host filesystem access outside the mounted working dir; network
      restricted to none by default (narrow egress rule for result upload
      is injected by the caller if needed).
DS-4  --rm flag + explicit force-remove on error: zero leftover state.
DS-5  Crash / timeout / OOM → status "failed" returned; no silent retry.
DS-6  Lifecycle events written to lifecycle_log.LifecycleLog (local only).
"""

from __future__ import annotations

import dataclasses
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from lifecycle_log import LifecycleLog

logger = logging.getLogger("computetorrent.sandbox_runtime.runner")

# ---------------------------------------------------------------------------
# Tuning constants — all overridable via env vars for integration tests
# ---------------------------------------------------------------------------

DEFAULT_CPU_LIMIT = float(os.environ.get("CT_SANDBOX_CPUS", "1.0"))
DEFAULT_MEM_LIMIT = os.environ.get("CT_SANDBOX_MEM", "2g")
DEFAULT_TIMEOUT_S = int(os.environ.get("CT_SANDBOX_TIMEOUT", "300"))
DEFAULT_IMAGE = os.environ.get("CT_SANDBOX_IMAGE", "python:3.11-slim")
NETWORK_MODE = os.environ.get("CT_SANDBOX_NETWORK", "none")   # DS-3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class TaskAssignment:
    """Mirrors the task_assign message shape from the root README."""
    task_id: str
    chunk_ids: list[int]
    swarm_id: str
    model_ref: str
    task_kind: str          # "inference" | "preprocessing" | etc.
    chunk_file_path: Path   # handed off by WebtorrentSync (WT-5)


@dataclasses.dataclass
class SandboxResult:
    task_id: str
    chunk_id: int
    status: str             # "completed" | "failed"
    output_ref: Optional[str]   # path to result file, or None on failure
    error: Optional[str]        # stderr snippet on failure, else None
    duration_s: float


# ---------------------------------------------------------------------------
# Docker availability check (used by desktop_app/docker_preflight.py)
# ---------------------------------------------------------------------------

def docker_is_available() -> bool:
    """Return True if `docker info` exits 0 — i.e. the Docker daemon is up."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

class SandboxRunner:
    """
    Runs one task chunk inside a fresh, isolated Docker container.

    Usage:
        runner = SandboxRunner()
        result = runner.run(task_assignment, chunk_id=7)
        # result.status == "completed" or "failed"
    """

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        cpu_limit: float = DEFAULT_CPU_LIMIT,
        mem_limit: str = DEFAULT_MEM_LIMIT,
        timeout_s: int = DEFAULT_TIMEOUT_S,
        gpu_enabled: bool = False,
        lifecycle_log: Optional[LifecycleLog] = None,
    ):
        self.image = image
        self.cpu_limit = cpu_limit
        self.mem_limit = mem_limit
        self.timeout_s = timeout_s
        self.gpu_enabled = gpu_enabled
        self.log = lifecycle_log or LifecycleLog()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: TaskAssignment, chunk_id: int) -> SandboxResult:
        """
        Execute one chunk inside a disposable container.

        1. Create a temp working directory on the host.
        2. Copy the chunk file into it (the only host path mounted — DS-3).
        3. Build the `docker run` command with all limits (DS-2).
        4. Execute; capture stdout/stderr; enforce timeout (DS-5).
        5. Collect the result file from the working dir.
        6. Destroy the working dir (DS-4, alongside Docker's --rm).
        """
        task_id = task.task_id
        work_dir = Path(tempfile.mkdtemp(prefix=f"ct_{task_id}_{chunk_id}_"))

        self.log.record(task_id, "created", f"chunk={chunk_id} workdir={work_dir}")

        try:
            # Stage the input file into the isolated work dir
            src = Path(task.chunk_file_path)
            if src.exists():
                shutil.copy2(src, work_dir / src.name)

            cmd = self._build_command(task, chunk_id, work_dir)
            logger.debug("docker cmd: %s", " ".join(cmd))

            self.log.record(task_id, "started", f"chunk={chunk_id} image={self.image}")
            t0 = time.monotonic()

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
                duration = time.monotonic() - t0

                if proc.returncode != 0:
                    raise _ContainerError(
                        f"exit {proc.returncode}",
                        stderr=proc.stderr[-2000:],  # last 2 KB
                    )

            except subprocess.TimeoutExpired as exc:
                duration = time.monotonic() - t0
                self._force_remove_container(task_id, chunk_id)
                raise _ContainerError(
                    f"timeout after {self.timeout_s}s", stderr=str(exc)
                ) from exc

            # Collect output — convention: container writes result.json
            output_path = work_dir / "result.json"
            output_ref: Optional[str] = None
            if output_path.exists():
                output_ref = str(output_path)

            self.log.record(task_id, "completed", f"chunk={chunk_id} duration={duration:.1f}s")
            return SandboxResult(
                task_id=task_id,
                chunk_id=chunk_id,
                status="completed",
                output_ref=output_ref,
                error=None,
                duration_s=duration,
            )

        except _ContainerError as exc:
            self.log.record(task_id, "failed", f"chunk={chunk_id} reason={exc.reason}")
            logger.error("Container failed [%s chunk %s]: %s", task_id, chunk_id, exc.reason)
            return SandboxResult(
                task_id=task_id,
                chunk_id=chunk_id,
                status="failed",
                output_ref=None,
                error=exc.stderr,
                duration_s=0.0,
            )

        finally:
            # DS-4: destroy working directory regardless of outcome
            self._cleanup_workdir(work_dir, task_id, chunk_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_command(
        self, task: TaskAssignment, chunk_id: int, work_dir: Path
    ) -> list[str]:
        """Assemble the `docker run` command with all required flags."""
        cmd = [
            "docker", "run",
            "--rm",                                      # DS-4: auto-remove
            f"--network={NETWORK_MODE}",                  # DS-3: no network
            f"--cpus={self.cpu_limit}",                   # DS-2: CPU cap
            f"--memory={self.mem_limit}",                 # DS-2: memory cap
            "--memory-swap=0",                            # disable swap
            f"--name=ct_{task.task_id}_{chunk_id}",      # identifiable name
            "-v", f"{work_dir}:/workspace:rw",           # DS-3: isolated mount
            "-w", "/workspace",
        ]

        # DS-2: GPU scoping via NVIDIA Container Toolkit (only if enabled)
        if self.gpu_enabled:
            cmd += ["--gpus", "all"]

        cmd.append(self.image)

        # Default entrypoint: run the task script if present, else echo done
        cmd += [
            "sh", "-c",
            (
                f"if [ -f /workspace/task_script.py ]; then "
                f"python /workspace/task_script.py; "
                f"else echo '{{\"status\":\"ok\"}}' > /workspace/result.json; fi"
            ),
        ]
        return cmd

    def _force_remove_container(self, task_id: str, chunk_id: int) -> None:
        """Best-effort container force-removal after a timeout."""
        name = f"ct_{task_id}_{chunk_id}"
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, timeout=10
            )
        except Exception as exc:
            logger.warning("Could not force-remove container %s: %s", name, exc)

    def _cleanup_workdir(self, work_dir: Path, task_id: str, chunk_id: int) -> None:
        """DS-4: remove the host-side working directory."""
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
            self.log.record(task_id, "destroyed", f"chunk={chunk_id} workdir removed")
        except Exception as exc:
            logger.warning("Could not clean up workdir %s: %s", work_dir, exc)


# ---------------------------------------------------------------------------
# Internal exception
# ---------------------------------------------------------------------------

class _ContainerError(Exception):
    def __init__(self, reason: str, stderr: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.stderr = stderr
