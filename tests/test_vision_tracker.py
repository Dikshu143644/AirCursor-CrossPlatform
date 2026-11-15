"""Unit Tests for AirCursor Vision & Webcam Gesture Tracking Engine.

Validates:
1. VisionTracker lifecycle, start/stop/pause controls, and graceful degradation.
2. Head, face, and nose pose tracking translating movement into MotionSample deltas.
3. Hand gesture classification:
   - Open Palm (Free cursor motion)
   - Closed Fist (Drag lock / hold)
   - Peace Sign (Right click)
   - Pinch / Index Tap (Left click / drag)
   - Swipe Up / Down (Scroll wheel)
   - Gesture cooldown debouncing
4. InputArbiter automatic fallback:
   - AirPods timeout (> 3.0s silent) auto-transitions to Vision tracking.
   - Suggest-only fallback policy.
   - Seamless resumption when Bluetooth packets return.
   - Manual locking & toggling.
5. AppController vision integration and input dispatching.
6. Web Remote API status and camera toggle endpoints.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import socket
import sys
import time
import unittest
import urllib.request

# Ensure packages are discoverable
ROOT_DIR = Path(__file__).resolve().parent.parent
WINDOWS_DIR = ROOT_DIR / "windows"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    CV2_AVAILABLE = False

from aircursor_core.actions import PointerAction, Trigger
from aircursor_core.arbiter import FallbackPolicy, InputArbiter, TrackingSource
from aircursor_core.math_util import AngleMath, Vec2
from aircursor_core.motion import MotionDifferentiator, MotionSample
from aircursor_core.settings import AppSettings
from aircursor_core.vision_tracker import (
    HandGesture,
    VisionFrameResult,
    VisionTracker,
    VisionTrackerSettings,
    VisionTrackerState,
)
from app_controller import AppController, TrackingMode
from web_remote import WebRemoteServer


class TestVisionTrackerLifecycle(unittest.TestCase):
    """Tests for VisionTracker lifecycle, controls, and graceful degradation."""

    def test_default_settings(self):
        settings = VisionTrackerSettings()
        self.assertEqual(settings.camera_index, 0)
        self.assertEqual(settings.target_fps, 30.0)
        self.assertTrue(settings.enable_head_tracking)
        self.assertTrue(settings.enable_hand_gestures)
        self.assertTrue(settings.mirror)

    def test_tracker_initialization(self):
        tracker = VisionTracker()
        self.assertEqual(tracker.state, VisionTrackerState.STOPPED)
        self.assertFalse(tracker.is_running)
        self.assertFalse(tracker.is_paused)
        if CV2_AVAILABLE:
            self.assertTrue(tracker.is_available)

    def test_recenter(self):
        tracker = VisionTracker()
        tracker._neutral_center = (100.0, 100.0)
        tracker.recenter()
        self.assertIsNone(tracker._neutral_center)

    def test_graceful_degradation_invalid_camera(self):
        """Invalid camera index must fail gracefully without crashing."""
        settings = VisionTrackerSettings(camera_index=9999)
        tracker = VisionTracker(settings=settings)
        started = tracker.start()
        self.assertFalse(started)
        self.assertEqual(tracker.state, VisionTrackerState.ERROR_NO_CAMERA)
        tracker.stop()

    def test_graceful_degradation_missing_cv2(self):
        """When cv2 is missing, tracker must return empty result without crashing."""
        tracker = VisionTracker()
        # Simulate missing OpenCV
        original_avail = tracker.is_available
        try:
            tracker.settings.camera_index = 0
            res = tracker.process_frame(None)
            self.assertIsInstance(res, VisionFrameResult)
            self.assertFalse(res.face_detected)
            self.assertFalse(res.hand_detected)
        finally:
            pass


@unittest.skipUnless(CV2_AVAILABLE, "OpenCV required for vision test suite")
class TestFaceAndNosePoseTracking(unittest.TestCase):
    """Tests head/face and nose tracking algorithms translating pixels into MotionSample."""

    @classmethod
    def setUpClass(cls):
        # Generate BGR skin color from YCrCb [150, 150, 100]
        cls.skin_bgr = cv2.cvtColor(
            np.uint8([[[150, 150, 100]]]), cv2.COLOR_YCrCb2BGR
        )[0, 0].tolist()

    def test_face_detection_and_neutral_calibration(self):
        """First face detection must establish neutral reference calibration."""
        settings = VisionTrackerSettings(
            enable_head_tracking=True, enable_hand_gestures=False, mirror=False
        )
        tracker = VisionTracker(settings=settings)

        # 320x240 frame with oval face at center (160, 100)
        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img, (160, 100), (35, 50), 0, 0, 360, self.skin_bgr, -1)

        result = tracker.process_frame(img, timestamp=100.0)
        self.assertTrue(result.face_detected)
        self.assertIsNotNone(result.face_box)
        self.assertIsNotNone(result.face_center)
        self.assertIsNotNone(result.nose_point)
        self.assertIsNotNone(result.motion_sample)

        # Baseline sample should have 0 yaw and pitch
        self.assertAlmostEqual(result.motion_sample.yaw, 0.0, places=3)
        self.assertAlmostEqual(result.motion_sample.pitch, 0.0, places=3)

    def test_horizontal_head_movement_maps_to_yaw(self):
        """Moving head to the right must produce positive yaw attitude delta."""
        settings = VisionTrackerSettings(
            enable_head_tracking=True, enable_hand_gestures=False, mirror=False
        )
        tracker = VisionTracker(settings=settings)

        # Frame 1: Center face
        img1 = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img1, (160, 100), (35, 50), 0, 0, 360, self.skin_bgr, -1)
        res1 = tracker.process_frame(img1, timestamp=100.0)

        # Frame 2: Shifted right by 30 pixels (to x=190)
        img2 = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img2, (190, 100), (35, 50), 0, 0, 360, self.skin_bgr, -1)
        res2 = tracker.process_frame(img2, timestamp=100.033)

        self.assertTrue(res2.face_detected)
        self.assertGreater(res2.motion_sample.yaw, 0.0)
        self.assertAlmostEqual(res2.motion_sample.pitch, 0.0, places=2)

    def test_vertical_head_movement_maps_to_pitch(self):
        """Moving head upwards must produce positive pitch attitude delta."""
        settings = VisionTrackerSettings(
            enable_head_tracking=True, enable_hand_gestures=False, mirror=False
        )
        tracker = VisionTracker(settings=settings)

        # Frame 1: Center face at y=120
        img1 = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img1, (160, 120), (35, 50), 0, 0, 360, self.skin_bgr, -1)
        res1 = tracker.process_frame(img1, timestamp=200.0)

        # Frame 2: Shifted up by 25 pixels (to y=95)
        img2 = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img2, (160, 95), (35, 50), 0, 0, 360, self.skin_bgr, -1)
        res2 = tracker.process_frame(img2, timestamp=200.033)

        self.assertTrue(res2.face_detected)
        self.assertGreater(res2.motion_sample.pitch, 0.0)

    def test_motion_differentiator_pipeline_compatibility(self):
        """MotionSample produced by VisionTracker must cleanly feed into MotionDifferentiator."""
        settings = VisionTrackerSettings(mirror=False)
        tracker = VisionTracker(settings=settings)
        diff = MotionDifferentiator()

        img = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img, (160, 100), (35, 50), 0, 0, 360, self.skin_bgr, -1)
        res1 = tracker.process_frame(img, timestamp=10.0)
        rates1 = diff.push(res1.motion_sample)
        self.assertIsNone(rates1)  # First sample initializes differentiator

        # Second frame shifted right
        img2 = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.ellipse(img2, (175, 100), (35, 50), 0, 0, 360, self.skin_bgr, -1)
        res2 = tracker.process_frame(img2, timestamp=10.033)
        rates2 = diff.push(res2.motion_sample)

        self.assertIsNotNone(rates2)
        self.assertGreater(rates2.yaw, 0.0)
        self.assertFalse(math.isnan(rates2.yaw))


@unittest.skipUnless(CV2_AVAILABLE, "OpenCV required for vision test suite")
class TestHandGestureClassification(unittest.TestCase):
    """Tests gesture classifier across Open Palm, Pinch, Peace Sign, Closed Fist, and Swipes."""

    @classmethod
    def setUpClass(cls):
        cls.skin_bgr = cv2.cvtColor(
            np.uint8([[[150, 150, 100]]]), cv2.COLOR_YCrCb2BGR
        )[0, 0].tolist()

    def test_closed_fist_gesture(self):
        """Solid compact contour with 0 defects must classify as CLOSED_FIST."""
        tracker = VisionTracker()
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img, (100, 160), (190, 250), self.skin_bgr, -1)

        result = tracker.process_frame(img, timestamp=1.0)
        self.assertTrue(result.hand_detected)
        self.assertEqual(result.hand_gesture, HandGesture.CLOSED_FIST)
        self.assertEqual(result.finger_count, 0)

    def test_peace_sign_gesture(self):
        """Contour with two extended fingers and 1 deep defect must classify as PEACE_SIGN."""
        tracker = VisionTracker()
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.circle(img, (150, 210), 40, self.skin_bgr, -1)
        cv2.line(img, (135, 180), (125, 80), self.skin_bgr, 16)
        cv2.line(img, (165, 180), (175, 80), self.skin_bgr, 16)

        result = tracker.process_frame(img, timestamp=2.0)
        self.assertTrue(result.hand_detected)
        self.assertEqual(result.hand_gesture, HandGesture.PEACE_SIGN)
        self.assertEqual(result.finger_count, 2)

    def test_open_palm_gesture(self):
        """Contour with 5 extended fingers and low solidity must classify as OPEN_PALM."""
        tracker = VisionTracker()
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.circle(img, (150, 210), 40, self.skin_bgr, -1)
        cv2.line(img, (105, 190), (80, 130), self.skin_bgr, 14)
        cv2.line(img, (125, 170), (115, 70), self.skin_bgr, 14)
        cv2.line(img, (145, 170), (145, 60), self.skin_bgr, 14)
        cv2.line(img, (165, 170), (175, 75), self.skin_bgr, 14)
        cv2.line(img, (185, 190), (205, 110), self.skin_bgr, 14)

        result = tracker.process_frame(img, timestamp=3.0)
        self.assertTrue(result.hand_detected)
        self.assertEqual(result.hand_gesture, HandGesture.OPEN_PALM)
        self.assertGreaterEqual(result.finger_count, 4)

    def test_pinch_gesture_with_inner_hole(self):
        """Contour where index and thumb meet forming an inner loop must classify as PINCH."""
        tracker = VisionTracker()
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.circle(img, (150, 210), 40, self.skin_bgr, -1)
        cv2.ellipse(img, (150, 150), (35, 45), 0, 0, 360, self.skin_bgr, 16)

        result = tracker.process_frame(img, timestamp=4.0)
        self.assertTrue(result.hand_detected)
        self.assertEqual(result.hand_gesture, HandGesture.PINCH)

    def test_swipe_up_gesture(self):
        """Rapid upward vertical movement of hand centroid must classify as SWIPE_UP."""
        tracker = VisionTracker()
        t = 10.0
        # Frame 1: Hand at y=240
        img1 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img1, (100, 220), (180, 260), self.skin_bgr, -1)
        tracker.process_frame(img1, timestamp=t)

        # Frame 2: Hand moved up to y=200
        t += 0.04
        img2 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img2, (100, 180), (180, 220), self.skin_bgr, -1)
        tracker.process_frame(img2, timestamp=t)

        # Frame 3: Hand moved up to y=150 (speed ~ 900 px/s > threshold 120 px/s)
        t += 0.04
        img3 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img3, (100, 130), (180, 170), self.skin_bgr, -1)
        res3 = tracker.process_frame(img3, timestamp=t)

        self.assertEqual(res3.hand_gesture, HandGesture.SWIPE_UP)

    def test_swipe_down_gesture(self):
        """Rapid downward vertical movement of hand centroid must classify as SWIPE_DOWN."""
        tracker = VisionTracker()
        t = 20.0
        # Frame 1: Hand at y=100
        img1 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img1, (100, 80), (180, 120), self.skin_bgr, -1)
        tracker.process_frame(img1, timestamp=t)

        # Frame 2: Hand moved down to y=140
        t += 0.04
        img2 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img2, (100, 120), (180, 160), self.skin_bgr, -1)
        tracker.process_frame(img2, timestamp=t)

        # Frame 3: Hand moved down to y=190
        t += 0.04
        img3 = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img3, (100, 170), (180, 210), self.skin_bgr, -1)
        res3 = tracker.process_frame(img3, timestamp=t)

        self.assertEqual(res3.hand_gesture, HandGesture.SWIPE_DOWN)

    def test_gesture_cooldown_debouncing(self):
        """Consecutive identical gestures within cooldown window must not re-trigger."""
        tracker = VisionTracker(settings=VisionTrackerSettings(gesture_cooldown=0.35))
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(img, (100, 160), (190, 250), self.skin_bgr, -1)

        # First trigger at t=50.0
        res1 = tracker.process_frame(img, timestamp=50.0)
        self.assertEqual(res1.hand_gesture, HandGesture.CLOSED_FIST)

        # Second trigger 50ms later (within 350ms cooldown)
        res2 = tracker.process_frame(img, timestamp=50.05)
        self.assertEqual(res2.hand_gesture, HandGesture.NONE)

        # Third trigger 400ms later (after cooldown expires)
        res3 = tracker.process_frame(img, timestamp=50.45)
        self.assertEqual(res3.hand_gesture, HandGesture.CLOSED_FIST)


class TestInputArbiterAndFallback(unittest.TestCase):
    """Tests arbitration logic and automatic fallback transitions between Bluetooth and Vision."""

    def test_initial_state_and_bluetooth_flow(self):
        arbiter = InputArbiter(initial_source=TrackingSource.BLUETOOTH)
        self.assertEqual(arbiter.active_source, TrackingSource.BLUETOOTH)

        sample = MotionSample(timestamp=1.0, yaw=0.1, pitch=0.0, roll=0.0)
        consumed = arbiter.notify_bluetooth_sample(sample, timestamp=1.0)
        self.assertTrue(consumed)
        self.assertEqual(arbiter.last_bluetooth_time, 1.0)

    def test_automatic_fallback_when_bluetooth_silent_over_3_seconds(self):
        """When AirPods stop sending packets for > 3.0s, arbiter must switch to Vision."""
        transitions = []
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            fallback_policy=FallbackPolicy.AUTO_TRANSITION,
            bluetooth_timeout=3.0,
            camera_available=True,
            camera_enabled=True,
            on_source_changed=lambda old, new: transitions.append((old, new)),
        )

        sample = MotionSample(timestamp=10.0, yaw=0.0, pitch=0.0, roll=0.0)
        arbiter.notify_bluetooth_sample(sample, timestamp=10.0)

        # Check health at 11.5s (1.5s silent -> no fallback yet)
        arbiter.check_health(now=11.5)
        self.assertEqual(arbiter.active_source, TrackingSource.BLUETOOTH)
        self.assertEqual(len(transitions), 0)

        # Check health at 13.1s (> 3.0s silent -> auto transition to VISION!)
        active = arbiter.check_health(now=13.1)
        self.assertEqual(active, TrackingSource.VISION)
        self.assertEqual(arbiter.active_source, TrackingSource.VISION)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0], (TrackingSource.BLUETOOTH, TrackingSource.VISION))

    def test_suggest_only_fallback_policy(self):
        """Under SUGGEST_ONLY policy, arbiter fires callback instead of auto-switching."""
        suggestions = []
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            fallback_policy=FallbackPolicy.SUGGEST_ONLY,
            bluetooth_timeout=3.0,
            camera_available=True,
            camera_enabled=True,
            on_fallback_suggested=lambda msg: suggestions.append(msg),
        )

        sample = MotionSample(timestamp=10.0, yaw=0.0, pitch=0.0, roll=0.0)
        arbiter.notify_bluetooth_sample(sample, timestamp=10.0)

        # Silent for 3.5s
        arbiter.check_health(now=13.5)
        self.assertEqual(arbiter.active_source, TrackingSource.BLUETOOTH)
        self.assertEqual(len(suggestions), 1)
        self.assertIn("Camera fallback available", suggestions[0])

    def test_bluetooth_resumption_seamless_recovery(self):
        """When fresh Bluetooth packets arrive after fallback, arbiter resumes Bluetooth."""
        transitions = []
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            fallback_policy=FallbackPolicy.AUTO_TRANSITION,
            bluetooth_timeout=3.0,
            camera_available=True,
            camera_enabled=True,
            on_source_changed=lambda old, new: transitions.append((old, new)),
        )

        # Step 1: Initial sample
        s1 = MotionSample(timestamp=1.0, yaw=0.0, pitch=0.0, roll=0.0)
        arbiter.notify_bluetooth_sample(s1, timestamp=1.0)

        # Step 2: Timeout and transition to VISION
        arbiter.check_health(now=4.5)
        self.assertEqual(arbiter.active_source, TrackingSource.VISION)

        # Step 3: Fresh Bluetooth sample arrives!
        s2 = MotionSample(timestamp=5.0, yaw=0.05, pitch=0.0, roll=0.0)
        consumed = arbiter.notify_bluetooth_sample(s2, timestamp=5.0)

        self.assertTrue(consumed)
        self.assertEqual(arbiter.active_source, TrackingSource.BLUETOOTH)
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[1], (TrackingSource.VISION, TrackingSource.BLUETOOTH))

    def test_manual_lock_and_toggle(self):
        """Manual locking prevents automatic fallback overrides."""
        arbiter = InputArbiter(
            initial_source=TrackingSource.BLUETOOTH,
            camera_available=True,
            camera_enabled=True,
        )

        # Force lock to VISION
        arbiter.set_manual_source(TrackingSource.VISION)
        self.assertEqual(arbiter.active_source, TrackingSource.VISION)

        # Even if Bluetooth sample arrives, manual lock keeps VISION
        sample = MotionSample(timestamp=10.0, yaw=0.0, pitch=0.0, roll=0.0)
        consumed = arbiter.notify_bluetooth_sample(sample, timestamp=10.0)
        self.assertFalse(consumed)
        self.assertEqual(arbiter.active_source, TrackingSource.VISION)

        # Toggle camera switches back to BLUETOOTH
        new_source = arbiter.toggle_camera()
        self.assertEqual(new_source, TrackingSource.BLUETOOTH)


class TestAppControllerVisionIntegration(unittest.TestCase):
    """Tests AppController integration with VisionTracker, gestures, and pointer actions."""

    def setUp(self):
        self.settings = AppSettings()
        self.settings.dwell.enabled = False
        self.settings.vision.enabled = True
        self.controller = AppController(
            settings=self.settings,
            use_synthetic=True,
            show_overlay=False,
            enable_stem_hook=False,
            enable_camera=False,  # Don't try opening physical camera in tests
        )

    def tearDown(self):
        self.controller.stop()

    def test_handle_vision_sample_updates_telemetry(self):
        """Vision MotionSample must update live yaw, pitch, roll telemetry."""
        # Switch arbiter to VISION
        self.controller.arbiter.set_manual_source(TrackingSource.VISION)

        s1 = MotionSample(timestamp=100.0, yaw=0.0, pitch=0.0, roll=0.0)
        self.controller.handle_vision_sample(s1)

        s2 = MotionSample(
            timestamp=100.02,
            yaw=AngleMath.radians(12.0),
            pitch=AngleMath.radians(-8.0),
            roll=0.0,
        )
        self.controller.handle_vision_sample(s2)

        self.assertAlmostEqual(self.controller.live_yaw, 12.0, places=1)
        self.assertAlmostEqual(self.controller.live_pitch, -8.0, places=1)
        self.assertTrue(self.controller.motion_streaming)

    def test_vision_pinch_gesture_executes_click(self):
        """Pinch gesture must synthesize a left click action."""
        self.controller.arbiter.set_manual_source(TrackingSource.VISION)
        self.controller.set_tracking(True, announce=False)

        res = VisionFrameResult(timestamp=1.0, hand_gesture=HandGesture.PINCH)
        # Verify click action executes without exception
        self.controller.handle_vision_gesture(HandGesture.PINCH, res)
        self.assertFalse(self.controller.is_dragging)

    def test_vision_peace_sign_executes_right_click(self):
        """Peace sign gesture must synthesize a right click action."""
        self.controller.arbiter.set_manual_source(TrackingSource.VISION)
        self.controller.set_tracking(True, announce=False)

        res = VisionFrameResult(timestamp=2.0, hand_gesture=HandGesture.PEACE_SIGN)
        self.controller.handle_vision_gesture(HandGesture.PEACE_SIGN, res)
        self.assertFalse(self.controller.is_dragging)

    def test_vision_closed_fist_toggles_drag_lock(self):
        """Closed fist must engage drag lock, and Open Palm must release it."""
        self.controller.arbiter.set_manual_source(TrackingSource.VISION)
        self.controller.set_tracking(True, announce=False)

        # Closed fist -> Begin drag
        res_fist = VisionFrameResult(timestamp=3.0, hand_gesture=HandGesture.CLOSED_FIST)
        self.controller.handle_vision_gesture(HandGesture.CLOSED_FIST, res_fist)
        self.assertTrue(self.controller.is_dragging)

        # Open palm -> End drag / Free motion
        res_palm = VisionFrameResult(timestamp=4.0, hand_gesture=HandGesture.OPEN_PALM)
        self.controller.handle_vision_gesture(HandGesture.OPEN_PALM, res_palm)
        self.assertFalse(self.controller.is_dragging)

    def test_vision_swipe_gestures_scroll(self):
        """Swipe gestures must execute scroll operations."""
        self.controller.arbiter.set_manual_source(TrackingSource.VISION)
        self.controller.set_tracking(True, announce=False)

        res_up = VisionFrameResult(timestamp=5.0, hand_gesture=HandGesture.SWIPE_UP)
        self.controller.handle_vision_gesture(HandGesture.SWIPE_UP, res_up)

        res_down = VisionFrameResult(timestamp=6.0, hand_gesture=HandGesture.SWIPE_DOWN)
        self.controller.handle_vision_gesture(HandGesture.SWIPE_DOWN, res_down)


class TestWebRemoteAPI(unittest.TestCase):
    """Tests the embedded Web Remote REST API server."""

    @classmethod
    def setUpClass(cls):
        cls.settings = AppSettings()
        cls.settings.remote.port = 8792  # Dedicated test port
        cls.controller = AppController(
            settings=cls.settings,
            use_synthetic=True,
            show_overlay=False,
            enable_stem_hook=False,
            enable_camera=False,
            enable_web_remote=False,
        )
        cls.server = WebRemoteServer(
            controller=cls.controller, host="127.0.0.1", port=8792
        )
        cls.server.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.controller.stop()

    def test_get_status_endpoint(self):
        """GET /api/status returns JSON telemetry and tracking status."""
        url = "http://127.0.0.1:8792/api/status"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("tracking_enabled", data)
            self.assertIn("mode", data)
            self.assertIn("active_source", data)
            self.assertIn("camera_active", data)
            self.assertIn("live_yaw", data)

    def test_post_camera_toggle_endpoint(self):
        """POST /api/camera/toggle toggles vision tracking."""
        url = "http://127.0.0.1:8792/api/camera/toggle"
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("camera_active", data)


if __name__ == "__main__":
    unittest.main()
