"""AirCursor Windows Comprehensive Self-Test Suite.

Verifies all components of the Windows application:
1. EventSynthesizer (SendInput, mouse moves, clicks, scrolls, keyboard)
2. ClickableProbe (UIA ElementFromPoint, ControlType, IDC_HAND fallback)
3. StemListener (WH_KEYBOARD_LL low-level hook setup and teardown)
4. OverlayController (Layered click-through HUD, dwell ring, pulse, toast)
5. SensorReceiver (OpenTrack UDP 48-byte packet parsing, radians conversion)
6. SyntheticSensorGenerator (Simulation stream, nod, shake, dwell injection)
7. BluetoothAirPodsHelper (Windows registry Bluetooth AirPods discovery)
8. HotKeyManager (Global shortcut hook setup and teardown)
9. AppController (120Hz pipeline, motion integration, cursor rollback, dwell)
10. Settings Persistence (JSON load/save round-trip)
"""

from __future__ import annotations

import math
from pathlib import Path
import socket
import struct
import sys
import time
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
WINDOWS_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from aircursor_core.actions import ActionMap, PointerAction, Trigger
from aircursor_core.gestures import HeadGesture
from aircursor_core.math_util import AngleMath, Vec2
from aircursor_core.motion import MotionSample
from aircursor_core.settings import AppSettings

from app_controller import AppController, TrackingMode
from clickable_probe import ClickableProbe
from event_synthesizer import EventSynthesizer, VK_CONTROL, VK_MENU, VK_TAB
from hotkey_manager import HotKeyManager
from overlay import OverlayController
from sensor_receiver import (
    BluetoothAirPodsHelper,
    OpenTrackReceiver,
    SyntheticSensorGenerator,
)
from stem_listener import StemListener


class TestEventSynthesizer(unittest.TestCase):
    def setUp(self):
        self.synth = EventSynthesizer()

    def test_current_location_and_bounds(self):
        loc = self.synth.current_location()
        self.assertIsInstance(loc, tuple)
        self.assertEqual(len(loc), 2)

        bounds = self.synth.get_screen_bounds()
        self.assertEqual(len(bounds), 4)
        x, y, w, h = bounds
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)

    def test_mouse_moves_and_clicks(self):
        cur_x, cur_y = self.synth.current_location()
        # Move slightly
        self.synth.move_to(cur_x, cur_y)
        self.synth.move_relative(0, 0)

        # Clicks
        self.synth.click(button="left", count=1)
        self.synth.click(button="right", count=1)
        self.synth.middle_click()

        # Drag lock
        self.assertFalse(self.synth.is_left_button_down)
        dragging = self.synth.toggle_drag()
        self.assertTrue(dragging)
        self.assertTrue(self.synth.is_left_button_down)
        dragging = self.synth.toggle_drag()
        self.assertFalse(dragging)
        self.assertFalse(self.synth.is_left_button_down)

    def test_scroll_and_keys(self):
        self.synth.scroll(vertical=0, horizontal=0)
        self.synth.scroll(vertical=1, horizontal=0)
        self.synth.scroll(vertical=-1, horizontal=1)

        # Safe keystroke: Shift key down and up
        self.synth.key_down(0x10)  # VK_SHIFT
        self.synth.key_up(0x10)


class TestClickableProbe(unittest.TestCase):
    def setUp(self):
        self.probe = ClickableProbe()

    def tearDown(self):
        self.probe.close()

    def test_probe_sync_and_async(self):
        # Sync test
        res = self.probe.is_clickable_sync(100, 100, timeout=0.2)
        self.assertIsInstance(res, bool)

        # Async test
        box = []
        import threading

        done = threading.Event()

        def _cb(v: bool):
            box.append(v)
            done.set()

        self.probe.check(100, 100, _cb)
        self.assertTrue(done.wait(timeout=1.0))
        self.assertEqual(len(box), 1)

    def test_cursor_shape_fallback(self):
        looks_clickable = self.probe.cursor_looks_clickable()
        self.assertIsInstance(looks_clickable, bool)


class TestStemListener(unittest.TestCase):
    def test_lifecycle(self):
        listener = StemListener(on_trigger=lambda t: None, intercept=False)
        listener.start()
        self.assertTrue(listener.is_active)
        time.sleep(0.1)
        listener.stop()
        self.assertFalse(listener.is_active)


class TestOverlayController(unittest.TestCase):
    def test_overlay_lifecycle_and_drawing(self):
        overlay = OverlayController(enabled=True)
        time.sleep(0.1)
        overlay.update_dwell(0.5, 200, 200)
        overlay.pulse(200, 200)
        overlay.show_toast("Self Test Running", "🎯")
        time.sleep(0.1)
        overlay.hide()
        overlay.close()


class TestSensorReceiver(unittest.TestCase):
    def test_opentrack_udp_parsing(self):
        samples = []
        receiver = OpenTrackReceiver(
            port=42429, on_sample=lambda s: samples.append(s)
        )
        receiver.start()

        # Send test OpenTrack 6-double packet
        # x, y, z in cm, yaw=15.0 deg, pitch=-10.0 deg, roll=5.0 deg
        test_packet = struct.pack("<6d", 0.0, 0.0, 0.0, 15.0, -10.0, 5.0)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(test_packet, ("127.0.0.1", 42429))
        sock.close()

        time.sleep(0.2)
        receiver.stop()

        self.assertGreaterEqual(len(samples), 1)
        s = samples[0]
        self.assertAlmostEqual(AngleMath.degrees(s.yaw), 15.0, places=2)
        self.assertAlmostEqual(AngleMath.degrees(s.pitch), -10.0, places=2)
        self.assertAlmostEqual(AngleMath.degrees(s.roll), 5.0, places=2)

    def test_synthetic_sensor_generator(self):
        gen_samples = []
        gen = SyntheticSensorGenerator(
            fps=120.0, on_sample=lambda s: gen_samples.append(s)
        )
        gen.start()
        time.sleep(0.15)

        # Trigger nod gesture in generator
        gen.trigger_nod()
        time.sleep(0.1)

        # Trigger shake
        gen.trigger_shake()
        time.sleep(0.1)

        gen.stop()
        self.assertGreater(len(gen_samples), 10)
        for s in gen_samples:
            self.assertIsInstance(s, MotionSample)
            self.assertGreater(s.timestamp, 0)


class TestBluetoothAirPodsHelper(unittest.TestCase):
    def test_bluetooth_scan(self):
        devices = BluetoothAirPodsHelper.list_paired_headphones()
        self.assertIsInstance(devices, list)

        airpods = BluetoothAirPodsHelper.get_paired_airpods()
        self.assertIsInstance(airpods, list)

        guide = BluetoothAirPodsHelper.get_setup_instructions()
        self.assertIn("AirPods Setup on Windows", guide)


class TestHotKeyManager(unittest.TestCase):
    def test_lifecycle(self):
        hm = HotKeyManager()
        box = []
        hm.register(ord("T"), ctrl=True, alt=True, callback=lambda: box.append("T"))
        hm.start()
        time.sleep(0.1)
        hm.stop()


class TestAppControllerIntegration(unittest.TestCase):
    def test_pipeline_execution(self):
        settings = AppSettings()
        settings.dwell.duration = 0.4
        settings.dwell.radius = 20.0

        controller = AppController(
            settings=settings,
            use_synthetic=True,
            show_overlay=False,
            enable_stem_hook=False,
        )
        controller.start()
        self.assertTrue(controller.tracking_enabled)

        # Wait for simulated telemetry frames to flow
        time.sleep(0.4)
        self.assertGreater(controller._sample_count, 10)
        self.assertTrue(controller.motion_streaming)

        # Test mode toggle
        controller.set_mode(TrackingMode.SCROLL)
        self.assertEqual(controller.mode, TrackingMode.SCROLL)
        controller.set_mode(TrackingMode.POINTER)
        self.assertEqual(controller.mode, TrackingMode.POINTER)

        # Test tracking pause & resume
        controller.set_tracking(False, announce=False)
        self.assertFalse(controller.tracking_enabled)
        controller.set_tracking(True, announce=False)
        self.assertTrue(controller.tracking_enabled)

        # Test Recenter
        controller.recenter()

        # Test Cursor rollback on nod trigger
        now = time.time()
        pos_before = controller.history.position(now - 0.05)
        self.assertIsNotNone(pos_before)

        # Trigger nod action
        controller._handle_trigger(Trigger.NOD, gesture_start=now)

        # Test Drag lock
        controller.begin_drag()
        self.assertTrue(controller.is_dragging)
        controller.end_drag()
        self.assertFalse(controller.is_dragging)

        controller.stop()


class TestSettingsPersistence(unittest.TestCase):
    def test_round_trip(self):
        s1 = AppSettings()
        s1.pointer.sensitivity = 1.85
        s1.pointer.smoothing = 0.72
        s1.dwell.duration = 0.65
        s1.gestures.nod_amplitude = 6.8

        json_str = s1.to_json()
        s2 = AppSettings.from_json(json_str)

        self.assertAlmostEqual(s2.pointer.sensitivity, 1.85, places=3)
        self.assertAlmostEqual(s2.pointer.smoothing, 0.72, places=3)
        self.assertAlmostEqual(s2.dwell.duration, 0.65, places=3)
        self.assertAlmostEqual(s2.gestures.nod_amplitude, 6.8, places=3)


def run_tests():
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
