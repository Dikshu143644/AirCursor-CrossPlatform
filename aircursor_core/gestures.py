"""Deliberate head gesture detection: Nod, Shake, and Tilt.

Matches AirCursor/Sources/AirCursorCore/Gestures.swift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from .math_util import AngleMath
from .motion import MotionDifferentiator, MotionSample

if TYPE_CHECKING:
    from .settings import GestureSettings


class HeadGesture(str, Enum):
    """Supported head gestures. Matches Swift HeadGesture enum."""

    NOD = "nod"
    SHAKE = "shake"
    TILT_LEFT = "tiltLeft"
    TILT_RIGHT = "tiltRight"

    # CamelCase aliases matching Swift enum cases
    nod = "nod"
    shake = "shake"
    tiltLeft = "tiltLeft"
    tiltRight = "tiltRight"


@dataclass
class GestureEvent:
    """Deliberate head movement event with timing and magnitude.

    Matches Swift GestureEvent struct.
    """

    gesture: HeadGesture
    start_time: float
    time: float
    magnitude: float

    # CamelCase property alias
    @property
    def startTime(self) -> float:
        return self.start_time


@dataclass
class _Pose:
    t: float
    yaw: float  # degrees, unwrapped (continuous)
    pitch: float  # degrees


class GestureDetector:
    """Detects deliberate head gestures from the head's angle over time.

    Shape-based detection is far more reliable than speed thresholds: AirPods report
    ~25 samples/s, so the peak speed of a natural nod is often missed, but its shape —
    dip a few degrees, come back — always shows up.

    - Nod: pitch leaves its starting angle by >= nodAmplitude, then returns most of
      the way, within nodWindow, with little sideways motion. Either direction.
    - Shake: yaw swings back and forth >= shakeAmplitude at least four times within
      shakeWindow, with little vertical motion.
    - Tilt: roll held beyond tiltAngle from the neutral posture for tiltHold.
      Fires once, then re-arms when the head returns toward neutral.
    """

    RE_NEUTRAL_AFTER: float = 4.0
    reNeutralAfter: float = RE_NEUTRAL_AFTER

    NOD_RETURN_FRACTION: float = 0.65
    nodReturnFraction: float = NOD_RETURN_FRACTION

    CROSS_AXIS_ALLOWANCE: float = 0.6
    crossAxisAllowance: float = CROSS_AXIS_ALLOWANCE

    MIN_NOD_SPEED: float = 30.0
    minNodSpeed: float = MIN_NOD_SPEED

    MIN_SHAKE_SPEED: float = 80.0
    minShakeSpeed: float = MIN_SHAKE_SPEED

    SHAKE_SWINGS: int = 4
    shakeSwings: int = SHAKE_SWINGS

    HISTORY_SPAN: float = 1.5
    historySpan: float = HISTORY_SPAN

    SETTLED_SPEED: float = 25.0
    settledSpeed: float = SETTLED_SPEED

    SETTLED_FOR: float = 0.15
    settledFor: float = SETTLED_FOR

    def __init__(self, settings: Optional[GestureSettings] = None):
        if settings is None:
            from .settings import GestureSettings

            settings = GestureSettings()
        self.settings: GestureSettings = settings

        self._history: List[_Pose] = []
        self._last_raw_yaw: Optional[float] = None
        self._cooldown_until: float = -float("inf")
        self._awaiting_still: bool = False
        self._still_since: Optional[float] = None
        self._roll_baseline: Optional[float] = None
        self._tilt_candidate: Optional[Tuple[HeadGesture, float]] = None
        self._tilt_latched: bool = False
        self._off_neutral_since: Optional[float] = None

    def relative_roll(self, roll_degrees: float) -> float:
        """Current roll relative to neutral, in degrees (for live display)."""
        if self._roll_baseline is None:
            return 0.0
        return AngleMath.wrapped_delta_degrees(roll_degrees, self._roll_baseline)

    relativeRoll = relative_roll

    def reset_tilt_baseline(self, to: Optional[float] = None) -> None:
        """Resets the roll baseline posture."""
        self._roll_baseline = to
        self._off_neutral_since = None
        self._tilt_candidate = None
        self._tilt_latched = False

    resetTiltBaseline = reset_tilt_baseline

    def reset(self) -> None:
        """Resets all detector state."""
        self._history.clear()
        self._last_raw_yaw = None
        self._cooldown_until = -float("inf")
        self._awaiting_still = False
        self._still_since = None
        self.reset_tilt_baseline()

    def process(
        self, sample: MotionSample, enabled: Optional[Set[HeadGesture]] = None
    ) -> Optional[GestureEvent]:
        """Feed every motion sample (angles in radians, as reported by sensor)."""
        if enabled is None:
            enabled = set(HeadGesture)

        t = sample.timestamp
        raw_yaw = AngleMath.degrees(sample.yaw)
        pitch = AngleMath.degrees(sample.pitch)
        roll = AngleMath.degrees(sample.roll)

        # Unwrap yaw so a turn across ±180° stays continuous; drop history after gaps.
        if self._history:
            last = self._history[-1]
            if (t - last.t > MotionDifferentiator.MAX_INTERVAL) or (t <= last.t):
                self._history.clear()
                self._last_raw_yaw = None

        if self._last_raw_yaw is not None and self._history:
            yaw = self._history[-1].yaw + AngleMath.wrapped_delta_degrees(raw_yaw, self._last_raw_yaw)
        else:
            yaw = raw_yaw

        self._last_raw_yaw = raw_yaw
        self._history.append(_Pose(t=t, yaw=yaw, pitch=pitch))

        if self._history and (t - self._history[0].t > self.HISTORY_SPAN):
            self._history = [p for p in self._history if t - p.t <= self.HISTORY_SPAN]

        tilt = self._update_tilt(roll_degrees=roll, time=t, enabled=enabled)

        if self._awaiting_still:
            speed = (
                self._peak_speed_between(self._history[-2], self._history[-1])
                if len(self._history) >= 2
                else 0.0
            )
            if speed < self.SETTLED_SPEED:
                if self._still_since is None:
                    self._still_since = t
                if t - self._still_since >= self.SETTLED_FOR:
                    self._awaiting_still = False
                    self._still_since = None
                    # Start fresh from the settled pose.
                    self._history = self._history[-1:]
            else:
                self._still_since = None
            return None

        if t < self._cooldown_until:
            return None

        if HeadGesture.NOD in enabled:
            e = self._detect_nod(now=t)
            if e is not None:
                return self._fire(e)

        if HeadGesture.SHAKE in enabled:
            e = self._detect_shake(now=t)
            if e is not None:
                return self._fire(e)

        if tilt is not None:
            return self._fire(tilt)

        return None

    def _fire(self, event: GestureEvent) -> GestureEvent:
        self._cooldown_until = event.time + self.settings.cooldown
        self._awaiting_still = True
        self._still_since = None
        self._tilt_candidate = None
        return event

    def _peak_speed_between(self, a: _Pose, b: _Pose) -> float:
        if b.t <= a.t:
            return 0.0
        return max(abs(b.pitch - a.pitch), abs(b.yaw - a.yaw)) / (b.t - a.t)

    def _peak_speed(self, poses: List[_Pose], axis: str) -> float:
        best = 0.0
        prev: Optional[_Pose] = None
        for p in poses:
            if prev is not None and p.t > prev.t:
                diff = abs(getattr(p, axis) - getattr(prev, axis))
                speed = diff / (p.t - prev.t)
                if speed > best:
                    best = speed
            prev = p
        return best

    def _detect_nod(self, now: float) -> Optional[GestureEvent]:
        if len(self._history) < 3:
            return None
        current = self._history[-1]
        last_index = len(self._history) - 1

        # Try every start point in the window, oldest first (earliest start = best cursor-restore point).
        for j in range(last_index - 1):
            if now - self._history[j].t > self.settings.nod_window:
                continue
            start = self._history[j]
            extreme = 0.0
            extreme_index = j
            for k in range(j + 1, last_index):
                d = self._history[k].pitch - start.pitch
                if abs(d) > abs(extreme):
                    extreme = d
                    extreme_index = k
            depth = abs(extreme)
            if depth < self.settings.nod_amplitude or extreme_index <= j:
                continue

            remaining = abs(current.pitch - start.pitch)
            if remaining > depth * (1.0 - self.NOD_RETURN_FRACTION):
                continue

            segment = self._history[j : last_index + 1]
            yaws = [p.yaw for p in segment]
            yaw_range = max(yaws) - min(yaws)
            if yaw_range > max(depth * self.CROSS_AXIS_ALLOWANCE, 3.0):
                continue
            if self._peak_speed(segment, "pitch") < self.MIN_NOD_SPEED:
                continue

            return GestureEvent(
                gesture=HeadGesture.NOD,
                start_time=start.t,
                time=now,
                magnitude=depth,
            )
        return None

    def _detect_shake(self, now: float) -> Optional[GestureEvent]:
        window = [p for p in self._history if now - p.t <= self.settings.shake_window]
        if len(window) < 4:
            return None
        first = window[0]

        anchor = first.yaw
        direction = 0
        swings = 0
        largest = 0.0

        for pose in window[1:]:
            d = pose.yaw - anchor
            if direction == 0:
                if abs(d) >= self.settings.shake_amplitude:
                    direction = 1 if d > 0 else -1
                    swings = 1
                    largest = abs(d)
                    anchor = pose.yaw
            elif direction == 1:
                if pose.yaw > anchor:
                    anchor = pose.yaw
                elif anchor - pose.yaw >= self.settings.shake_amplitude:
                    swings += 1
                    largest = max(largest, anchor - pose.yaw)
                    direction = -1
                    anchor = pose.yaw
            else:
                if pose.yaw < anchor:
                    anchor = pose.yaw
                elif pose.yaw - anchor >= self.settings.shake_amplitude:
                    swings += 1
                    largest = max(largest, pose.yaw - anchor)
                    direction = 1
                    anchor = pose.yaw

        if swings < self.SHAKE_SWINGS:
            return None

        pitches = [p.pitch for p in window]
        pitch_range = max(pitches) - min(pitches)
        if pitch_range > largest * self.CROSS_AXIS_ALLOWANCE:
            return None

        if self._peak_speed(window, "yaw") < self.MIN_SHAKE_SPEED:
            return None

        return GestureEvent(
            gesture=HeadGesture.SHAKE,
            start_time=first.t,
            time=now,
            magnitude=largest,
        )

    def _update_tilt(
        self, roll_degrees: float, time: float, enabled: Set[HeadGesture]
    ) -> Optional[GestureEvent]:
        if self._roll_baseline is None:
            self._roll_baseline = roll_degrees
            return None

        base = self._roll_baseline
        rel = AngleMath.wrapped_delta_degrees(roll_degrees, base)

        if abs(rel) < self.settings.tilt_angle * 0.5:
            # Near neutral: slowly follow posture changes and re-arm.
            self._roll_baseline = base + rel * 0.02
            self._tilt_latched = False
            self._tilt_candidate = None
            self._off_neutral_since = None
            return None

        if self._off_neutral_since is not None:
            if time - self._off_neutral_since > self.RE_NEUTRAL_AFTER:
                self._roll_baseline = roll_degrees
                self._off_neutral_since = None
                self._tilt_candidate = None
                self._tilt_latched = False
                return None
        else:
            self._off_neutral_since = time

        if (
            HeadGesture.TILT_LEFT not in enabled and HeadGesture.TILT_RIGHT not in enabled
        ) or self._tilt_latched:
            return None

        if abs(rel) < self.settings.tilt_angle:
            self._tilt_candidate = None
            return None

        is_right = (rel > 0) != self.settings.swap_tilt_direction
        gesture = HeadGesture.TILT_RIGHT if is_right else HeadGesture.TILT_LEFT

        if self._tilt_candidate is None or self._tilt_candidate[0] != gesture:
            self._tilt_candidate = (gesture, time)
            return None

        candidate_gesture, candidate_since = self._tilt_candidate
        if time - candidate_since < self.settings.tilt_hold:
            return None

        self._tilt_latched = True
        self._tilt_candidate = None

        if gesture not in enabled or time < self._cooldown_until:
            return None

        return GestureEvent(
            gesture=gesture,
            start_time=candidate_since,
            time=time,
            magnitude=abs(rel),
        )
