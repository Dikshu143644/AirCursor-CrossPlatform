#!/usr/bin/env python3
"""
AirCursor for Linux - Standalone Head-Tracking Pointer Daemon.
Integrates AirPods BlueZ L2CAP (MTU 2582), uinput virtual input synthesis,
AT-SPI smart dwell probing, GTK/Cairo click-through overlay, and AirCursorCore.
"""

from __future__ import annotations
import argparse
import json
import os
import signal
import sys
import time
from typing import Optional

from aircursor_core import (
    ActionMap,
    AngleMath,
    AppSettings,
    CursorHistory,
    DwellDetector,
    GestureDetector,
    HeadGesture,
    MotionDifferentiator,
    MotionSample,
    PointerAction,
    PointerMapper,
    PointerSmoother,
    Trigger,
    Vec2,
)
from airpods_bluez import AirPodsBlueZDriver, BluetoothScanner
from event_synthesizer import LinuxEventSynthesizer
from clickable_probe import LinuxClickableProbe
from overlay import LinuxOverlayController


class AirCursorLinuxDaemon:
    """Central daemon tying sensors, math core, input synthesis, and visual overlay."""

    def __init__(self, settings: AppSettings, mac_address: str, enable_overlay: bool = True, enable_atspi: bool = True) -> None:
        self.settings = settings
        self.mac_address = mac_address
        self.enable_overlay = enable_overlay
        self.enable_atspi = enable_atspi

        # State flags
        self.is_tracking_active = True
        self.is_scroll_mode = False
        self._running = False

        # Core math & interaction components
        self.differentiator = MotionDifferentiator()
        self.smoother = PointerSmoother()
        self.history = CursorHistory(capacity=360)
        self.gesture_detector = GestureDetector(self.settings.gestures)
        self.dwell_detector = DwellDetector(self.settings.dwell)

        # Subsystems
        self.synthesizer = LinuxEventSynthesizer()
        self.probe = LinuxClickableProbe() if enable_atspi else None
        self.overlay = LinuxOverlayController() if enable_overlay else None
        self.driver: Optional[AirPodsBlueZDriver] = None

        # Hover caching
        self._last_checked_anchor_id = -1
        self._is_element_clickable = False

    def start(self) -> None:
        """Starts daemon and initiates background worker loops."""
        self._running = True
        print(f"[*] Starting AirCursor Linux daemon...")
        print(f"[*] Target AirPods MAC: {self.mac_address}")
        print(f"[*] Sensitivity: {self.settings.pointer.sensitivity}x, Deadzone: {self.settings.pointer.deadzone}°/s")
        print(f"[*] Dwell Hover Click: {'Enabled' if self.settings.dwell.enabled else 'Disabled'} ({self.settings.dwell.duration}s)")

        # Initialize AirPods BlueZ driver
        self.driver = AirPodsBlueZDriver(
            mac_address=self.mac_address,
            on_sample=self.on_motion_sample,
            on_status=self.on_driver_status,
        )
        self.driver.start()

        # Run frame tick loop (100 Hz = 10 ms interval)
        self._main_loop()

    def stop(self) -> None:
        """Clean shutdown handler."""
        if not self._running:
            return
        self._running = False
        print("\n[*] Shutting down AirCursor daemon...")

        if self.driver:
            self.driver.stop()
        if self.overlay:
            self.overlay.close()
        if self.synthesizer:
            self.synthesizer.close()
        print("[*] Goodbye!")

    def on_driver_status(self, status: str, connected: bool) -> None:
        print(f"[Bluetooth] {status}")
        if self.overlay and self.settings.show_hud:
            self.overlay.show_hud(status)

    # --------------------------------------------------------------------------
    # Motion Pipeline & Gesture Dispatch
    # --------------------------------------------------------------------------

    def on_motion_sample(self, sample: MotionSample) -> None:
        """Invoked on incoming orientation sample from BlueZ L2CAP driver."""
        rates = self.differentiator.push(sample)

        # 1. Evaluate Head Gestures (Nod, Shake, Tilt)
        enabled_gestures = self.settings.actions.enabled_head_gestures
        gesture_event = self.gesture_detector.process(sample, enabled_gestures)
        if gesture_event:
            self.handle_gesture(gesture_event)

        # 2. Update Velocity Target for Smoother
        if rates and self.is_tracking_active:
            target_vel = PointerMapper.cursor_velocity(rates, self.settings.pointer)
            self.smoother.set_target(target_vel, sample.timestamp)

    def handle_gesture(self, event) -> None:
        """Translates gesture into mapped action."""
        trigger = Trigger(event.gesture)
        action = self.settings.actions.get(trigger)
        print(f"[Gesture] Detected {event.gesture.value} (magnitude: {event.magnitude:.1f}°) -> Action: {action.value}")

        # Undo cursor jitter caused by nod movement before clicking
        if event.gesture == HeadGesture.NOD and action.is_click:
            pre_nod_pos = self.history.position_at(event.start_time)
            if pre_nod_pos:
                cur_x, cur_y = self.synthesizer.get_current_location()
                dx = pre_nod_pos.x - cur_x
                dy = pre_nod_pos.y - cur_y
                self.synthesizer.move_relative(dx, dy)

        self.execute_action(action)

    def execute_action(self, action: PointerAction) -> None:
        """Executes a pointer, mouse, or system action."""
        cur_x, cur_y = self.synthesizer.get_current_location()

        if action == PointerAction.NONE:
            return
        elif action == PointerAction.LEFT_CLICK:
            self.synthesizer.click("left")
            if self.overlay and self.settings.show_click_pulse:
                self.overlay.pulse(cur_x, cur_y)
            self.dwell_detector.reset()
        elif action == PointerAction.RIGHT_CLICK:
            self.synthesizer.click("right")
            if self.overlay and self.settings.show_click_pulse:
                self.overlay.pulse(cur_x, cur_y)
            self.dwell_detector.reset()
        elif action == PointerAction.DOUBLE_CLICK:
            self.synthesizer.click("left", count=2)
            if self.overlay and self.settings.show_click_pulse:
                self.overlay.pulse(cur_x, cur_y)
            self.dwell_detector.reset()
        elif action == PointerAction.MIDDLE_CLICK:
            self.synthesizer.click("middle")
            self.dwell_detector.reset()
        elif action == PointerAction.TOGGLE_DRAG:
            locked = self.synthesizer.toggle_drag()
            if self.overlay and self.settings.show_hud:
                self.overlay.show_hud("Drag Lock: ON" if locked else "Drag Lock: OFF")
        elif action == PointerAction.TOGGLE_SCROLL_MODE:
            self.is_scroll_mode = not self.is_scroll_mode
            if self.overlay and self.settings.show_hud:
                self.overlay.show_hud("Scroll Mode: ON" if self.is_scroll_mode else "Scroll Mode: OFF")
        elif action == PointerAction.TOGGLE_TRACKING:
            self.is_tracking_active = not self.is_tracking_active
            self.smoother.reset()
            if self.overlay and self.settings.show_hud:
                self.overlay.show_hud("Tracking: RESUMED" if self.is_tracking_active else "Tracking: PAUSED")
        elif action == PointerAction.RECENTER:
            center_x = self.synthesizer.screen_width / 2.0
            center_y = self.synthesizer.screen_height / 2.0
            dx = center_x - cur_x
            dy = center_y - cur_y
            self.synthesizer.move_relative(dx, dy)
            self.smoother.reset()
        elif action == PointerAction.MISSION_CONTROL:
            self.synthesizer.mission_control()
        elif action == PointerAction.BACK:
            self.synthesizer.browser_back()
        elif action == PointerAction.FORWARD:
            self.synthesizer.browser_forward()
        elif action == PointerAction.SCREENSHOT:
            self.synthesizer.screenshot()

    # --------------------------------------------------------------------------
    # Main Frame Step Loop (60-120 Hz)
    # --------------------------------------------------------------------------

    def _main_loop(self) -> None:
        last_time = time.time()
        frame_interval = 1.0 / 100.0  # 100 Hz

        while self._running:
            now = time.time()
            dt = now - last_time
            last_time = now

            if self.is_tracking_active:
                # 1. Advance Smoother
                displacement = self.smoother.step(now, dt, self.settings.pointer.smoothing)

                if self.is_scroll_mode:
                    # Map vertical & horizontal head turns to scrolling
                    v_scroll = int(-displacement.y * 0.15 * self.settings.pointer.scroll_speed)
                    h_scroll = int(-displacement.x * 0.15 * self.settings.pointer.scroll_speed)
                    if self.settings.pointer.invert_scroll:
                        v_scroll, h_scroll = -v_scroll, -h_scroll
                    if v_scroll != 0 or h_scroll != 0:
                        self.synthesizer.scroll(v_scroll, h_scroll)
                else:
                    if displacement.x != 0.0 or displacement.y != 0.0:
                        self.synthesizer.move_relative(displacement.x, displacement.y)

                # 2. Update Cursor History
                cur_x, cur_y = self.synthesizer.get_current_location()
                pos = Vec2(cur_x, cur_y)
                self.history.append(pos, now)

                # 3. Dwell Hover Click Check
                if self.settings.dwell.enabled and not self.is_scroll_mode:
                    update = self.dwell_detector.update(pos, now)

                    # Probe element interactivity once per new resting anchor
                    if self.dwell_detector.anchor_id != self._last_checked_anchor_id:
                        self._last_checked_anchor_id = self.dwell_detector.anchor_id
                        if self.settings.dwell.smart and self.probe:
                            self._is_element_clickable = self.probe.is_clickable(cur_x, cur_y)
                        else:
                            self._is_element_clickable = True

                    # Only show progress and click if element is clickable
                    progress = update.progress if self._is_element_clickable else None

                    if self.overlay:
                        self.overlay.update(progress, cur_x, cur_y)

                    if update.fired and self._is_element_clickable:
                        dwell_action = self.settings.actions.get(Trigger.DWELL)
                        self.execute_action(dwell_action)
                else:
                    if self.overlay:
                        self.overlay.update(None, cur_x, cur_y)

            # Frame rate pacing
            elapsed = time.time() - now
            sleep_time = max(0.001, frame_interval - elapsed)
            time.sleep(sleep_time)


# ==============================================================================
# CLI Entry Point & Parameter Parsing
# ==============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="AirCursor for Linux - AirPods Head-Tracking Mouse Daemon")
    parser.add_argument("--address", "-a", type=str, help="AirPods Bluetooth MAC address (e.g. AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--scan", "-s", action="store_true", help="Scan and list paired AirPods then exit")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="Pointer sensitivity multiplier (default 1.0)")
    parser.add_argument("--deadzone", type=float, default=3.0, help="Tremor filter deadzone in deg/s (default 3.0)")
    parser.add_argument("--dwell-duration", type=float, default=0.8, help="Dwell hover duration in seconds (default 0.8)")
    parser.add_argument("--no-dwell", action="store_true", help="Disable dwell hover clicking")
    parser.add_argument("--no-smart-dwell", action="store_true", help="Click everywhere without probing AT-SPI for buttons")
    parser.add_argument("--no-overlay", action="store_true", help="Disable GTK transparent dwell ring overlay")
    parser.add_argument("--no-atspi", action="store_true", help="Disable AT-SPI accessibility tree probing")
    parser.add_argument("--config", "-c", type=str, help="Path to custom JSON configuration file")
    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Device Scanning
    if args.scan:
        print("[*] Scanning paired AirPods / Beats devices...")
        devices = BluetoothScanner.find_paired_airpods()
        if not devices:
            print("[-] No paired AirPods found. Pair them in your Linux Bluetooth settings first.")
        else:
            print(f"[+] Found {len(devices)} device(s):")
            for mac, name in devices:
                print(f"    - {name} ({mac})")
        return

    # 2. Determine Bluetooth Address
    mac = args.address
    if not mac:
        devices = BluetoothScanner.find_paired_airpods()
        if devices:
            mac, name = devices[0]
            print(f"[+] Auto-selected paired device: {name} ({mac})")
        else:
            print("[-] No paired AirPods found automatically.")
            print("    Please provide --address AA:BB:CC:DD:EE:FF or run with --scan.")
            sys.exit(1)

    # 3. Load or Configure Settings
    settings = AppSettings()
    if args.config and os.path.isfile(args.config):
        try:
            with open(args.config, "r") as f:
                settings = AppSettings.from_dict(json.load(f))
            print(f"[+] Loaded configuration from {args.config}")
        except Exception as e:
            print(f"[!] Warning: Failed to load config: {e}. Using defaults.")

    if args.sensitivity:
        settings.pointer.sensitivity = args.sensitivity
    if args.deadzone:
        settings.pointer.deadzone = args.deadzone
    if args.dwell_duration:
        settings.dwell.duration = args.dwell_duration
    if args.no_dwell:
        settings.dwell.enabled = False
    if args.no_smart_dwell:
        settings.dwell.smart = False

    # 4. Instantiate & Launch Daemon
    daemon = AirCursorLinuxDaemon(
        settings=settings,
        mac_address=mac,
        enable_overlay=not args.no_overlay,
        enable_atspi=not args.no_atspi,
    )

    def signal_handler(sig, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        daemon.start()
    except KeyboardInterrupt:
        daemon.stop()


if __name__ == "__main__":
    main()
