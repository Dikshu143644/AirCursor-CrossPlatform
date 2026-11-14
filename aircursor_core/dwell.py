"""Hover click (dwell) detection.

Matches AirCursor/Sources/AirCursorCore/Gestures.swift (DwellDetector).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .math_util import Vec2

if TYPE_CHECKING:
    from .settings import DwellSettings


@dataclass
class DwellUpdate:
    """Status update from DwellDetector.

    Matches Swift DwellDetector.Update struct.
    """

    progress: Optional[float]  # 0...1 while dwelling (None = hide indicator)
    fired: bool


class DwellDetector:
    """Clicks when the cursor rests in one spot.

    Requires movement between clicks so a stationary cursor never machine-guns.
    """

    REVEAL_FRACTION: float = 0.2
    revealFraction: float = REVEAL_FRACTION

    def __init__(self, settings: Optional[DwellSettings] = None):
        if settings is None:
            from .settings import DwellSettings

            settings = DwellSettings()
        self.settings: DwellSettings = settings

        self._anchor: Optional[Vec2] = None
        self._anchor_time: float = 0.0
        self._armed: bool = False
        self._anchor_id: int = 0
        self._anchor_position: Optional[Vec2] = None

    @property
    def anchor_id(self) -> int:
        """Changes every time the pointer settles somewhere new."""
        return self._anchor_id

    anchorID = anchor_id

    @property
    def anchor_position(self) -> Optional[Vec2]:
        """Settled resting position of the pointer."""
        return self._anchor_position

    anchorPosition = anchor_position

    def reset(self) -> None:
        """Disarm until the cursor moves again (call after any click)."""
        self._armed = False
        self._anchor = None

    def update(self, position: Vec2, time: float) -> DwellUpdate:
        """Feeds the current cursor position and time, returning progress / click."""
        if self._anchor is None:
            self._anchor = position
            self._anchor_time = time
            return DwellUpdate(progress=None, fired=False)

        if position.distance(self._anchor) > self.settings.radius:
            self._anchor = position
            self._anchor_time = time
            self._armed = True
            self._anchor_id += 1
            self._anchor_position = position
            return DwellUpdate(progress=None, fired=False)

        if not self._armed or self.settings.duration <= 0:
            return DwellUpdate(progress=None, fired=False)

        fraction = (time - self._anchor_time) / self.settings.duration
        if fraction >= 1.0:
            self._armed = False
            return DwellUpdate(progress=1.0, fired=True)

        progress_val = fraction if fraction >= self.REVEAL_FRACTION else None
        return DwellUpdate(progress=progress_val, fired=False)
