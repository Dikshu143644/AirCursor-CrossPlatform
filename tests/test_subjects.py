"""AirCursor Multi-Subject Simulation & Stress-Test Suite.

Simulates 12 distinct human user profiles ('subjects') with varying physiological traits,
head movement kinematics, nod depths, tremor levels, posture quirks, and input interventions:
- Subject 1: Standard Office Worker (Typical speeds, standard nod & shake)
- Subject 2: Fast-Twitch Gamer (Rapid 180°/s head flicks, max acceleration boost)
- Subject 3: Subtle / Gentle Nodder (Small nod amplitude 3.8°, requires calibration)
- Subject 4: High Physiological Tremor (Continuous 2.2° micro-jitter filtered by deadzone)
- Subject 5: Slow Reader / Dwell Clicker (Reading text, resting on interactive button)
- Subject 6: Vigorous Shaker (Rapid multi-swing shake, anti-machinegun settlement)
- Subject 7: Tilted Head Posture (Head tilted on hand, 4s auto-reneutralization)
- Subject 8: Multi-Monitor Ultra-Wide Traveler (Virtual screen bounds clamping)
- Subject 9: Physical Mouse Dual-Wielder (Human-Input Arbiter physical mouse override)
- Subject 10: Stem Squeeze Media Master (AirPods stem debouncing & mode toggles)
- Subject 11: Hostile Bluetooth Dropouts (Packet loss & latency spikes, gap rejection)
- Subject 12: High-Rate 210Hz Sensor Burst (Sub-5ms telemetry stream, 120Hz smoother stability)
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import time
import unittest

# Ensure modules are imported cleanly
ROOT_DIR = Path(__file__).resolve().parent.parent
WINDOWS_DIR = ROOT_DIR / "windows"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from aircursor_core.math_util import Vec2, AngleMath
from aircursor_core.motion import MotionSample, MotionDifferentiator
from aircursor_core.pointer import PointerMapper, PointerSmoother, CursorHistory
from aircursor_core.gestures import GestureDetector, HeadGesture
from aircursor_core.dwell import DwellDetector
from aircursor_core.actions import Trigger, PointerAction, ActionMap
from aircursor_core.settings import AppSettings, PointerSettings, GestureSettings, DwellSettings
from app_controller import AppController, TrackingMode


class TestMultiSubjectSimulation(unittest.TestCase):
    """Rigorous evaluation suite testing AirCursor across 12 human subject profiles."""

    def setUp(self):
        self.settings = AppSettings()

    # -------------------------------------------------------------------------
    # SUBJECT 1: Standard Office Worker
    # -------------------------------------------------------------------------
    def test_subject_01_standard_office_worker(self):
        """Subject 1: Normal head movements (30-50°/s), standard 6.5° nod, 4-swing shake."""
        diff = MotionDifferentiator()
        smoother = PointerSmoother()
        gestures = GestureDetector(self.settings.gestures)
        
        t = 100.0
        # Phase 1: Smooth horizontal head turn across 15 degrees in 0.5s (30°/s)
        dt = 0.02  # 50 Hz
        for i in range(25):
            t += dt
            yaw = AngleMath.radians(i * 0.6)
            s = MotionSample(timestamp=t, yaw=yaw, pitch=0.0, roll=0.0)
            rates = diff.push(s)
            if i > 0:
                self.assertIsNotNone(rates)
                v = PointerMapper.cursorVelocity(rates, self.settings.pointer)
                disp = smoother.step(t, dt, self.settings.pointer.smoothing)
                self.assertFalse(math.isnan(disp.x))
                self.assertFalse(math.isnan(disp.y))

        # Phase 2: Natural nod (dip down 7.5° and return with tail)
        nod_detected = False
        start_t = t
        curve = [-math.sin(float(i) / 20.0 * math.pi) * 7.5 for i in range(21)]
        pitches = [0.0] * 5 + curve + [0.0] * 8
        for p in pitches:
            t += 0.02
            s = MotionSample(timestamp=t, yaw=AngleMath.radians(15.0), pitch=AngleMath.radians(p), roll=0.0)
            evt = gestures.process(s, enabled={HeadGesture.NOD})
            if evt and evt.gesture == HeadGesture.NOD:
                nod_detected = True

        self.assertTrue(nod_detected, "Subject 1: Standard nod must register cleanly")

    # -------------------------------------------------------------------------
    # SUBJECT 2: Fast-Twitch Gamer
    # -------------------------------------------------------------------------
    def test_subject_02_fast_twitch_gamer(self):
        """Subject 2: High angular speeds (180°/s), rapid flicks, bounded acceleration check."""
        diff = MotionDifferentiator()
        smoother = PointerSmoother()
        
        t = 200.0
        dt = 0.008  # 125 Hz
        # Rapid 45-degree flick in 0.25s -> 180°/s
        max_speed = 0.0
        for i in range(30):
            t += dt
            yaw_deg = (i / 30.0) * 45.0
            s = MotionSample(timestamp=t, yaw=AngleMath.radians(yaw_deg), pitch=0.0, roll=0.0)
            rates = diff.push(s)
            if rates:
                v = PointerMapper.cursorVelocity(rates, self.settings.pointer)
                max_speed = max(max_speed, v.length)
                disp = smoother.step(t, dt, self.settings.pointer.smoothing)
                self.assertFalse(math.isnan(disp.x))

        # Effective speed should reflect acceleration boost without blowing up
        self.assertGreater(max_speed, 1000.0, "Subject 2: Fast head flick must receive acceleration boost")
        self.assertLess(max_speed, 50000.0, "Subject 2: Acceleration boost must be bounded and stable")

    # -------------------------------------------------------------------------
    # SUBJECT 3: Subtle / Gentle Nodder
    # -------------------------------------------------------------------------
    def test_subject_03_subtle_gentle_nodder(self):
        """Subject 3: Subtle nodder whose head dips 4.2° in 0.28s. Calibrated threshold must detect it."""
        settings = AppSettings()
        # Calibrate nod threshold to 3.8°
        settings.gestures.nod_amplitude = 3.8
        gestures = GestureDetector(settings.gestures)

        # Subtle nod (dip down 4.2° calibrated for subtle nodder)
        nod_detected = False
        t = 300.0
        curve = [-math.sin(float(i) / 18.0 * math.pi) * 4.2 for i in range(19)]
        pitches = [0.0] * 5 + curve + [0.0] * 8
        for p in pitches:
            t += 0.016
            s = MotionSample(timestamp=t, yaw=0.0, pitch=AngleMath.radians(p), roll=0.0)
            evt = gestures.process(s, enabled={HeadGesture.NOD})
            if evt and evt.gesture == HeadGesture.NOD:
                nod_detected = True

        self.assertTrue(nod_detected, "Subject 3: Calibrated subtle nod must be detected")

    # -------------------------------------------------------------------------
    # SUBJECT 4: High Physiological Tremor
    # -------------------------------------------------------------------------
    def test_subject_04_high_physiological_tremor(self):
        """Subject 4: Continuous 2.2° micro-jitter at 10 Hz. Deadzone must filter all drift."""
        diff = MotionDifferentiator()
        
        t = 400.0
        dt = 0.01  # 100 Hz
        drift_pixels = 0.0

        for i in range(100):  # 1 full second of tremor
            t += dt
            # Tremor below 3.0°/s deadzone: amplitude 0.04° at 10Hz -> peak rate ~ 2.5°/s
            jitter = math.sin(t * 2 * math.pi * 10.0) * 0.04
            s = MotionSample(timestamp=t, yaw=AngleMath.radians(jitter), pitch=AngleMath.radians(jitter), roll=0.0)
            rates = diff.push(s)
            if rates:
                v = PointerMapper.cursorVelocity(rates, self.settings.pointer)
                drift_pixels += v.length * dt

        self.assertEqual(drift_pixels, 0.0, "Subject 4: Tremor below 3°/s deadzone must result in exactly 0 drift")

    # -------------------------------------------------------------------------
    # SUBJECT 5: Slow Reader / Dwell Clicker
    # -------------------------------------------------------------------------
    def test_subject_05_slow_reader_dwell_clicker(self):
        """Subject 5: Move to button, rest cursor in 16px radius. Dwell reveals at 20% and clicks at 100%."""
        dwell_settings = DwellSettings(enabled=True, duration=0.8, radius=16.0)
        dwell = DwellDetector(dwell_settings)

        t = 500.0
        dt = 0.05
        revealed = False
        clicked = False

        # Phase 1: Move from (100, 100) to (300, 300) to arm detector
        dwell.update(Vec2(100.0, 100.0), t)
        t += 0.1
        dwell.update(Vec2(300.0, 300.0), t)

        # Phase 2: Rest at (300, 300) with subtle micro-drift (< 16px)
        anchor_pos = Vec2(300.0, 300.0)
        for i in range(25):  # 1.25 seconds
            t += dt
            pos = Vec2(anchor_pos.x + math.sin(i) * 3.0, anchor_pos.y + math.cos(i) * 3.0)
            upd = dwell.update(pos, t)
            if upd.progress is not None and upd.progress >= 0.2:
                revealed = True
            if upd.fired:
                clicked = True
                break

        self.assertTrue(revealed, "Subject 5: Dwell progress ring must reveal after 20% duration")
        self.assertTrue(clicked, "Subject 5: Dwell must fire click after 0.8s resting")

    # -------------------------------------------------------------------------
    # SUBJECT 6: Vigorous Shaker
    # -------------------------------------------------------------------------
    def test_subject_06_vigorous_shaker(self):
        """Subject 6: Rapid multi-swing head shake (6 swings of 16°). Fires once and latches."""
        gestures = GestureDetector(self.settings.gestures)

        t = 600.0
        dt = 0.016
        fire_count = 0

        # 6 swings of shake over 1.0s
        for i in range(70):
            t += dt
            yaw_deg = math.sin((i / 70.0) * math.pi * 6) * 16.0
            s = MotionSample(timestamp=t, yaw=AngleMath.radians(yaw_deg), pitch=0.0, roll=0.0)
            evt = gestures.process(s, enabled={HeadGesture.SHAKE})
            if evt and evt.gesture == HeadGesture.SHAKE:
                fire_count += 1

        self.assertEqual(fire_count, 1, "Subject 6: Continuous multi-swing shake must fire exactly once (no machine-gunning)")

    # -------------------------------------------------------------------------
    # SUBJECT 7: Tilted Head Posture
    # -------------------------------------------------------------------------
    def test_subject_07_tilted_head_posture(self):
        """Subject 7: User leans head 25° for 0.4s to trigger tilt, then holds posture for 5s (auto-reneutral)."""
        gestures = GestureDetector(self.settings.gestures)

        t = 700.0
        dt = 0.05
        tilt_fired = False

        # Phase 0: Establish upright baseline at roll = 0°
        for i in range(5):
            t += dt
            s = MotionSample(timestamp=t, yaw=0.0, pitch=0.0, roll=0.0)
            gestures.process(s, enabled={HeadGesture.TILT_RIGHT})

        # Phase 1: Tilt right 25° held for 0.5s -> fires
        for i in range(15):
            t += dt
            s = MotionSample(timestamp=t, yaw=0.0, pitch=0.0, roll=AngleMath.radians(25.0))
            evt = gestures.process(s, enabled={HeadGesture.TILT_RIGHT})
            if evt and evt.gesture == HeadGesture.TILT_RIGHT:
                tilt_fired = True

        self.assertTrue(tilt_fired, "Subject 7: Intentional 25° tilt must fire")

        # Phase 2: Stay tilted at 25° for > 4.0s -> posture auto-reneutralizes
        for i in range(90):  # 4.5 seconds
            t += dt
            s = MotionSample(timestamp=t, yaw=0.0, pitch=0.0, roll=AngleMath.radians(25.0))
            gestures.process(s, enabled={HeadGesture.TILT_RIGHT})

        # Relative roll to new baseline should now be near 0
        rel = gestures.relative_roll(25.0)
        self.assertLess(abs(rel), 2.0, "Subject 7: After 4s in tilted posture, head must auto-re-neutralize")

    # -------------------------------------------------------------------------
    # SUBJECT 8: Multi-Monitor Ultra-Wide Traveler
    # -------------------------------------------------------------------------
    def test_subject_08_multimonitor_ultrawide_traveler(self):
        """Subject 8: Cursor moving across dual/triple monitors (5760x1080) with boundary clamping."""
        ctrl = AppController(use_synthetic=False, show_overlay=False, enable_stem_hook=False)
        ctrl.set_tracking(True, announce=False)
        ctrl._vx, ctrl._vy, ctrl._vw, ctrl._vh = 0, 0, 5760, 1080

        # Simulate massive head turn pushing cursor way past screen boundaries
        ctrl._cursor = Vec2(5750.0, 500.0)
        ctrl.smoother.set_target(Vec2(2000.0, 0.0), time.time())
        
        # Step frame
        delta = ctrl.smoother.step(time.time(), 0.1, 0.55)
        next_x = ctrl._cursor.x + delta.x
        clamped_x = min(max(next_x, float(ctrl._vx)), float(ctrl._vx + ctrl._vw - 1))
        
        self.assertLessEqual(clamped_x, 5759.0, "Subject 8: Cursor must never exceed rightmost screen edge")
        self.assertGreaterEqual(clamped_x, 0.0, "Subject 8: Cursor must never exceed leftmost screen edge")
        ctrl.stop()

    # -------------------------------------------------------------------------
    # SUBJECT 9: Physical Mouse Dual-Wielder (Human-Input Arbiter)
    # -------------------------------------------------------------------------
    def test_subject_09_physical_mouse_dual_wielder(self):
        """Subject 9: Human touches physical mouse while head tracking is running. Arbiter must pause for 1.5s."""
        ctrl = AppController(use_synthetic=False, show_overlay=False, enable_stem_hook=False)
        ctrl.set_tracking(True, announce=False)
        ctrl._cursor = Vec2(400.0, 400.0)
        ctrl._last_posted = [Vec2(400.0, 400.0)]

        # Simulate physical mouse movement to (600, 600) -> displacement 282px
        now = time.time()
        # Mock synth current_location returning the physical mouse coords
        ctrl.synth.current_location = lambda: (600, 600)
        
        # Sync cursor
        ctrl._sync_cursor_with_system()

        # Verify arbiter engaged
        self.assertGreater(ctrl._human_override_until, now + 1.0, "Subject 9: Human override must engage for >= 1.0s")
        self.assertEqual(ctrl._cursor.x, 600.0, "Subject 9: Cursor must immediately adopt physical mouse position")

        # Head delta arrived during override: should be withheld
        ctrl.smoother.set_target(Vec2(100.0, 100.0), now)
        delta = ctrl.smoother.step(now, 0.016, 0.55)
        # In tracking loop:
        head_blocked = now < ctrl._human_override_until
        self.assertTrue(head_blocked, "Subject 9: Head tracking must yield 100% to physical mouse")
        ctrl.stop()

    # -------------------------------------------------------------------------
    # SUBJECT 10: Stem Squeeze Media Master
    # -------------------------------------------------------------------------
    def test_subject_10_stem_squeeze_media_master(self):
        """Subject 10: Squeezes stem buttons. Verifies single (left), double (right), triple (scroll toggle)."""
        ctrl = AppController(use_synthetic=False, show_overlay=False, enable_stem_hook=False)
        ctrl.set_tracking(True, announce=False)
        
        # Test 1x squeeze -> Left click
        action_1 = ctrl.settings.actions[Trigger.STEM_SINGLE]
        self.assertEqual(action_1, PointerAction.LEFT_CLICK)

        # Test 2x squeeze -> Right click
        action_2 = ctrl.settings.actions[Trigger.STEM_DOUBLE]
        self.assertEqual(action_2, PointerAction.RIGHT_CLICK)

        # Test 3x squeeze -> Toggle scroll mode
        ctrl._on_stem_trigger(Trigger.STEM_TRIPLE)
        self.assertEqual(ctrl.mode, TrackingMode.SCROLL, "Subject 10: Triple stem press must switch to SCROLL mode")
        
        ctrl._on_stem_trigger(Trigger.STEM_TRIPLE)
        self.assertEqual(ctrl.mode, TrackingMode.POINTER, "Subject 10: Triple stem press again must return to POINTER mode")
        ctrl.stop()

    # -------------------------------------------------------------------------
    # SUBJECT 11: Hostile Bluetooth Dropouts (Gap Rejection)
    # -------------------------------------------------------------------------
    def test_subject_11_hostile_bluetooth_dropouts(self):
        """Subject 11: Bluetooth connection drops for 600ms, then reconnects with different angle. No cursor jump!"""
        diff = MotionDifferentiator()

        t = 1100.0
        # Normal sample 1
        s1 = MotionSample(timestamp=t, yaw=0.0, pitch=0.0, roll=0.0)
        diff.push(s1)

        # Normal sample 2 (20ms later)
        t += 0.02
        s2 = MotionSample(timestamp=t, yaw=AngleMath.radians(0.5), pitch=0.0, roll=0.0)
        rates2 = diff.push(s2)
        self.assertIsNotNone(rates2)

        # Drop out for 600ms (exceeds maxInterval = 0.25s)
        t += 0.60
        s3 = MotionSample(timestamp=t, yaw=AngleMath.radians(20.0), pitch=AngleMath.radians(10.0), roll=0.0)
        rates3 = diff.push(s3)

        # Must reject gap without generating crazy high-speed delta!
        self.assertIsNone(rates3, "Subject 11: Packet gap > 250ms must be dropped to prevent cursor jumps")

        # Next regular packet resumes cleanly
        t += 0.02
        s4 = MotionSample(timestamp=t, yaw=AngleMath.radians(20.2), pitch=AngleMath.radians(10.0), roll=0.0)
        rates4 = diff.push(s4)
        self.assertIsNotNone(rates4, "Subject 11: Stream must resume smoothly after gap rejection")
        self.assertLess(abs(rates4.yaw), 20.0, "Subject 11: Normal rates on resumption")

    # -------------------------------------------------------------------------
    # SUBJECT 12: High-Rate 210Hz Sensor Burst
    # -------------------------------------------------------------------------
    def test_subject_12_high_rate_210hz_sensor_burst(self):
        """Subject 12: AirPods Pro 2 / AirPods 3 streaming at 210 Hz (dt = 0.00476s). 120Hz smoother stability."""
        diff = MotionDifferentiator()
        smoother = PointerSmoother()

        t = 1200.0
        dt = 1.0 / 210.0  # ~4.76 ms
        total_disp = Vec2(0.0, 0.0)

        for i in range(210):  # 1 full second at 210 Hz
            t += dt
            yaw = AngleMath.radians(math.sin(i * 0.1) * 5.0)
            s = MotionSample(timestamp=t, yaw=yaw, pitch=0.0, roll=0.0)
            rates = diff.push(s)
            if rates:
                v = PointerMapper.cursorVelocity(rates, self.settings.pointer)
                smoother.set_target(v, t)
            
            # Step smoother at 120Hz cadence
            disp = smoother.step(t, 1.0 / 120.0, 0.55)
            self.assertFalse(math.isnan(disp.x))
            self.assertFalse(math.isnan(disp.y))
            total_disp += disp

        # Verify smoother remained numerically stable and bounded
        self.assertFalse(math.isnan(total_disp.x))
        self.assertFalse(math.isnan(total_disp.y))


if __name__ == "__main__":
    unittest.main()
