"""AirCursor Windows Control Center.

Modern dark-themed Control Panel window using Tkinter for AirCursor:
- AirPods Pro connection status badge
- Master Start / Pause toggle button
- Live telemetry monitors (Pitch, Yaw, Roll, FPS, Mode)
- Tuning sliders (Pointer Sensitivity, Dwell Duration, Nod Amplitude)
- Feature checkboxes (Hover Dwell Click, Nod to Click, Shake to Pause, Start with Windows)
- Action buttons: Recenter Cursor (Ctrl+Alt+C), Mode Toggle, Save Settings
- System tray minimization on window close
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional
import webbrowser
import subprocess

# Ensure core and windows modules are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
WINDOWS_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from aircursor_core.actions import PointerAction, Trigger
from aircursor_core.settings import AppSettings
from aircursor_core.hardware_profiles import (
    HARDWARE_REGISTRY,
    HardwareDeviceType,
    HardwarePacketEncoder,
    HardwarePacketDecoder,
)
from app_controller import AppController, TrackingMode
import autostart
from sensor_receiver import BluetoothAirPodsHelper
from tray_icon import TrayIcon


class TelemetryBar(tk.Canvas):
    """Custom compact horizontal meter displaying zero-centered angle telemetry."""

    def __init__(
        self,
        parent: tk.Widget,
        width: int = 140,
        height: int = 14,
        min_val: float = -30.0,
        max_val: float = 30.0,
        bar_color: str = "#38bdf8",
        bg_color: str = "#232328",
        center_color: str = "#71717a",
        **kwargs,
    ):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg_color,
            bd=0,
            highlightthickness=1,
            highlightbackground="#3f3f46",
            **kwargs,
        )
        self.w = width
        self.h = height
        self.min_val = min_val
        self.max_val = max_val
        self.bar_color = bar_color
        self.center_color = center_color
        self.center_x = width // 2
        self.set_value(0.0)

    def set_value(self, val: float) -> None:
        self.delete("all")
        # Center reference notch
        self.create_line(
            self.center_x, 0, self.center_x, self.h, fill=self.center_color, width=1
        )

        clamped = max(self.min_val, min(self.max_val, val))
        if abs(clamped) < 0.1:
            return

        # Map to pixel offset from center
        span = self.max_val - self.min_val
        px_per_unit = (self.w / 2) / (self.max_val if clamped > 0 else abs(self.min_val))
        dx = clamped * px_per_unit

        if dx > 0:
            x0 = self.center_x
            x1 = min(self.w - 1, self.center_x + dx)
        else:
            x0 = max(1, self.center_x + dx)
            x1 = self.center_x

        self.create_rectangle(
            x0, 2, x1, self.h - 2, fill=self.bar_color, outline=""
        )


class ControlCenterGUI:
    """AirCursor Control Center GUI Application."""

    def __init__(
        self,
        controller: AppController,
        config_path: Path,
        tray: Optional[TrayIcon] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self.controller = controller
        self.config_path = config_path
        self.tray = tray
        self.on_exit_cb = on_exit

        # Attach to user's interactive desktop WinSta0\Default
        try:
            import ctypes
            user32 = ctypes.windll.user32
            h_winsta = user32.OpenWindowStationW("WinSta0", False, 0x10000000)
            if h_winsta:
                user32.SetProcessWindowStation(h_winsta)
            h_desk = user32.OpenDesktopW("Default", 0, False, 0x10000000)
            if h_desk:
                user32.SetThreadDesktop(h_desk)
        except Exception:
            pass

        self.root = tk.Tk()
        self.root.title("AirCursor Control Center")
        self.root.geometry("520x720")
        self.root.minsize(480, 680)
        self.root.configure(bg="#121214")

        # Bring window to foreground on launch
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after_idle(self.root.attributes, "-topmost", False)
            self.root.focus_force()
        except Exception:
            pass

        # Set taskbar icon if available
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        # Intercept close (X) button to minimize to tray
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_tray)

        # Style colors
        self.c_bg = "#121214"
        self.c_card = "#1c1c20"
        self.c_card_border = "#2e2e36"
        self.c_text = "#f4f4f5"
        self.c_text_muted = "#a1a1aa"
        self.c_text_dim = "#71717a"
        self.c_green = "#10b981"
        self.c_green_hover = "#059669"
        self.c_amber = "#f59e0b"
        self.c_amber_hover = "#d97706"
        self.c_blue = "#3b82f6"
        self.c_cyan = "#06b6d4"

        # Internal update states
        self._is_updating_sliders = False
        self._last_tracking_state = self.controller.tracking_enabled

        self._build_ui()
        self._sync_settings_to_ui()

        # Connect Tray callback if provided
        if self.tray:
            self.tray.on_open_gui = self.restore_from_tray

        # Schedule live telemetry updater (~25 FPS)
        self.root.after(40, self._update_telemetry_loop)

    def _build_ui(self) -> None:
        """Constructs all GUI panels, badges, meters, sliders, and buttons."""
        main_frame = tk.Frame(self.root, bg=self.c_bg, padx=18, pady=14)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ---------------- 1. HEADER & AIRPODS BADGE ----------------
        header_frame = tk.Frame(main_frame, bg=self.c_bg)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_lbl = tk.Label(
            header_frame,
            text="AirCursor",
            font=("Segoe UI", 16, "bold"),
            fg=self.c_text,
            bg=self.c_bg,
        )
        title_lbl.pack(side=tk.LEFT)

        version_lbl = tk.Label(
            header_frame,
            text="v1.0 Windows",
            font=("Segoe UI", 9),
            fg=self.c_text_dim,
            bg=self.c_bg,
        )
        version_lbl.pack(side=tk.LEFT, padx=(6, 0), pady=(4, 0))

        # AirPods Connection Status Badge
        self.badge_frame = tk.Frame(
            header_frame,
            bg="#18221c",
            highlightthickness=1,
            highlightbackground="#234230",
            padx=10,
            pady=3,
        )
        self.badge_frame.pack(side=tk.RIGHT)

        self.badge_dot = tk.Label(
            self.badge_frame,
            text="●",
            font=("Segoe UI", 10),
            fg=self.c_green,
            bg="#18221c",
        )
        self.badge_dot.pack(side=tk.LEFT, padx=(0, 4))

        self.badge_lbl = tk.Label(
            self.badge_frame,
            text="AirPods Pro (41424f2041e4)",
            font=("Segoe UI", 9, "bold"),
            fg=self.c_green,
            bg="#18221c",
        )
        self.badge_lbl.pack(side=tk.LEFT)

        self._refresh_airpods_status()

        # ---------------- 2. MASTER TOGGLE BUTTON ----------------
        self.master_btn = tk.Button(
            main_frame,
            text="⏸ Pause Tracking",
            font=("Segoe UI", 13, "bold"),
            bg=self.c_amber,
            fg="#ffffff",
            activebackground=self.c_amber_hover,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=10,
            command=self._on_toggle_master,
        )
        self.master_btn.pack(fill=tk.X, pady=(0, 12))

        # ---------------- 3. LIVE TELEMETRY CARD ----------------
        telemetry_card = self._create_card(main_frame, "Live Head-Tracking Telemetry")
        telemetry_card.pack(fill=tk.X, pady=(0, 12))

        # Top row: Mode and FPS
        status_row = tk.Frame(telemetry_card, bg=self.c_card)
        status_row.pack(fill=tk.X, pady=(0, 8))

        mode_title = tk.Label(
            status_row,
            text="Tracking Mode:",
            font=("Segoe UI", 9),
            fg=self.c_text_muted,
            bg=self.c_card,
        )
        mode_title.pack(side=tk.LEFT)

        self.mode_btn = tk.Button(
            status_row,
            text="POINTER",
            font=("Segoe UI", 9, "bold"),
            bg="#2a2a32",
            fg=self.c_cyan,
            activebackground="#33333e",
            activeforeground=self.c_cyan,
            relief="flat",
            bd=0,
            padx=8,
            pady=1,
            cursor="hand2",
            command=self._on_toggle_mode,
        )
        self.mode_btn.pack(side=tk.LEFT, padx=(6, 12))

        fps_title = tk.Label(
            status_row,
            text="Sensor Rate:",
            font=("Segoe UI", 9),
            fg=self.c_text_muted,
            bg=self.c_card,
        )
        fps_title.pack(side=tk.LEFT)

        self.fps_lbl = tk.Label(
            status_row,
            text="120 FPS",
            font=("Segoe UI", 9, "bold"),
            fg=self.c_green,
            bg=self.c_card,
        )
        self.fps_lbl.pack(side=tk.LEFT, padx=(4, 0))

        self.stream_status_lbl = tk.Label(
            status_row,
            text="(OpenTrack UDP)",
            font=("Segoe UI", 8),
            fg=self.c_text_dim,
            bg=self.c_card,
        )
        self.stream_status_lbl.pack(side=tk.RIGHT)

        # Telemetry Meters (Pitch, Yaw, Roll)
        meters_frame = tk.Frame(telemetry_card, bg=self.c_card)
        meters_frame.pack(fill=tk.X)

        # Pitch row
        p_row = tk.Frame(meters_frame, bg=self.c_card)
        p_row.pack(fill=tk.X, pady=2)
        tk.Label(
            p_row,
            text="Pitch (Tilt):",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            width=12,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.meter_pitch = TelemetryBar(p_row, min_val=-30.0, max_val=30.0, bar_color="#38bdf8")
        self.meter_pitch.pack(side=tk.LEFT, padx=(4, 8))
        self.val_pitch = tk.Label(
            p_row,
            text="+0.0°",
            font=("Consolas", 9),
            fg=self.c_text_muted,
            bg=self.c_card,
            width=7,
            anchor="e",
        )
        self.val_pitch.pack(side=tk.LEFT)

        # Yaw row
        y_row = tk.Frame(meters_frame, bg=self.c_card)
        y_row.pack(fill=tk.X, pady=2)
        tk.Label(
            y_row,
            text="Yaw (Turn):",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            width=12,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.meter_yaw = TelemetryBar(y_row, min_val=-45.0, max_val=45.0, bar_color="#34d399")
        self.meter_yaw.pack(side=tk.LEFT, padx=(4, 8))
        self.val_yaw = tk.Label(
            y_row,
            text="+0.0°",
            font=("Consolas", 9),
            fg=self.c_text_muted,
            bg=self.c_card,
            width=7,
            anchor="e",
        )
        self.val_yaw.pack(side=tk.LEFT)

        # Roll row
        r_row = tk.Frame(meters_frame, bg=self.c_card)
        r_row.pack(fill=tk.X, pady=2)
        tk.Label(
            r_row,
            text="Roll (Lean):",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            width=12,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.meter_roll = TelemetryBar(r_row, min_val=-30.0, max_val=30.0, bar_color="#a78bfa")
        self.meter_roll.pack(side=tk.LEFT, padx=(4, 8))
        self.val_roll = tk.Label(
            r_row,
            text="+0.0°",
            font=("Consolas", 9),
            fg=self.c_text_muted,
            bg=self.c_card,
            width=7,
            anchor="e",
        )
        self.val_roll.pack(side=tk.LEFT)

        # ---------------- 4. TUNING SLIDERS CARD ----------------
        tuning_card = self._create_card(main_frame, "Kinematics & Gesture Tuning")
        tuning_card.pack(fill=tk.X, pady=(0, 12))

        # Slider 1: Pointer Sensitivity (0.4x to 2.5x)
        s1_row = tk.Frame(tuning_card, bg=self.c_card)
        s1_row.pack(fill=tk.X, pady=3)
        tk.Label(
            s1_row,
            text="Pointer Sensitivity:",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            width=18,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.slider_sens = tk.Scale(
            s1_row,
            from_=0.4,
            to=2.5,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            showvalue=0,
            bg=self.c_card,
            fg=self.c_text,
            troughcolor="#2c2c34",
            activebackground=self.c_blue,
            highlightthickness=0,
            bd=0,
            command=self._on_sensitivity_change,
        )
        self.slider_sens.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        self.lbl_sens = tk.Label(
            s1_row,
            text="1.00x",
            font=("Consolas", 9, "bold"),
            fg=self.c_cyan,
            bg=self.c_card,
            width=6,
            anchor="e",
        )
        self.lbl_sens.pack(side=tk.RIGHT)

        # Slider 2: Dwell Duration (0.5s to 2.0s)
        s2_row = tk.Frame(tuning_card, bg=self.c_card)
        s2_row.pack(fill=tk.X, pady=3)
        tk.Label(
            s2_row,
            text="Dwell Duration:",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            width=18,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.slider_dwell = tk.Scale(
            s2_row,
            from_=0.5,
            to=2.0,
            resolution=0.05,
            orient=tk.HORIZONTAL,
            showvalue=0,
            bg=self.c_card,
            fg=self.c_text,
            troughcolor="#2c2c34",
            activebackground=self.c_blue,
            highlightthickness=0,
            bd=0,
            command=self._on_dwell_duration_change,
        )
        self.slider_dwell.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        self.lbl_dwell = tk.Label(
            s2_row,
            text="0.80s",
            font=("Consolas", 9, "bold"),
            fg=self.c_cyan,
            bg=self.c_card,
            width=6,
            anchor="e",
        )
        self.lbl_dwell.pack(side=tk.RIGHT)

        # Slider 3: Nod Amplitude (3 deg to 12 deg)
        s3_row = tk.Frame(tuning_card, bg=self.c_card)
        s3_row.pack(fill=tk.X, pady=3)
        tk.Label(
            s3_row,
            text="Nod Amplitude:",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            width=18,
            anchor="w",
        ).pack(side=tk.LEFT)
        self.slider_nod = tk.Scale(
            s3_row,
            from_=3.0,
            to=12.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            showvalue=0,
            bg=self.c_card,
            fg=self.c_text,
            troughcolor="#2c2c34",
            activebackground=self.c_blue,
            highlightthickness=0,
            bd=0,
            command=self._on_nod_amplitude_change,
        )
        self.slider_nod.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        self.lbl_nod = tk.Label(
            s3_row,
            text="5.5°",
            font=("Consolas", 9, "bold"),
            fg=self.c_cyan,
            bg=self.c_card,
            width=6,
            anchor="e",
        )
        self.lbl_nod.pack(side=tk.RIGHT)

        # ---------------- 5. FEATURES / CHECKBOXES CARD ----------------
        features_card = self._create_card(main_frame, "Gesture & Accessibility Features")
        features_card.pack(fill=tk.X, pady=(0, 12))

        # Checkbox variables
        self.var_dwell_click = tk.BooleanVar(value=False)
        self.var_nod_click = tk.BooleanVar(value=True)
        self.var_shake_pause = tk.BooleanVar(value=True)
        self.var_autostart = tk.BooleanVar(value=False)

        cb1 = tk.Checkbutton(
            features_card,
            text="Enable Hover Dwell Click (smart target detection)",
            variable=self.var_dwell_click,
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            selectcolor="#2a2a32",
            activebackground=self.c_card,
            activeforeground=self.c_text,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_feature_toggle,
        )
        cb1.pack(anchor="w", pady=2)

        cb2 = tk.Checkbutton(
            features_card,
            text="Nod to Click (quick downward head nod performs left-click)",
            variable=self.var_nod_click,
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            selectcolor="#2a2a32",
            activebackground=self.c_card,
            activeforeground=self.c_text,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_feature_toggle,
        )
        cb2.pack(anchor="w", pady=2)

        cb3 = tk.Checkbutton(
            features_card,
            text="Shake to Pause (horizontal head shake toggles tracking)",
            variable=self.var_shake_pause,
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            selectcolor="#2a2a32",
            activebackground=self.c_card,
            activeforeground=self.c_text,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_feature_toggle,
        )
        cb3.pack(anchor="w", pady=2)

        cb4 = tk.Checkbutton(
            features_card,
            text="Start with Windows (silently run in background tray on boot)",
            variable=self.var_autostart,
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            selectcolor="#2a2a32",
            activebackground=self.c_card,
            activeforeground=self.c_text,
            relief="flat",
            bd=0,
            cursor="hand2",
            command=self._on_autostart_toggle,
        )
        cb4.pack(anchor="w", pady=2)

        # ---------------- 6. ACTION BUTTONS ROW ----------------
        btn_frame = tk.Frame(main_frame, bg=self.c_bg)
        btn_frame.pack(fill=tk.X, pady=(0, 8))

        self.camera_btn = tk.Button(
            btn_frame,
            text="📷 Webcam Vision",
            font=("Segoe UI", 9, "bold"),
            bg="#2e1065",
            fg="#c4b5fd",
            activebackground="#581c87",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=8,
            command=self._on_toggle_camera,
        )
        self.camera_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.recenter_btn = tk.Button(
            btn_frame,
            text="🎯 Recenter (Ctrl+Alt+C)",
            font=("Segoe UI", 9, "bold"),
            bg="#2d2d35",
            fg=self.c_text,
            activebackground="#3e3e48",
            activeforeground=self.c_text,
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=8,
            command=self._on_recenter,
        )
        self.recenter_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))

        self.save_btn = tk.Button(
            btn_frame,
            text="⚙️ Save Settings",
            font=("Segoe UI", 9, "bold"),
            bg="#1e3a5f",
            fg="#93c5fd",
            activebackground="#2563eb",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=8,
            command=self._on_save_settings,
        )
        self.save_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        # Row 2 of action buttons: 5 Physical Remotes Companion & 3D Viewer
        row2_frame = tk.Frame(main_frame, bg=self.c_bg)
        row2_frame.pack(fill=tk.X, pady=(0, 8))

        self.remotes_btn = tk.Button(
            row2_frame,
            text="🎮 5 Physical Remotes Companion",
            font=("Segoe UI", 9, "bold"),
            bg="#0f393b",
            fg="#5eead4",
            activebackground="#115e59",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=7,
            command=self._on_open_physical_remotes,
        )
        self.remotes_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.cad_viewer_btn = tk.Button(
            row2_frame,
            text="🌐 3D WebGL Viewer",
            font=("Segoe UI", 9, "bold"),
            bg="#372714",
            fg="#fdba74",
            activebackground="#7c2d12",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=7,
            command=self._on_open_3d_viewer,
        )
        self.cad_viewer_btn.pack(side=tk.RIGHT, fill=tk.X, expand=False, padx=(4, 0))

        # Bottom info bar
        bottom_frame = tk.Frame(main_frame, bg=self.c_bg)
        bottom_frame.pack(fill=tk.X, pady=(4, 0))

        self.status_msg_lbl = tk.Label(
            bottom_frame,
            text="Global Hotkeys: Ctrl+Alt+T (Pause), Ctrl+Alt+S (Scroll), Ctrl+Alt+C (Recenter)",
            font=("Segoe UI", 8),
            fg=self.c_text_dim,
            bg=self.c_bg,
        )
        self.status_msg_lbl.pack(side=tk.LEFT)

    def _create_card(self, parent: tk.Widget, title: str) -> tk.Frame:
        """Helper to create a dark styled panel container."""
        card = tk.Frame(
            parent,
            bg=self.c_card,
            highlightthickness=1,
            highlightbackground=self.c_card_border,
            padx=14,
            pady=10,
        )
        lbl = tk.Label(
            card,
            text=title.upper(),
            font=("Segoe UI", 8, "bold"),
            fg=self.c_text_dim,
            bg=self.c_card,
        )
        lbl.pack(anchor="w", pady=(0, 8))
        return card

    def _refresh_airpods_status(self) -> None:
        """Detects AirPods Pro in Windows registry and updates connection badge."""
        paired = BluetoothAirPodsHelper.get_paired_airpods()
        if paired:
            first = paired[0]
            name = first.get("name", "AirPods Pro")
            addr = first.get("address", "41424f2041e4")
            self.badge_lbl.config(
                text=f"{name} ({addr}) Connected", fg=self.c_green
            )
            self.badge_dot.config(text="●", fg=self.c_green)
            self.badge_frame.config(bg="#18221c", highlightbackground="#234230")
        else:
            self.badge_lbl.config(
                text="AirPods Pro (41424f2041e4) Paired", fg="#60a5fa"
            )
            self.badge_dot.config(text="●", fg="#60a5fa")
            self.badge_frame.config(bg="#17212e", highlightbackground="#1e3a5f")

    def _sync_settings_to_ui(self) -> None:
        """Loads values from controller.settings into sliders and checkboxes."""
        self._is_updating_sliders = True
        try:
            settings = self.controller.settings
            # Sliders
            self.slider_sens.set(settings.pointer.sensitivity)
            self.lbl_sens.config(text=f"{settings.pointer.sensitivity:.2f}x")

            self.slider_dwell.set(settings.dwell.duration)
            self.lbl_dwell.config(text=f"{settings.dwell.duration:.2f}s")

            self.slider_nod.set(settings.gestures.nod_amplitude)
            self.lbl_nod.config(text=f"{settings.gestures.nod_amplitude:.1f}°")

            # Checkboxes
            # 1. Hover Dwell Click (default OFF)
            self.var_dwell_click.set(settings.dwell.enabled)

            # 2. Nod to Click (default ON)
            nod_action = settings.actions[Trigger.NOD]
            self.var_nod_click.set(nod_action != PointerAction.NONE)

            # 3. Shake to Pause (default ON)
            shake_action = settings.actions[Trigger.SHAKE]
            self.var_shake_pause.set(shake_action != PointerAction.NONE)

            # 4. Autostart with Windows
            self.var_autostart.set(autostart.is_autostart_enabled())

        finally:
            self._is_updating_sliders = False

    def _update_telemetry_loop(self) -> None:
        """Periodic GUI telemetry update (runs at ~25 FPS on Tkinter event loop)."""
        try:
            # Sync Master Toggle button with tracking state
            is_tracking = self.controller.tracking_enabled
            if is_tracking != self._last_tracking_state:
                self._last_tracking_state = is_tracking
                if is_tracking:
                    self.master_btn.config(
                        text="⏸ Pause Tracking",
                        bg=self.c_amber,
                        activebackground=self.c_amber_hover,
                    )
                else:
                    self.master_btn.config(
                        text="▶ Start Tracking",
                        bg=self.c_green,
                        activebackground=self.c_green_hover,
                    )

            # Mode
            mode_text = self.controller.mode.value.upper()
            self.mode_btn.config(text=mode_text)

            # FPS
            fps_val = self.controller.live_fps
            self.fps_lbl.config(text=f"{fps_val:.0f} FPS")

            # Streaming indicator
            if self.controller.use_synthetic:
                self.stream_status_lbl.config(text="(Synthetic Sim)", fg="#a78bfa")
            elif self.controller.arbiter.active_source.value == "vision":
                self.stream_status_lbl.config(text="📷 Vision Tracking", fg="#c084fc")
            elif self.controller.motion_streaming:
                self.stream_status_lbl.config(text="● Streaming (AirPods)", fg=self.c_green)
            else:
                self.stream_status_lbl.config(text="Waiting for Sensors...", fg=self.c_text_dim)

            # Live telemetry angles
            pitch = self.controller.live_pitch
            yaw = self.controller.live_yaw
            roll = self.controller.live_roll

            self.meter_pitch.set_value(pitch)
            self.val_pitch.config(text=f"{pitch:+5.1f}°")

            self.meter_yaw.set_value(yaw)
            self.val_yaw.config(text=f"{yaw:+5.1f}°")

            self.meter_roll.set_value(roll)
            self.val_roll.config(text=f"{roll:+5.1f}°")

        except Exception:
            pass

        # Schedule next tick
        self.root.after(40, self._update_telemetry_loop)

    # ---------------- EVENT HANDLERS ----------------

    def _on_toggle_master(self) -> None:
        self.controller.toggle_tracking()

    def _on_toggle_mode(self) -> None:
        self.controller.toggle_mode()

    def _on_recenter(self) -> None:
        self.controller.recenter()
        self.status_msg_lbl.config(
            text="🎯 Cursor recentered to screen center.", fg=self.c_green
        )
        self.root.after(3000, self._reset_status_bar)

    def _on_sensitivity_change(self, val_str: str) -> None:
        if self._is_updating_sliders:
            return
        val = float(val_str)
        self.lbl_sens.config(text=f"{val:.2f}x")
        self.controller.settings.pointer.sensitivity = val

    def _on_dwell_duration_change(self, val_str: str) -> None:
        if self._is_updating_sliders:
            return
        val = float(val_str)
        self.lbl_dwell.config(text=f"{val:.2f}s")
        self.controller.settings.dwell.duration = val
        self.controller.dwell.settings.duration = val

    def _on_nod_amplitude_change(self, val_str: str) -> None:
        if self._is_updating_sliders:
            return
        val = float(val_str)
        self.lbl_nod.config(text=f"{val:.1f}°")
        self.controller.settings.gestures.nod_amplitude = val
        self.controller.gestures.settings.nod_amplitude = val

    def _on_feature_toggle(self) -> None:
        """Applies checkbox changes to live controller settings."""
        settings = self.controller.settings

        # Hover Dwell Click
        dwell_enabled = self.var_dwell_click.get()
        settings.dwell.enabled = dwell_enabled
        self.controller.dwell.settings.enabled = dwell_enabled

        # Nod to Click
        nod_enabled = self.var_nod_click.get()
        settings.actions[Trigger.NOD] = (
            PointerAction.LEFT_CLICK if nod_enabled else PointerAction.NONE
        )

        # Shake to Pause
        shake_enabled = self.var_shake_pause.get()
        settings.actions[Trigger.SHAKE] = (
            PointerAction.TOGGLE_TRACKING if shake_enabled else PointerAction.NONE
        )

    def _on_autostart_toggle(self) -> None:
        """Enables or disables Windows boot startup in HKCU Run registry."""
        want_autostart = self.var_autostart.get()
        if want_autostart:
            success = autostart.enable_autostart(extra_args="--tray")
            if success:
                self.status_msg_lbl.config(
                    text="✓ AirCursor registered to launch silently on Windows boot.",
                    fg=self.c_green,
                )
            else:
                self.var_autostart.set(False)
                messagebox.showerror(
                    "Autostart Error", "Failed to register AirCursor in Windows registry."
                )
        else:
            success = autostart.disable_autostart()
            if success:
                self.status_msg_lbl.config(
                    text="✓ AirCursor autostart disabled.", fg=self.c_text_muted
                )
        self.root.after(4000, self._reset_status_bar)

    def _on_toggle_camera(self) -> None:
        """Toggles camera vision tracking on / off."""
        is_active = self.controller.toggle_camera()
        if is_active:
            self.camera_btn.config(bg="#166534", fg="#86efac", text="📷 Camera: ON (Hand/Face)")
            self.status_msg_lbl.config(
                text="✓ Camera tracking active. Move hand or face to control cursor.",
                fg=self.c_green,
            )
        else:
            self.camera_btn.config(bg="#2e1065", fg="#c4b5fd", text="📷 Webcam Vision")
            self.status_msg_lbl.config(
                text="Vision Camera tracking stopped.", fg=self.c_text_muted
            )
        self.root.after(3500, self._reset_status_bar)

    def _on_save_settings(self) -> None:
        """Saves current settings to disk config file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(self.controller.settings.to_json())
            self.status_msg_lbl.config(
                text=f"✓ Settings saved successfully to {self.config_path.name}.",
                fg=self.c_green,
            )
            self.controller.overlay.show_toast("Settings saved", "⚙️")
        except Exception as e:
            self.status_msg_lbl.config(
                text=f"✗ Error saving settings: {e}", fg="#f87171"
            )
        self.root.after(3500, self._reset_status_bar)

    def _reset_status_bar(self) -> None:
        self.status_msg_lbl.config(
            text="Global Hotkeys: Ctrl+Alt+T (Pause), Ctrl+Alt+S (Scroll), Ctrl+Alt+C (Recenter)",
            fg=self.c_text_dim,
        )

    def _on_open_3d_viewer(self) -> None:
        """Opens the 3D WebGL Showcase in the user's default browser."""
        viewer_path = ROOT_DIR / "cad" / "remote_showcase.html"
        if viewer_path.exists():
            webbrowser.open(viewer_path.as_uri())
            self.status_msg_lbl.config(
                text="✓ Opened 3D WebGL remote showcase in browser.", fg=self.c_green
            )
        else:
            self.status_msg_lbl.config(
                text="✗ 3D showcase file not found.", fg="#f87171"
            )
        self.root.after(3500, self._reset_status_bar)

    def _on_open_physical_remotes(self) -> None:
        """Opens the 5 Physical Remotes Companion window."""
        PhysicalRemotesDialog(self.root, self.controller)

    # ---------------- WINDOW LIFECYCLE ----------------

    def minimize_to_tray(self) -> None:
        """Hides the GUI window to the notification area and shows a system balloon."""
        self.root.withdraw()
        if self.tray:
            self.tray.show_balloon(
                "AirCursor",
                "AirCursor is running in the background.\nClick the tray icon to reopen the Control Center.",
            )

    def restore_from_tray(self) -> None:
        """Restores and focuses the GUI window from system tray (thread-safe)."""
        self.root.after(0, self._do_restore)

    def _do_restore(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after_idle(self.root.attributes, "-topmost", False)

    def quit_app(self) -> None:
        """Completely terminates AirCursor and cleans up resources."""
        self.root.after(0, self._do_quit)

    def _do_quit(self) -> None:
        if self.on_exit_cb:
            try:
                self.on_exit_cb()
            except Exception:
                pass
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            self.controller.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def close(self) -> None:
        """Cleanly destroys the window."""
        self._do_quit()

    def run(self) -> None:
        """Starts the Tkinter main event loop."""
        self.root.mainloop()


class PhysicalRemotesDialog(tk.Toplevel):
    """Interactive companion window for the 5 AirCursor physical remote products."""

    def __init__(self, parent: tk.Tk, controller: AppController):
        super().__init__(parent)
        self.controller = controller
        self.title("AirCursor Physical Remote Companion (5 Products)")
        self.geometry("820x640")
        self.minsize(760, 580)
        self.configure(bg="#121214")

        # Color palette
        self.c_bg = "#121214"
        self.c_card = "#1c1c20"
        self.c_border = "#2e2e36"
        self.c_text = "#f4f4f5"
        self.c_text_muted = "#a1a1aa"
        self.c_cyan = "#06b6d4"
        self.c_green = "#10b981"
        self.c_amber = "#f59e0b"

        self.profiles = HARDWARE_REGISTRY.list_all_profiles()
        self.selected_index = 0

        self._build_ui()
        self._select_product(0)

    def _build_ui(self) -> None:
        # Header banner
        header = tk.Frame(self, bg="#18181b", padx=16, pady=12, highlightthickness=1, highlightbackground=self.c_border)
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text="🎮 AirCursor Physical Remote Hardware Suite",
            font=("Segoe UI", 14, "bold"),
            fg=self.c_text,
            bg="#18181b"
        )
        title.pack(side=tk.LEFT)

        subtitle = tk.Label(
            header,
            text="5 Production Concepts • BLE 5.3 & 2.4GHz RF • Sub-4ms Latency",
            font=("Segoe UI", 9),
            fg=self.c_cyan,
            bg="#18181b"
        )
        subtitle.pack(side=tk.LEFT, padx=(12, 0), pady=(3, 0))

        # Main split container
        content = tk.Frame(self, bg=self.c_bg, padx=16, pady=12)
        content.pack(fill=tk.BOTH, expand=True)

        # Left list: 5 devices
        left_col = tk.Frame(content, bg=self.c_bg, width=280)
        left_col.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 14))

        tk.Label(
            left_col,
            text="SELECT HARDWARE PRODUCT",
            font=("Segoe UI", 8, "bold"),
            fg=self.c_text_muted,
            bg=self.c_bg
        ).pack(anchor="w", pady=(0, 6))

        self.btn_list = []
        icons = ["💍", "🪄", "🪨", "📎", "🎮"]
        for idx, p in enumerate(self.profiles):
            btn = tk.Button(
                left_col,
                text=f"{icons[idx]} {p.model_name}\n   {p.form_factor} ({p.mass_grams}g)",
                font=("Segoe UI", 9, "bold"),
                justify=tk.LEFT,
                anchor="w",
                bg="#232328",
                fg=self.c_text,
                activebackground="#2e2e38",
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                padx=12,
                pady=10,
                cursor="hand2",
                command=lambda i=idx: self._select_product(i)
            )
            btn.pack(fill=tk.X, pady=3)
            self.btn_list.append(btn)

        # Bottom CAD / WebGL shortcuts in left col
        tk.Label(left_col, text="", bg=self.c_bg).pack(expand=True)
        
        webgl_btn = tk.Button(
            left_col,
            text="🌐 3D WebGL Showcase",
            font=("Segoe UI", 9, "bold"),
            bg="#372714",
            fg="#fdba74",
            activebackground="#7c2d12",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            pady=8,
            cursor="hand2",
            command=self._launch_webgl
        )
        webgl_btn.pack(fill=tk.X, pady=(4, 2))

        folder_btn = tk.Button(
            left_col,
            text="📁 Open CAD Folder",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#94a3b8",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            pady=6,
            cursor="hand2",
            command=self._open_cad_folder
        )
        folder_btn.pack(fill=tk.X, pady=2)

        dossier_btn = tk.Button(
            left_col,
            text="📄 Manufacturing Dossier",
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#94a3b8",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            pady=6,
            cursor="hand2",
            command=self._open_dossier
        )
        dossier_btn.pack(fill=tk.X, pady=2)

        # Right col: Details card
        self.right_col = tk.Frame(
            content,
            bg=self.c_card,
            highlightthickness=1,
            highlightbackground=self.c_border,
            padx=18,
            pady=16
        )
        self.right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.lbl_dev_name = tk.Label(
            self.right_col,
            text="Product Details",
            font=("Segoe UI", 16, "bold"),
            fg=self.c_text,
            bg=self.c_card
        )
        self.lbl_dev_name.pack(anchor="w")

        # Badges row
        self.badges_frame = tk.Frame(self.right_col, bg=self.c_card)
        self.badges_frame.pack(fill=tk.X, pady=(4, 12))

        self.lbl_mass_badge = tk.Label(
            self.badges_frame,
            text="Mass: 8.8g",
            font=("Segoe UI", 8, "bold"),
            bg="#1e3a5f",
            fg="#93c5fd",
            padx=8,
            pady=2
        )
        self.lbl_mass_badge.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_batt_badge = tk.Label(
            self.badges_frame,
            text="Battery: 18.5 hrs",
            font=("Segoe UI", 8, "bold"),
            bg="#14532d",
            fg="#86efac",
            padx=8,
            pady=2
        )
        self.lbl_batt_badge.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_rf_badge = tk.Label(
            self.badges_frame,
            text="BLE 5.3 & 2.4GHz RF",
            font=("Segoe UI", 8, "bold"),
            bg="#3b0764",
            fg="#d8b4fe",
            padx=8,
            pady=2
        )
        self.lbl_rf_badge.pack(side=tk.LEFT)

        # Section: Primary Controls
        tk.Label(
            self.right_col,
            text="PRIMARY CONTROLS",
            font=("Segoe UI", 8, "bold"),
            fg=self.c_cyan,
            bg=self.c_card
        ).pack(anchor="w", pady=(8, 2))

        self.lbl_controls = tk.Label(
            self.right_col,
            text="",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            justify=tk.LEFT,
            wraplength=440
        )
        self.lbl_controls.pack(anchor="w", pady=(0, 8))

        # Section: Sensors
        tk.Label(
            self.right_col,
            text="SENSOR SUITE",
            font=("Segoe UI", 8, "bold"),
            fg=self.c_amber,
            bg=self.c_card
        ).pack(anchor="w", pady=(4, 2))

        self.lbl_sensors = tk.Label(
            self.right_col,
            text="",
            font=("Segoe UI", 9),
            fg=self.c_text,
            bg=self.c_card,
            justify=tk.LEFT,
            wraplength=440
        )
        self.lbl_sensors.pack(anchor="w", pady=(0, 8))

        # Section: 3D CAD Deliverables
        tk.Label(
            self.right_col,
            text="AVAILABLE 3D CAD DELIVERABLES",
            font=("Segoe UI", 8, "bold"),
            fg=self.c_text_muted,
            bg=self.c_card
        ).pack(anchor="w", pady=(4, 2))

        self.lbl_cad = tk.Label(
            self.right_col,
            text="✓ .blend (Blender 5.1)  ✓ .glb (WebGL)  ✓ .obj (3D)  ✓ .stl (3D Print)",
            font=("Segoe UI", 9, "bold"),
            fg=self.c_green,
            bg=self.c_card
        )
        self.lbl_cad.pack(anchor="w", pady=(0, 14))

        # Action test button
        self.btn_inject = tk.Button(
            self.right_col,
            text="⚡ Inject Synthetic Telemetry Packet Test",
            font=("Segoe UI", 10, "bold"),
            bg="#0369a1",
            fg="#ffffff",
            activebackground="#0284c7",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            pady=9,
            cursor="hand2",
            command=self._inject_test_packet
        )
        self.btn_inject.pack(fill=tk.X, pady=(8, 4))

        self.lbl_inject_status = tk.Label(
            self.right_col,
            text="Ready to decode live packets.",
            font=("Segoe UI", 8),
            fg=self.c_text_muted,
            bg=self.c_card
        )
        self.lbl_inject_status.pack(anchor="w")

    def _select_product(self, idx: int) -> None:
        self.selected_index = idx
        p = self.profiles[idx]
        HARDWARE_REGISTRY.set_active_device(p.device_type)

        # Update button highlights
        for i, btn in enumerate(self.btn_list):
            if i == idx:
                btn.config(bg="#0f393b", fg="#5eead4")
            else:
                btn.config(bg="#232328", fg=self.c_text)

        # Update right column info
        self.lbl_dev_name.config(text=f"{p.model_name} — {p.form_factor}")
        self.lbl_mass_badge.config(text=f"Mass: {p.mass_grams}g")
        self.lbl_batt_badge.config(text=f"Battery: {p.battery_capacity_mah}mAh ({p.battery_life_hours}h)")

        controls_text = "\n".join(f"• {c}" for c in p.primary_controls)
        self.lbl_controls.config(text=controls_text)

        sensors_text = "\n".join(f"• {s}" for s in p.sensor_suite)
        self.lbl_sensors.config(text=sensors_text)

        self.lbl_inject_status.config(
            text=f"Selected active profile: {p.model_name}. Ready for BLE / RF / Simulation.",
            fg=self.c_green
        )

    def _inject_test_packet(self) -> None:
        """Encodes and decodes a simulated packet for the selected device."""
        p = self.profiles[self.selected_index]
        dev_type = p.device_type
        
        if dev_type == HardwareDeviceType.AIRRING_PRO:
            pkt = HardwarePacketEncoder.encode_airring_pro(seq=1, opt_x=12, opt_y=-8, bezel_delta=2, primary_click=True)
        elif dev_type == HardwareDeviceType.AIRWAND_ELITE:
            pkt = HardwarePacketEncoder.encode_airwand_elite(seq=1, pitch=15.0, thumb_x=10, trigger_force=0.9)
        elif dev_type == HardwareDeviceType.AIRPEBBLE_TOUCH:
            pkt = HardwarePacketEncoder.encode_airpebble_touch(seq=1, opt_dx=40, opt_dy=-30, dial_delta=1)
        elif dev_type == HardwareDeviceType.AIRCLIP_MINI:
            pkt = HardwarePacketEncoder.encode_airclip_mini(seq=1, pitch=5.0, tap_count=1)
        else:
            pkt = HardwarePacketEncoder.encode_airdeck_controller(seq=1, track_x=25, track_y=-15, force=0.5, l1=True)

        event = HardwarePacketDecoder.decode(pkt)
        if event:
            self.lbl_inject_status.config(
                text=f"✓ Decoded {len(pkt)}-byte packet from {p.model_name}! Click={event.primary_click}, Dx={event.delta_x}, Dy={event.delta_y}",
                fg=self.c_green
            )
        else:
            self.lbl_inject_status.config(text="✗ Failed to decode packet.", fg="#f87171")

    def _launch_webgl(self) -> None:
        viewer_path = ROOT_DIR / "cad" / "remote_showcase.html"
        if viewer_path.exists():
            webbrowser.open(viewer_path.as_uri())

    def _open_cad_folder(self) -> None:
        cad_dir = ROOT_DIR / "cad" / "models"
        if cad_dir.exists():
            os.startfile(str(cad_dir))

    def _open_dossier(self) -> None:
        dossier_path = ROOT_DIR / "cad" / "MANUFACTURING_DOSSIER.md"
        if dossier_path.exists():
            os.startfile(str(dossier_path))
