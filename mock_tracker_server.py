"""
ComputeTorrent — Mock Tracker / Relay Server

Runs on port 8080 and serves both:
  1. WebSocket endpoint  ws://localhost:8080
     • Accepts `register` from the desktop seeder app
     • Sends one `task_assign` after registration
     • Echoes `status_update` / `result_submit` / `heartbeat` as ack
     • Re-broadcasts task status as Socket.io events so the web portal
       live dashboard updates in real time

  2. HTTP REST endpoints  http://localhost:8080
     • POST /api/tasks          — WP-1: receive a submitted task
     • GET  /api/tasks          — WP-4: list task history
     • GET  /api/tasks/{taskId} — WP-3: fetch single task result

  3. Socket.io endpoint  http://localhost:8080  (via python-socketio)
     • Emits task:status  → { taskId, state, seederCount, chunksTotal, chunksDone }
     • Emits task:complete → { taskId, outputRef }

Usage:
    python mock_tracker_server.py

Stop with Ctrl-C.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from typing import Any

import aiohttp.web as web
import socketio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mock_tracker")

HOST = "0.0.0.0"
PORT = int(os.environ.get("CT_TRACKER_PORT", "8080"))

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

tasks: dict[str, dict] = {}          # taskId → task record
registered_seeders: list[dict] = []  # list of seeder profiles

# ---------------------------------------------------------------------------
# Socket.io server (for web portal live updates)
# ---------------------------------------------------------------------------

sio = socketio.AsyncServer(
    async_mode="aiohttp",
    cors_allowed_origins="*",
)


async def _broadcast_status(task_id: str, state: str,
                             seeder_count: int = 1,
                             chunks_total: int = 4,
                             chunks_done: int = 0) -> None:
    await sio.emit("task:status", {
        "taskId": task_id,
        "state": state,
        "seederCount": seeder_count,
        "chunksTotal": chunks_total,
        "chunksDone": chunks_done,
    })
    logger.info("[Socket.io] task:status %s → %s (%d/%d chunks)", task_id, state, chunks_done, chunks_total)


async def _simulate_task_progress(task_id: str) -> None:
    """Fake a task running through all states so the web portal live view works."""
    chunks_total = 4
    await asyncio.sleep(1)
    await _broadcast_status(task_id, "downloading", seeder_count=1, chunks_total=chunks_total, chunks_done=0)
    tasks[task_id]["status"] = "downloading"

    for i in range(1, chunks_total + 1):
        await asyncio.sleep(1.5)
        await _broadcast_status(task_id, "running", seeder_count=1, chunks_total=chunks_total, chunks_done=i)
        tasks[task_id]["status"] = "running"

    await asyncio.sleep(1)
    tasks[task_id]["status"] = "completed"
    tasks[task_id]["outputRef"] = f"http://localhost:{PORT}/results/{task_id}/output.json"
    await _broadcast_status(task_id, "completed", seeder_count=1, chunks_total=chunks_total, chunks_done=chunks_total)
    await sio.emit("task:complete", {
        "taskId": task_id,
        "outputRef": tasks[task_id]["outputRef"],
    })
    logger.info("[Socket.io] task:complete %s", task_id)


# ---------------------------------------------------------------------------
# WebSocket handler — for the desktop seeder app
# ---------------------------------------------------------------------------

SAMPLE_TASK = {
    "type": "task_assign",
    "task_id": None,           # filled in per-connection
    "chunk_ids": [0, 1, 2, 3],
    "swarm_id": "swarm_demo",
    "model_ref": "phi-3-gguf",
    "task_kind": "inference",
}


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info("[WS] Seeder connected from %s", request.remote)

    task_id = f"task_{uuid.uuid4().hex[:8]}"

    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                data: dict = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")
            logger.info("[WS] ← %s", msg_type)

            if msg_type == "register":
                registered_seeders.append(data)
                await ws.send_str(json.dumps({"type": "registered", "ok": True}))
                logger.info("[WS] → registered (tier=%s)", data.get("tier"))

                # Send a task assignment after a short delay
                await asyncio.sleep(0.5)
                task = {**SAMPLE_TASK, "task_id": task_id}
                # Register the task in our store so the REST API can see it
                tasks[task_id] = {
                    "taskId": task_id,
                    "taskKind": "inference",
                    "modelRef": "phi-3-gguf",
                    "submittedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "status": "queued",
                    "outputRef": None,
                }
                await ws.send_str(json.dumps(task))
                logger.info("[WS] → task_assign %s", task_id)
                # Start simulated progress for web portal
                asyncio.create_task(_simulate_task_progress(task_id))

            elif msg_type in ("status_update", "result_submit", "heartbeat"):
                # Update our task store if we have it
                if msg_type == "status_update" and data.get("task_id") in tasks:
                    tasks[data["task_id"]]["status"] = data.get("state", "unknown")
                await ws.send_str(json.dumps({"type": "ack", "ref": msg_type}))
                logger.info("[WS] → ack %s", msg_type)

        elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
            break

    logger.info("[WS] Seeder disconnected")
    return ws


# ---------------------------------------------------------------------------
# REST handlers — for the web portal
# ---------------------------------------------------------------------------

async def _post_tasks(request: web.Request) -> web.Response:
    """WP-1: Submit a new task."""
    try:
        form = await request.post()
    except Exception:
        form = {}
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    task_kind = form.get("taskKind", "inference")
    model_ref = form.get("modelRef", "unknown")

    tasks[task_id] = {
        "taskId": task_id,
        "taskKind": task_kind,
        "modelRef": model_ref,
        "submittedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "queued",
        "outputRef": None,
        "swarmId": f"swarm_{task_id}",
    }
    logger.info("[REST] POST /api/tasks → %s (%s)", task_id, task_kind)
    asyncio.create_task(_simulate_task_progress(task_id))
    return web.json_response({
        "taskId": task_id,
        "swarmId": tasks[task_id]["swarmId"],
        "status": "queued",
    })


async def _get_tasks(request: web.Request) -> web.Response:
    """WP-4: List all tasks."""
    return web.json_response(list(tasks.values()))


async def _get_task(request: web.Request) -> web.Response:
    """WP-3: Get single task result."""
    task_id = request.match_info["taskId"]
    task = tasks.get(task_id)
    if not task:
        raise web.HTTPNotFound(reason=f"Task {task_id} not found")
    return web.json_response(task)


# ---------------------------------------------------------------------------
# App assembly
# ---------------------------------------------------------------------------

def make_app() -> web.Application:
    app = web.Application()
    sio.attach(app)  # mounts socket.io at /socket.io/

    app.router.add_get("/ws", _ws_handler)
    app.router.add_post("/api/tasks", _post_tasks)
    app.router.add_get("/api/tasks", _get_tasks)
    app.router.add_get("/api/tasks/{taskId}", _get_task)

    # CORS headers for web portal (development)
    @web.middleware
    async def cors_middleware(request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    app.middlewares.append(cors_middleware)
    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════╗
║      ComputeTorrent Mock Tracker — starting up       ║
╠══════════════════════════════════════════════════════╣
║  WebSocket (desktop app)  ws://localhost:{PORT}/ws       ║
║  REST API  (web portal)   http://localhost:{PORT}/api    ║
║  Socket.io (live updates) http://localhost:{PORT}        ║
╚══════════════════════════════════════════════════════╝
Press Ctrl-C to stop.
""")
    app = make_app()
    web.run_app(app, host=HOST, port=PORT, print=lambda _: None)
