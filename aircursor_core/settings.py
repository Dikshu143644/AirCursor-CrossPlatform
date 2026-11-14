"""Configuration models and serialization for AirCursor.

Matches AirCursor/Sources/AirCursorCore/Settings.swift.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .actions import ActionMap


def _get_lenient(d: Dict[str, Any], keys: list[str], default_val: Any, val_type: type) -> Any:
    """Lenient decode: a missing or mistyped key falls back to the default."""
    for k in keys:
        if k in d:
            v = d[k]
            if v is None and default_val is None:
                return None
            if isinstance(v, val_type):
                return v
            # Handle float conversions from int
            if val_type is float and isinstance(v, (int, float)):
                return float(v)
            # Handle bool
            if val_type is bool and isinstance(v, bool):
                return bool(v)
    return default_val


@dataclass
class PointerSettings:
    """Settings governing pointer motion and sensitivity."""

    sensitivity: float = 1.0
    acceleration: float = 0.6
    deadzone: float = 3.0
    smoothing: float = 0.55
    invert_horizontal: bool = False
    invert_vertical: bool = False
    scroll_speed: float = 1.0
    invert_scroll: bool = False

    # CamelCase property aliases matching Swift API
    @property
    def invertHorizontal(self) -> bool:
        return self.invert_horizontal

    @invertHorizontal.setter
    def invertHorizontal(self, val: bool) -> None:
        self.invert_horizontal = val

    @property
    def invertVertical(self) -> bool:
        return self.invert_vertical

    @invertVertical.setter
    def invertVertical(self, val: bool) -> None:
        self.invert_vertical = val

    @property
    def scrollSpeed(self) -> float:
        return self.scroll_speed

    @scrollSpeed.setter
    def scrollSpeed(self, val: float) -> None:
        self.scroll_speed = val

    @property
    def invertScroll(self) -> bool:
        return self.invert_scroll

    @invertScroll.setter
    def invertScroll(self, val: bool) -> None:
        self.invert_scroll = val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sensitivity": self.sensitivity,
            "acceleration": self.acceleration,
            "deadzone": self.deadzone,
            "smoothing": self.smoothing,
            "invertHorizontal": self.invert_horizontal,
            "invertVertical": self.invert_vertical,
            "scrollSpeed": self.scroll_speed,
            "invertScroll": self.invert_scroll,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PointerSettings:
        default = cls()
        if not isinstance(data, dict):
            return default
        return cls(
            sensitivity=_get_lenient(data, ["sensitivity"], default.sensitivity, float),
            acceleration=_get_lenient(data, ["acceleration"], default.acceleration, float),
            deadzone=_get_lenient(data, ["deadzone"], default.deadzone, float),
            smoothing=_get_lenient(data, ["smoothing"], default.smoothing, float),
            invert_horizontal=_get_lenient(
                data, ["invertHorizontal", "invert_horizontal"], default.invert_horizontal, bool
            ),
            invert_vertical=_get_lenient(
                data, ["invertVertical", "invert_vertical"], default.invert_vertical, bool
            ),
            scroll_speed=_get_lenient(data, ["scrollSpeed", "scroll_speed"], default.scroll_speed, float),
            invert_scroll=_get_lenient(data, ["invertScroll", "invert_scroll"], default.invert_scroll, bool),
        )


@dataclass
class GestureSettings:
    """Settings governing deliberate head gestures."""

    nod_amplitude: float = 5.5
    nod_window: float = 0.8
    shake_amplitude: float = 12.0
    shake_window: float = 1.4
    tilt_angle: float = 22.0
    tilt_hold: float = 0.3
    swap_tilt_direction: bool = False
    cooldown: float = 0.5

    # CamelCase property aliases matching Swift API
    @property
    def nodAmplitude(self) -> float:
        return self.nod_amplitude

    @nodAmplitude.setter
    def nodAmplitude(self, val: float) -> None:
        self.nod_amplitude = val

    @property
    def nodWindow(self) -> float:
        return self.nod_window

    @nodWindow.setter
    def nodWindow(self, val: float) -> None:
        self.nod_window = val

    @property
    def shakeAmplitude(self) -> float:
        return self.shake_amplitude

    @shakeAmplitude.setter
    def shakeAmplitude(self, val: float) -> None:
        self.shake_amplitude = val

    @property
    def shakeWindow(self) -> float:
        return self.shake_window

    @shakeWindow.setter
    def shakeWindow(self, val: float) -> None:
        self.shake_window = val

    @property
    def tiltAngle(self) -> float:
        return self.tilt_angle

    @tiltAngle.setter
    def tiltAngle(self, val: float) -> None:
        self.tilt_angle = val

    @property
    def tiltHold(self) -> float:
        return self.tilt_hold

    @tiltHold.setter
    def tiltHold(self, val: float) -> None:
        self.tilt_hold = val

    @property
    def swapTiltDirection(self) -> bool:
        return self.swap_tilt_direction

    @swapTiltDirection.setter
    def swapTiltDirection(self, val: bool) -> None:
        self.swap_tilt_direction = val

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodAmplitude": self.nod_amplitude,
            "nodWindow": self.nod_window,
            "shakeAmplitude": self.shake_amplitude,
            "shakeWindow": self.shake_window,
            "tiltAngle": self.tilt_angle,
            "tiltHold": self.tilt_hold,
            "swapTiltDirection": self.swap_tilt_direction,
            "cooldown": self.cooldown,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> GestureSettings:
        default = cls()
        if not isinstance(data, dict):
            return default
        return cls(
            nod_amplitude=_get_lenient(data, ["nodAmplitude", "nod_amplitude"], default.nod_amplitude, float),
            nod_window=_get_lenient(data, ["nodWindow", "nod_window"], default.nod_window, float),
            shake_amplitude=_get_lenient(
                data, ["shakeAmplitude", "shake_amplitude"], default.shake_amplitude, float
            ),
            shake_window=_get_lenient(data, ["shakeWindow", "shake_window"], default.shake_window, float),
            tilt_angle=_get_lenient(data, ["tiltAngle", "tilt_angle"], default.tilt_angle, float),
            tilt_hold=_get_lenient(data, ["tiltHold", "tilt_hold"], default.tilt_hold, float),
            swap_tilt_direction=_get_lenient(
                data, ["swapTiltDirection", "swap_tilt_direction"], default.swap_tilt_direction, bool
            ),
            cooldown=_get_lenient(data, ["cooldown"], default.cooldown, float),
        )


@dataclass
class DwellSettings:
    """Hover click settings."""

    enabled: bool = True
    smart: bool = True
    duration: float = 0.8
    radius: float = 16.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "smart": self.smart,
            "duration": self.duration,
            "radius": self.radius,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DwellSettings:
        default = cls()
        if not isinstance(data, dict):
            return default
        return cls(
            enabled=_get_lenient(data, ["enabled"], default.enabled, bool),
            smart=_get_lenient(data, ["smart"], default.smart, bool),
            duration=_get_lenient(data, ["duration"], default.duration, float),
            radius=_get_lenient(data, ["radius"], default.radius, float),
        )


@dataclass
class AppSettings:
    """Top-level configuration container for AirCursor."""

    CURRENT_VERSION: int = 3
    currentVersion: int = CURRENT_VERSION

    version: int = CURRENT_VERSION
    pointer: PointerSettings = field(default_factory=PointerSettings)
    gestures: GestureSettings = field(default_factory=GestureSettings)
    dwell: DwellSettings = field(default_factory=DwellSettings)
    actions: ActionMap = field(default_factory=ActionMap)
    stem_controls_enabled: bool = True
    keep_audio_route_active: bool = True
    route_audio_to_headphones: bool = True
    show_hud: bool = True
    show_click_pulse: bool = True
    has_completed_onboarding: bool = False
    check_for_updates: bool = True
    skipped_update_version: Optional[str] = None

    # CamelCase property aliases matching Swift API
    @property
    def stemControlsEnabled(self) -> bool:
        return self.stem_controls_enabled

    @stemControlsEnabled.setter
    def stemControlsEnabled(self, val: bool) -> None:
        self.stem_controls_enabled = val

    @property
    def keepAudioRouteActive(self) -> bool:
        return self.keep_audio_route_active

    @keepAudioRouteActive.setter
    def keepAudioRouteActive(self, val: bool) -> None:
        self.keep_audio_route_active = val

    @property
    def routeAudioToHeadphones(self) -> bool:
        return self.route_audio_to_headphones

    @routeAudioToHeadphones.setter
    def routeAudioToHeadphones(self, val: bool) -> None:
        self.route_audio_to_headphones = val

    @property
    def showHUD(self) -> bool:
        return self.show_hud

    @showHUD.setter
    def showHUD(self, val: bool) -> None:
        self.show_hud = val

    @property
    def showClickPulse(self) -> bool:
        return self.show_click_pulse

    @showClickPulse.setter
    def showClickPulse(self, val: bool) -> None:
        self.show_click_pulse = val

    @property
    def hasCompletedOnboarding(self) -> bool:
        return self.has_completed_onboarding

    @hasCompletedOnboarding.setter
    def hasCompletedOnboarding(self, val: bool) -> None:
        self.has_completed_onboarding = val

    @property
    def checkForUpdates(self) -> bool:
        return self.check_for_updates

    @checkForUpdates.setter
    def checkForUpdates(self, val: bool) -> None:
        self.check_for_updates = val

    @property
    def skippedUpdateVersion(self) -> Optional[str]:
        return self.skipped_update_version

    @skippedUpdateVersion.setter
    def skippedUpdateVersion(self, val: Optional[str]) -> None:
        self.skipped_update_version = val

    def migrated(self) -> AppSettings:
        """Upgrades settings saved by older builds."""
        s = copy.deepcopy(self)
        if s.version < 2:
            # v2: smart hover click becomes the default hands-free tap, and nods are
            # measured in degrees (smaller default).
            s.dwell = DwellSettings()
            s.gestures.nod_amplitude = GestureSettings().nod_amplitude
        if s.version < 3:
            # v3: shake needs bigger, repeated swings so glancing around never pauses.
            s.gestures.shake_amplitude = GestureSettings().shake_amplitude
            s.gestures.shake_window = GestureSettings().shake_window
        s.version = self.CURRENT_VERSION
        return s

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "pointer": self.pointer.to_dict(),
            "gestures": self.gestures.to_dict(),
            "dwell": self.dwell.to_dict(),
            "actions": self.actions.to_dict(),
            "stemControlsEnabled": self.stem_controls_enabled,
            "keepAudioRouteActive": self.keep_audio_route_active,
            "routeAudioToHeadphones": self.route_audio_to_headphones,
            "showHUD": self.show_hud,
            "showClickPulse": self.show_click_pulse,
            "hasCompletedOnboarding": self.has_completed_onboarding,
            "checkForUpdates": self.check_for_updates,
            "skippedUpdateVersion": self.skipped_update_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppSettings:
        default = cls()
        if not isinstance(data, dict):
            return default

        # Note: missing version in JSON defaults to 1 in Swift (v1 unversioned config)
        version_val = _get_lenient(data, ["version"], 1, int)
        pointer_data = data.get("pointer", {})
        gestures_data = data.get("gestures", {})
        dwell_data = data.get("dwell", {})
        actions_data = data.get("actions", {})

        return cls(
            version=version_val,
            pointer=PointerSettings.from_dict(pointer_data) if isinstance(pointer_data, dict) else default.pointer,
            gestures=GestureSettings.from_dict(gestures_data)
            if isinstance(gestures_data, dict)
            else default.gestures,
            dwell=DwellSettings.from_dict(dwell_data) if isinstance(dwell_data, dict) else default.dwell,
            actions=ActionMap.from_dict(actions_data) if isinstance(actions_data, dict) else default.actions,
            stem_controls_enabled=_get_lenient(
                data, ["stemControlsEnabled", "stem_controls_enabled"], default.stem_controls_enabled, bool
            ),
            keep_audio_route_active=_get_lenient(
                data, ["keepAudioRouteActive", "keep_audio_route_active"], default.keep_audio_route_active, bool
            ),
            route_audio_to_headphones=_get_lenient(
                data,
                ["routeAudioToHeadphones", "route_audio_to_headphones"],
                default.route_audio_to_headphones,
                bool,
            ),
            show_hud=_get_lenient(data, ["showHUD", "show_hud"], default.show_hud, bool),
            show_click_pulse=_get_lenient(
                data, ["showClickPulse", "show_click_pulse"], default.show_click_pulse, bool
            ),
            has_completed_onboarding=_get_lenient(
                data, ["hasCompletedOnboarding", "has_completed_onboarding"], default.has_completed_onboarding, bool
            ),
            check_for_updates=_get_lenient(
                data, ["checkForUpdates", "check_for_updates"], default.check_for_updates, bool
            ),
            skipped_update_version=_get_lenient(
                data, ["skippedUpdateVersion", "skipped_update_version"], None, str
            ),
        )

    @classmethod
    def from_json(cls, json_str: str) -> AppSettings:
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception:
            return cls()
