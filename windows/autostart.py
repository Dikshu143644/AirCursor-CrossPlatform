"""AirCursor Windows Autostart Manager.

Manages registry key HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\\AirCursor
to run silently with pythonw.exe on Windows startup.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import winreg

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_VALUE_NAME = "AirCursor"


def get_pythonw_path() -> Path:
    """Finds pythonw.exe for windowless background execution."""
    current_exe = Path(sys.executable)
    if current_exe.name.lower() == "pythonw.exe":
        return current_exe
    candidate = current_exe.with_name("pythonw.exe")
    if candidate.exists():
        return candidate
    which_path = shutil.which("pythonw")
    if which_path:
        return Path(which_path)
    return current_exe


def get_main_script_path() -> Path:
    """Returns absolute path to windows/main.py."""
    return Path(__file__).resolve().parent / "main.py"


def is_autostart_enabled() -> bool:
    """Checks if AirCursor is registered to run on Windows startup."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, APP_VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def get_autostart_command() -> str | None:
    """Returns the current autostart command string, or None if not set."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ
        ) as key:
            val, _ = winreg.QueryValueEx(key, APP_VALUE_NAME)
            return str(val)
    except (FileNotFoundError, OSError):
        return None


def enable_autostart(extra_args: str = "--tray") -> bool:
    """Registers AirCursor in HKCU Run to launch silently with pythonw.exe."""
    pythonw = get_pythonw_path()
    main_py = get_main_script_path()
    cmd = f'"{pythonw}" "{main_py}" {extra_args}'.strip()

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, cmd)
            return True
    except OSError as e:
        print(f"[Error] Failed to enable autostart: {e}", file=sys.stderr)
        return False


def disable_autostart() -> bool:
    """Removes AirCursor from HKCU Run key."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, APP_VALUE_NAME)
                return True
            except FileNotFoundError:
                return True  # Already disabled
    except OSError as e:
        print(f"[Error] Failed to disable autostart: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AirCursor Autostart Manager")
    parser.add_argument("--check", action="store_true", help="Check autostart status")
    parser.add_argument(
        "--enable", action="store_true", help="Enable autostart on Windows boot"
    )
    parser.add_argument("--disable", action="store_true", help="Disable autostart")
    args = parser.parse_args()

    if args.enable:
        if enable_autostart():
            print("AirCursor autostart enabled successfully.")
        else:
            sys.exit(1)
    elif args.disable:
        if disable_autostart():
            print("AirCursor autostart disabled successfully.")
        else:
            sys.exit(1)
    elif args.check:
        enabled = is_autostart_enabled()
        print(f"AirCursor autostart enabled: {enabled}")
        if enabled:
            print(f"Command: {get_autostart_command()}")
    else:
        print(
            f"AirCursor autostart status: {'ENABLED' if is_autostart_enabled() else 'DISABLED'}"
        )
