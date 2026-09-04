# Docker Sandbox Runtime — DS-1 to DS-6

**Status:** not yet implemented. Next in the MVP Build Order (step 2) —
standalone, testable with a dummy script in an isolated container, no
network dependency needed.

## What it owns
- Spin up a **fresh, disposable container per task** (DS-1) — never reused.
- Enforce hard resource limits: capped CPU, capped memory, GPU scoped via
  the NVIDIA Container Toolkit for the assigned task only (DS-2).
- No network access except pulling the assigned chunk and returning the
  result; no host filesystem access outside the container's mounted
  working directory (DS-3).
- Destroy the container immediately on completion or failure — no
  leftover state or files (DS-4).
- On crash / timeout / resource-limit breach, report `status: failed`
  back through the Networking Client rather than retrying silently (DS-5).
- Log lifecycle events (created, started, completed, destroyed) locally
  for user-facing debugging — never expose raw logs to the network (DS-6).

## Planned shape
```
sandbox_runtime/
  runner.py          # SandboxRunner.run(task) -> Result, wraps `docker run`
                      # with --rm, --network=none (+ narrow egress rule),
                      # --cpus, --memory, --gpus per NVIDIA Container Toolkit
  lifecycle_log.py    # local JSONL logger for created/started/completed/destroyed
  tests/
    test_runner.py    # run a dummy echo/sleep script through the real
                       # Docker Engine on the dev machine; assert the
                       # container is gone afterward and files are wiped
```

## Interface with the rest of the app
- Input: a task assignment (`task_assign` message shape, see root README)
  plus the chunk file path handed off by the WebTorrent Sync Client
  (mounted as a volume — WT-5).
- Output: a result file path + a `status_update` (`completed`/`failed`)
  pushed through the Networking Client.

## Dependency note
Requires Docker Engine + NVIDIA Container Toolkit on the host. NFR-3
("degrade gracefully if Docker isn't available") needs a `docker info`
pre-flight check on app launch with a clear install-guidance message —
that check belongs in the Desktop App shell (`desktop_app/`), not here.
