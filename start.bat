@echo off
title ComputeTorrent — Full Stack Launcher
color 0A

echo.
echo  ================================================
echo   ComputeTorrent Seeder — Starting Full Stack
echo  ================================================
echo.

REM ── Step 1: Check Docker ────────────────────────────────────────
echo [1/3] Checking Docker...
docker ps >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Docker is not running!
    echo  Please open Docker Desktop and wait for "Engine running"
    echo  then run this script again.
    echo.
    pause
    exit /b 1
)
echo  Docker OK
echo.

REM ── Step 2: Start Mock Tracker ──────────────────────────────────
echo [2/3] Starting Mock Tracker on port 8080...
start "ComputeTorrent Tracker" cmd /k "cd /d d:\computetorrent-seeder && python mock_tracker_server.py"
timeout /t 3 /nobreak >nul

REM ── Step 3: Start Web Portal ────────────────────────────────────
echo [3/3] Starting Web Portal on port 3000...
start "ComputeTorrent Web Portal" cmd /k "cd /d d:\computetorrent-seeder\computetorrent-seeder\web_portal && npm run dev"
timeout /t 5 /nobreak >nul

REM ── Step 4: Start Desktop App ───────────────────────────────────
echo [4/4] Starting Desktop App...
start "ComputeTorrent Desktop App" cmd /k "cd /d d:\computetorrent-seeder\computetorrent-seeder\desktop_app && python main.py"
timeout /t 4 /nobreak >nul

REM ── Open Browser ────────────────────────────────────────────────
echo.
echo  Opening Web Portal in browser...
start http://localhost:3000
echo.
echo  ================================================
echo   All services started!
echo.
echo   Web Portal  →  http://localhost:3000
echo   Tracker     →  ws://localhost:8080/ws
echo   Desktop App →  GUI window should be open
echo.
echo   Close this window to keep everything running.
echo   To STOP everything, close the 3 terminal windows.
echo  ================================================
echo.
pause
