@echo off
title AirCursor Control Center
cd /d "%~dp0"

cls
echo ========================================================
echo               AirCursor for Windows
echo            Control Center & Head Tracker
echo ========================================================
echo.
echo Launching AirCursor Control Center...
echo Global Hotkeys:
echo   Ctrl+Alt+T : Pause / Resume Tracking
echo   Ctrl+Alt+S : Toggle Scroll Mode
echo   Ctrl+Alt+C : Recenter Cursor
echo.

python main.py %*
