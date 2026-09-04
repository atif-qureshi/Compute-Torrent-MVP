# ComputeTorrent — Provider (Seeder) MVP

> Distributed ML compute network — Partner 2 implementation (Seeder side)

A user installs the Seeder app → app detects hardware → connects to the network → receives a task → runs it safely inside an isolated Docker container → returns the result. Never puts the user's real files or system at risk.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  PROVIDER DESKTOP APPLICATION                 │
│                                                               │
│  ┌─────────────────┐    ┌──────────────────────┐             │
│  │ Hardware         │    │ Networking Client     │──► Tracker │
│  │ Profiling        │    │ WebSocket + WebRTC    │            │
│  └────────┬─────────┘    └──────────┬────────────┘            │
│           │                         │                          │
│           └──────────┬──────────────┘                          │
│                      ▼                                          │
│           ┌──────────────────────┐                             │
│           │  Task Dispatcher UI   │                             │
│           └────┬─────────────────┘                             │
│                │                                                │
│       ┌────────┴────────┐                                       │
│       ▼                 ▼                                       │
│  ┌──────────┐    ┌──────────────────┐                          │
│  │WebTorrent│───►│  Docker Sandbox   │                          │
│  │File Sync │    │  Runtime          │                          │
│  └──────────┘    └────────┬─────────┘                          │
│                            │                                    │
│                            ▼  Result → Networking Client        │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│            WEB PORTAL  (Requestor Dashboard)                  │
│   Submit Task → Live Status (Socket.io) → Download Result     │
└──────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
computetorrent-seeder/
│
├── hardware_profiling/       # HP-1 to HP-5  — GPU/CPU/RAM detection + tier
├── sandbox_runtime/          # DS-1 to DS-6  — Docker isolated execution
├── networking_client/        # NC-1 to NC-6  — WebSocket + WebRTC client
├── webtorrent_sync/          # WT-1 to WT-5  — BitTorrent file sync (Node.js)
├── desktop_app/              # APP-1 to APP-6 — CustomTkinter GUI + system tray
└── web_portal/               # WP-1 to WP-5  — Next.js requestor dashboard
│
├── mock_tracker_server.py    # Local dev tracker (WebSocket + REST + Socket.io)
├── start.bat                 # One-click launch all services
└── stop.bat                  # One-click stop all services
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Desktop App | Python 3.10, CustomTkinter, pystray |
| Hardware Detection | psutil, pynvml |
| Sandbox Runtime | Docker Engine, subprocess |
| Networking | websockets, asyncio, STUN/WebRTC |
| File Sync | WebTorrent (Node.js), Python bridge |
| Web Portal | Next.js 16, React 19, Tailwind CSS 4 |
| Live Updates | Socket.io |
| Packaging | PyInstaller (Windows .exe) |

---

## Test Results

| Module | Tests | Status |
|--------|-------|--------|
| `hardware_profiling` | 9 / 9 | ✅ |
| `sandbox_runtime` | 12 / 13 | ✅ (1 skipped — needs Docker) |
| `networking_client` | 10 / 10 | ✅ |
| `webtorrent_sync` | 10 / 10 | ✅ |
| `desktop_app` | 35 / 35 | ✅ |
| **Total** | **76 / 77** | ✅ |

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- Docker Desktop (running)

### 1. Install Python dependencies
```bash
pip install customtkinter pystray Pillow psutil websockets aiohttp python-socketio
cd computetorrent-seeder/hardware_profiling  && pip install -r requirements.txt
cd computetorrent-seeder/sandbox_runtime     && pip install -r requirements.txt
cd computetorrent-seeder/networking_client   && pip install -r requirements.txt
```

### 2. Install Node dependencies
```bash
cd computetorrent-seeder/webtorrent_sync && npm install
cd computetorrent-seeder/web_portal      && npm install
```

### 3. Run everything (Windows)
```
Double-click:  start.bat
```
This starts:
- **Mock Tracker** on `ws://localhost:8080/ws`
- **Web Portal** on `http://localhost:3000`
- **Desktop App** GUI window

### 4. Stop everything
```
Double-click:  stop.bat
```

---

## Running Tests

```bash
# Python modules
cd computetorrent-seeder/hardware_profiling && python -m pytest tests/ -v
cd computetorrent-seeder/sandbox_runtime    && python -m pytest tests/ -v
cd computetorrent-seeder/networking_client  && python -m pytest tests/ -v --asyncio-mode=auto
cd computetorrent-seeder/desktop_app        && python -m pytest tests/ -v --asyncio-mode=auto

# Node.js module
cd computetorrent-seeder/webtorrent_sync && npm test
```

---

## Data Contracts (Partner 1 Interface)

```json
// register — sent on connect
{ "type": "register", "profile": { "GPU": "RTX 3060", "VRAM": 12, "CUDA": true, "RAM": 16 }, "tier": 1 }

// task_assign — received from Tracker
{ "type": "task_assign", "task_id": "abc123", "chunk_ids": [7, 14], "swarm_id": "swarm_abc123", "model_ref": "phi-3-gguf", "task_kind": "inference" }

// status_update — sent to Tracker
{ "type": "status_update", "task_id": "abc123", "state": "running" }

// result_submit — sent to Tracker
{ "type": "result_submit", "task_id": "abc123", "chunk_id": 7, "output_ref": "result_chunk7.json" }
```

---

## Web Portal Pages

| Route | Requirement | Description |
|-------|-------------|-------------|
| `/` | — | Home / landing |
| `/submit` | WP-1 | Task submission form |
| `/dashboard/[taskId]` | WP-2 | Live swarm status via Socket.io |
| `/results/[taskId]` | WP-3 | Result display + download |
| `/history` | WP-4 | Past tasks + credit history |

---

## Package as .exe (Windows)

```bash
cd computetorrent-seeder
desktop_app\build.bat
# Output: dist\ComputeTorrentSeeder.exe
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CT_TRACKER_URL` | `ws://localhost:8080/ws` | Tracker WebSocket URL |
| `CT_SANDBOX_CPUS` | `1.0` | CPU limit per container |
| `CT_SANDBOX_MEM` | `2g` | Memory limit per container |
| `CT_SANDBOX_TIMEOUT` | `300` | Container timeout (seconds) |
| `NEXT_PUBLIC_TRACKER_URL` | `http://localhost:8080` | Tracker URL for web portal |

---

## License

MIT
