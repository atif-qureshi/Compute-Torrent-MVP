# WebTorrent File Sync Client — WT-1 to WT-5

**Status:** not yet implemented. MVP Build Order step 4 — join a test
swarm, download a test file, before wiring into the full task flow.

## What it owns
- Join the per-task private WebTorrent swarm named in the task
  assignment, scoped to that task's requestor + assigned seeders (WT-1).
- Download the assigned dataset/model chunk(s), verifying integrity via
  WebTorrent's built-in SHA-1 piece hashing (WT-2).
- Resume-on-failure for interrupted downloads (WT-3).
- Leave the swarm once the result is submitted — per-task swarms are
  torn down after completion, not seeded indefinitely (WT-4).
- Hand the downloaded chunk's path to the Docker Sandbox Runtime as a
  **mounted volume only** — never a raw host-filesystem path outside the
  container's isolated workspace (WT-5).

## Tech
WebTorrent (Node.js implementation), run as a child process / local
service from the desktop app's backend.

## Planned shape
```
webtorrent_sync/
  package.json
  sync_client.js       # joinSwarm(swarmId), downloadChunks(), leaveSwarm()
  bridge.py             # thin Python<->Node bridge so hardware_profiling /
                         # sandbox_runtime (Python) can call into this
  tests/
    test_sync_client.js # spin up a local test swarm + seed file, confirm
                         # download + resume-on-failure + swarm teardown
```

## Interface with the rest of the app
- Triggered by a `task_assign` message from the Networking Client.
- Output: a local chunk file path, passed to `sandbox_runtime` as a
  mount (see WT-5 — this is a hard boundary, not a suggestion).
