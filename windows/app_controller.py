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
from aircursor_core.arbiter import FallbackPolicy, InputArbiter, TrackingSource
from aircursor_core.dwell import DwellDetector, DwellUpdate
from aircursor_core.gestures import GestureDetector, HeadGesture
from aircursor_core.math_util import AngleMath, Vec2
from aircursor_core.motion import AngularRates, MotionDifferentiator, MotionSample
from aircursor_core.pointer import CursorHistory, PointerMapper, PointerSmoother
from aircursor_core.settings import AppSettings
from aircursor_core.vision_tracker import (
    HandGesture,
    VisionFrameResult,
    VisionTracker,
    VisionTrackerSettings,
    VisionTrackerState,
)

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
from web_remote import WebRemoteServer


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
        enable_camera: Optional[bool] = None,
        camera_index: Optional[int] = None,
        enable_web_remote: bool = True,
        web_remote_port: Optional[int] = None,
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

        # Apply camera & remote overrides if specified
        if enable_camera is not None:
            self.settings.vision.enabled = enable_camera
        if camera_index is not None:
            self.settings.vision.camera_index = camera_index
        if web_remote_port is not None:
            self.settings.remote.port = web_remote_port

        self.enable_camera: bool = bool(self.settings.vision.enabled)

        # Multi-Source Input Arbiter
        initial_source = (
            TrackingSource.SYNTHETIC
            if self.use_synthetic
            else (
                TrackingSource.VISION
                if (self.enable_camera and not self.use_synthetic)
                else TrackingSource.BLUETOOTH
            )
        )
        self.arbiter = InputArbiter(
            initial_source=initial_source,
            fallback_policy=(
                FallbackPolicy.AUTO_TRANSITION
                if self.settings.vision.auto_fallback
                else FallbackPolicy.SUGGEST_ONLY
            ),
            bluetooth_timeout=3.0,
            camera_available=False,
            camera_enabled=self.settings.vision.enabled,
            on_source_changed=self._on_tracking_source_changed,
            on_fallback_suggested=self._on_fallback_suggested,
        )

        # State: Start active by default so cursor is immediately controllable
        self.tracking_enabled: bool = True
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
        self._vision_differentiator = MotionDifferentiator()
        self.smoother = PointerSmoother()
        self.gestures = GestureDetector(settings=self.settings.gestures)
        self.dwell = DwellDetector(settings=self.settings.dwell)
        self.history = CursorHistory(capacity=360)  # 3 seconds @ 120Hz

        # Sensor receivers
        self.udp_receiver: Optional[OpenTrackReceiver] = None
        self.synthetic_generator: Optional[SyntheticSensorGenerator] = None

        # Vision Tracker subsystem
        self.vision_tracker: Optional[VisionTracker] = None
        self._init_vision_tracker()

        # Web Remote API server subsystem
        self.enable_web_remote: bool = enable_web_remote and self.settings.remote.enabled
        self.web_remote: Optional[WebRemoteServer] = (
            WebRemoteServer(
                controller=self,
                host=self.settings.remote.bind,
                port=self.settings.remote.port,
            )
            if self.enable_web_remote
            else None
        )

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

    def _init_vision_tracker(self) -> None:
        """Initializes VisionTracker instance and synchronizes with arbiter."""
        vision_cfg = VisionTrackerSettings(
            camera_index=self.settings.vision.camera_index,
            target_fps=float(self.settings.vision.max_fps),
            enable_head_tracking=self.settings.vision.face_tracking,
            enable_hand_gestures=self.settings.vision.hand_gestures,
            enable_hand_tracking=getattr(self.settings.vision, "hand_tracking", True),
            hand_sensitivity=getattr(self.settings.vision, "hand_sensitivity", 2.5),
        )
        self.vision_tracker = VisionTracker(
            settings=vision_cfg,
            on_sample=self.handle_vision_sample,
            on_gesture=self.handle_vision_gesture,
        )
        self.arbiter.set_camera_status(
            available=self.vision_tracker.is_available,
            enabled=self.enable_camera or self.settings.vision.enabled,
        )

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

        # Start Web Remote server if enabled
        if self.web_remote:
            self.web_remote.start()

        # Start Vision tracker if camera is enabled
        if self.enable_camera and self.vision_tracker:
            if self.vision_tracker.start():
                self.arbiter.set_camera_status(available=True, enabled=True)
                if self.arbiter.active_source == TrackingSource.BLUETOOTH and self.arbiter.is_bluetooth_stale:
                    self.arbiter.set_manual_source(TrackingSource.VISION)

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
        if self.vision_tracker:
            self.vision_tracker.stop()
        if self.web_remote:
            self.web_remote.stop()
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
        # Ctrl + Alt + V: Toggle vision camera tracking
        self.hotkeys.register(ord("V"), ctrl=True, alt=True, callback=self.toggle_camera)

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

        # Check with arbiter whether Bluetooth sample should drive cursor
        should_consume = self.arbiter.notify_bluetooth_sample(sample, timestamp=now)
        if not should_consume:
            return

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

    def handle_vision_sample(self, sample: MotionSample) -> None:
        """Called whenever a new vision camera tracking reading arrives."""
        now = time.time()
        self._last_sample_host_time = now
        self._sample_count += 1
        self.motion_streaming = True

        should_consume = self.arbiter.notify_vision_sample(sample, timestamp=now)
        if not should_consume:
            return

        # Differentiate attitude into angular velocities (deg/s) using vision differentiator
        rates = self._vision_differentiator.push(sample)
        if rates is None:
            return

        self.live_yaw = AngleMath.degrees(sample.yaw)
        self.live_pitch = AngleMath.degrees(sample.pitch)
        self.live_roll = AngleMath.degrees(sample.roll)
        self.live_yaw_rate = rates.yaw
        self.live_pitch_rate = rates.pitch

        if self.tracking_enabled and (now >= self._human_override_until):
            target_vel = PointerMapper.cursor_velocity(rates, self.settings.pointer)
            self.smoother.set_target(target_vel, now)

    def handle_vision_gesture(self, gesture: HandGesture, result: VisionFrameResult) -> None:
        """Dispatches vision hand gestures to pointer actions."""
        if not self.tracking_enabled or time.time() < self._human_override_until:
            return

        px = self._cursor.x if self._cursor else float(self._vx + self._vw // 2)
        py = self._cursor.y if self._cursor else float(self._vy + self._vh // 2)

        if gesture == HandGesture.OPEN_PALM:
            # Open Palm: Free motion (release drag lock if active)
            if self.is_dragging:
                self.end_drag(px, py)

        elif gesture == HandGesture.PINCH:
            # Pinch / Index Tap: Left Click / Drag
            if self.is_dragging:
                self.end_drag(px, py)
            else:
                self.synth.click(button="left", x=px, y=py)
                self.overlay.pulse(px, py)
                self.overlay.show_toast("Pinch Click", "👌")

        elif gesture == HandGesture.PEACE_SIGN:
            # Peace Sign / Two Fingers Up: Right Click
            if self.is_dragging:
                self.end_drag(px, py)
            self.synth.click(button="right", x=px, y=py)
            self.overlay.pulse(px, py)
            self.overlay.show_toast("Right Click", "✌")

        elif gesture == HandGesture.CLOSED_FIST:
            # Closed Fist: Drag lock / Hold
            if not self.is_dragging:
                self.begin_drag(px, py)

        elif gesture == HandGesture.SWIPE_UP:
            # Swipe Hand Up: Scroll Wheel Up
            self.synth.scroll(vertical=3, horizontal=0)
            self.overlay.show_toast("Scroll Up", "▲")

        elif gesture == HandGesture.SWIPE_DOWN:
            # Swipe Hand Down: Scroll Wheel Down
            self.synth.scroll(vertical=-3, horizontal=0)
            self.overlay.show_toast("Scroll Down", "▼")

    def toggle_camera(self) -> bool:
        """Toggles camera vision tracking on or off."""
        if self.vision_tracker and self.vision_tracker.is_running:
            self.stop_camera()
            return False
        else:
            return self.start_camera()

    def start_camera(self) -> bool:
        """Starts camera vision tracking and switches arbiter source."""
        if not self.vision_tracker:
            self._init_vision_tracker()
        if not self.vision_tracker:
            return False

        success = self.vision_tracker.start()
        if success:
            self.enable_camera = True
            self.arbiter.set_camera_status(available=True, enabled=True)
            self.arbiter.set_manual_source(TrackingSource.VISION)
            self._vision_differentiator.reset()
            self.overlay.show_toast("Camera Active: Move Hand or Head", "📷")
            return True
        else:
            self.overlay.show_toast("Camera Unavailable", "⚠")
            return False

    def stop_camera(self) -> None:
        """Stops camera vision tracking and returns to Bluetooth arbitration."""
        if self.vision_tracker:
            self.vision_tracker.stop()
        self.enable_camera = False
        self.arbiter.set_camera_status(
            available=self.vision_tracker.is_available if self.vision_tracker else False,
            enabled=False,
        )
        self.arbiter.set_manual_source(None)
        self._vision_differentiator.reset()
        self.overlay.show_toast("Camera Vision Tracking Stopped", "📷")

    def _on_tracking_source_changed(
        self, old_source: TrackingSource, new_source: TrackingSource
    ) -> None:
        """Dispatched when arbiter transitions tracking between Bluetooth, Vision, etc."""
        if new_source == TrackingSource.VISION:
            if self.vision_tracker and not self.vision_tracker.is_running:
                self.vision_tracker.start()
            self.smoother.reset()
            self._vision_differentiator.reset()
            self.overlay.show_toast("Camera Active: Move Hand or Face", "📷")
        elif new_source == TrackingSource.BLUETOOTH:
            self.smoother.reset()
            self.differentiator.reset()
            self.overlay.show_toast("AirPods Connected — Head Tracking Active", "🎧")

    def _on_fallback_suggested(self, message: str) -> None:
        """Dispatched when AirPods are silent and camera fallback is recommended."""
        self.overlay.show_toast("AirPods silent — Press Ctrl+Alt+V for Camera", "📷")

    def _tracking_loop(self) -> None:
        """Runs at 120 Hz to integrate cursor velocity and handle dwell inspection."""
        target_interval = 1.0 / 120.0
        last_frame_time = time.perf_counter()

        while self._running:
            t0 = time.perf_counter()
            now = time.time()
            dt = min(max(t0 - last_frame_time, 0.0), 0.05)
            last_frame_time = t0

            # Arbiter watchdog: check if Bluetooth timed out > 3.0s and auto-fallback is needed
            self.arbiter.check_health(now)

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

            # Watchdog: detect if motion stream went stale (> 1.5s for AirPods or > 3s for Vision)
            stale_threshold = 3.0 if self.arbiter.active_source == TrackingSource.VISION else 1.5
            if self.motion_streaming and (now - self._last_sample_host_time > stale_threshold):
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

    def handle_remote_action(
        self, action: str, dx: float = 0.0, dy: float = 0.0, extra: Optional[dict] = None
    ) -> bool:
        """Thread-safe handler for user actions from mobile web remote."""
        act = action.strip().lower()
        if act in ("click", "left_click"):
            if self.is_dragging:
                self.end_drag()
            else:
                self.synth.click(button="left")
            return True
        elif act == "right_click":
            if self.is_dragging:
                self.end_drag()
            self.synth.click(button="right")
            return True
        elif act == "middle_click":
            self.synth.click(button="middle")
            return True
        elif act == "double_click":
            if self.is_dragging:
                self.end_drag()
            self.synth.double_click()
            return True
        elif act in ("drag_toggle", "drag"):
            if self.is_dragging:
                self.end_drag()
            else:
                self.begin_drag()
            return True
        elif act == "recenter":
            self.recenter()
            return True
        elif act == "scroll":
            self.synth.scroll(vertical=int(dy), horizontal=int(dx))
            return True
        elif act in ("jump_to", "move_to"):
            # Absolute coordinate jump from virtual screen mini-map
            self.synth.move_to(dx, dy)
            self._cursor = Vec2(float(dx), float(dy))
            return True
        # D-Pad and Navigation keys
        elif act in ("dpad_up", "key_up", "up"):
            self.synth.press_key("up")
            return True
        elif act in ("dpad_down", "key_down", "down"):
            self.synth.press_key("down")
            return True
        elif act in ("dpad_left", "key_left", "left"):
            self.synth.press_key("left")
            return True
        elif act in ("dpad_right", "key_right", "right"):
            self.synth.press_key("right")
            return True
        elif act in ("dpad_ok", "dpad_center", "key_enter", "enter", "select", "ok"):
            self.synth.press_key("enter")
            return True
        elif act in ("key_esc", "esc", "escape"):
            self.synth.press_key("escape")
            return True
        elif act in ("key_space", "space"):
            self.synth.press_key("space")
            return True
        elif act in ("key_tab", "tab"):
            self.synth.press_key("tab")
            return True
        elif act in ("key_backspace", "backspace"):
            self.synth.press_key("backspace")
            return True
        elif act in ("browser_back", "back"):
            self.synth.browser_back()
            return True
        elif act in ("browser_forward", "forward"):
            self.synth.browser_forward()
            return True
        elif act in ("page_up", "pgup"):
            self.synth.press_key("page_up")
            return True
        elif act in ("page_down", "pgdn"):
            self.synth.press_key("page_down")
            return True
        elif act in ("home", "key_home"):
            self.synth.press_key("home")
            return True
        elif act in ("end", "key_end"):
            self.synth.press_key("end")
            return True
        # Media Controls
        elif act in ("volume_up", "vol_up"):
            self.synth.volume_up()
            return True
        elif act in ("volume_down", "vol_down"):
            self.synth.volume_down()
            return True
        elif act in ("volume_mute", "mute"):
            self.synth.volume_mute()
            return True
        elif act in ("media_play_pause", "play_pause", "play"):
            self.synth.media_play_pause()
            return True
        elif act in ("media_next", "next_track"):
            self.synth.media_next()
            return True
        elif act in ("media_prev", "prev_track"):
            self.synth.media_prev()
            return True
        # Windows & TV Display Controls
        elif act in ("fullscreen", "f11"):
            self.synth.fullscreen()
            return True
        elif act in ("show_desktop", "desktop"):
            self.synth.show_desktop()
            return True
        elif act in ("task_view", "mission_control"):
            self.synth.mission_control()
            return True
        elif act in ("app_switch", "app_windows"):
            self.synth.app_windows()
            return True
        elif act in ("previous_space", "desktop_left"):
            self.synth.previous_space()
            return True
        elif act in ("next_space", "desktop_right"):
            self.synth.next_space()
            return True
        elif act in ("screenshot", "snip"):
            self.synth.screenshot()
            return True
        elif act == "type_text":
            text = ""
            if extra and "text" in extra:
                text = str(extra["text"])
            if text:
                self.synth.type_text(text)
            return True
        elif act in ("toggle_tracking", "pause", "resume"):
            if act == "pause":
                self.set_tracking(False)
            elif act == "resume":
                self.set_tracking(True)
            else:
                self.toggle_tracking()
            return True
        elif act in ("toggle_mode", "scroll_mode", "pointer_mode"):
            if act == "scroll_mode":
                self.set_mode(TrackingMode.SCROLL)
            elif act == "pointer_mode":
                self.set_mode(TrackingMode.POINTER)
            else:
                self.toggle_mode()
            return True
        elif act in ("camera_toggle", "toggle_camera"):
            if hasattr(self, "toggle_camera"):
                self.toggle_camera()
            return True
        # Numeric keys (0-9)
        elif len(act) == 1 and act.isdigit():
            self.synth.press_key(act)
            return True
        return False

    def handle_remote_motion(self, data: dict) -> bool:
        """Thread-safe handler for motion data (dx, dy or gyro) from mobile web remote."""
        dx = float(data.get("dx", 0.0))
        dy = float(data.get("dy", 0.0))
        if abs(dx) > 0.001 or abs(dy) > 0.001:
            if self.mode == TrackingMode.SCROLL:
                self.synth.scroll(vertical=int(dy), horizontal=int(dx))
            else:
                self.synth.move_relative(dx, dy)
                mx, my = self.synth.current_location()
                self._cursor = Vec2(float(mx), float(my))

        gyro = data.get("gyro")
        if gyro and isinstance(gyro, dict):
            pitch = float(gyro.get("pitch", 0.0))
            yaw = float(gyro.get("yaw", 0.0))
            roll = float(gyro.get("roll", 0.0))
            if abs(pitch) > math.pi or abs(yaw) > math.pi:
                pitch = AngleMath.radians(pitch)
                yaw = AngleMath.radians(yaw)
                roll = AngleMath.radians(roll)
            sample = MotionSample(timestamp=time.time(), yaw=yaw, pitch=pitch, roll=roll)
            self.handle_sample(sample)
        return True
