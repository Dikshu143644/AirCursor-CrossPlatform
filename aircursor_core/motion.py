"""Attitude readings and angular velocity differentiation.

Matches AirCursor/Sources/AirCursorCore/Motion.swift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .math_util import AngleMath


@dataclass
class MotionSample:
    """One attitude reading from the headphones.

    Angles are in radians, timestamp in seconds.
    """

    timestamp: float
    yaw: float
    pitch: float
    roll: float


@dataclass
class AngularRates:
    """Angular velocities in degrees per second, derived from consecutive attitude samples."""

    timestamp: float
    yaw: float
    pitch: float
    roll: float


class MotionDifferentiator:
    """Turns a stream of attitude samples into angular rates.

    Handles wrap-around and rejects gaps (e.g. after a Bluetooth hiccup) so they
    never produce a cursor jump.
    """

    MIN_INTERVAL: float = 0.002
    MAX_INTERVAL: float = 0.25
    minInterval: float = MIN_INTERVAL
    maxInterval: float = MAX_INTERVAL

    def __init__(self, min_interval: float = MIN_INTERVAL, max_interval: float = MAX_INTERVAL):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.last: Optional[MotionSample] = None

    def reset(self) -> None:
        """Clears the previous sample reference."""
        self.last = None

    def push(self, sample: MotionSample) -> Optional[AngularRates]:
        """Pushes a new attitude sample and returns angular rates if valid.

        Always retains the latest sample even if a gap is rejected (matching Swift `defer { last = sample }`).
        """
        previous = self.last
        self.last = sample

        if previous is None:
            return None

        dt = sample.timestamp - previous.timestamp
        if dt < self.min_interval or dt > self.max_interval:
            return None

        yaw_rate = AngleMath.degrees(AngleMath.wrapped_delta(sample.yaw, previous.yaw)) / dt
        pitch_rate = AngleMath.degrees(AngleMath.wrapped_delta(sample.pitch, previous.pitch)) / dt
        roll_rate = AngleMath.degrees(AngleMath.wrapped_delta(sample.roll, previous.roll)) / dt

        return AngularRates(
            timestamp=sample.timestamp,
            yaw=yaw_rate,
            pitch=pitch_rate,
            roll=roll_rate,
        )
