@echo off
REM ---------------------------------------------------------------
REM ComputeTorrent Seeder — Windows build script (APP-1)
REM Run from the repo root:  desktop_app\build.bat
REM
REM Prerequisites:
REM   pip install pyinstaller customtkinter pystray Pillow psutil
REM               websockets pynvml
REM   Node.js on PATH (for the WebtorrentBridge child process)
REM ---------------------------------------------------------------

echo [1/3] Installing Python dependencies...
pip install pyinstaller customtkinter pystray Pillow psutil websockets pynvml --quiet
if errorlevel 1 goto :fail

echo [2/3] Installing Node.js dependencies for webtorrent_sync...
pushd webtorrent_sync
npm install --prefer-offline
popd
if errorlevel 1 goto :fail

echo [3/3] Building with PyInstaller...
pyinstaller desktop_app\computetorrent_seeder.spec --distpath dist --workpath build\pyinstaller_work --clean
if errorlevel 1 goto :fail

echo.
echo =========================================================
echo  Build complete: dist\ComputeTorrentSeeder.exe
echo =========================================================
goto :eof

:fail
echo.
echo BUILD FAILED — see errors above.
exit /b 1
