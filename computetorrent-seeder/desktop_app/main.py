"""
ComputeTorrent Seeder — Desktop App Entry Point
APP-1 (Windows-first, packaged via PyInstaller)
APP-5 (system tray — minimises to tray, no need to stay in focus)

This module bootstraps all four backend modules, runs the docker preflight
check, and launches the GUI (CustomTkinter). The system tray icon uses
pystray so the app stays alive when the window is closed.

Run directly:  python main.py
Packaged:      PyInstaller produces a single .exe with --onefile --noconsole

Optional environment overrides (see each module's constants):
  CT_TRACKER_URL      ws://tracker:8080   (networking_client)
  CT_SANDBOX_CPUS     1.0                 (sandbox_runtime)
  CT_SANDBOX_MEM      2g                  (sandbox_runtime)
  CT_SANDBOX_TIMEOUT  300                 (sandbox_runtime)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("computetorrent.desktop_app.main")

# ---------------------------------------------------------------------------
# Path setup — resolve sibling modules when run directly or from PyInstaller
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent   # computetorrent-seeder/
for sibling in ("hardware_profiling", "sandbox_runtime", "networking_client"):
    p = str(ROOT / sibling)
    if p not in sys.path:
        sys.path.insert(0, p)

# ---------------------------------------------------------------------------
# Backend imports
# ---------------------------------------------------------------------------

from docker_preflight import run_preflight                           # noqa: E402
from controller import AppController, AppState                       # noqa: E402
from onboarding_screen import OnboardingViewModel                    # noqa: E402
from dashboard_screen import DashboardViewModel                      # noqa: E402

try:
    from hardware_profiling.profiler import HardwareProfiler
except ModuleNotFoundError:
    from profiler import HardwareProfiler                            # flat import

try:
    from sandbox_runtime.runner import SandboxRunner
except ModuleNotFoundError:
    from runner import SandboxRunner                                 # flat sibling import

try:
    from networking_client.ws_client import NetworkingClient
except ModuleNotFoundError:
    from ws_client import NetworkingClient                           # flat sibling import

try:
    from webtorrent_sync.bridge import WebtorrentBridge
    _WT_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _WT_AVAILABLE = False
    WebtorrentBridge = None                                          # type: ignore


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _build_backend(state: AppState) -> AppController:
    """Wire all four modules together; return the controller."""
    profiler = HardwareProfiler()
    reg_payload = profiler.registration_payload()

    sandbox = SandboxRunner()

    tracker_url = os.environ.get("CT_TRACKER_URL", "ws://localhost:8080/ws")
    net_client = NetworkingClient(
        tracker_url=tracker_url,
        registration_payload=reg_payload,
        enable_stun=True,
    )

    wt_bridge = None
    if _WT_AVAILABLE and WebtorrentBridge:
        wt_bridge = WebtorrentBridge()
        try:
            wt_bridge.start()
        except Exception as exc:
            logger.warning("WebtorrentBridge failed to start: %s — continuing without it.", exc)
            wt_bridge = None

    return AppController(
        profiler=profiler,
        sandbox_runner=sandbox,
        networking_client=net_client,
        wt_bridge=wt_bridge,
        state=state,
    )


# ---------------------------------------------------------------------------
# GUI (CustomTkinter) — only imported if available; falls back to a headless
# text-mode loop so the app still runs in CI / without a display.
# ---------------------------------------------------------------------------

def _run_gui(controller: AppController, state: AppState, preflight_ok: bool) -> None:
    try:
        import customtkinter as ctk  # type: ignore
        _run_ctk_gui(ctk, controller, state, preflight_ok)
    except ImportError:
        logger.warning("customtkinter not installed — running in headless mode.")
        _run_headless(controller, state, preflight_ok)


def _run_headless(controller: AppController, state: AppState, preflight_ok: bool) -> None:
    """Minimal text-mode loop for environments without a display."""
    import time
    controller.start(sandbox_ok=preflight_ok)
    logger.info("Running in headless mode. Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()


def _run_ctk_gui(
    ctk,
    controller: AppController,
    state: AppState,
    preflight_ok: bool,
) -> None:
    """
    Full CustomTkinter UI with:
      - Onboarding screen (APP-2)
      - Dashboard screen  (APP-3 / APP-4)
      - System tray icon  (APP-5)
    """
    try:
        import pystray                           # type: ignore
        from PIL import Image as PILImage        # type: ignore
        _TRAY_AVAILABLE = True
    except ImportError:
        _TRAY_AVAILABLE = False

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    root.title("ComputeTorrent Seeder")
    root.geometry("520x400")
    root.resizable(False, False)

    # --- Onboarding ---
    profiler_for_ui = controller._profiler
    onboarding = OnboardingViewModel(profiler=profiler_for_ui)
    onboarding.run_profiling()

    frame = ctk.CTkFrame(root)
    frame.pack(fill="both", expand=True, padx=20, pady=20)

    title_lbl = ctk.CTkLabel(frame, text="ComputeTorrent Seeder", font=ctk.CTkFont(size=20, weight="bold"))
    title_lbl.pack(pady=(10, 4))

    if not preflight_ok:
        warn_lbl = ctk.CTkLabel(
            frame,
            text="⚠ Docker not found. Seeding disabled.\nInstall Docker Desktop and relaunch.",
            text_color="orange",
        )
        warn_lbl.pack(pady=8)

    tier_lbl = ctk.CTkLabel(frame, text=onboarding.tier_label(), font=ctk.CTkFont(size=13))
    tier_lbl.pack(pady=4)

    hw = onboarding.hardware_summary
    hw_text = (
        f"GPU: {hw.get('GPU') or 'None'}  |  RAM: {hw.get('RAM', '?')} GB  |  "
        f"Cores: {hw.get('Cores', '?')}"
    )
    hw_lbl = ctk.CTkLabel(frame, text=hw_text)
    hw_lbl.pack(pady=2)

    # --- Dashboard ---
    dashboard = DashboardViewModel(state=state, controller=controller)

    sep = ctk.CTkFrame(frame, height=2)
    sep.pack(fill="x", pady=12)

    status_lbl = ctk.CTkLabel(frame, text="Status: …")
    status_lbl.pack()
    task_lbl = ctk.CTkLabel(frame, text="Task: Idle")
    task_lbl.pack()
    totals_lbl = ctk.CTkLabel(frame, text="Completed: 0  |  Credits: 0.00")
    totals_lbl.pack(pady=4)

    def refresh_labels():
        status_lbl.configure(text=f"Status: {dashboard.connection_status}")
        task_lbl.configure(text=f"Task: {dashboard.current_task}")
        totals_lbl.configure(
            text=f"Completed: {dashboard.tasks_completed}  |  Credits: {dashboard.credits_earned}"
        )

    dashboard.set_on_change(refresh_labels)
    refresh_labels()

    btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
    btn_frame.pack(pady=10)

    def toggle_pause():
        if state.paused:
            dashboard.resume()
            pause_btn.configure(text="⏸ Pause Seeding")
        else:
            dashboard.pause()
            pause_btn.configure(text="▶ Resume Seeding")

    pause_btn = ctk.CTkButton(
        btn_frame, text="⏸ Pause Seeding",
        command=toggle_pause,
        state="normal" if preflight_ok else "disabled",
    )
    pause_btn.pack(side="left", padx=6)

    stop_btn = ctk.CTkButton(
        btn_frame, text="⏹ Stop",
        command=lambda: (controller.stop(), root.destroy()),
        fg_color="gray30",
    )
    stop_btn.pack(side="left", padx=6)

    # --- System tray (APP-5) ---
    def _setup_tray():
        try:
            img = PILImage.new("RGB", (64, 64), color=(30, 120, 200))
            menu = pystray.Menu(
                pystray.MenuItem("Show", lambda: root.after(0, root.deiconify)),
                pystray.MenuItem("Quit", lambda: (controller.stop(), root.after(0, root.destroy))),
            )
            icon = pystray.Icon("ComputeTorrent", img, "ComputeTorrent Seeder", menu)
            threading.Thread(target=icon.run, daemon=True).start()
        except Exception as exc:
            logger.warning("Tray icon unavailable: %s", exc)

    if _TRAY_AVAILABLE:
        root.protocol("WM_DELETE_WINDOW", lambda: root.withdraw())  # minimise to tray
        _setup_tray()
    else:
        root.protocol("WM_DELETE_WINDOW", lambda: (controller.stop(), root.destroy()))

    # Start controller loop
    controller.start(sandbox_ok=preflight_ok)

    # Periodic state refresh every 500 ms
    def _tick():
        refresh_labels()
        root.after(500, _tick)

    root.after(500, _tick)
    root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    state = AppState()

    # Docker preflight (APP-6)
    preflight = run_preflight(check_nvidia=True)
    if not preflight.ok:
        logger.warning("Docker preflight failed: %s", preflight.message)
    else:
        logger.info("Docker preflight passed.")

    controller = _build_backend(state)
    _run_gui(controller, state, preflight_ok=preflight.ok)


if __name__ == "__main__":
    main()
