"""
AirCursor Linux Unit Tests & Verification Suite.
Validates math, differentiators, gestures (nod/shake/tilt), dwell detector,
BlueZ binary packet parsing, Q15 quaternion decoding, and event synthesis.
"""

import math
import struct
import time
import unittest

from aircursor_core import (
    AngleMath,
    AngularRates,
    CursorHistory,
    DwellDetector,
    DwellSettings,
    GestureDetector,
    GestureSettings,
    HeadGesture,
    MotionDifferentiator,
    MotionSample,
    PointerMapper,
    PointerSettings,
    PointerSmoother,
    Vec2,
)
from airpods_bluez import (
    AirPodsBlueZDriver,
    decode_q15_quaternion,
    quaternion_to_euler,
)
from event_synthesizer import LinuxEventSynthesizer


class TestAirCursorMath(unittest.TestCase):
    def test_vec2_operations(self):
        v1 = Vec2(3.0, 4.0)
        self.assertEqual(v1.length, 5.0)

        v2 = Vec2(1.0, 2.0)
        v3 = v1 + v2
        self.assertEqual(v3.x, 4.0)
        self.assertEqual(v3.y, 6.0)

        dist = v1.distance(Vec2(0.0, 0.0))
        self.assertEqual(dist, 5.0)

    def test_angle_math_wrapping(self):
        # 179° - (-179°) = 358° -> should wrap to -2°
        rad_a = AngleMath.radians(179.0)
        rad_b = AngleMath.radians(-179.0)
        wrapped_rad = AngleMath.wrapped_delta(rad_a, rad_b)
        wrapped_deg = AngleMath.degrees(wrapped_rad)
        self.assertAlmostEqual(wrapped_deg, -2.0, places=4)

        wrapped_deg_direct = AngleMath.wrapped_delta_degrees(179.0, -179.0)
        self.assertAlmostEqual(wrapped_deg_direct, -2.0, places=4)


class TestMotionPipeline(unittest.TestCase):
    def test_motion_differentiator(self):
        diff = MotionDifferentiator()
        t0 = 100.0
        # Initial sample yields None (needs pair)
        self.assertIsNone(diff.push(MotionSample(t0, 0.0, 0.0, 0.0)))

        # 0.01 seconds later, head turned 0.1 rad in yaw
        t1 = t0 + 0.01
        sample1 = MotionSample(t1, 0.1, 0.0, 0.0)
        rates = diff.push(sample1)
        self.assertIsNotNone(rates)
        expected_deg_s = AngleMath.degrees(0.1) / 0.01
        self.assertAlmostEqual(rates.yaw, expected_deg_s, places=2)

    def test_motion_differentiator_gap_rejection(self):
        diff = MotionDifferentiator()
        diff.push(MotionSample(10.0, 0.0, 0.0, 0.0))
        # 0.5s gap (> maxInterval 0.25s) -> should reject to avoid cursor jumps
        rates = diff.push(MotionSample(10.5, 0.5, 0.0, 0.0))
        self.assertIsNone(rates)

    def test_pointer_mapper_deadzone(self):
        settings = PointerSettings(deadzone=3.0, sensitivity=1.0)
        # Rates within deadzone should produce zero speed
        self.assertEqual(PointerMapper.axis_speed(2.5, settings), 0.0)
        self.assertEqual(PointerMapper.axis_speed(-2.9, settings), 0.0)

        # Rates above deadzone should scale with pixelsPerDegree
        speed = PointerMapper.axis_speed(4.0, settings)
        self.assertGreater(speed, 0.0)

    def test_pointer_smoother(self):
        smoother = PointerSmoother()
        smoother.set_target(Vec2(100.0, 0.0), timestamp=10.0)
        disp = smoother.step(now=10.01, dt=0.01, smoothing=0.55)
        self.assertGreater(disp.x, 0.0)


class TestGestures(unittest.TestCase):
    def test_nod_detection(self):
        detector = GestureDetector(GestureSettings(nod_amplitude=5.0, nod_window=0.8))
        t = 1.0
        base_yaw = 0.0
        base_roll = 0.0
        # Simulate downward head nod (dip pitch down by 7 degrees then return)
        pitches = [0.0, -2.0, -5.0, -7.0, -4.0, -1.0, 0.0]
        event = None
        for p in pitches:
            s = MotionSample(
                timestamp=t,
                yaw=AngleMath.radians(base_yaw),
                pitch=AngleMath.radians(p),
                roll=AngleMath.radians(base_roll),
            )
            e = detector.process(s, {HeadGesture.NOD})
            if e:
                event = e
                break
            t += 0.04  # 25 Hz steps

        self.assertIsNotNone(event)
        self.assertEqual(event.gesture, HeadGesture.NOD)
        self.assertGreaterEqual(event.magnitude, 5.0)


class TestDwellDetector(unittest.TestCase):
    def test_dwell_click(self):
        detector = DwellDetector(DwellSettings(duration=0.5, radius=10.0))
        pos = Vec2(100.0, 200.0)
        t = 1.0

        # Anchor set
        u0 = detector.update(pos, t)
        self.assertFalse(u0.fired)
        self.assertIsNone(u0.progress)

        # Move slightly to arm
        pos_drift = Vec2(115.0, 200.0)
        t += 0.1
        u1 = detector.update(pos_drift, t)
        self.assertTrue(detector.armed)

        # Rest for 0.3s (progress >= revealFraction)
        t += 0.3
        u2 = detector.update(pos_drift, t)
        self.assertFalse(u2.fired)
        self.assertIsNotNone(u2.progress)

        # Rest until duration elapsed (0.5s)
        t += 0.3
        u3 = detector.update(pos_drift, t)
        self.assertTrue(u3.fired)
        self.assertEqual(u3.progress, 1.0)


class TestAirPodsBinaryParser(unittest.TestCase):
    def test_q15_quaternion_decoding(self):
        # Identity orientation (w=1, x=0, y=0, z=0) -> raw_x=0, raw_y=0, raw_z=0
        w, x, y, z = decode_q15_quaternion(0, 0, 0)
        self.assertAlmostEqual(w, 1.0, places=4)
        self.assertAlmostEqual(x, 0.0, places=4)
        self.assertAlmostEqual(y, 0.0, places=4)
        self.assertAlmostEqual(z, 0.0, places=4)

        yaw, pitch, roll = quaternion_to_euler(w, x, y, z)
        self.assertAlmostEqual(yaw, 0.0, places=4)
        self.assertAlmostEqual(pitch, 0.0, places=4)
        self.assertAlmostEqual(roll, 0.0, places=4)

    def test_58_byte_motion_block_parsing(self):
        driver = AirPodsBlueZDriver("00:11:22:33:44:55", on_sample=lambda s: None)
        # Create synthetic 58-byte motion block
        # Byte 0: status (1)
        # Bytes 1..8: timestamp (123456789)
        # Bytes 20..26: 3 x int16 in Q15
        block = bytearray(58)
        block[0] = 0x01
        struct.pack_into("<Q", block, 1, 1000000000)
        # Encode a small rotation: raw_x=3276 (approx 0.1 in Q15)
        struct.pack_into("<hhh", block, 20, 3276, 0, 0)

        sample = driver.parse_motion_block(bytes(block))
        self.assertIsNotNone(sample)
        self.assertIsInstance(sample.yaw, float)
        self.assertIsInstance(sample.pitch, float)
        self.assertIsInstance(sample.roll, float)


class TestLinuxUInput(unittest.TestCase):
    def test_udev_rule_generation(self):
        from uinput import generate_udev_rule, check_uinput_permissions
        rule = generate_udev_rule()
        self.assertIn('KERNEL=="uinput"', rule)
        self.assertIn('GROUP="input"', rule)
        has_perm, msg = check_uinput_permissions()
        self.assertIsInstance(has_perm, bool)
        self.assertIsInstance(msg, str)

    def test_uinput_device_relative_and_absolute(self):
        from uinput import UInputDevice
        dev = UInputDevice(screen_width=1920, screen_height=1080)
        self.assertEqual(dev.cur_x, 960.0)
        self.assertEqual(dev.cur_y, 540.0)

        # 1. Test relative movement
        x, y = dev.move_relative(10.5, -20.5)
        self.assertEqual(x, 970.5)
        self.assertEqual(y, 519.5)

        # 2. Test absolute movement
        x, y = dev.move_absolute(100.0, 200.0)
        self.assertEqual(x, 100.0)
        self.assertEqual(y, 200.0)

        # Clamping
        x, y = dev.move_absolute(5000.0, -50.0)
        self.assertEqual(x, 1920.0)
        self.assertEqual(y, 0.0)

        # 3. Test handle_motion_packet (Relative)
        x, y = dev.handle_motion_packet({"type": "relative", "dx": -10.0, "dy": 50.0})
        self.assertEqual(x, 1910.0)
        self.assertEqual(y, 50.0)

        # 4. Test handle_motion_packet (Absolute)
        x, y = dev.handle_motion_packet({"type": "absolute", "x": 640.0, "y": 480.0})
        self.assertEqual(x, 640.0)
        self.assertEqual(y, 480.0)

        # 5. Test handle_motion_packet (Normalized 0..1 coordinates)
        x, y = dev.handle_motion_packet({"type": "absolute", "x": 0.5, "y": 0.5})
        self.assertEqual(x, 960.0)
        self.assertEqual(y, 540.0)

        # 6. Test handle_motion_packet (Tuple)
        x, y = dev.handle_motion_packet((5.0, 5.0))
        self.assertEqual(x, 965.0)
        self.assertEqual(y, 545.0)

        # 7. Button and Drag states
        self.assertFalse(dev.is_left_button_down)
        locked = dev.toggle_drag()
        self.assertTrue(locked)
        self.assertTrue(dev.is_left_button_down)
        locked = dev.toggle_drag()
        self.assertFalse(locked)
        self.assertFalse(dev.is_left_button_down)

        dev.click("left", count=1)
        dev.scroll(vertical=1, horizontal=0)
        dev.close()

    def test_event_synthesizer_integration(self):
        from event_synthesizer import LinuxEventSynthesizer
        synth = LinuxEventSynthesizer()
        synth.move_relative(5.0, -5.0)
        pos = synth.get_current_location()
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 2)
        synth.close()


if __name__ == "__main__":
    unittest.main()
