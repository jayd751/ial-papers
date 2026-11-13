@echo off
rem Double-click to run the past paper downloader on Windows.
cd /d "%~dp0"
echo Starting IAL Papers downloader...
echo Your browser will open. Close this window to stop.
where python >nul 2>nul
if %errorlevel%==0 (
  python web.py
) else (
  py web.py
)
pause
