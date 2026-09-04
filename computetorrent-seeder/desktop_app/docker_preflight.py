"""
Docker pre-flight check — NFR-3 / APP-6

Run once on app launch before anything else. If Docker is unavailable
the app shows a clear install-guidance message and refuses to start
seeding. This check is the sole enforcement point for APP-6 ("no task
ever runs without sandbox_runtime active").
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Optional

logger = logging.getLogger("computetorrent.desktop_app.docker_preflight")

DOCKER_INSTALL_URL = "https://docs.docker.com/get-docker/"
NVIDIA_TOOLKIT_URL = "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DockerPreflightResult:
    def __init__(self, ok: bool, message: str, nvidia_ok: Optional[bool] = None):
        self.ok = ok
        self.message = message
        self.nvidia_ok = nvidia_ok   # None = not checked, True/False = checked

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:  # pragma: no cover
        return f"DockerPreflightResult(ok={self.ok}, nvidia_ok={self.nvidia_ok})"


def run_preflight(check_nvidia: bool = False) -> DockerPreflightResult:
    """
    Check Docker Engine availability (and optionally NVIDIA Container Toolkit).

    Returns a DockerPreflightResult whose `.ok` is True only if Docker is up.
    Never raises — all errors are captured into the result message.
    """
    docker_ok, docker_msg = _check_docker()
    if not docker_ok:
        return DockerPreflightResult(
            ok=False,
            message=(
                f"Docker Engine not found or not running.\n\n"
                f"{docker_msg}\n\n"
                f"Install Docker Desktop from: {DOCKER_INSTALL_URL}\n"
                "Then relaunch ComputeTorrent."
            ),
        )

    nvidia_ok: Optional[bool] = None
    if check_nvidia:
        nvidia_ok = _check_nvidia()
        if not nvidia_ok:
            logger.info("NVIDIA Container Toolkit not available — GPU tasks will be skipped.")

    return DockerPreflightResult(
        ok=True,
        message="Docker is available." + (
            " NVIDIA Container Toolkit detected." if nvidia_ok else ""
        ),
        nvidia_ok=nvidia_ok,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_docker() -> tuple[bool, str]:
    """Return (ok, detail_message)."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, "docker info exited 0"
        return False, result.stderr.strip()[:500]
    except FileNotFoundError:
        return False, "docker executable not found in PATH"
    except subprocess.TimeoutExpired:
        return False, "docker info timed out after 10s"
    except Exception as exc:
        return False, str(exc)


def _check_nvidia() -> bool:
    """Return True if nvidia-container-cli is reachable."""
    try:
        result = subprocess.run(
            ["nvidia-container-cli", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False
