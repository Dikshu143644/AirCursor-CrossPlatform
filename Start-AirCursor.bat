@echo off
title AirCursor for Windows
if exist "%~dp0windows" (
    cd /d "%~dp0windows"
) else (
    cd /d "%~dp0AirCursor_CrossPlatform\windows"
)
cls
echo ========================================================
echo               AirCursor for Windows
echo     Head-Tracking Cursor & Hands-Free Gesture Control
echo ========================================================
echo.
echo Select an option:
echo.
echo   [1] Start Live Head Tracking (OpenTrack UDP / Port 4242)
echo   [2] Start Demo / Simulation Mode (Test without AirPods)
echo   [3] Inspect Paired AirPods & Bluetooth Setup Guide
echo   [4] Run Verification Self-Test Suite
echo   [5] Exit
echo.
set /p opt="Enter choice [1-5]: "

if "%opt%"=="1" (
    cls
    echo Starting AirCursor Live Mode (OpenTrack UDP port 4242)...
    echo Hotkeys:
    echo   Ctrl+Alt+T : Pause / Resume
    echo   Ctrl+Alt+S : Toggle Scroll Mode
    echo   Ctrl+Alt+C : Recenter Cursor
    echo   Ctrl+C     : Exit
    echo.
    python main.py --tray
    pause
    goto end
)

if "%opt%"=="2" (
    cls
    echo Starting AirCursor Simulation Mode...
    echo (Moving cursor with synthetic head tracking and testing dwell hover click)
    echo Note: The overlay HUD is 100%% transparent! Press Ctrl+Alt+T to Pause/Resume.
    echo.
    python main.py --synthetic --tray
    pause
    goto end
)

if "%opt%"=="3" (
    cls
    python main.py --setup-info
    echo.
    pause
    goto end
)

if "%opt%"=="4" (
    cls
    echo Running Windows Self-Test Suite...
    python test_windows_app.py
    echo.
    echo Running Core Engine Test Suite...
    python -m unittest ..\tests\test_core.py
    echo.
    pause
    goto end
)

:end
