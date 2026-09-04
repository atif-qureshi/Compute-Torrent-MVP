"""
Python ↔ Node.js bridge for the WebTorrent Sync Client — WT-5

The rest of the backend (hardware_profiling, sandbox_runtime, networking_client)
is Python. This thin bridge lets Python code start and talk to the Node.js
sync_client.js process via stdin/stdout JSON-RPC, so the Python controller
can trigger downloads and get back chunk file paths without Node knowledge.

Protocol (newline-delimited JSON):
  Python → Node:
    { "id": 1, "method": "joinSwarm",    "params": { "swarmId": "...", "magnetUri": "..." } }
    { "id": 2, "method": "leaveSwarm",   "params": { "swarmId": "..." } }
    { "id": 3, "method": "resolveChunkPath", "params": { "swarmId": "...", "filename": "..." } }
    { "id": 4, "method": "shutdown" }

  Node → Python:
    { "id": 1, "result": "/path/to/chunk.bin" }   # success
    { "id": 1, "error":  "message" }               # failure
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("computetorrent.webtorrent_sync.bridge")

_NODE_SCRIPT = Path(__file__).parent / "bridge_server.js"


class WebtorrentBridge:
    """
    Manages a long-lived Node.js child process running bridge_server.js.

    Usage:
        bridge = WebtorrentBridge()
        bridge.start()
        chunk_path = bridge.join_swarm("swarm_abc123", "magnet:?xt=...")
        bridge.leave_swarm("swarm_abc123")
        bridge.stop()
    """

    def __init__(self, node_script: Path = _NODE_SCRIPT):
        self._script = node_script
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._pending: dict[int, threading.Event] = {}
        self._results: dict[int, dict] = {}
        self._next_id = 1
        self._reader_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the Node.js bridge process."""
        self._proc = subprocess.Popen(
            ["node", str(self._script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        logger.info("WebtorrentBridge started (pid %s)", self._proc.pid)

    def stop(self) -> None:
        """Send shutdown and wait for the process to exit."""
        try:
            self._send_request("shutdown", {})
        except Exception:
            pass
        if self._proc:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        logger.info("WebtorrentBridge stopped.")

    def join_swarm(self, swarm_id: str, magnet_uri: str) -> str:
        """WT-1/WT-2/WT-3: Download chunks; return local file path."""
        return self._call("joinSwarm", {"swarmId": swarm_id, "magnetUri": magnet_uri})

    def leave_swarm(self, swarm_id: str) -> None:
        """WT-4: Leave the swarm after result submission."""
        self._call("leaveSwarm", {"swarmId": swarm_id})

    def resolve_chunk_path(self, swarm_id: str, filename: str) -> str:
        """WT-5: Get a safe, validated chunk path for sandbox mounting."""
        return self._call("resolveChunkPath", {"swarmId": swarm_id, "filename": filename})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call(self, method: str, params: dict) -> str:
        req_id, event = self._send_request(method, params)
        if not event.wait(timeout=130):
            raise TimeoutError(f"No response for {method} (id={req_id}) within 130s")
        response = self._results.pop(req_id)
        if "error" in response:
            raise RuntimeError(f"WebtorrentBridge error: {response['error']}")
        return response["result"]

    def _send_request(self, method: str, params: dict) -> tuple[int, threading.Event]:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            event = threading.Event()
            self._pending[req_id] = event

        msg = json.dumps({"id": req_id, "method": method, "params": params}) + "\n"
        if self._proc and self._proc.stdin:
            self._proc.stdin.write(msg)
            self._proc.stdin.flush()
        return req_id, event

    def _read_loop(self) -> None:
        """Background thread: reads JSON lines from Node stdout."""
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                req_id = msg.get("id")
                if req_id in self._pending:
                    self._results[req_id] = msg
                    self._pending.pop(req_id).set()
            except json.JSONDecodeError:
                logger.warning("Non-JSON from Node bridge: %r", line)
