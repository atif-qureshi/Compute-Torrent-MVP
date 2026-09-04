# Networking Client — NC-1 to NC-6

**Status:** not yet implemented. MVP Build Order step 3 — connect and
send/receive fake messages against a mock server before wiring to the
real Tracker.

## What it owns
- Open a WebSocket connection on launch (after hardware profiling) and
  register the node with its profile + tier (NC-1).
- Persistent online/idle heartbeat (NC-2).
- Listen for `task_assign` messages: chunk ID, model script reference,
  dataset reference, expected chunk count (NC-3).
- Attempt a STUN handshake for a direct WebRTC upgrade; on failure, fall
  back to the relay silently — no user-facing error (NC-4).
- Push `status_update` messages (queued → downloading → running →
  completed/failed) over the same connection (NC-5).
- Handle disconnect/reconnect: attempt to resume a dropped task; if
  resume fails, mark it failed locally and re-register (NC-6).

## Interface (black box on the other side — Partner 1's Tracker/Relay)
The message schema is the actual contract we build against; see the
root README's "Data Contracts" section for the current draft
(`register`, `task_assign`, `status_update`, `result_submit`). Per NFR-5,
nothing in this module should assume anything about the Tracker's
internal implementation beyond that schema.

## Planned shape
```
networking_client/
  ws_client.py        # NetworkingClient: connect(), register(), on_task_assign(),
                       # send_status(), heartbeat loop, reconnect-with-backoff
  webrtc_upgrade.py    # STUN handshake attempt, silent fallback to relay
  mock_tracker.py      # a tiny local WebSocket server for step-3 testing,
                        # standing in for Partner 1's real Tracker
  tests/
    test_ws_client.py  # exercise register/task_assign/status_update/reconnect
                        # against mock_tracker.py
```
