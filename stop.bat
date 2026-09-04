@echo off
title ComputeTorrent — Stop All
color 0C

echo.
echo  Stopping all ComputeTorrent services...
echo.

taskkill /FI "WINDOWTITLE eq ComputeTorrent Tracker*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq ComputeTorrent Web Portal*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq ComputeTorrent Desktop App*" /T /F >nul 2>&1

echo  All services stopped.
echo.
pause
