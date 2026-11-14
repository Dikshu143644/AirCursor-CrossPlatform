"""AirCursor for Windows - Main Entry Point.

Head-tracking mouse control using Apple AirPods on Microsoft Windows:
- OpenTrack UDP ingestion on port 4242 (aap-head-tracker, MagicAAP, or network bridge)
- Synthetic sensor simulation mode (--synthetic)
- 120Hz smooth pointer kinematics & gesture recognition (Nod to click, Shake to pause)
- Smart Dwell Click with Windows UI Automation (UIA) probe
- Transparent click-through HUD overlay with dwell progress ring
- Global media key capture for AirPods stem squeezes
- System Tray integration and global hotkeys
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Optional

# Ensure packages are discoverable
ROOT_DIR = Path(__file__).resolve().parent.parent
WINDOWS_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from aircursor_core.settings import AppSettings
from app_controller import AppController, TrackingMode
from sensor_receiver import BluetoothAirPodsHelper
from tray_icon import TrayIcon


def get_default_config_path() -> Path:
    user_home = Path.home()
    config_dir = user_home / ".aircursor"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "settings.json"


def load_settings(config_path: Path) -> AppSettings:
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
                return AppSettings.from_json(content)
        except Exception as e:
            print(f"[Warning] Failed to load settings from {config_path}: {e}")
    return AppSettings()


def save_settings(settings: AppSettings, config_path: Path) -> None:
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(settings.to_json())
    except Exception as e:
        print(f"[Warning] Failed to save settings to {config_path}: {e}")


def print_banner() -> None:
    banner = (
        "\033[96m"
        "╔══════════════════════════════════════════════════════════════════════╗\n"
        "║                        AirCursor for Windows                         ║\n"
        "║            AirPods Head-Tracking Mouse & Gesture Engine              ║\n"
        "╚══════════════════════════════════════════════════════════════════════╝"
        "\033[0m"
    )
    print(banner)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AirCursor: AirPods Head Tracking Mouse Controller for Windows"
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use synthetic sensor simulation instead of physical AirPods",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4242,
        help="OpenTrack UDP listening port (default: 4242)",
    )
    parser.add_argument(
        "--bind",
        type=str,
        default="0.0.0.0",
        help="IP address to bind UDP receiver (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--no-overlay",
        action="store_true",
        help="Disable transparent HUD overlay window",
    )
    parser.add_argument(
        "--no-stem",
        action="store_true",
        help="Disable media key stem click interception",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Enable Windows System Tray icon",
    )
    parser.add_argument(
        "--sensitivity",
        type=float,
        default=None,
        help="Override pointer sensitivity multiplier (default: 1.0)",
    )
    parser.add_argument(
        "--smoothing",
        type=float,
        default=None,
        help="Override pointer smoothing (0.0=raw to 0.95=smooth, default: 0.55)",
    )
    parser.add_argument(
        "--dwell-duration",
        type=float,
        default=None,
        help="Override hover click dwell duration in seconds (default: 0.8)",
    )
    parser.add_argument(
        "--nod-amplitude",
        type=float,
        default=None,
        help="Override nod gesture amplitude in degrees (default: 5.5)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to JSON configuration file",
    )
    parser.add_argument(
        "--setup-info",
        action="store_true",
        help="Print AirPods Bluetooth setup guide and paired devices, then exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="AirCursor Windows v1.0.0",
    )

    args = parser.parse_args()

    if args.setup_info:
        print_banner()
        print(BluetoothAirPodsHelper.get_setup_instructions())
        paired = BluetoothAirPodsHelper.get_paired_airpods()
        if paired:
            print("\033[92mPaired AirPods detected on this system:\033[0m")
            for dev in paired:
                print(f"  • {dev.get('name')} (MAC: {dev.get('address')})")
        else:
            print("\033[93mNo paired AirPods found in Windows Bluetooth settings.\033[0m")
        sys.exit(0)

    config_path = Path(args.config) if args.config else get_default_config_path()
    settings = load_settings(config_path)

    # Apply CLI overrides
    if args.sensitivity is not None:
        settings.pointer.sensitivity = args.sensitivity
    if args.smoothing is not None:
        settings.pointer.smoothing = args.smoothing
    if args.dwell_duration is not None:
        settings.dwell.duration = args.dwell_duration
    if args.nod_amplitude is not None:
        settings.gestures.nod_amplitude = args.nod_amplitude

    print_banner()
    print(f"[*] Configuration: {config_path}")
    print(f"[*] Ingestion Mode: {'Synthetic Simulation' if args.synthetic else f'OpenTrack UDP ({args.bind}:{args.port})'}")
    print(f"[*] Overlay HUD: {'Disabled' if args.no_overlay else 'Active'}")
    print(f"[*] Stem Listener: {'Disabled' if args.no_stem else 'Active'}")

    paired_airpods = BluetoothAirPodsHelper.get_paired_airpods()
    if paired_airpods:
        names = ", ".join(d.get("name", "AirPods") for d in paired_airpods)
        print(f"[*] Paired AirPods: \033[92m{names}\033[0m")
    else:
        print("[*] Paired AirPods: None detected in Windows Bluetooth")

    print("\n\033[93m[Global Hotkeys]\033[0m")
    print("  • Ctrl + Alt + T : Pause / Resume Tracking")
    print("  • Ctrl + Alt + S : Toggle Scroll Mode / Pointer Mode")
    print("  • Ctrl + Alt + C : Recenter Cursor")
    print("  • Ctrl + Alt + D : Toggle Left-Mouse Drag Lock")
    print("  • Ctrl + C       : Exit AirCursor\n")

    controller = AppController(
        settings=settings,
        use_synthetic=args.synthetic,
        udp_port=args.port,
        udp_host=args.bind,
        show_overlay=not args.no_overlay,
        enable_stem_hook=not args.no_stem,
    )

    tray: Optional[TrayIcon] = None
    if args.tray:
        tray = TrayIcon(
            on_toggle_tracking=controller.toggle_tracking,
            on_toggle_mode=controller.toggle_mode,
            on_recenter=controller.recenter,
            on_exit=lambda: os.kill(os.getpid(), signal.SIGINT),
            is_tracking_fn=lambda: controller.tracking_enabled,
            get_mode_fn=lambda: controller.mode.value,
        )
        tray.start()
        print("[*] System Tray Icon active.")

    stop_event = threading.Event()

    def _sig_handler(sig, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, _sig_handler)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _sig_handler)

    controller.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.2)
            # Format live dashboard status line
            status = "TRACKING" if controller.tracking_enabled else "PAUSED  "
            status_color = "\033[92m" if controller.tracking_enabled else "\033[93m"
            mode_str = controller.mode.value.upper()
            stream_str = "STREAMING" if controller.motion_streaming else "WAITING  "

            sys.stdout.write(
                f"\r{status_color}[{status}]\033[0m "
                f"Mode: {mode_str:<7} | "
                f"Sensors: {stream_str} | "
                f"Yaw: {controller.live_yaw:>6.1f}° Pitch: {controller.live_pitch:>6.1f}° Roll: {controller.live_roll:>6.1f}° | "
                f"FPS: {controller.live_fps:>4.0f}  "
            )
            sys.stdout.flush()

            if tray:
                tooltip = f"AirCursor - {status} ({mode_str})"
                tray.update_tooltip(tooltip)

    except KeyboardInterrupt:
        pass
    finally:
        print("\n\n[*] Shutting down AirCursor...")
        if tray:
            tray.stop()
        controller.stop()
        save_settings(settings, config_path)
        print("[*] AirCursor terminated cleanly. Have a great day!")


if __name__ == "__main__":
    main()
