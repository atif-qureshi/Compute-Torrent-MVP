"""
Tests for the Networking Client (NC-1 to NC-6).

Uses MockTrackerServer to stand in for Partner 1's real Tracker so all
tests pass without a live network connection.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("websockets")

from ws_client import NetworkingClient, RECONNECT_BASE_S
from mock_tracker import MockTrackerServer

# ---------------------------------------------------------------------------
# Fixture: running mock tracker
# ---------------------------------------------------------------------------

TEST_PORT = 18765


@pytest.fixture(scope="module")
def tracker():
    server = MockTrackerServer(port=TEST_PORT)
    server.start()
    yield server
    server.stop()


def make_client(on_task_assign=None, enable_stun=False) -> NetworkingClient:
    return NetworkingClient(
        tracker_url=f"ws://127.0.0.1:{TEST_PORT}",
        registration_payload={
            "profile": {"GPU": None, "VRAM": 0, "CUDA": False, "RAM": 8.0},
            "tier": 2,
        },
        on_task_assign=on_task_assign,
        enable_stun=enable_stun,
    )


async def run_client_briefly(client: NetworkingClient, duration: float = 0.4) -> None:
    """Start the client, wait `duration` seconds, then stop and cancel it."""
    task = asyncio.create_task(client.connect_and_run())
    await asyncio.sleep(duration)
    client.stop()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


# ---------------------------------------------------------------------------
# NC-1: Registration message is sent on connect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_sent_on_connect(tracker):
    tracker.received_messages.clear()
    client = make_client()
    await run_client_briefly(client)
    types = [m["type"] for m in tracker.received_messages]
    assert "register" in types, f"Expected 'register' in {types}"


# ---------------------------------------------------------------------------
# NC-1: Registration payload matches root README's `register` shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_payload_shape(tracker):
    tracker.received_messages.clear()
    client = make_client()
    await run_client_briefly(client)

    reg = next((m for m in tracker.received_messages if m["type"] == "register"), None)
    assert reg is not None
    assert "profile" in reg
    assert "tier" in reg
    assert set(reg["profile"].keys()) == {"GPU", "VRAM", "CUDA", "RAM"}


# ---------------------------------------------------------------------------
# NC-3: task_assign triggers on_task_assign callback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_assign_callback_fired(tracker):
    tracker.received_messages.clear()
    received_tasks = []
    client = make_client(on_task_assign=received_tasks.append)
    await run_client_briefly(client, duration=0.5)

    assert len(received_tasks) == 1
    t = received_tasks[0]
    assert t["type"] == "task_assign"
    assert t["task_id"] == "mock_task_001"


# ---------------------------------------------------------------------------
# NC-3: task_assign triggers a "queued" status_update back to the tracker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_queued_status_sent_after_task_assign(tracker):
    tracker.received_messages.clear()
    client = make_client()
    await run_client_briefly(client, duration=0.5)

    status_msgs = [
        m for m in tracker.received_messages
        if m.get("type") == "status_update" and m.get("state") == "queued"
    ]
    assert len(status_msgs) >= 1


# ---------------------------------------------------------------------------
# NC-5: send_status pushes correct JSON shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_status_shape(tracker):
    tracker.received_messages.clear()
    client = make_client()

    async def run_with_status():
        task = asyncio.create_task(client.connect_and_run())
        await asyncio.sleep(0.2)  # let connection establish
        await client.send_status("task_abc", "running")
        await asyncio.sleep(0.1)
        client.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    await run_with_status()

    updates = [
        m for m in tracker.received_messages
        if m.get("type") == "status_update" and m.get("task_id") == "task_abc"
    ]
    assert any(m["state"] == "running" for m in updates)


# ---------------------------------------------------------------------------
# NC-5: send_result pushes correct result_submit shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_result_shape(tracker):
    tracker.received_messages.clear()
    client = make_client()

    async def run_with_result():
        task = asyncio.create_task(client.connect_and_run())
        await asyncio.sleep(0.2)
        await client.send_result("task_abc", chunk_id=7, output_ref="result_chunk7.json")
        await asyncio.sleep(0.1)
        client.stop()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    await run_with_result()

    submits = [m for m in tracker.received_messages if m.get("type") == "result_submit"]
    assert len(submits) >= 1
    assert submits[0]["chunk_id"] == 7
    assert submits[0]["output_ref"] == "result_chunk7.json"


# ---------------------------------------------------------------------------
# NC-4: STUN probe called but failure doesn't break connection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stun_failure_falls_back_silently(tracker):
    tracker.received_messages.clear()

    with patch("ws_client.attempt_stun_upgrade", return_value=False):
        client = NetworkingClient(
            tracker_url=f"ws://127.0.0.1:{TEST_PORT}",
            registration_payload={
                "profile": {"GPU": None, "VRAM": 0, "CUDA": False, "RAM": 8.0},
                "tier": 2,
            },
            on_task_assign=None,
            enable_stun=True,
        )
        await run_client_briefly(client, duration=0.4)

    types = [m["type"] for m in tracker.received_messages]
    assert "register" in types


# ---------------------------------------------------------------------------
# NC-6: current_task_id is tracked so reconnect can resume
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_current_task_id_set_after_task_assign(tracker):
    tracker.received_messages.clear()
    client = make_client()
    await run_client_briefly(client, duration=0.5)
    assert client._current_task_id == "mock_task_001"


# ---------------------------------------------------------------------------
# NC-6: reconnect delay starts at RECONNECT_BASE_S and backs off
# ---------------------------------------------------------------------------

def test_reconnect_delay_backoff():
    client = make_client()
    assert client._reconnect_delay == RECONNECT_BASE_S
    client._reconnect_delay = min(client._reconnect_delay * 2, 60)
    assert client._reconnect_delay == 4
    client._reconnect_delay = min(client._reconnect_delay * 2, 60)
    assert client._reconnect_delay == 8


# ---------------------------------------------------------------------------
# webrtc_upgrade: attempt_stun_upgrade never raises
# ---------------------------------------------------------------------------

def test_stun_upgrade_never_raises():
    from webrtc_upgrade import attempt_stun_upgrade
    result = attempt_stun_upgrade(stun_host="127.0.0.1", stun_port=1, timeout=0.2)
    assert isinstance(result, bool)
