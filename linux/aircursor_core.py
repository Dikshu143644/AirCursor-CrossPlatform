"""
AirCursor Core - Pure Python Port of the AirCursor Mathematical & Interaction Engine.
Maintains 100% mathematical fidelity with the macOS Swift reference implementation.
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


# ==============================================================================
# Math Primitives
# ==============================================================================

@dataclass
class Vec2:
    """2D Vector for pointer coordinates, displacement, and velocity."""
    x: float = 0.0
    y: float = 0.0

    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def distance(self, other: Vec2) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def __add__(self, other: Vec2) -> Vec2:
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def __iadd__(self, other: Vec2) -> Vec2:
        self.x += other.x
        self.y += other.y
        return self

    def __isub__(self, other: Vec2) -> Vec2:
        self.x -= other.x
        self.y -= other.y
        return self

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


class AngleMath:
    """Angle manipulation utilities (degrees and radians)."""
    
    @staticmethod
    def wrapped_delta(a: float, b: float) -> float:
        """Shortest signed difference a - b in radians, wrapped into (-pi, pi]."""
        return math.atan2(math.sin(a - b), math.cos(a - b))

    @staticmethod
    def wrapped_delta_degrees(a: float, b: float) -> float:
        """Shortest signed difference a - b in degrees, wrapped into (-180, 180]."""
        return AngleMath.degrees(AngleMath.wrapped_delta(AngleMath.radians(a), AngleMath.radians(b)))

    @staticmethod
    def degrees(rad: float) -> float:
        return rad * 180.0 / math.pi

    @staticmethod
    def radians(deg: float) -> float:
        return deg * math.pi / 180.0


# ==============================================================================
# Motion Readings & Differentiation
# ==============================================================================

@dataclass
class MotionSample:
    """One attitude reading from headphones or IMU. Angles in radians, timestamp in seconds."""
    timestamp: float
    yaw: float
    pitch: float
    roll: float


@dataclass
class AngularRates:
    """Angular velocities in degrees per second, derived from consecutive samples."""
    timestamp: float
    yaw: float
    pitch: float
    roll: float


class MotionDifferentiator:
    """
    Turns a stream of attitude samples into angular rates, handling wrap-around
    and rejecting gaps so they never produce a cursor jump.
    """
    MIN_INTERVAL: float = 0.002
    MAX_INTERVAL: float = 0.25

    def __init__(self) -> None:
        self.last: Optional[MotionSample] = None

    def reset(self) -> None:
        self.last = None

    def push(self, sample: MotionSample) -> Optional[AngularRates]:
        previous = self.last
        self.last = sample
        if previous is None:
            return None

        dt = sample.timestamp - previous.timestamp
        if dt < self.MIN_INTERVAL or dt > self.MAX_INTERVAL:
            return None

        return AngularRates(
            timestamp=sample.timestamp,
            yaw=AngleMath.degrees(AngleMath.wrapped_delta(sample.yaw, previous.yaw)) / dt,
            pitch=AngleMath.degrees(AngleMath.wrapped_delta(sample.pitch, previous.pitch)) / dt,
            roll=AngleMath.degrees(AngleMath.wrapped_delta(sample.roll, previous.roll)) / dt,
        )


# ==============================================================================
# Pointer Velocity Mapping & Smoothing
# ==============================================================================

@dataclass
class PointerSettings:
    sensitivity: float = 1.0
    acceleration: float = 0.6
    deadzone: float = 3.0  # deg/s below which cursor holds still (filters tremor)
    smoothing: float = 0.55  # 0 = raw, 0.95 = very smooth
    invert_horizontal: bool = False
    invert_vertical: bool = False
    scroll_speed: float = 1.0
    invert_scroll: bool = False


class PointerMapper:
    """Maps head angular velocity to cursor velocity."""
    PIXELS_PER_DEGREE: float = 28.0

    @classmethod
    def axis_speed(cls, rate: float, settings: PointerSettings) -> float:
        magnitude = abs(rate)
        if magnitude <= settings.deadzone:
            return 0.0
        effective = magnitude - settings.deadzone
        # Gentle, bounded acceleration: slow head = precise, fast head = travel
        boost = 1.0 + settings.acceleration * min(effective / 60.0, 3.0)
        speed = effective * cls.PIXELS_PER_DEGREE * settings.sensitivity * boost
        return -speed if rate < 0 else speed

    @classmethod
    def cursor_velocity(cls, rates: AngularRates, settings: PointerSettings) -> Vec2:
        """
        Cursor velocity in screen points/s (origin top-left, +y is down).
        Turning head left (+yaw) moves cursor left; looking up (+pitch) moves it up.
        """
        dx = -cls.axis_speed(rates.yaw, settings)
        dy = -cls.axis_speed(rates.pitch, settings)
        if settings.invert_horizontal:
            dx = -dx
        if settings.invert_vertical:
            dy = -dy
        return Vec2(dx, dy)


class PointerSmoother:
    """
    Interpolates/smoothes cursor velocities between head samples (~25-100Hz)
    and frame refresh (60-144Hz) using frame-rate independent exponential smoothing.
    """
    STALE_AFTER: float = 0.12

    def __init__(self) -> None:
        self.velocity = Vec2(0.0, 0.0)
        self.target = Vec2(0.0, 0.0)
        self.target_time = -math.inf

    def set_target(self, v: Vec2, timestamp: float) -> None:
        self.target = v
        self.target_time = timestamp

    def reset(self) -> None:
        self.velocity = Vec2(0.0, 0.0)
        self.target = Vec2(0.0, 0.0)
        self.target_time = -math.inf

    def step(self, now: float, dt: float, smoothing: float) -> Vec2:
        if dt <= 0:
            return Vec2(0.0, 0.0)
        goal = Vec2(0.0, 0.0) if (now - self.target_time) > self.STALE_AFTER else self.target
        s = min(max(smoothing, 0.0), 0.97)
        # Frame-rate independent exponential smoothing (s is the per-1/60s retention)
        alpha = 1.0 - math.pow(s, dt * 60.0)
        self.velocity += (goal - self.velocity) * alpha
        if goal.x == 0.0 and goal.y == 0.0 and self.velocity.length < 2.0:
            self.velocity = Vec2(0.0, 0.0)
        return self.velocity * dt


class CursorHistory:
    """
    Ring buffer of recent cursor positions, allowing gesture execution to click
    where the user was looking before the gesture motion perturbed the cursor.
    """
    def __init__(self, capacity: int = 360) -> None:
        self.capacity = max(1, capacity)
        self.buffer: List[Tuple[float, Vec2]] = []
        self.head = 0

    def append(self, position: Vec2, timestamp: float) -> None:
        if len(self.buffer) < self.capacity:
            self.buffer.append((timestamp, Vec2(position.x, position.y)))
        else:
            self.buffer[self.head] = (timestamp, Vec2(position.x, position.y))
            self.head = (self.head + 1) % self.capacity

    def clear(self) -> None:
        self.buffer.clear()
        self.head = 0

    def position_at(self, timestamp: float) -> Optional[Vec2]:
        if not self.buffer:
            return None
        if len(self.buffer) < self.capacity:
            ordered = self.buffer
        else:
            ordered = self.buffer[self.head:] + self.buffer[:self.head]

        best = ordered[0][1]
        for t, pos in ordered:
            if t <= timestamp:
                best = pos
            else:
                break
        return Vec2(best.x, best.y)


# ==============================================================================
# Gestures & Detection
# ==============================================================================

class HeadGesture(str, Enum):
    NOD = "nod"
    SHAKE = "shake"
    TILT_LEFT = "tiltLeft"
    TILT_RIGHT = "tiltRight"


@dataclass
class GestureEvent:
    gesture: HeadGesture
    start_time: float
    time: float
    magnitude: float


@dataclass
class GestureSettings:
    nod_amplitude: float = 5.5       # degrees dip
    nod_window: float = 0.8          # seconds for whole nod
    shake_amplitude: float = 12.0    # degrees swing
    shake_window: float = 1.4        # seconds for 4 swings
    tilt_angle: float = 22.0         # degrees roll from neutral
    tilt_hold: float = 0.3           # seconds held
    swap_tilt_direction: bool = False
    cooldown: float = 0.5            # quiet period after gesture


@dataclass
class _Pose:
    t: float
    yaw: float    # degrees unwrapped
    pitch: float  # degrees


class GestureDetector:
    """
    Shape-based head gesture detector (Nod, Shake, Tilt).
    Reliable over ~25Hz-100Hz packet streams.
    """
    RE_NEUTRAL_AFTER: float = 4.0
    NOD_RETURN_FRACTION: float = 0.65
    CROSS_AXIS_ALLOWANCE: float = 0.6
    MIN_NOD_SPEED: float = 30.0
    MIN_SHAKE_SPEED: float = 80.0
    SHAKE_SWINGS: int = 4
    HISTORY_SPAN: float = 1.5
    SETTLED_SPEED: float = 25.0
    SETTLED_FOR: float = 0.15

    def __init__(self, settings: Optional[GestureSettings] = None) -> None:
        self.settings = settings or GestureSettings()
        self.history: List[_Pose] = []
        self.last_raw_yaw: Optional[float] = None
        self.cooldown_until: float = -math.inf
        self.awaiting_still: bool = False
        self.still_since: Optional[float] = None
        self.roll_baseline: Optional[float] = None
        self.tilt_candidate: Optional[Tuple[HeadGesture, float]] = None
        self.tilt_latched: bool = False
        self.off_neutral_since: Optional[float] = None

    def relative_roll(self, roll_degrees: float) -> float:
        if self.roll_baseline is None:
            return 0.0
        return AngleMath.wrapped_delta_degrees(roll_degrees, self.roll_baseline)

    def reset_tilt_baseline(self, roll_degrees: Optional[float] = None) -> None:
        self.roll_baseline = roll_degrees
        self.off_neutral_since = None
        self.tilt_candidate = None
        self.tilt_latched = False

    def reset(self) -> None:
        self.history.clear()
        self.last_raw_yaw = None
        self.cooldown_until = -math.inf
        self.awaiting_still = False
        self.still_since = None
        self.reset_tilt_baseline()

    def process(self, sample: MotionSample, enabled: Set[HeadGesture]) -> Optional[GestureEvent]:
        t = sample.timestamp
        raw_yaw = AngleMath.degrees(sample.yaw)
        pitch = AngleMath.degrees(sample.pitch)
        roll = AngleMath.degrees(sample.roll)

        # Unwrap yaw across +-180 boundaries; reset on gap
        if self.history and (t - self.history[-1].t > MotionDifferentiator.MAX_INTERVAL or t <= self.history[-1].t):
            self.history.clear()
            self.last_raw_yaw = None

        if self.last_raw_yaw is not None and self.history:
            yaw = self.history[-1].yaw + AngleMath.wrapped_delta_degrees(raw_yaw, self.last_raw_yaw)
        else:
            yaw = raw_yaw
        self.last_raw_yaw = raw_yaw

        self.history.append(_Pose(t=t, yaw=yaw, pitch=pitch))
        if self.history and (t - self.history[0].t > self.HISTORY_SPAN):
            self.history = [p for p in self.history if t - p.t <= self.HISTORY_SPAN]

        tilt = self._update_tilt(roll, t, enabled)

        if self.awaiting_still:
            speed = self._peak_speed_between(self.history[-2], self.history[-1]) if len(self.history) >= 2 else 0.0
            if speed < self.SETTLED_SPEED:
                if self.still_since is None:
                    self.still_since = t
                if t - self.still_since >= self.SETTLED_FOR:
                    self.awaiting_still = False
                    self.still_since = None
                    self.history = [self.history[-1]]
            else:
                self.still_since = None
            return None

        if t < self.cooldown_until:
            return None

        if HeadGesture.NOD in enabled:
            e = self._detect_nod(t)
            if e:
                return self._fire(e)

        if HeadGesture.SHAKE in enabled:
            e = self._detect_shake(t)
            if e:
                return self._fire(e)

        if tilt:
            return self._fire(tilt)

        return None

    def _fire(self, event: GestureEvent) -> GestureEvent:
        self.cooldown_until = event.time + self.settings.cooldown
        self.awaiting_still = True
        self.still_since = None
        self.tilt_candidate = None
        return event

    def _peak_speed_between(self, a: _Pose, b: _Pose) -> float:
        if b.t <= a.t:
            return 0.0
        return max(abs(b.pitch - a.pitch), abs(b.yaw - a.yaw)) / (b.t - a.t)

    def _detect_nod(self, now: float) -> Optional[GestureEvent]:
        if len(self.history) < 3:
            return None
        current = self.history[-1]
        last_index = len(self.history) - 1

        for j in range(last_index - 1):
            if now - self.history[j].t > self.settings.nod_window:
                continue
            start = self.history[j]
            extreme = 0.0
            extreme_index = j
            for k in range(j + 1, last_index):
                d = self.history[k].pitch - start.pitch
                if abs(d) > abs(extreme):
                    extreme = d
                    extreme_index = k

            depth = abs(extreme)
            if depth < self.settings.nod_amplitude or extreme_index <= j:
                continue

            remaining = abs(current.pitch - start.pitch)
            if remaining > depth * (1.0 - self.NOD_RETURN_FRACTION):
                continue

            segment = self.history[j:last_index + 1]
            yaw_values = [p.yaw for p in segment]
            yaw_range = max(yaw_values) - min(yaw_values)
            if yaw_range > max(depth * self.CROSS_AXIS_ALLOWANCE, 3.0):
                continue
            if self._peak_speed(segment, lambda p: p.pitch) < self.MIN_NOD_SPEED:
                continue

            return GestureEvent(gesture=HeadGesture.NOD, start_time=start.t, time=now, magnitude=depth)

        return None

    def _detect_shake(self, now: float) -> Optional[GestureEvent]:
        window = [p for p in self.history if now - p.t <= self.settings.shake_window]
        if len(window) < 4:
            return None

        anchor = window[0].yaw
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

        pitch_values = [p.pitch for p in window]
        pitch_range = max(pitch_values) - min(pitch_values)
        if pitch_range > largest * self.CROSS_AXIS_ALLOWANCE:
            return None
        if self._peak_speed(window, lambda p: p.yaw) < self.MIN_SHAKE_SPEED:
            return None

        return GestureEvent(gesture=HeadGesture.SHAKE, start_time=window[0].t, time=now, magnitude=largest)

    def _peak_speed(self, poses: List[_Pose], axis_fn) -> float:
        best = 0.0
        for i in range(1, len(poses)):
            dt = poses[i].t - poses[i - 1].t
            if dt > 0:
                rate = abs(axis_fn(poses[i]) - axis_fn(poses[i - 1])) / dt
                if rate > best:
                    best = rate
        return best

    def _update_tilt(self, roll_degrees: float, t: float, enabled: Set[HeadGesture]) -> Optional[GestureEvent]:
        if self.roll_baseline is None:
            self.roll_baseline = roll_degrees
            return None

        rel = AngleMath.wrapped_delta_degrees(roll_degrees, self.roll_baseline)

        if abs(rel) < self.settings.tilt_angle * 0.5:
            # Near neutral: follow slow baseline changes
            self.roll_baseline += rel * 0.02
            self.tilt_latched = False
            self.tilt_candidate = None
            self.off_neutral_since = None
            return None

        if self.off_neutral_since is not None:
            if t - self.off_neutral_since > self.RE_NEUTRAL_AFTER:
                self.roll_baseline = roll_degrees
                self.off_neutral_since = None
                self.tilt_candidate = None
                self.tilt_latched = False
                return None
        else:
            self.off_neutral_since = t

        if (HeadGesture.TILT_LEFT not in enabled and HeadGesture.TILT_RIGHT not in enabled) or self.tilt_latched:
            return None

        if abs(rel) < self.settings.tilt_angle:
            self.tilt_candidate = None
            return None

        is_right = (rel > 0) != self.settings.swap_tilt_direction
        gesture = HeadGesture.TILT_RIGHT if is_right else HeadGesture.TILT_LEFT

        if self.tilt_candidate is None or self.tilt_candidate[0] != gesture:
            self.tilt_candidate = (gesture, t)
            return None

        if t - self.tilt_candidate[1] < self.settings.tilt_hold:
            return None

        self.tilt_latched = True
        cand_since = self.tilt_candidate[1]
        self.tilt_candidate = None

        if gesture in enabled and t >= self.cooldown_until:
            return GestureEvent(gesture=gesture, start_time=cand_since, time=t, magnitude=abs(rel))
        return None


# ==============================================================================
# Dwell Detection
# ==============================================================================

@dataclass
class DwellSettings:
    enabled: bool = True
    smart: bool = True               # Only click interactive elements
    duration: float = 0.8            # Seconds hover before click
    radius: float = 16.0             # Allowed drift pixels


@dataclass
class DwellUpdate:
    progress: Optional[float]        # 0.0..1.0 while dwelling, None = hide indicator
    fired: bool


class DwellDetector:
    """Detects resting pointer hover state to trigger clicks."""
    REVEAL_FRACTION: float = 0.2

    def __init__(self, settings: Optional[DwellSettings] = None) -> None:
        self.settings = settings or DwellSettings()
        self.anchor: Optional[Vec2] = None
        self.anchor_time: float = 0.0
        self.armed: bool = False
        self.anchor_id: int = 0
        self.anchor_position: Optional[Vec2] = None

    def reset(self) -> None:
        self.armed = False
        self.anchor = None

    def update(self, position: Vec2, timestamp: float) -> DwellUpdate:
        if self.anchor is None:
            self.anchor = Vec2(position.x, position.y)
            self.anchor_time = timestamp
            return DwellUpdate(progress=None, fired=False)

        if position.distance(self.anchor) > self.settings.radius:
            self.anchor = Vec2(position.x, position.y)
            self.anchor_time = timestamp
            self.armed = True
            self.anchor_id += 1
            self.anchor_position = Vec2(position.x, position.y)
            return DwellUpdate(progress=None, fired=False)

        if not self.armed or self.settings.duration <= 0:
            return DwellUpdate(progress=None, fired=False)

        fraction = (timestamp - self.anchor_time) / self.settings.duration
        if fraction >= 1.0:
            self.armed = False
            return DwellUpdate(progress=1.0, fired=True)

        prog = fraction if fraction >= self.REVEAL_FRACTION else None
        return DwellUpdate(progress=prog, fired=False)


# ==============================================================================
# Triggers & Actions
# ==============================================================================

class Trigger(str, Enum):
    STEM_SINGLE = "stemSingle"
    STEM_DOUBLE = "stemDouble"
    STEM_TRIPLE = "stemTriple"
    NOD = "nod"
    SHAKE = "shake"
    TILT_LEFT = "tiltLeft"
    TILT_RIGHT = "tiltRight"
    DWELL = "dwell"

    @property
    def is_stem(self) -> bool:
        return self in (Trigger.STEM_SINGLE, Trigger.STEM_DOUBLE, Trigger.STEM_TRIPLE)

    @property
    def head_gesture(self) -> Optional[HeadGesture]:
        mapping = {
            Trigger.NOD: HeadGesture.NOD,
            Trigger.SHAKE: HeadGesture.SHAKE,
            Trigger.TILT_LEFT: HeadGesture.TILT_LEFT,
            Trigger.TILT_RIGHT: HeadGesture.TILT_RIGHT,
        }
        return mapping.get(self)


class PointerAction(str, Enum):
    NONE = "none"
    LEFT_CLICK = "leftClick"
    RIGHT_CLICK = "rightClick"
    DOUBLE_CLICK = "doubleClick"
    MIDDLE_CLICK = "middleClick"
    TOGGLE_DRAG = "toggleDrag"
    TOGGLE_SCROLL_MODE = "toggleScrollMode"
    TOGGLE_TRACKING = "toggleTracking"
    RECENTER = "recenter"
    MISSION_CONTROL = "missionControl"
    APP_WINDOWS = "appWindows"
    PREVIOUS_SPACE = "previousSpace"
    NEXT_SPACE = "nextSpace"
    BACK = "back"
    FORWARD = "forward"
    SCREENSHOT = "screenshot"

    @property
    def is_click(self) -> bool:
        return self in (
            PointerAction.LEFT_CLICK,
            PointerAction.RIGHT_CLICK,
            PointerAction.DOUBLE_CLICK,
            PointerAction.MIDDLE_CLICK,
            PointerAction.TOGGLE_DRAG,
        )


class ActionMap:
    """Bindings from Trigger to PointerAction."""
    DEFAULTS: Dict[Trigger, PointerAction] = {
        Trigger.STEM_SINGLE: PointerAction.LEFT_CLICK,
        Trigger.STEM_DOUBLE: PointerAction.RIGHT_CLICK,
        Trigger.STEM_TRIPLE: PointerAction.TOGGLE_SCROLL_MODE,
        Trigger.NOD: PointerAction.LEFT_CLICK,
        Trigger.SHAKE: PointerAction.TOGGLE_TRACKING,
        Trigger.TILT_LEFT: PointerAction.NONE,
        Trigger.TILT_RIGHT: PointerAction.NONE,
        Trigger.DWELL: PointerAction.LEFT_CLICK,
    }

    def __init__(self, bindings: Optional[Dict[Trigger, PointerAction]] = None) -> None:
        self.bindings = dict(self.DEFAULTS)
        if bindings:
            self.bindings.update(bindings)

    def get(self, trigger: Trigger) -> PointerAction:
        return self.bindings.get(trigger, PointerAction.NONE)

    def set(self, trigger: Trigger, action: PointerAction) -> None:
        self.bindings[trigger] = action

    @property
    def enabled_head_gestures(self) -> Set[HeadGesture]:
        gestures = set()
        for t in Trigger:
            g = t.head_gesture
            if g and self.get(t) != PointerAction.NONE:
                gestures.add(g)
        return gestures


@dataclass
class AppSettings:
    version: int = 3
    pointer: PointerSettings = field(default_factory=PointerSettings)
    gestures: GestureSettings = field(default_factory=GestureSettings)
    dwell: DwellSettings = field(default_factory=DwellSettings)
    actions: ActionMap = field(default_factory=ActionMap)
    stem_controls_enabled: bool = True
    route_audio_to_headphones: bool = True
    show_hud: bool = True
    show_click_pulse: bool = True

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "pointer": {
                "sensitivity": self.pointer.sensitivity,
                "acceleration": self.pointer.acceleration,
                "deadzone": self.pointer.deadzone,
                "smoothing": self.pointer.smoothing,
                "invert_horizontal": self.pointer.invert_horizontal,
                "invert_vertical": self.pointer.invert_vertical,
                "scroll_speed": self.pointer.scroll_speed,
                "invert_scroll": self.pointer.invert_scroll,
            },
            "gestures": {
                "nod_amplitude": self.gestures.nod_amplitude,
                "nod_window": self.gestures.nod_window,
                "shake_amplitude": self.gestures.shake_amplitude,
                "shake_window": self.gestures.shake_window,
                "tilt_angle": self.gestures.tilt_angle,
                "tilt_hold": self.gestures.tilt_hold,
                "swap_tilt_direction": self.gestures.swap_tilt_direction,
                "cooldown": self.gestures.cooldown,
            },
            "dwell": {
                "enabled": self.dwell.enabled,
                "smart": self.dwell.smart,
                "duration": self.dwell.duration,
                "radius": self.dwell.radius,
            },
            "actions": {k.value: v.value for k, v in self.actions.bindings.items()},
            "stem_controls_enabled": self.stem_controls_enabled,
            "show_hud": self.show_hud,
            "show_click_pulse": self.show_click_pulse,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AppSettings:
        settings = cls()
        if not data:
            return settings

        settings.version = data.get("version", 3)
        p = data.get("pointer", {})
        settings.pointer.sensitivity = p.get("sensitivity", 1.0)
        settings.pointer.acceleration = p.get("acceleration", 0.6)
        settings.pointer.deadzone = p.get("deadzone", 3.0)
        settings.pointer.smoothing = p.get("smoothing", 0.55)
        settings.pointer.invert_horizontal = p.get("invert_horizontal", False)
        settings.pointer.invert_vertical = p.get("invert_vertical", False)
        settings.pointer.scroll_speed = p.get("scroll_speed", 1.0)
        settings.pointer.invert_scroll = p.get("invert_scroll", False)

        g = data.get("gestures", {})
        settings.gestures.nod_amplitude = g.get("nod_amplitude", 5.5)
        settings.gestures.nod_window = g.get("nod_window", 0.8)
        settings.gestures.shake_amplitude = g.get("shake_amplitude", 12.0)
        settings.gestures.shake_window = g.get("shake_window", 1.4)
        settings.gestures.tilt_angle = g.get("tilt_angle", 22.0)
        settings.gestures.tilt_hold = g.get("tilt_hold", 0.3)
        settings.gestures.swap_tilt_direction = g.get("swap_tilt_direction", False)
        settings.gestures.cooldown = g.get("cooldown", 0.5)

        d = data.get("dwell", {})
        settings.dwell.enabled = d.get("enabled", True)
        settings.dwell.smart = d.get("smart", True)
        settings.dwell.duration = d.get("duration", 0.8)
        settings.dwell.radius = d.get("radius", 16.0)

        acts = data.get("actions", {})
        for k_str, v_str in acts.items():
            try:
                trig = Trigger(k_str)
                act = PointerAction(v_str)
                settings.actions.set(trig, act)
            except ValueError:
                pass

        settings.stem_controls_enabled = data.get("stem_controls_enabled", True)
        settings.show_hud = data.get("show_hud", True)
        settings.show_click_pulse = data.get("show_click_pulse", True)
        return settings
