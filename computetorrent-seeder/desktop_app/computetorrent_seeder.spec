# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — ComputeTorrent Seeder (Windows-first, APP-1)

Build command (run from the repo root):
  pyinstaller desktop_app/computetorrent_seeder.spec

Output: dist/ComputeTorrentSeeder.exe  (single-file, no console window)

What is bundled:
  • desktop_app/          — controller, screens, preflight, main
  • hardware_profiling/   — HardwareProfiler
  • sandbox_runtime/      — SandboxRunner, LifecycleLog
  • networking_client/    — NetworkingClient, webrtc_upgrade
  (webtorrent_sync runs as a child Node.js process — NOT bundled here;
   bridge_server.js is included as a data file and Node.exe must be on PATH
   or bundled separately by the installer.)

Hidden imports are listed explicitly so PyInstaller's static analyser
doesn't miss them (psutil, websockets, customtkinter, pystray use
dynamic imports / C extensions that the analyser cannot always detect).
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent          # computetorrent-seeder/
DESKTOP = ROOT / 'desktop_app'
HW      = ROOT / 'hardware_profiling'
SANDBOX = ROOT / 'sandbox_runtime'
NET     = ROOT / 'networking_client'
WT      = ROOT / 'webtorrent_sync'

block_cipher = None

a = Analysis(
    [str(DESKTOP / 'main.py')],
    pathex=[
        str(DESKTOP),
        str(HW),
        str(SANDBOX),
        str(NET),
    ],
    binaries=[],
    datas=[
        # Include webtorrent bridge server so the child process can be launched
        (str(WT / 'bridge_server.js'), 'webtorrent_sync'),
        (str(WT / 'sync_client.js'),   'webtorrent_sync'),
        (str(WT / 'package.json'),     'webtorrent_sync'),
    ],
    hiddenimports=[
        # stdlib / async
        'asyncio',
        'asyncio.selector_events',
        # networking
        'websockets',
        'websockets.legacy',
        'websockets.legacy.client',
        'websockets.legacy.server',
        # system info
        'psutil',
        'psutil._pswindows',
        # GPU detection
        'pynvml',
        # GUI
        'customtkinter',
        'tkinter',
        'tkinter.ttk',
        # tray
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        # webtorrent bridge (Python side)
        'webtorrent_sync.bridge',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        'unittest',
        '_pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ComputeTorrentSeeder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window (APP-5 tray app)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # replace with 'assets/icon.ico' when available
    # Windows version info (optional — fill in before release)
    # version='file_version_info.txt',
)
