"""Mathematical utilities for AirCursor: vectors and angle math.

Matches AirCursor/Sources/AirCursorCore/Math.swift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Tuple


@dataclass
class Vec2:
    """Minimal 2D vector used by the pointer pipeline.

    Kept free of any platform-specific UI frameworks (AppKit/CoreGraphics/Win32/Android).
    """

    x: float = 0.0
    y: float = 0.0

    @property
    def length(self) -> float:
        """Euclidean norm / magnitude of the vector."""
        return math.sqrt(self.x * self.x + self.y * self.y)

    def distance(self, other: Vec2) -> float:
        """Euclidean distance to another Vec2."""
        return (self - other).length

    def distance_to(self, other: Vec2) -> float:
        """Alias for distance(other)."""
        return self.distance(other)

    def __add__(self, other: Vec2) -> Vec2:
        if isinstance(other, Vec2):
            return Vec2(self.x + other.x, self.y + other.y)
        return NotImplemented

    def __sub__(self, other: Vec2) -> Vec2:
        if isinstance(other, Vec2):
            return Vec2(self.x - other.x, self.y - other.y)
        return NotImplemented

    def __mul__(self, scalar: float) -> Vec2:
        if isinstance(scalar, (int, float)):
            return Vec2(self.x * float(scalar), self.y * float(scalar))
        return NotImplemented

    def __rmul__(self, scalar: float) -> Vec2:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec2:
        if isinstance(scalar, (int, float)):
            if scalar == 0:
                raise ZeroDivisionError("division by zero in Vec2")
            return Vec2(self.x / float(scalar), self.y / float(scalar))
        return NotImplemented

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def __iter__(self):
        """Allows tuple unpacking: x, y = vec."""
        yield self.x
        yield self.y

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Vec2:
        return cls(float(data.get("x", 0.0)), float(data.get("y", 0.0)))


# Class-level zero constant matching Swift Vec2.zero
Vec2.zero = Vec2(0.0, 0.0)


class AngleMath:
    """Angle math utilities for wrapping deltas and converting units.

    Matches Swift AngleMath enum.
    """

    @staticmethod
    def degrees(radians_val: float) -> float:
        """Converts radians to degrees."""
        return radians_val * 180.0 / math.pi

    @staticmethod
    def radians(degrees_val: float) -> float:
        """Converts degrees to radians."""
        return degrees_val * math.pi / 180.0

    @staticmethod
    def wrapped_delta(a: float, b: float) -> float:
        """Shortest signed difference `a - b` in radians, wrapped into (-π, π].

        Matches Swift `atan2(sin(a - b), cos(a - b))`.
        """
        diff = a - b
        return math.atan2(math.sin(diff), math.cos(diff))

    @staticmethod
    def wrapped_delta_degrees(a: float, b: float) -> float:
        """Shortest signed difference `a - b` in degrees, wrapped into (-180, 180].

        Matches Swift `degrees(wrappedDelta(radians(a), radians(b)))`.
        """
        rad_a = AngleMath.radians(a)
        rad_b = AngleMath.radians(b)
        return AngleMath.degrees(AngleMath.wrapped_delta(rad_a, rad_b))

    # CamelCase aliases matching Swift API
    wrappedDelta = wrapped_delta
    wrappedDeltaDegrees = wrapped_delta_degrees
