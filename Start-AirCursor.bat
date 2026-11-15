@echo off
title AirCursor Control Center
if exist "%~dp0windows\main.py" (
    cd /d "%~dp0windows"
) else if exist "%~dp0AirCursor_CrossPlatform\windows\main.py" (
    cd /d "%~dp0AirCursor_CrossPlatform\windows"
) else if exist "%~dp0main.py" (
    cd /d "%~dp0"
)

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
