# ComputeTorrent — Provider (Seeder) Desktop App & Web Portal (Partner 2)

Implements Partner 2's ownership area from *ComputeTorrent Working &
Architecture v3*: the Seeder desktop application (hardware profiling,
networking, sandboxed execution, WebTorrent sync) and the Requestor-facing
web portal.

## MVP goal

> A user installs the Seeder app, the app detects their hardware,
> connects to the network, receives a task, runs it safely inside an
> isolated container, and returns a result — without ever putting the
> user's real files or system at risk.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                PROVIDER DESKTOP APPLICATION               │
│                                                             │
│  ┌───────────────┐   ┌──────────────────┐                 │
│  │ Hardware       │   │ Networking Client │──► (to Tracker/│
│  │ Profiling      │   │ (WebSocket +      │    Relay –     │
│  │ Module         │   │  optional WebRTC) │    external)   │
│  └───────┬────────┘   └────────┬──────────┘                │
│          │                     │                            │
│          ▼                     ▼                            │
│  ┌───────────────────────────────────────────┐             │
│  │        Task Receiver / Dispatcher UI        │             │
│  └───────┬─────────────────────┬──────────────┘             │
│          │                     │                            │
│          ▼                     ▼                            │
│  ┌───────────────┐   ┌──────────────────────┐              │
│  │ WebTorrent     │   │ Docker Sandbox        │              │
│  │ File Sync      │──►│ Runtime (execution)   │              │
│  │ Client         │   │                       │              │
│  └───────────────┘   └──────────┬────────────┘              │
│                                  │                            │
│                                  ▼                            │
│                       Result → returned via Networking Client │
└─────────────────────────────────────────────────────────┘

              (separately, on the requestor side)
┌─────────────────────────────────────────────────────────┐
│           WEB PORTAL FRONTEND (Requestor dashboard)        │
│  Task submission form → Live status view (Socket.io) →     │
│  Result display / download                                  │
└─────────────────────────────────────────────────────────┘
```

Anything belonging to the Coordination/Tracker Server, Task Slicing
Engine, or Verification logic is Partner 1's — treated here strictly as
an external interface (see **Data Contracts** below).

## MVP Build Order & current status

| # | Component | Status |
|---|-----------|--------|
| 1 | `hardware_profiling/` — HP-1 to HP-5 | ✅ **built & tested** (9/9 tests passing) |
| 2 | `sandbox_runtime/` — DS-1 to DS-6 | ✅ **built & tested** (12/13 — 1 skipped, needs Docker) |
| 3 | `networking_client/` — NC-1 to NC-6 | ✅ **built & tested** (10/10 tests passing) |
| 4 | `webtorrent_sync/` — WT-1 to WT-5 | ✅ **built & tested** (10/10 tests passing) |
| 5 | `desktop_app/` — APP-1 to APP-6 | ✅ **built & tested** (35/35 tests passing) |
| 6 | Package as installable executable | ✅ **done** — PyInstaller `.spec` + `build.bat` |
| 7 | `web_portal/` — WP-1 to WP-5 | ✅ **built** — Next.js 16 + Tailwind + Socket.io, `npm run build` clean |

Each unbuilt module's `README.md` carries its requirement IDs and planned
file layout, so the next piece can be picked up without re-deriving the
spec.

## Running what's built

```bash
# Hardware profiling (no Docker/network needed)
cd hardware_profiling
pip install -r requirements.txt
python demo.py
python -m pytest tests/

# Sandbox runtime
cd sandbox_runtime
pip install -r requirements.txt
python -m pytest tests/

# Networking client (mock tracker, no live network)
cd networking_client
pip install -r requirements.txt
python -m pytest tests/ --asyncio-mode=auto

# WebTorrent sync (Node.js, mocked)
cd webtorrent_sync
npm install
npm test

# Desktop app
cd desktop_app
pip install -r requirements.txt
python -m pytest tests/ --asyncio-mode=auto
python main.py                  # launches the GUI (needs customtkinter)

# Web portal
cd web_portal
npm install
npm run dev                     # http://localhost:3000
npm run build                   # production bundle

# Package desktop app as .exe (Windows)
cd ..
desktop_app\build.bat
```

## Data Contracts (working draft against Partner 1's Tracker/Relay)

```json
// register (sent on connect)
{ "type": "register", "profile": { "GPU": "RTX 3060", "VRAM": 12, "CUDA": true, "RAM": 16 }, "tier": 1 }

// task_assign (received)
{ "type": "task_assign", "task_id": "abc123", "chunk_ids": [7, 14], "swarm_id": "swarm_abc123", "model_ref": "phi-3-gguf", "task_kind": "inference" }

// status_update (sent)
{ "type": "status_update", "task_id": "abc123", "state": "running" }

// result_submit (sent)
{ "type": "result_submit", "task_id": "abc123", "chunk_id": 7, "output_ref": "result_chunk7.json" }
```

Field names to be finalized jointly with Partner 1 — `hardware_profiling`
already produces payloads matching the `register` shape
(`HardwareProfiler.registration_payload()`).

## Non-functional requirements this scaffold already respects

- **NFR-3** (degrade gracefully without Docker/GPU): `hardware_profiling`
  never raises on a GPU-less machine — verified by
  `test_profiler_degrades_gracefully_with_no_gpu`.
- **NFR-5** (don't assume Tracker internals): the module boundaries above
  mirror the doc's black-box split — `networking_client` only knows the
  JSON schema, nothing about how Partner 1's Tracker is implemented.

## Next step

Everything in the MVP build order is complete. To run the full stack:

1. Start the web portal: `cd web_portal && npm run dev`
2. Set `NEXT_PUBLIC_TRACKER_URL` (copy `.env.local.example` → `.env.local`) to Partner 1's Tracker URL.
3. Launch the desktop app: `cd desktop_app && python main.py` (set `CT_TRACKER_URL` to the same URL).
4. Package for distribution: `desktop_app\build.bat` produces `dist\ComputeTorrentSeeder.exe`.
