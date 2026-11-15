"""AirCursor Windows Shortcut & Installer Engine.

Creates and removes Desktop and Start Menu shortcuts, and manages autostart configuration.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

# Ensure windows package is discoverable
WINDOWS_DIR = Path(__file__).resolve().parent
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

import autostart


def get_desktop_dir() -> Path:
    """Returns the user's active Desktop folder via PowerShell."""
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "[Environment]::GetFolderPath('Desktop')",
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        if out:
            p = Path(out)
            if p.exists():
                return p
    except Exception:
        pass
    fallback = Path.home() / "Desktop"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_start_menu_programs_dir() -> Path:
    """Returns the Start Menu Programs folder."""
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "[Environment]::GetFolderPath('Programs')",
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        if out:
            p = Path(out)
            if p.exists():
                return p
    except Exception:
        pass
    fallback = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def create_windows_shortcut(
    shortcut_path: Path,
    target_path: Path,
    arguments: str = "",
    working_dir: Path | None = None,
    description: str = "AirCursor - AirPods Head-Tracking Mouse Controller",
) -> bool:
    """Creates a .lnk shortcut using PowerShell WScript.Shell COM object."""
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    work_dir = str(working_dir or target_path.parent)

    ps_script = (
        f"$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path.resolve()}'); "
        f"$Shortcut.TargetPath = '{target_path.resolve()}'; "
        f"$Shortcut.Arguments = '{arguments}'; "
        f"$Shortcut.WorkingDirectory = '{work_dir}'; "
        f"$Shortcut.Description = '{description}'; "
        f"$Shortcut.Save();"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            capture_output=True,
        )
        return shortcut_path.exists()
    except Exception as e:
        print(f"[Error] Failed to create shortcut {shortcut_path}: {e}")
        return False


def install(
    enable_boot: bool = False,
    create_desktop: bool = True,
    create_start_menu: bool = True,
) -> bool:
    """Installs AirCursor shortcuts and optionally configures autostart."""
    pythonw = autostart.get_pythonw_path()
    main_py = autostart.get_main_script_path()
    windows_dir = main_py.parent

    print(f"[*] Python interpreter (GUI): {pythonw}")
    print(f"[*] Main entry script: {main_py}")

    success = True

    # 1. Desktop Shortcut
    if create_desktop:
        desktop_lnk = get_desktop_dir() / "AirCursor.lnk"
        ok = create_windows_shortcut(
            shortcut_path=desktop_lnk,
            target_path=pythonw,
            arguments=f'"{main_py}"',
            working_dir=windows_dir,
            description="AirCursor Control Center",
        )
        if ok:
            print(f"[✓] Desktop shortcut created: {desktop_lnk}")
        else:
            print(f"[✗] Failed to create Desktop shortcut")
            success = False

    # 2. Start Menu Shortcut
    if create_start_menu:
        programs_lnk = get_start_menu_programs_dir() / "AirCursor.lnk"
        ok = create_windows_shortcut(
            shortcut_path=programs_lnk,
            target_path=pythonw,
            arguments=f'"{main_py}"',
            working_dir=windows_dir,
            description="AirCursor Control Center",
        )
        if ok:
            print(f"[✓] Start Menu shortcut created: {programs_lnk}")
        else:
            print(f"[✗] Failed to create Start Menu shortcut")
            success = False

    # 3. Boot Autostart
    if enable_boot:
        if autostart.enable_autostart(extra_args="--tray"):
            print("[✓] Windows boot autostart configured (runs silently in tray)")
        else:
            print("[✗] Failed to configure Windows autostart")
            success = False

    return success


def _safe_delete(path: Path, max_retries: int = 6, delay: float = 0.25) -> bool:
    """Deletes a file with retries in case OneDrive or Antivirus has a temporary lock."""
    if not path.exists():
        return True
    for _ in range(max_retries):
        try:
            path.unlink()
            return True
        except (PermissionError, OSError):
            time.sleep(delay)
    return not path.exists()


def uninstall() -> bool:
    """Removes AirCursor shortcuts and autostart registry entries."""
    print("[*] Uninstalling AirCursor shortcuts and autostart keys...")

    # 1. Remove Desktop Shortcut
    desktop_lnk = get_desktop_dir() / "AirCursor.lnk"
    if desktop_lnk.exists():
        if _safe_delete(desktop_lnk):
            print(f"[✓] Removed Desktop shortcut: {desktop_lnk}")
        else:
            print(f"[✗] Error removing Desktop shortcut: {desktop_lnk}")

    # Also check standard Desktop if different from redirected OneDrive
    alt_desktop = Path.home() / "Desktop" / "AirCursor.lnk"
    if alt_desktop.exists() and alt_desktop != desktop_lnk:
        if _safe_delete(alt_desktop):
            print(f"[✓] Removed Desktop shortcut: {alt_desktop}")

    # 2. Remove Start Menu Shortcut
    programs_lnk = get_start_menu_programs_dir() / "AirCursor.lnk"
    if programs_lnk.exists():
        if _safe_delete(programs_lnk):
            print(f"[✓] Removed Start Menu shortcut: {programs_lnk}")
        else:
            print(f"[✗] Error removing Start Menu shortcut: {programs_lnk}")

    # 3. Disable Autostart
    if autostart.disable_autostart():
        print("[✓] Cleared autostart registry key (HKCU Run)")
    else:
        print("[✗] Error clearing autostart registry key")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AirCursor Windows Installer")
    parser.add_argument("--install", action="store_true", help="Install shortcuts")
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Enable Windows boot startup with --tray",
    )
    parser.add_argument("--uninstall", action="store_true", help="Uninstall shortcuts")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    elif args.install:
        install(enable_boot=args.autostart)
    else:
        # Default interactive behavior
        print("Specify --install or --uninstall")
