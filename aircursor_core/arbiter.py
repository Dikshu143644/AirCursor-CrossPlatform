"""AirCursor Input Arbiter & Multi-Source Tracking Coordinator.

Manages arbitration between input modalities:
- AirPods Bluetooth (OpenTrack UDP / BlueZ / Direct IMU)
- Camera Vision Tracking (Head pose & Hand gestures)
- Synthetic Sensor Simulation
- Physical Mouse Intervention (Human-Input Override)

Supports automatic fallback: if AirPods Bluetooth packets stop arriving
for > 3.0 seconds, automatically transitions to Vision Tracking fallback.
"""

from __future__ import annotations

import enum
import time
from typing import Callable, Optional

from .motion import MotionSample


class TrackingSource(str, enum.Enum):
    """Active input tracking source."""

    NONE = "none"
    BLUETOOTH = "bluetooth"          # AirPods IMU (OpenTrack UDP, MagicAAP, BlueZ)
    VISION = "vision"                # Webcam face/nose pose & hand tracking
    SYNTHETIC = "synthetic"          # Synthetic simulation generator
    MOUSE_OVERRIDE = "mouse_override"# Physical human mouse intervention


class FallbackPolicy(str, enum.Enum):
    """Policy for automatic fallback when primary source is lost."""

    AUTO_TRANSITION = "auto_transition"  # Seamlessly switch to fallback
    SUGGEST_ONLY = "suggest_only"        # Fire notification / suggestion event
    MANUAL = "manual"                    # Only switch upon user command


class InputArbiter:
    """Coordinates and arbitrates input sources for cursor motion."""

    DEFAULT_BLUETOOTH_TIMEOUT: float = 3.0  # seconds

    def __init__(
        self,
        initial_source: TrackingSource = TrackingSource.BLUETOOTH,
        fallback_policy: FallbackPolicy = FallbackPolicy.AUTO_TRANSITION,
        bluetooth_timeout: float = DEFAULT_BLUETOOTH_TIMEOUT,
        camera_available: bool = False,
        camera_enabled: bool = False,
        on_source_changed: Optional[Callable[[TrackingSource, TrackingSource], None]] = None,
        on_fallback_suggested: Optional[Callable[[str], None]] = None,
    ):
        self._active_source: TrackingSource = initial_source
        self._previous_source: TrackingSource = TrackingSource.NONE
        self.fallback_policy: FallbackPolicy = fallback_policy
        self.bluetooth_timeout: float = bluetooth_timeout

        self.camera_available: bool = camera_available
        self.camera_enabled: bool = camera_enabled

        self._manual_lock: Optional[TrackingSource] = None
        self._last_bluetooth_time: float = 0.0
        self._last_vision_time: float = 0.0

        self.on_source_changed: Optional[Callable[[TrackingSource, TrackingSource], None]] = on_source_changed
        self.on_fallback_suggested: Optional[Callable[[str], None]] = on_fallback_suggested

    @property
    def active_source(self) -> TrackingSource:
        return self._active_source

    @property
    def previous_source(self) -> TrackingSource:
        return self._previous_source

    @property
    def manual_lock(self) -> Optional[TrackingSource]:
        return self._manual_lock

    @property
    def last_bluetooth_time(self) -> float:
        return self._last_bluetooth_time

    @property
    def last_vision_time(self) -> float:
        return self._last_vision_time

    @property
    def is_bluetooth_stale(self) -> bool:
        """True if no Bluetooth packet has been received within bluetooth_timeout."""
        if self._last_bluetooth_time <= 0:
            return True
        return (time.time() - self._last_bluetooth_time) > self.bluetooth_timeout

    def set_camera_status(self, available: bool, enabled: bool) -> None:
        """Updates camera hardware readiness and enabled preference."""
        self.camera_available = available
        self.camera_enabled = enabled

    def set_manual_source(self, source: Optional[TrackingSource]) -> None:
        """Locks tracking to a specific source, or clears lock (None) for auto-arbitration."""
        self._manual_lock = source
        if source is not None and source != self._active_source:
            self._transition_to(source)

    def toggle_camera(self) -> TrackingSource:
        """Manually toggles between VISION tracking and BLUETOOTH tracking."""
        if self._active_source == TrackingSource.VISION:
            target = TrackingSource.BLUETOOTH
        else:
            target = TrackingSource.VISION
        self.set_manual_source(target)
        return self._active_source

    def notify_bluetooth_sample(self, sample: MotionSample, timestamp: Optional[float] = None) -> bool:
        """Processes an incoming AirPods Bluetooth sample.

        Returns True if the sample should be consumed by the pointer pipeline.
        """
        now = timestamp if timestamp is not None else time.time()
        self._last_bluetooth_time = now

        # If locked manually to another source (e.g. forced VISION), do not auto-switch
        if self._manual_lock is not None:
            return self._manual_lock == TrackingSource.BLUETOOTH

        # If we were on VISION fallback because Bluetooth was silent, resume Bluetooth!
        if self._active_source != TrackingSource.BLUETOOTH and self._active_source != TrackingSource.SYNTHETIC:
            self._transition_to(TrackingSource.BLUETOOTH)

        return self._active_source == TrackingSource.BLUETOOTH

    def notify_vision_sample(self, sample: MotionSample, timestamp: Optional[float] = None) -> bool:
        """Processes an incoming Vision camera tracking sample.

        Returns True if the sample should be consumed by the pointer pipeline.
        """
        now = timestamp if timestamp is not None else time.time()
        self._last_vision_time = now

        if self._manual_lock is not None:
            return self._manual_lock == TrackingSource.VISION

        return self._active_source == TrackingSource.VISION

    def check_health(self, now: Optional[float] = None) -> TrackingSource:
        """Periodic watchdog check for source timeouts and fallback transitions.

        Called during the main engine loop (e.g. 120Hz).
        """
        current_time = now if now is not None else time.time()

        # If manually locked, do not perform auto transitions
        if self._manual_lock is not None:
            return self._active_source

        # Check if Bluetooth has stalled > 3.0 seconds
        if self._active_source == TrackingSource.BLUETOOTH:
            if self._last_bluetooth_time > 0 and (current_time - self._last_bluetooth_time > self.bluetooth_timeout):
                # Bluetooth is silent! Check if camera fallback is viable
                can_fallback = self.camera_available and self.camera_enabled

                if can_fallback:
                    if self.fallback_policy == FallbackPolicy.AUTO_TRANSITION:
                        self._transition_to(TrackingSource.VISION)
                    elif self.fallback_policy == FallbackPolicy.SUGGEST_ONLY:
                        if self.on_fallback_suggested:
                            self.on_fallback_suggested(
                                f"AirPods silent for {self.bluetooth_timeout:.1f}s. Camera fallback available."
                            )

        return self._active_source

    def _transition_to(self, new_source: TrackingSource) -> None:
        """Internal transition handler with notification dispatch."""
        if self._active_source == new_source:
            return

        old_source = self._active_source
        self._previous_source = old_source
        self._active_source = new_source

        if self.on_source_changed:
            self.on_source_changed(old_source, new_source)
