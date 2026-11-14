"""Maps head rotation rate to cursor velocity, smooths motion, and tracks history.

Matches AirCursor/Sources/AirCursorCore/Pointer.swift.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from .math_util import Vec2
from .motion import AngularRates

if TYPE_CHECKING:
    from .settings import PointerSettings


class PointerMapper:
    """Maps head angular velocity to cursor velocity.

    Velocity ("relative") mapping is used rather than absolute angle mapping: it never
    needs recalibration, survives sensor drift, and lets you "ratchet" across large or
    multiple displays the way you'd lift and re-place a mouse.
    """

    PIXELS_PER_DEGREE: float = 28.0
    pixelsPerDegree: float = PIXELS_PER_DEGREE

    @classmethod
    def axis_speed(cls, rate: float, settings: PointerSettings) -> float:
        """Speed (px/s) for one axis given a rotation rate in deg/s. Sign is preserved."""
        magnitude = abs(rate)
        if magnitude <= settings.deadzone:
            return 0.0
        effective = magnitude - settings.deadzone
        # Gentle, bounded acceleration: slow head = precise, fast head = travel.
        boost = 1.0 + settings.acceleration * min(effective / 60.0, 3.0)
        speed = effective * cls.PIXELS_PER_DEGREE * settings.sensitivity * boost
        return -speed if rate < 0 else speed

    axisSpeed = axis_speed

    @classmethod
    def cursor_velocity(cls, rates: AngularRates, settings: PointerSettings) -> Vec2:
        """Cursor velocity in screen points per second.

        Global screen coordinates (origin top-left, +y is down).
        Turning head left (+yaw) moves cursor left (-x); looking up (+pitch) moves it up (-y).
        """
        dx = -cls.axis_speed(rates.yaw, settings)
        dy = -cls.axis_speed(rates.pitch, settings)

        inv_h = getattr(settings, "invert_horizontal", False) or getattr(
            settings, "invertHorizontal", False
        )
        inv_v = getattr(settings, "invert_vertical", False) or getattr(
            settings, "invertVertical", False
        )

        if inv_h:
            dx = -dx
        if inv_v:
            dy = -dy

        return Vec2(dx, dy)

    cursorVelocity = cursor_velocity


class PointerSmoother:
    """Frame-rate independent exponential velocity smoother with stale sample cutoff.

    Headphone motion arrives at ~25 Hz; the screen refreshes at 60-120 Hz.
    The smoother eases the cursor toward the latest target velocity every frame
    so motion is fluid, and stops it promptly if samples go stale.
    """

    STALE_AFTER: float = 0.12
    staleAfter: float = STALE_AFTER

    def __init__(self, stale_after: float = STALE_AFTER):
        self.stale_after: float = stale_after
        self.velocity: Vec2 = Vec2.zero
        self.target: Vec2 = Vec2.zero
        self.target_time: float = -float("inf")

    def set_target(self, v: Vec2, at: float) -> None:
        """Sets the new target velocity and timestamp."""
        self.target = v
        self.target_time = at

    setTarget = set_target

    def reset(self) -> None:
        """Resets velocities to zero."""
        self.velocity = Vec2.zero
        self.target = Vec2.zero
        self.target_time = -float("inf")

    def step(self, now: float, dt: float, smoothing: float) -> Vec2:
        """Advances by `dt` seconds and returns the cursor displacement for this frame."""
        if dt <= 0:
            return Vec2.zero

        goal = Vec2.zero if (now - self.target_time) > self.stale_after else self.target
        s = min(max(smoothing, 0.0), 0.97)

        # Frame-rate independent exponential smoothing (s is the per-1/60s retention).
        alpha = 1.0 - pow(s, dt * 60.0)
        self.velocity += (goal - self.velocity) * alpha

        if goal == Vec2.zero and self.velocity.length < 2.0:
            self.velocity = Vec2.zero

        return self.velocity * dt


class CursorHistory:
    """Recent cursor positions ring buffer.

    Allows a head gesture to click where you were pointing *before* the gesture itself nudged the cursor.
    """

    def __init__(self, capacity: int = 360):
        self.capacity: int = max(1, capacity)
        self._buffer: List[Tuple[float, Vec2]] = []
        self._head: int = 0

    def append(self, position: Vec2, at: float) -> None:
        """Appends a position sample at timestamp `at`."""
        if len(self._buffer) < self.capacity:
            self._buffer.append((at, position))
        else:
            self._buffer[self._head] = (at, position)
            self._head = (self._head + 1) % self.capacity

    def remove_all(self) -> None:
        """Clears all history entries."""
        self._buffer.clear()
        self._head = 0

    removeAll = remove_all
    clear = remove_all

    def position(self, at: float) -> Optional[Vec2]:
        """Most recent position recorded at or before `at`; the oldest one if `at`
        predates the buffer; None if empty.
        """
        if not self._buffer:
            return None

        if len(self._buffer) < self.capacity:
            ordered = self._buffer
        else:
            ordered = self._buffer[self._head :] + self._buffer[: self._head]

        best = ordered[0][1]
        for entry_time, pos in ordered:
            if entry_time <= at:
                best = pos
            else:
                break
        return best
