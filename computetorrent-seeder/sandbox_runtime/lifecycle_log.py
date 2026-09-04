"""
Lifecycle Logger — DS-6
Writes container lifecycle events (created, started, completed, destroyed)
to a local JSONL file. Never exposes raw logs to the network.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger("computetorrent.sandbox_runtime.lifecycle")

EventKind = Literal["created", "started", "completed", "destroyed", "failed"]

# Default log path — sits next to this file; Desktop App can override via env var.
DEFAULT_LOG_PATH = Path(os.environ.get(
    "CT_SANDBOX_LOG_PATH",
    Path(__file__).parent / "sandbox_lifecycle.jsonl"
))


class LifecycleLog:
    """Append-only JSONL log for container lifecycle events (DS-6).

    Each line is a JSON object:
      { "ts": "<ISO-8601>", "task_id": "...", "event": "created|started|...", "detail": "..." }
    """

    def __init__(self, log_path: Path = DEFAULT_LOG_PATH):
        self.log_path = log_path

    def record(self, task_id: str, event: EventKind, detail: str = "") -> None:
        entry = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "task_id": task_id,
            "event": event,
            "detail": detail,
        }
        logger.debug("Lifecycle [%s] %s — %s", task_id, event, detail)
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except OSError as exc:
            # Non-fatal — a logging failure must never kill the main flow.
            logger.warning("Could not write lifecycle log: %s", exc)

    def read_all(self) -> list[dict]:
        """Return all log entries as a list of dicts (for tests / UI)."""
        if not self.log_path.exists():
            return []
        entries = []
        with open(self.log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries
