@echo off
title AirCursor Installer
setlocal enabledelayedexpansion

if exist "%~dp0windows\installer.py" (
    cd /d "%~dp0windows"
) else if exist "%~dp0AirCursor_CrossPlatform\windows\installer.py" (
    cd /d "%~dp0AirCursor_CrossPlatform\windows"
) else if exist "%~dp0installer.py" (
    cd /d "%~dp0"
) else (
    echo [!] Could not locate AirCursor windows directory.
    pause
    exit /b 1
)

cls
echo ========================================================
echo               AirCursor for Windows Installer
echo ========================================================
echo.
echo This installer will create:
echo   1. Desktop Shortcut ('AirCursor')
echo   2. Start Menu Program Shortcut ('AirCursor')
echo.
echo Both shortcuts point to pythonw.exe to launch the
echo Control Center cleanly without a console window.
echo.

set /p boot="Would you like AirCursor to automatically start on boot in tray? [y/N]: "

if /i "%boot%"=="y" (
    echo.
    echo [*] Installing shortcuts with boot autostart enabled...
    python installer.py --install --autostart
) else (
    echo.
    echo [*] Installing shortcuts...
    python installer.py --install
)

echo.
echo ========================================================
echo Installation complete! You can launch AirCursor anytime
echo from your Desktop, Start Menu, or Start-AirCursor.bat.
echo ========================================================
echo.
pause
