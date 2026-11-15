"""Regression tests for the existing universal AirCursor foundations."""
import unittest

from aircursor_core.arbiter import FallbackPolicy, InputArbiter, TrackingSource
from aircursor_core.motion import MotionSample
from aircursor_core.pairing_qr import PairingQR
from aircursor_core.vision_tracker import VisionFrameResult, VisionTracker
from aircursor_core.web_remote_server import WebRemoteServer


class InputArbiterTests(unittest.TestCase):
    def sample(self, timestamp=100.0):
        return MotionSample(timestamp=timestamp, yaw=0.0, pitch=0.0, roll=0.0)

    def test_bluetooth_timeout_activates_camera_fallback(self):
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            fallback_policy=FallbackPolicy.AUTO_TRANSITION,
            bluetooth_timeout=3.0,
            camera_available=True,
            camera_enabled=True,
        )
        arbiter.notify_bluetooth_sample(self.sample(), timestamp=100.0)
        self.assertEqual(arbiter.check_health(now=103.1), TrackingSource.VISION)

    def test_bluetooth_reconnect_preempts_vision_fallback(self):
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            camera_available=True,
            camera_enabled=True,
        )
        arbiter.notify_bluetooth_sample(self.sample(), timestamp=100.0)
        arbiter.check_health(now=104.0)
        self.assertEqual(arbiter.active_source, TrackingSource.VISION)
        self.assertTrue(arbiter.notify_bluetooth_sample(self.sample(105.0), timestamp=105.0))
        self.assertEqual(arbiter.active_source, TrackingSource.BLUETOOTH)

    def test_manual_source_lock_prevents_automatic_fallback(self):
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            camera_available=True,
            camera_enabled=True,
        )
        arbiter.set_manual_source(TrackingSource.BLUETOOTH)
        arbiter.notify_bluetooth_sample(self.sample(), timestamp=100.0)
        self.assertEqual(arbiter.check_health(now=120.0), TrackingSource.BLUETOOTH)


class VisionTrackerTests(unittest.TestCase):
    def test_empty_frame_returns_safe_result_without_camera_access(self):
        tracker = VisionTracker()
        result = tracker.process_frame(None, timestamp=42.0)
        self.assertIsInstance(result, VisionFrameResult)
        self.assertEqual(result.timestamp, 42.0)
        self.assertFalse(result.face_detected)
        self.assertFalse(result.hand_detected)


class PairingTests(unittest.TestCase):
    def test_pairing_qr_contains_expected_lan_url(self):
        pairing = PairingQR(port=8765, ip="192.168.1.12")
        self.assertEqual(pairing.url, "http://192.168.1.12:8765")
        matrix = pairing.matrix
        self.assertGreater(len(matrix), 20)
        self.assertTrue(all(len(row) == len(matrix) for row in matrix))
        self.assertTrue(all(isinstance(cell, bool) for row in matrix for cell in row))


class WebRemoteDispatchTests(unittest.TestCase):
    def test_action_callback_receives_remote_command(self):
        server = WebRemoteServer(host="127.0.0.1", port=8765, controller=None)
        received = []
        server.set_action_callback(lambda action, dx, dy, extra: received.append((action, dx, dy, extra)))
        server.dispatch_action("left_click", dx=0.25, dy=-0.5, extra={"source": "unit-test"})
        self.assertEqual(received, [("left_click", 0.25, -0.5, {"source": "unit-test"})])

    def test_motion_callback_receives_payload(self):
        server = WebRemoteServer(host="127.0.0.1", port=8765, controller=None)
        received = []
        server.set_motion_callback(received.append)
        payload = {"dx": 0.1, "dy": -0.2, "source": "phone"}
        server.dispatch_motion(payload)
        self.assertEqual(received, [payload])


if __name__ == "__main__":
    unittest.main()
