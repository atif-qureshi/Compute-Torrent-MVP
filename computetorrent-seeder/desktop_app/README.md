# Provider Desktop Application (shell/installer) — APP-1 to APP-6

**Status:** not yet implemented. MVP Build Order step 5 — wire
`hardware_profiling`, `sandbox_runtime`, `networking_client`, and
`webtorrent_sync` together behind a UI, then package (step 6).

## What it owns
- Single installable package, Windows first (APP-1) — PyInstaller or an
  Electron-based packager per the architecture doc.
- First-run onboarding: detect hardware → show tier → "Start Seeding"
  button (APP-2), built directly on top of `hardware_profiling`.
- Main dashboard: connection status, current task + progress, total
  tasks completed, credits earned (APP-3).
- "Pause Seeding" / "Stop" control, without closing the app (APP-4).
- Runs minimized to the system tray, no need to stay in focus (APP-5).
- Hard invariant: no task ever runs without `sandbox_runtime` active —
  not optional, not bypassable (APP-6).

## Tech
Python + PyQt / CustomTkinter, per the architecture doc's chosen stack.

## Planned shape
```
desktop_app/
  main.py               # app entry point, system tray integration
  onboarding_screen.py   # wraps hardware_profiling.HardwareProfiler (APP-2)
  dashboard_screen.py     # status, current task, totals, credits (APP-3)
  docker_preflight.py     # `docker info` check on launch; clear install
                           # guidance if missing (NFR-3)
  controller.py            # glue: networking_client <-> webtorrent_sync <->
                            # sandbox_runtime <-> UI state, enforces APP-6
```

## Why this comes after the four backend modules
Each of `hardware_profiling`, `sandbox_runtime`, `networking_client`, and
`webtorrent_sync` is independently testable without a UI. Building the
shell last means the UI is wired against already-working, already-tested
pieces instead of being debugged alongside them.
