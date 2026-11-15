"""AirCursor Vision & Webcam Gesture Tracking Engine.

Provides zero-cloud real-time camera tracking that acts as an automatic fallback
when AirPods or Bluetooth IMU sensors are disconnected or silent:
1. Head / Nose / Face Pose Tracking:
   - Estimates head yaw, pitch, and roll displacement from webcam frames.
   - Translates nose and face center motion into smooth MotionSample instances.
2. Hand Gesture Recognition:
   - Open Palm: Free motion (moves cursor smoothly)
   - Pinch / Index Tap: Left click / drag
   - Peace Sign (Two fingers): Right click
   - Closed Fist: Drag lock / hold
   - Swipe Up / Down: Scroll wheel
3. Zero Crash & Graceful Degradation:
   - Works seamlessly with OpenCV (cv2) when available.
   - Provides mock/stub fallback with helpful install hints if cv2 or camera is absent.
   - Threaded worker loop with start/stop/pause controls and frame rate throttling (30-60 FPS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import enum
import math
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# Import Core Motion models
from .math_util import AngleMath, Vec2
from .motion import MotionSample

# Check OpenCV and NumPy availability
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None  # type: ignore
    np = None   # type: ignore
    CV2_AVAILABLE = False


class HandGesture(str, enum.Enum):
    """Recognized vision hand gestures."""

    NONE = "none"
    OPEN_PALM = "open_palm"          # Free motion (moves cursor smoothly)
    PINCH = "pinch"                  # Left click / Drag (Index tip meets thumb tip)
    PEACE_SIGN = "peace_sign"        # Right click (Two fingers up)
    CLOSED_FIST = "closed_fist"      # Drag lock / Hold
    SWIPE_UP = "swipe_up"            # Scroll Wheel Up
    SWIPE_DOWN = "swipe_down"        # Scroll Wheel Down


class VisionTrackerState(str, enum.Enum):
    """Operational states of the vision tracker engine."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR_NO_CV2 = "error_no_cv2"
    ERROR_NO_CAMERA = "error_no_camera"


@dataclass
class VisionFrameResult:
    """Output telemetry bundle produced for each processed video frame."""

    timestamp: float
    face_detected: bool = False
    face_box: Optional[Tuple[int, int, int, int]] = None  # (x, y, w, h)
    face_center: Optional[Tuple[float, float]] = None     # (cx, cy)
    nose_point: Optional[Tuple[float, float]] = None      # (nx, ny)
    motion_sample: Optional[MotionSample] = None          # Converted head/hand attitude
    hand_detected: bool = False
    hand_box: Optional[Tuple[int, int, int, int]] = None
    hand_center: Optional[Tuple[float, float]] = None     # (cx, cy)
    hand_tip: Optional[Tuple[float, float]] = None        # (tx, ty) fingertip
    hand_gesture: HandGesture = HandGesture.NONE
    finger_count: int = 0
    confidence: float = 0.0
    tracking_mode_used: str = "none"                      # "hand", "head", or "none"


@dataclass
class VisionTrackerSettings:
    """Configuration parameters for webcam capture and computer vision pipeline."""

    camera_index: int = 0
    target_fps: float = 30.0
    frame_width: int = 640
    frame_height: int = 480
    mirror: bool = True
    yaw_sensitivity: float = 0.45       # Radians max yaw angle
    pitch_sensitivity: float = 0.35     # Radians max pitch angle
    roll_sensitivity: float = 0.25      # Radians max roll angle
    deadzone: float = 0.015             # Normalized center deadzone
    gesture_cooldown: float = 0.35      # Seconds between gesture triggers
    swipe_threshold: float = 120.0      # Pixels per second for vertical swipe
    enable_head_tracking: bool = True
    enable_hand_gestures: bool = True
    enable_hand_tracking: bool = True   # Enable hand motion to move the cursor
    hand_sensitivity: float = 2.5       # Responsiveness multiplier for hand motion


class VisionTracker:
    """Real-time webcam head pose and hand gesture tracking engine."""

    def __init__(
        self,
        settings: Optional[VisionTrackerSettings] = None,
        on_sample: Optional[Callable[[MotionSample], None]] = None,
        on_gesture: Optional[Callable[[HandGesture, VisionFrameResult], None]] = None,
        on_frame: Optional[Callable[[VisionFrameResult], None]] = None,
    ):
        self.settings = settings or VisionTrackerSettings()
        self.on_sample = on_sample
        self.on_gesture = on_gesture
        self.on_frame = on_frame

        self._state: VisionTrackerState = VisionTrackerState.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._paused: bool = False

        # Tracking state
        self._neutral_center: Optional[Tuple[float, float]] = None
        self._last_face_center: Optional[Tuple[float, float]] = None
        self._neutral_hand: Optional[Tuple[float, float]] = None
        self._last_hand_time: float = 0.0
        self._prev_hand_pt: Optional[Tuple[float, float]] = None
        self._smoothed_hand_pt: Optional[Tuple[float, float]] = None
        self._hand_yaw: float = 0.0
        self._hand_pitch: float = 0.0
        self._last_gesture: HandGesture = HandGesture.NONE
        self._last_gesture_time: float = 0.0
        self._hand_history: List[Tuple[float, float]] = []  # [(timestamp, y_center)]

        # Telemetry stats
        self.frames_processed: int = 0
        self.last_fps: float = 0.0
        self._fps_count: int = 0
        self._fps_timer: float = time.time()

        # Haar cascade classifier cache if available
        self._face_cascade = None
        if CV2_AVAILABLE:
            self._init_cascades()

    @property
    def is_available(self) -> bool:
        """True if OpenCV is installed."""
        return CV2_AVAILABLE

    @property
    def state(self) -> VisionTrackerState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == VisionTrackerState.RUNNING

    @property
    def is_paused(self) -> bool:
        return self._paused

    def _init_cascades(self) -> None:
        """Attempts to load OpenCV Haar Cascade face detector if present on system."""
        if not CV2_AVAILABLE:
            return
        cascade_paths = [
            getattr(cv2.data, "haarcascades", "") + "haarcascade_frontalface_default.xml",
            os.path.join(os.path.dirname(cv2.__file__), "data", "haarcascade_frontalface_default.xml"),
        ]
        for p in cascade_paths:
            if os.path.exists(p):
                try:
                    self._face_cascade = cv2.CascadeClassifier(p)
                    break
                except Exception:
                    pass

    def recenter(self) -> None:
        """Recenters reference face and hand positions."""
        self._neutral_center = None
        self._neutral_hand = None
        self._prev_hand_pt = None
        self._smoothed_hand_pt = None
        self._hand_yaw = 0.0
        self._hand_pitch = 0.0

    def start(self) -> bool:
        """Starts the vision capture worker thread."""
        if not CV2_AVAILABLE:
            self._state = VisionTrackerState.ERROR_NO_CV2
            print(
                "[AirCursor Vision] OpenCV (cv2) or NumPy is not installed. "
                "Install with: pip install opencv-python numpy"
            )
            return False

        if self._state == VisionTrackerState.RUNNING:
            return True

        self._stop_event.clear()
        self._paused = False
        self._state = VisionTrackerState.STARTING

        # Pre-flight camera check
        cap = cv2.VideoCapture(self.settings.camera_index)
        if not cap.isOpened():
            cap.release()
            self._state = VisionTrackerState.ERROR_NO_CAMERA
            print(f"[AirCursor Vision] Unable to open camera index {self.settings.camera_index}.")
            return False
        cap.release()

        self._thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="AirCursor-VisionTracker"
        )
        self._thread.start()
        self._state = VisionTrackerState.RUNNING
        return True

    def stop(self) -> None:
        """Stops the worker thread and releases webcam resources."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._state = VisionTrackerState.STOPPED

    def pause(self) -> None:
        """Pauses frame processing while keeping camera open."""
        self._paused = True
        self._state = VisionTrackerState.PAUSED

    def resume(self) -> None:
        """Resumes frame processing."""
        self._paused = False
        self._state = VisionTrackerState.RUNNING

    def _worker_loop(self) -> None:
        """Continuous camera capture loop with frame throttling and graceful error handling."""
        cap = cv2.VideoCapture(self.settings.camera_index)
        if not cap.isOpened():
            self._state = VisionTrackerState.ERROR_NO_CAMERA
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.settings.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.settings.frame_height)
        self._state = VisionTrackerState.RUNNING

        frame_interval = 1.0 / max(self.settings.target_fps, 5.0)

        try:
            while not self._stop_event.is_set():
                t_start = time.perf_counter()

                ret, frame = cap.read()
                if not ret or frame is None:
                    time.sleep(0.01)
                    continue

                if not self._paused:
                    now = time.time()
                    result = self.process_frame(frame, timestamp=now)

                    if result.motion_sample and self.on_sample:
                        self.on_sample(result.motion_sample)

                    if result.hand_gesture != HandGesture.NONE and self.on_gesture:
                        self.on_gesture(result.hand_gesture, result)

                    if self.on_frame:
                        self.on_frame(result)

                    # Update FPS metrics
                    self.frames_processed += 1
                    self._fps_count += 1
                    if now - self._fps_timer >= 1.0:
                        self.last_fps = self._fps_count / (now - self._fps_timer)
                        self._fps_count = 0
                        self._fps_timer = now

                # Throttle frame rate to achieve target FPS with minimal CPU load
                elapsed = time.perf_counter() - t_start
                sleep_sec = frame_interval - elapsed
                if sleep_sec > 0.001:
                    time.sleep(sleep_sec)

        except Exception as e:
            print(f"[AirCursor Vision] Worker exception: {e}")
        finally:
            cap.release()
            self._state = VisionTrackerState.STOPPED

    def process_frame(
        self, frame: Any, timestamp: Optional[float] = None
    ) -> VisionFrameResult:
        """Processes a single image frame (BGR numpy array).

        Can be called directly for offline video analysis or unit testing.
        """
        now = timestamp if timestamp is not None else time.time()

        if not CV2_AVAILABLE or frame is None:
            return VisionFrameResult(timestamp=now)

        if self.settings.mirror:
            frame = cv2.flip(frame, 1)

        h, w = frame.shape[:2]
        result = VisionFrameResult(timestamp=now)

        # -------------------------------------------------------------
        # 1. Head / Face & Nose Pose Tracking
        # -------------------------------------------------------------
        face_box = None
        face_sample = None
        if self.settings.enable_head_tracking:
            face_box = self._detect_face(frame)
            if face_box is not None:
                fx, fy, fw, fh = face_box
                cx = float(fx + fw / 2.0)
                cy = float(fy + fh / 2.0)

                # Nose tip is typically ~50% horizontally, ~55% vertically within the face rect
                nx = float(fx + fw * 0.5)
                ny = float(fy + fh * 0.55)

                result.face_detected = True
                result.face_box = face_box
                result.face_center = (cx, cy)
                result.nose_point = (nx, ny)

                # Initialize neutral calibration point on first detection
                if self._neutral_center is None:
                    self._neutral_center = (cx, cy)

                ncx, ncy = self._neutral_center

                # Normalized offsets from neutral reference center
                norm_dx = (cx - ncx) / max(w * 0.5, 1.0)
                norm_dy = (cy - ncy) / max(h * 0.5, 1.0)

                # Deadzone check
                if abs(norm_dx) < self.settings.deadzone:
                    norm_dx = 0.0
                if abs(norm_dy) < self.settings.deadzone:
                    norm_dy = 0.0

                # Map normalized offsets to pitch and yaw angles in radians
                yaw_rad = norm_dx * self.settings.yaw_sensitivity
                pitch_rad = -norm_dy * self.settings.pitch_sensitivity
                roll_rad = 0.0

                face_sample = MotionSample(
                    timestamp=now,
                    yaw=float(yaw_rad),
                    pitch=float(pitch_rad),
                    roll=float(roll_rad),
                )
                self._last_face_center = (cx, cy)

        # -------------------------------------------------------------
        # 2. Hand Presence, Gesture Recognition & Motion Tracking
        # -------------------------------------------------------------
        hand_sample = None
        if self.settings.enable_hand_gestures or getattr(self.settings, "enable_hand_tracking", True):
            hand_contour, hierarchy = self._detect_hand_contour(frame, face_box=face_box)
            if hand_contour is not None and len(hand_contour) >= 5:
                hx, hy, hw, hh = cv2.boundingRect(hand_contour)
                result.hand_detected = True
                result.hand_box = (hx, hy, hw, hh)

                # Locate fingertip (highest point / minimum Y) and hand center
                topmost = tuple(hand_contour[hand_contour[:, :, 1].argmin()][0])
                hand_tip = (float(topmost[0]), float(topmost[1]))
                hand_center = (float(hx + hw / 2.0), float(hy + hh / 2.0))
                result.hand_tip = hand_tip
                result.hand_center = hand_center

                gesture, finger_count, conf = self.classify_hand_contour(
                    hand_contour, hierarchy=hierarchy, frame_shape=(h, w), now=now
                )
                result.hand_gesture = gesture
                result.finger_count = finger_count
                result.confidence = conf

                # Generate Hand Motion Sample for cursor movement
                if getattr(self.settings, "enable_hand_tracking", True):
                    # Tracking point: blend fingertip and centroid for stability and responsiveness
                    ctrl_x = hand_tip[0] * 0.7 + hand_center[0] * 0.3
                    ctrl_y = hand_tip[1] * 0.7 + hand_center[1] * 0.3
                    ctrl_pt = (ctrl_x, ctrl_y)

                    if self._neutral_hand is None or (now - self._last_hand_time > 0.4):
                        self._neutral_hand = ctrl_pt
                        self._prev_hand_pt = ctrl_pt
                        self._smoothed_hand_pt = ctrl_pt
                        self._hand_yaw = 0.0
                        self._hand_pitch = 0.0

                    alpha = 0.65
                    sx = alpha * ctrl_x + (1.0 - alpha) * self._smoothed_hand_pt[0]
                    sy = alpha * ctrl_y + (1.0 - alpha) * self._smoothed_hand_pt[1]
                    self._smoothed_hand_pt = (sx, sy)

                    p_sx, p_sy = self._prev_hand_pt
                    dx = sx - p_sx
                    dy = sy - p_sy
                    self._prev_hand_pt = (sx, sy)

                    norm_dx = dx / max(w * 0.5, 1.0)
                    norm_dy = dy / max(h * 0.5, 1.0)

                    if abs(norm_dx) < self.settings.deadzone * 0.3:
                        norm_dx = 0.0
                    if abs(norm_dy) < self.settings.deadzone * 0.3:
                        norm_dy = 0.0

                    hand_sens = getattr(self.settings, "hand_sensitivity", 2.5)

                    # In mirrored frame:
                    # Move hand right (dx > 0) -> target cursor velocity right (dx > 0) -> rate.yaw < 0 -> delta_yaw < 0
                    # Move hand left (dx < 0) -> target cursor velocity left (dx < 0) -> rate.yaw > 0 -> delta_yaw > 0
                    # Move hand up (dy < 0) -> target cursor velocity up (dy < 0) -> rate.pitch > 0 -> delta_pitch > 0
                    # Move hand down (dy > 0) -> target cursor velocity down (dy > 0) -> rate.pitch < 0 -> delta_pitch < 0
                    delta_yaw = -norm_dx * self.settings.yaw_sensitivity * hand_sens
                    delta_pitch = -norm_dy * self.settings.pitch_sensitivity * hand_sens

                    self._hand_yaw += delta_yaw
                    self._hand_pitch += delta_pitch

                    hand_sample = MotionSample(
                        timestamp=now,
                        yaw=float(self._hand_yaw),
                        pitch=float(self._hand_pitch),
                        roll=0.0,
                    )
                    self._last_hand_time = now

        # -------------------------------------------------------------
        # 3. Arbitrate Output Motion Sample: Hand Priority over Head
        # -------------------------------------------------------------
        if hand_sample is not None and result.hand_detected:
            # Active hand tracking moves cursor directly
            result.motion_sample = hand_sample
            result.tracking_mode_used = "hand"
        elif face_sample is not None and result.face_detected:
            # When hand is resting or out of view, head pose moves cursor
            result.motion_sample = face_sample
            result.tracking_mode_used = "head"
        else:
            result.tracking_mode_used = "none"

        return result

    def _detect_face(self, frame: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """Detects the primary face bounding box via Haar Cascades or Skin Color Morphology."""
        h, w = frame.shape[:2]

        # Method A: Haar Cascade if loaded
        if self._face_cascade is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
            )
            if len(faces) > 0:
                largest = max(faces, key=lambda b: b[2] * b[3])
                return (int(largest[0]), int(largest[1]), int(largest[2]), int(largest[3]))

        # Method B: Robust Skin Color blob in upper region of frame
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        skin_mask = cv2.inRange(ycrcb, np.array([0, 133, 77]), np.array([255, 173, 127]))

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(skin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        min_face_area = (w * h) * 0.015
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_face_area:
                continue
            bx, by, bw, bh = cv2.boundingRect(cnt)
            aspect = bw / float(bh)
            cy = by + bh * 0.5

            # If there are deep defects (extended fingers), this is a hand, NOT a face!
            defects_count = self._count_deep_defects(cnt, bh)
            if defects_count > 0:
                continue

            # If only one contour exists and is located in the lower region, it's a hand
            if len(contours) == 1 and cy > (h * 0.55):
                continue

            if 0.4 <= aspect <= 1.5 and cy < (h * 0.75):
                candidates.append((area, by, (bx, by, bw, bh)))

        if candidates:
            # Sort primarily by uppermost position (faces are above hands), then by area
            candidates.sort(key=lambda item: (item[1], -item[0]))
            return candidates[0][2]

        return None

    def _count_deep_defects(self, cnt: np.ndarray, bh: int) -> int:
        """Counts prominent finger gaps using convexity defects."""
        hull_idx = cv2.convexHull(cnt, returnPoints=False)
        if hull_idx is None or len(hull_idx) <= 3 or len(cnt) <= 3:
            return 0
        try:
            defects = cv2.convexityDefects(cnt, hull_idx)
            if defects is None:
                return 0
            count = 0
            for s, e, f, d in defects.reshape(-1, 4):
                depth = d / 256.0
                if depth > (bh * 0.10) and depth > 8.0:
                    count += 1
            return count
        except Exception:
            return 0

    def _detect_hand_contour(
        self, frame: np.ndarray, face_box: Optional[Tuple[int, int, int, int]] = None
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Detects hand contour by segmenting skin regions and masking out the face."""
        h, w = frame.shape[:2]

        # Generate skin mask with dual YCrCb + HSV color spaces for lighting tolerance
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        mask_ycrcb = cv2.inRange(ycrcb, np.array([0, 130, 75]), np.array([255, 180, 135]))

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask_hsv1 = cv2.inRange(hsv, np.array([0, 15, 35]), np.array([28, 255, 255]))
        mask_hsv2 = cv2.inRange(hsv, np.array([165, 15, 35]), np.array([180, 255, 255]))
        mask_hsv = cv2.bitwise_or(mask_hsv1, mask_hsv2)

        skin_mask = cv2.bitwise_and(mask_ycrcb, mask_hsv)
        if cv2.countNonZero(skin_mask) < (w * h * 0.005):
            skin_mask = mask_ycrcb

        # If a face was detected, zero out the face region with a margin so it isn't mistaken for a hand
        if face_box is not None:
            fx, fy, fw, fh = face_box
            margin_x = int(fw * 0.2)
            margin_y = int(fh * 0.2)
            x0 = max(0, fx - margin_x)
            y0 = max(0, fy - margin_y)
            x1 = min(w, fx + fw + margin_x)
            y1 = min(h, fy + fh + margin_y)
            skin_mask[y0:y1, x0:x1] = 0

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_OPEN, kernel, iterations=1)
        skin_mask = cv2.morphologyEx(skin_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        # RETR_CCOMP retrieves external contours and inner holes (valuable for pinch loops)
        contours, hierarchy = cv2.findContours(skin_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, None

        min_hand_area = (w * h) * 0.008
        hand_candidates = []
        for i, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            if area > min_hand_area:
                hand_candidates.append((area, cnt, i))

        if not hand_candidates:
            return None, None

        hand_candidates.sort(key=lambda item: item[0], reverse=True)
        return hand_candidates[0][1], hierarchy

    def classify_hand_contour(
        self,
        contour: np.ndarray,
        hierarchy: Optional[np.ndarray] = None,
        frame_shape: Tuple[int, int] = (480, 640),
        now: Optional[float] = None,
    ) -> Tuple[HandGesture, int, float]:
        """Classifies hand gesture from contour geometry:

        - Closed Fist: Solidity > 0.82, 0 deep finger defects
        - Peace Sign: 1 deep defect between index and middle finger, 2 fingers extended
        - Open Palm: 3+ deep defects, solidity < 0.75, 4-5 fingers extended
        - Pinch: Index tip touches thumb tip (inner hole loop or minimal pinch distance)
        - Swipe Up / Down: Rapid vertical centroid movement
        """
        current_time = now if now is not None else time.time()
        area = cv2.contourArea(contour)
        if area <= 0:
            return HandGesture.NONE, 0, 0.0

        bx, by, bw, bh = cv2.boundingRect(contour)
        cx = bx + bw / 2.0
        cy = by + bh / 2.0

        # Maintain vertical centroid history for swipe detection
        self._hand_history.append((current_time, cy))
        # Keep recent 0.35s window
        self._hand_history = [
            (t, y) for (t, y) in self._hand_history if (current_time - t) <= 0.35
        ]

        # Check Swipe Hand Up / Down gesture
        if len(self._hand_history) >= 3:
            dt = self._hand_history[-1][0] - self._hand_history[0][0]
            if dt >= 0.05:
                dy = self._hand_history[-1][1] - self._hand_history[0][1]
                velocity_y = dy / dt  # Pixels per second
                if velocity_y < -self.settings.swipe_threshold:
                    if self._check_cooldown(current_time, HandGesture.SWIPE_UP):
                        return HandGesture.SWIPE_UP, 0, 0.9
                elif velocity_y > self.settings.swipe_threshold:
                    if self._check_cooldown(current_time, HandGesture.SWIPE_DOWN):
                        return HandGesture.SWIPE_DOWN, 0, 0.9

        # Convex hull and solidity
        hull_pts = cv2.convexHull(contour, returnPoints=True)
        hull_area = cv2.contourArea(hull_pts)
        solidity = float(area / max(hull_area, 1.0))

        # Check for inner loop / hole (pinch circle formation)
        has_inner_hole = False
        if hierarchy is not None and len(hierarchy.shape) >= 2:
            flat_hier = hierarchy.reshape(-1, 4)
            for h_entry in flat_hier:
                # If an entry has a parent or inner child of appropriate area
                if h_entry[3] >= 0:
                    has_inner_hole = True
                    break

        # Calculate convexity defects
        hull_indices = cv2.convexHull(contour, returnPoints=False)
        deep_defects = 0
        defect_tips: List[Tuple[int, int]] = []

        if hull_indices is not None and len(hull_indices) > 3 and len(contour) > 3:
            try:
                defects = cv2.convexityDefects(contour, hull_indices)
                if defects is not None:
                    flat_defects = defects.reshape(-1, 4)
                    for s_idx, e_idx, f_idx, d_val in flat_defects:
                        depth = d_val / 256.0
                        pt_start = contour[s_idx][0]
                        pt_end = contour[e_idx][0]
                        pt_far = contour[f_idx][0]

                        # Calculate defect angle
                        a = math.hypot(pt_end[0] - pt_start[0], pt_end[1] - pt_start[1])
                        b = math.hypot(pt_far[0] - pt_start[0], pt_far[1] - pt_start[1])
                        c = math.hypot(pt_end[0] - pt_far[0], pt_end[1] - pt_far[1])

                        if b * c > 0:
                            cos_angle = max(-1.0, min(1.0, (b * b + c * c - a * a) / (2.0 * b * c)))
                            angle = math.acos(cos_angle)
                            # Deep acute defect between extended fingers
                            if angle <= math.pi * 0.55 and depth > (bh * 0.12):
                                deep_defects += 1
                                defect_tips.append((int(pt_start[0]), int(pt_start[1])))
            except Exception:
                pass

        # Estimate extended fingers from deep defects
        # 0 defects = 0-1 finger; 1 defect = 2 fingers (peace sign); 3-4 defects = 4-5 fingers (open palm)
        extended_fingers = deep_defects + 1 if deep_defects > 0 else (0 if solidity > 0.80 else 1)

        # 1. Pinch / Index Tap: Inner hole detected OR index meets thumb
        if has_inner_hole or self._is_pinch_contour(contour, bx, by, bw, bh):
            if self._check_cooldown(current_time, HandGesture.PINCH):
                return HandGesture.PINCH, 1, 0.92

        # 2. Closed Fist: High solidity, minimal defects (no inner holes)
        if solidity >= 0.82 and deep_defects == 0 and not has_inner_hole:
            if self._check_cooldown(current_time, HandGesture.CLOSED_FIST):
                return HandGesture.CLOSED_FIST, 0, 0.95

        # 3. Peace Sign / Two Fingers Up: Exactly 1 deep finger gap, elongated vertical profile
        if deep_defects == 1 or extended_fingers == 2:
            if self._check_cooldown(current_time, HandGesture.PEACE_SIGN):
                return HandGesture.PEACE_SIGN, 2, 0.88

        # 4. Open Palm: 3 or more defects, low solidity, all fingers spread
        if deep_defects >= 3 or (extended_fingers >= 4 and solidity < 0.75):
            if self._check_cooldown(current_time, HandGesture.OPEN_PALM):
                return HandGesture.OPEN_PALM, 5, 0.94

        # Default fallback: If solidity is moderate and extended fingers >= 3, treat as open palm
        if extended_fingers >= 3:
            return HandGesture.OPEN_PALM, extended_fingers, 0.70

        return HandGesture.NONE, extended_fingers, 0.50

    def _is_pinch_contour(
        self, contour: np.ndarray, bx: int, by: int, bw: int, bh: int
    ) -> bool:
        """Heuristic check for pinch gesture when inner hole is subtle."""
        area = cv2.contourArea(contour)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = float(area / max(hull_area, 1.0))
        if solidity >= 0.82:
            return False

        # Find extreme leftmost and uppermost contour points
        leftmost = tuple(contour[contour[:, :, 0].argmin()][0])
        topmost = tuple(contour[contour[:, :, 1].argmin()][0])
        if leftmost == topmost:
            return False

        tip_distance = math.hypot(leftmost[0] - topmost[0], leftmost[1] - topmost[1])
        diag = math.hypot(bw, bh)
        return diag > 0 and 0.02 < (tip_distance / diag) < 0.22

    def _check_cooldown(self, now: float, gesture: HandGesture) -> bool:
        """Debounces rapid gesture re-triggering."""
        if gesture == self._last_gesture and (now - self._last_gesture_time) < self.settings.gesture_cooldown:
            return False
        self._last_gesture = gesture
        self._last_gesture_time = now
        return True
