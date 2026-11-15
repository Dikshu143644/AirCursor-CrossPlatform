@echo off
title AirCursor Uninstaller
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
echo              AirCursor for Windows Uninstaller
echo ========================================================
echo.
echo Removing Desktop shortcuts, Start Menu shortcuts,
echo and clearing Windows autostart registry entries...
echo.

python installer.py --uninstall

echo.
echo ========================================================
echo Uninstallation complete! Shortcuts and autostart removed.
echo ========================================================
echo.
pause
