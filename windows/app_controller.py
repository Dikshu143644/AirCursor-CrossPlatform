"""AirCursor Windows AppController.

Full 120Hz head tracking orchestrator for Windows matching macOS AppController lifecycle:
- Manages sensor streaming (UDP OpenTrack or Synthetic generator)
- Differentiates attitude into angular rates (MotionDifferentiator)
- Maps rates to screen velocity with deadzone, sensitivity, and acceleration (PointerMapper)
- Smooths motion with frame-rate independent exponential filter (PointerSmoother)
- Human-Input Arbiter: yields 100% control to physical mouse with 1.5s cooldown when moved
- Standby State Machine: starts in paused/standby mode; dwell click disabled by default
- Detects deliberate head gestures (Nod, Shake, Tilt) with automatic cursor drift rollback
- Detects dwell resting spots and smart interactive probe checks (ClickableProbe)
- Injects inputs via Win32 SendInput (EventSynthesizer)
- Renders HUD feedback, dwell progress ring, and toasts (OverlayController)
- Captures AirPods stem presses (StemListener)
- Global hotkeys (Ctrl+Alt+T: Pause/Resume, Ctrl+Alt+S: Scroll/Pointer, Ctrl+Alt+C: Recenter, Ctrl+Alt+D: Drag)
"""

from __future__ import annotations

import enum
import math
import os
import sys
import threading
import time
from typing import Callable, Optional, Tuple

# Import Core modules
sys.path.insert(0, r"c:\Users\omkar\TV\AirCursor_CrossPlatform")
from aircursor_core.actions import ActionMap, PointerAction, Trigger
from aircursor_core.dwell import DwellDetector, DwellUpdate
from aircursor_core.gestures import GestureDetector, HeadGesture
from aircursor_core.math_util import AngleMath, Vec2
from aircursor_core.motion import AngularRates, MotionDifferentiator, MotionSample
from aircursor_core.pointer import CursorHistory, PointerMapper, PointerSmoother
from aircursor_core.settings import AppSettings

# Import Windows Platform modules
sys.path.insert(0, r"c:\Users\omkar\TV\AirCursor_CrossPlatform\windows")
from clickable_probe import ClickableProbe
from event_synthesizer import EventSynthesizer
from overlay import OverlayController
from sensor_receiver import (
    BluetoothAirPodsHelper,
    OpenTrackReceiver,
    SyntheticSensorGenerator,
)
from stem_listener import StemListener
from hotkey_manager import HotKeyManager


class TrackingMode(str, enum.Enum):
    POINTER = "pointer"
    SCROLL = "scroll"


class AppController:
    """Central orchestrator for the Windows AirCursor application."""

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        use_synthetic: bool = False,
        udp_port: int = 4242,
        udp_host: str = "0.0.0.0",
        show_overlay: bool = True,
        enable_stem_hook: bool = True,
    ):
        # Standby State Machine: default dwell clicking to False unless explicitly configured
        if settings is None:
            self.settings: AppSettings = AppSettings()
            self.settings.dwell.enabled = False
        else:
            self.settings = settings

        self.use_synthetic: bool = use_synthetic
        self.udp_port: int = udp_port
        self.udp_host: str = udp_host
        self.show_overlay: bool = show_overlay
        self.enable_stem_hook: bool = enable_stem_hook

        # State: Standby State Machine starts paused by default
        self.tracking_enabled: bool = False
        self.mode: TrackingMode = TrackingMode.POINTER
        self.is_dragging: bool = False
        self.motion_streaming: bool = False

        # Human-Input Arbiter: physical mouse movement yields control for 1.5 seconds
        self._human_override_until: float = 0.0

        # Live telemetry readout for UI / Console
        self.live_yaw: float = 0.0
        self.live_pitch: float = 0.0
        self.live_roll: float = 0.0
        self.live_yaw_rate: float = 0.0
        self.live_pitch_rate: float = 0.0
        self.live_fps: float = 0.0

        # Subsystems
        self.synth = EventSynthesizer()
        self.probe = ClickableProbe()
        self.overlay = OverlayController(enabled=self.show_overlay)
        self.stem = (
            StemListener(on_trigger=self._on_stem_trigger, intercept=True)
            if self.enable_stem_hook
            else None
        )
        self.hotkeys = HotKeyManager()
        self._register_hotkeys()

        # Pipeline components
        self.differentiator = MotionDifferentiator()
        self.smoother = PointerSmoother()
        self.gestures = GestureDetector(settings=self.settings.gestures)
        self.dwell = DwellDetector(settings=self.settings.dwell)
        self.history = CursorHistory(capacity=360)  # 3 seconds @ 120Hz

        # Sensor receivers
        self.udp_receiver: Optional[OpenTrackReceiver] = None
        self.synthetic_generator: Optional[SyntheticSensorGenerator] = None

        # Tracking loop threading
        self._running: bool = False
        self._frame_thread: Optional[threading.Thread] = None
        self._cursor: Optional[Vec2] = None
        self._last_posted: list[Vec2] = []
        self._last_frame_delta: float = 0.0
        self._scroll_remainder = Vec2(0.0, 0.0)

        # Timings & Statistics
        self._last_sample_host_time: float = 0.0
        self._sample_count: int = 0
        self._frame_count: int = 0
        self._fps_timer: float = time.time()
        self._probed_anchor: int = -1
        self._anchor_clickable: Optional[bool] = None

        # Multi-monitor bounds
        self._vx, self._vy, self._vw, self._vh = self.synth.get_screen_bounds()

    def start(self, start_tracking: bool = False) -> None:
        """Starts the full AirCursor engine. Starts paused by default (Standby State Machine)."""
        if self._running:
            return
        self._running = True

        # Initialize cursor position to current mouse position
        mx, my = self.synth.current_location()
        self._cursor = Vec2(float(mx), float(my))

        # Start Stem listener if enabled
        if self.stem:
            self.stem.start()

        # Start Hotkey listener
        if self.enable_stem_hook and self.hotkeys:
            self.hotkeys.start()

        # Start Sensor Ingestion
        if self.use_synthetic:
            self.synthetic_generator = SyntheticSensorGenerator(
                fps=120.0, on_sample=self.handle_sample
            )
            self.synthetic_generator.start()
        else:
            self.udp_receiver = OpenTrackReceiver(
                host=self.udp_host, port=self.udp_port, on_sample=self.handle_sample
            )
            self.udp_receiver.start()

        # Start High-Frequency 120Hz Tracking Frame Thread
        self._frame_thread = threading.Thread(
            target=self._tracking_loop, daemon=True, name="AirCursor-120Hz-Engine"
        )
        self._frame_thread.start()

        # Standby State Machine: Starts paused by default unless explicitly requested
        if start_tracking:
            self.set_tracking(True, announce=True)
        else:
            self.set_tracking(False, announce=False)

    def stop(self) -> None:
        """Stops the engine and releases all resources."""
        self._running = False
        self.set_tracking(False, announce=False)

        if self.stem:
            self.stem.stop()
        if self.hotkeys:
            self.hotkeys.stop()
        if self.udp_receiver:
            self.udp_receiver.stop()
        if self.synthetic_generator:
            self.synthetic_generator.stop()
        if self._frame_thread and self._frame_thread.is_alive():
            self._frame_thread.join(timeout=0.5)

        self.probe.close()
        self.overlay.close()
        self.synth.release_all_buttons()

    def _register_hotkeys(self) -> None:
        """Configures default global hotkeys (Ctrl+Alt+T, Ctrl+Alt+S, Ctrl+Alt+C, Ctrl+Alt+D)."""
        # Ctrl + Alt + T: Toggle tracking
        self.hotkeys.register(ord("T"), ctrl=True, alt=True, callback=self.toggle_tracking)
        # Ctrl + Alt + S: Toggle scroll mode
        self.hotkeys.register(ord("S"), ctrl=True, alt=True, callback=self.toggle_mode)
        # Ctrl + Alt + C: Recenter
        self.hotkeys.register(ord("C"), ctrl=True, alt=True, callback=self.recenter)
        # Ctrl + Alt + D: Toggle drag
        self.hotkeys.register(
            ord("D"),
            ctrl=True,
            alt=True,
            callback=lambda: self.end_drag() if self.is_dragging else self.begin_drag(),
        )

    def set_tracking(self, enabled: bool, announce: bool = True) -> None:
        """Pauses or resumes cursor tracking."""
        if self.tracking_enabled == enabled:
            return
        self.tracking_enabled = enabled
        self.smoother.reset()
        self.dwell.reset()
        self.overlay.hide()

        if self.is_dragging:
            self.end_drag()

        if announce:
            msg = "Head tracking on" if enabled else "Head tracking paused"
            sym = "🎯" if enabled else "⏸"
            self.overlay.show_toast(msg, sym)

    def toggle_tracking(self) -> None:
        """Toggles tracking state."""
        self.set_tracking(not self.tracking_enabled, announce=True)

    def set_mode(self, new_mode: TrackingMode) -> None:
        """Switches between POINTER and SCROLL mode."""
        if self.mode == new_mode:
            return
        if self.is_dragging:
            self.end_drag()

        self.mode = new_mode
        self._scroll_remainder = Vec2(0.0, 0.0)
        self.smoother.reset()
        self.dwell.reset()
        self.overlay.hide()

        if new_mode == TrackingMode.SCROLL:
            self.overlay.show_toast("Scroll mode — turn head to scroll", "↕")
        else:
            self.overlay.show_toast("Pointer mode", "🖱")

    def toggle_mode(self) -> None:
        """Toggles between POINTER and SCROLL mode."""
        next_mode = (
            TrackingMode.SCROLL
            if self.mode == TrackingMode.POINTER
            else TrackingMode.POINTER
        )
        self.set_mode(next_mode)

    def recenter(self) -> None:
        """Recenters cursor to screen center and resets gesture posture baseline."""
        cx = self._vx + self._vw // 2
        cy = self._vy + self._vh // 2
        self._cursor = Vec2(float(cx), float(cy))
        self.synth.move_to(cx, cy)
        self.smoother.reset()
        self.gestures.reset_tilt_baseline()
        self.overlay.show_toast("Recentered", "🎯")

    def handle_sample(self, sample: MotionSample) -> None:
        """Called whenever a new headphone sensor reading arrives (typically ~25-100Hz)."""
        now = time.time()
        self._last_sample_host_time = now
        self._sample_count += 1
        self.motion_streaming = True

        # Process deliberate gestures only if tracking is enabled and not in human override
        enabled_gestures = self.settings.actions.enabled_head_gestures
        gesture_event = self.gestures.process(sample, enabled=enabled_gestures)
        if (
            gesture_event
            and self.tracking_enabled
            and (now >= self._human_override_until)
        ):
            # Calculate gesture start time in host clock
            start_host = gesture_event.start_time + (now - sample.timestamp)
            trigger = Trigger.from_gesture(gesture_event.gesture)
            self._handle_trigger(trigger, gesture_start=start_host)

        # Differentiate attitude into angular velocities (deg/s)
        rates = self.differentiator.push(sample)
        if rates is None:
            return

        # Update live telemetry metrics
        self.live_yaw = AngleMath.degrees(sample.yaw)
        self.live_pitch = AngleMath.degrees(sample.pitch)
        self.live_roll = AngleMath.degrees(sample.roll)
        self.live_yaw_rate = rates.yaw
        self.live_pitch_rate = rates.pitch

        # Feed target velocity to smoother only if tracking is enabled and not in human override
        if self.tracking_enabled and (now >= self._human_override_until):
            target_vel = PointerMapper.cursor_velocity(rates, self.settings.pointer)
            self.smoother.set_target(target_vel, now)

    def _tracking_loop(self) -> None:
        """Runs at 120 Hz to integrate cursor velocity and handle dwell inspection."""
        target_interval = 1.0 / 120.0
        last_frame_time = time.perf_counter()

        while self._running:
            t0 = time.perf_counter()
            now = time.time()
            dt = min(max(t0 - last_frame_time, 0.0), 0.05)
            last_frame_time = t0

            # FPS counter
            self._frame_count += 1
            if now - self._fps_timer >= 1.0:
                self.live_fps = self._frame_count / (now - self._fps_timer)
                self._frame_count = 0
                self._fps_timer = now

            # Step smoother
            delta = self.smoother.step(
                now, dt, smoothing=self.settings.pointer.smoothing
            )

            # Sync with physical mouse
            self._sync_cursor_with_system()
            if self._cursor is None:
                continue

            # Human-Input Arbiter: While now < _human_override_until, head tracking
            # yields 100% control to the physical mouse!
            is_human_override = now < self._human_override_until

            # Process movement according to active mode
            if self.tracking_enabled and not is_human_override:
                if self.mode == TrackingMode.POINTER:
                    if delta.length > 0.01:
                        next_x = self._cursor.x + delta.x
                        next_y = self._cursor.y + delta.y
                        # Clamp to virtual desktop
                        clamped_x = min(max(next_x, float(self._vx)), float(self._vx + self._vw - 1))
                        clamped_y = min(max(next_y, float(self._vy)), float(self._vy + self._vh - 1))

                        self._last_frame_delta = math.hypot(
                            clamped_x - self._cursor.x, clamped_y - self._cursor.y
                        )
                        self._cursor = Vec2(clamped_x, clamped_y)
                        self._post_cursor(clamped_x, clamped_y)
                    else:
                        self._last_frame_delta = 0.0

                elif self.mode == TrackingMode.SCROLL:
                    # Scroll synthesis
                    self._scroll_remainder += delta * (0.6 * self.settings.pointer.scroll_speed)
                    sx = int(math.trunc(self._scroll_remainder.x))
                    sy = int(math.trunc(self._scroll_remainder.y))
                    if sx != 0 or sy != 0:
                        self._scroll_remainder -= Vec2(float(sx), float(sy))
                        sign = 1 if self.settings.pointer.invert_scroll else -1
                        self.synth.scroll(vertical=sy * sign, horizontal=sx * sign)
            else:
                self._last_frame_delta = 0.0

            # Record position in cursor history
            self.history.append(self._cursor, now)

            # Dwell / Hover click detection (only active when tracking enabled and no human override)
            if (
                self.tracking_enabled
                and not is_human_override
                and self.mode == TrackingMode.POINTER
                and self.settings.dwell.enabled
                and self.settings.actions[Trigger.DWELL] != PointerAction.NONE
                and self.motion_streaming
                and not self.is_dragging
            ):
                update: DwellUpdate = self.dwell.update(self._cursor, now)
                progress = update.progress
                fired = update.fired

                if self.settings.dwell.smart:
                    anchor = self.dwell.anchor_id
                    if (progress is not None or fired) and (self._probed_anchor != anchor):
                        self._probed_anchor = anchor
                        self._anchor_clickable = None

                        def _probe_callback(clickable: bool):
                            if self._probed_anchor == anchor:
                                self._anchor_clickable = clickable

                        self.probe.check(self._cursor.x, self._cursor.y, _probe_callback)

                    if self._anchor_clickable is not True:
                        progress = None
                        fired = False

                self.overlay.update_dwell(progress, self._cursor.x, self._cursor.y)

                if fired:
                    self._handle_trigger(Trigger.DWELL, gesture_start=None)
            else:
                self.overlay.update_dwell(None, self._cursor.x, self._cursor.y)

            # Watchdog: detect if motion stream went stale (> 1.5s)
            if self.motion_streaming and (now - self._last_sample_host_time > 1.5):
                self.motion_streaming = False
                self.smoother.reset()
                if self.is_dragging:
                    self.end_drag()

            # High precision sleep to hit 120Hz cadence
            elapsed = time.perf_counter() - t0
            sleep_time = target_interval - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time)

    def _sync_cursor_with_system(self) -> None:
        """Adopts real cursor location if an external mouse/trackpad moved it."""
        actual_x, actual_y = self.synth.current_location()
        actual = Vec2(float(actual_x), float(actual_y))

        if self._cursor is None:
            self._cursor = actual
            self._last_posted = [actual]
            return

        tolerance = max(6.0, self._last_frame_delta * 2.0 + 6.0)
        is_ours = any(actual.distance(p) <= tolerance for p in self._last_posted)

        if not is_ours:
            # Human-Input Arbiter: Physical mouse movement detected!
            # Set 1.5s override cooldown, reset smoother and dwell immediately.
            now = time.time()
            self._human_override_until = now + 1.5
            self._cursor = actual
            self._last_posted = [actual]
            self.smoother.reset()
            self.dwell.reset()
            self.overlay.hide()

    def _post_cursor(self, x: float, y: float) -> None:
        """Dispatches cursor move to Win32."""
        self.synth.move_to(x, y)
        self._last_posted.append(Vec2(x, y))
        if len(self._last_posted) > 4:
            self._last_posted.pop(0)

    def _on_stem_trigger(self, trigger: Trigger) -> None:
        """Dispatched from StemListener low-level hook."""
        self._handle_trigger(trigger, gesture_start=None)

    def _handle_trigger(self, trigger: Trigger, gesture_start: Optional[float]) -> None:
        """Maps a trigger (Nod, Shake, StemSingle, Dwell, etc.) to its configured PointerAction."""
        action = self.settings.actions[trigger]
        if action == PointerAction.NONE:
            return

        # Suppress actions during human mouse override (except manual toggle tracking)
        if time.time() < self._human_override_until and action != PointerAction.TOGGLE_TRACKING:
            return

        # Head gestures cannot pause tracking during initial calibration
        if (
            action == PointerAction.TOGGLE_TRACKING
            and trigger.head_gesture is not None
            and not self.settings.has_completed_onboarding
        ):
            return

        if not self.tracking_enabled and action != PointerAction.TOGGLE_TRACKING:
            return

        # Cursor Rollback: If this was a nod or shake gesture, restore the cursor to
        # exactly where the user was looking before the nod began!
        target_point = self._cursor or Vec2(0.0, 0.0)
        if (
            gesture_start is not None
            and self.tracking_enabled
            and self.mode == TrackingMode.POINTER
        ):
            # Rollback to 60ms before gesture start
            before_pos = self.history.position(gesture_start - 0.06)
            if before_pos:
                target_point = before_pos
                self._cursor = before_pos
                self._post_cursor(before_pos.x, before_pos.y)
                self.smoother.reset()

        self._execute_action(action, target_point)

    def _execute_action(self, action: PointerAction, point: Vec2) -> None:
        """Executes the Win32 input action."""
        px, py = point.x, point.y

        if action == PointerAction.LEFT_CLICK:
            if self.is_dragging:
                self.end_drag(px, py)
            else:
                self.synth.click(button="left", x=px, y=py)
                self.overlay.pulse(px, py)

        elif action == PointerAction.RIGHT_CLICK:
            if self.is_dragging:
                self.end_drag(px, py)
            self.synth.click(button="right", x=px, y=py)
            self.overlay.pulse(px, py)

        elif action == PointerAction.DOUBLE_CLICK:
            if self.is_dragging:
                self.end_drag(px, py)
            self.synth.double_click(x=px, y=py)
            self.overlay.pulse(px, py)

        elif action == PointerAction.MIDDLE_CLICK:
            self.synth.click(button="middle", x=px, y=py)
            self.overlay.pulse(px, py)

        elif action == PointerAction.TOGGLE_DRAG:
            if self.is_dragging:
                self.end_drag(px, py)
            else:
                self.begin_drag(px, py)

        elif action == PointerAction.TOGGLE_SCROLL_MODE:
            self.toggle_mode()

        elif action == PointerAction.TOGGLE_TRACKING:
            self.toggle_tracking()

        elif action == PointerAction.RECENTER:
            self.recenter()

        elif action == PointerAction.MISSION_CONTROL:
            self.synth.mission_control()
            self.overlay.show_toast("Task View", "🗔")

        elif action == PointerAction.APP_WINDOWS:
            self.synth.app_windows()
            self.overlay.show_toast("App Switcher", "🗖")

        elif action == PointerAction.PREVIOUS_SPACE:
            self.synth.previous_space()
            self.overlay.show_toast("Desktop Left", "⯇")

        elif action == PointerAction.NEXT_SPACE:
            self.synth.next_space()
            self.overlay.show_toast("Desktop Right", "⯈")

        elif action == PointerAction.BACK:
            self.synth.browser_back()
            self.overlay.show_toast("Back", "⯇")

        elif action == PointerAction.FORWARD:
            self.synth.browser_forward()
            self.overlay.show_toast("Forward", "⯈")

        elif action == PointerAction.SCREENSHOT:
            self.synth.screenshot()
            self.overlay.show_toast("Snipping Tool", "✂")

        if action.is_click:
            self.dwell.reset()

    def begin_drag(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Starts left mouse drag lock."""
        self.synth.left_down(x, y)
        self.is_dragging = True
        if x is not None and y is not None:
            self.overlay.pulse(x, y)
        self.overlay.show_toast("Dragging — click again to drop", "✊")

    def end_drag(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Releases left mouse drag lock."""
        self.synth.left_up(x, y)
        self.is_dragging = False
        if x is not None and y is not None:
            self.overlay.pulse(x, y)
        self.overlay.show_toast("Dropped", "🖐")
