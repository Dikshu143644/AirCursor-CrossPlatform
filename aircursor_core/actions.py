"""Actions and trigger bindings.

Matches AirCursor/Sources/AirCursorCore/Actions.swift.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .gestures import HeadGesture


class Trigger(str, Enum):
    """Something the user does with their AirPods / head.

    Matches Swift Trigger enum.
    """

    STEM_SINGLE = "stemSingle"
    STEM_DOUBLE = "stemDouble"
    STEM_TRIPLE = "stemTriple"
    NOD = "nod"
    SHAKE = "shake"
    TILT_LEFT = "tiltLeft"
    TILT_RIGHT = "tiltRight"
    DWELL = "dwell"

    @property
    def id(self) -> str:
        return self.value

    @property
    def display_name(self) -> str:
        names = {
            Trigger.STEM_SINGLE: "Press stem once",
            Trigger.STEM_DOUBLE: "Press stem twice",
            Trigger.STEM_TRIPLE: "Press stem three times",
            Trigger.NOD: "Nod",
            Trigger.SHAKE: "Shake head",
            Trigger.TILT_LEFT: "Tilt head left",
            Trigger.TILT_RIGHT: "Tilt head right",
            Trigger.DWELL: "Hover (rest the pointer)",
        }
        return names.get(self, self.value)

    displayName = display_name

    @property
    def is_stem(self) -> bool:
        return self in (Trigger.STEM_SINGLE, Trigger.STEM_DOUBLE, Trigger.STEM_TRIPLE)

    isStem = is_stem

    @property
    def head_gesture(self) -> Optional[HeadGesture]:
        if self == Trigger.NOD:
            return HeadGesture.NOD
        elif self == Trigger.SHAKE:
            return HeadGesture.SHAKE
        elif self == Trigger.TILT_LEFT:
            return HeadGesture.TILT_LEFT
        elif self == Trigger.TILT_RIGHT:
            return HeadGesture.TILT_RIGHT
        return None

    headGesture = head_gesture

    @classmethod
    def from_head_gesture(cls, gesture: HeadGesture) -> Trigger:
        if gesture == HeadGesture.NOD:
            return cls.NOD
        elif gesture == HeadGesture.SHAKE:
            return cls.SHAKE
        elif gesture == HeadGesture.TILT_LEFT:
            return cls.TILT_LEFT
        elif gesture == HeadGesture.TILT_RIGHT:
            return cls.TILT_RIGHT
        raise ValueError(f"Unknown head gesture: {gesture}")

    @classmethod
    def parse(cls, value: Any) -> Optional[Trigger]:
        if isinstance(value, Trigger):
            return value
        if isinstance(value, str):
            for t in cls:
                if t.value == value or t.name == value:
                    return t
        return None


# Aliases on Trigger
Trigger.stemSingle = Trigger.STEM_SINGLE  # type: ignore
Trigger.stemDouble = Trigger.STEM_DOUBLE  # type: ignore
Trigger.stemTriple = Trigger.STEM_TRIPLE  # type: ignore
Trigger.nod = Trigger.NOD  # type: ignore
Trigger.shake = Trigger.SHAKE  # type: ignore
Trigger.tiltLeft = Trigger.TILT_LEFT  # type: ignore
Trigger.tiltRight = Trigger.TILT_RIGHT  # type: ignore
Trigger.dwell = Trigger.DWELL  # type: ignore


class PointerAction(str, Enum):
    """What AirCursor does in response to a trigger.

    Matches Swift PointerAction enum.
    """

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
    def id(self) -> str:
        return self.value

    @property
    def display_name(self) -> str:
        names = {
            PointerAction.NONE: "Do nothing",
            PointerAction.LEFT_CLICK: "Left click",
            PointerAction.RIGHT_CLICK: "Right click",
            PointerAction.DOUBLE_CLICK: "Double click",
            PointerAction.MIDDLE_CLICK: "Middle click",
            PointerAction.TOGGLE_DRAG: "Start / drop drag",
            PointerAction.TOGGLE_SCROLL_MODE: "Toggle scroll mode",
            PointerAction.TOGGLE_TRACKING: "Pause / resume tracking",
            PointerAction.RECENTER: "Recenter cursor",
            PointerAction.MISSION_CONTROL: "Mission Control",
            PointerAction.APP_WINDOWS: "App windows",
            PointerAction.PREVIOUS_SPACE: "Previous Space",
            PointerAction.NEXT_SPACE: "Next Space",
            PointerAction.BACK: "Back (⌘[)",
            PointerAction.FORWARD: "Forward (⌘])",
            PointerAction.SCREENSHOT: "Screenshot tool",
        }
        return names.get(self, self.value)

    displayName = display_name

    @property
    def is_click(self) -> bool:
        """Actions that put a mouse button event on screen."""
        return self in (
            PointerAction.LEFT_CLICK,
            PointerAction.RIGHT_CLICK,
            PointerAction.DOUBLE_CLICK,
            PointerAction.MIDDLE_CLICK,
            PointerAction.TOGGLE_DRAG,
        )

    isClick = is_click

    @classmethod
    def parse(cls, value: Any) -> Optional[PointerAction]:
        if isinstance(value, PointerAction):
            return value
        if isinstance(value, str):
            for a in cls:
                if a.value == value or a.name == value:
                    return a
        return None


# Aliases on PointerAction
PointerAction.none = PointerAction.NONE  # type: ignore
PointerAction.leftClick = PointerAction.LEFT_CLICK  # type: ignore
PointerAction.rightClick = PointerAction.RIGHT_CLICK  # type: ignore
PointerAction.doubleClick = PointerAction.DOUBLE_CLICK  # type: ignore
PointerAction.middleClick = PointerAction.MIDDLE_CLICK  # type: ignore
PointerAction.toggleDrag = PointerAction.TOGGLE_DRAG  # type: ignore
PointerAction.toggleScrollMode = PointerAction.TOGGLE_SCROLL_MODE  # type: ignore
PointerAction.toggleTracking = PointerAction.TOGGLE_TRACKING  # type: ignore
PointerAction.recenter = PointerAction.RECENTER  # type: ignore
PointerAction.missionControl = PointerAction.MISSION_CONTROL  # type: ignore
PointerAction.appWindows = PointerAction.APP_WINDOWS  # type: ignore
PointerAction.previousSpace = PointerAction.PREVIOUS_SPACE  # type: ignore
PointerAction.nextSpace = PointerAction.NEXT_SPACE  # type: ignore
PointerAction.back = PointerAction.BACK  # type: ignore
PointerAction.forward = PointerAction.FORWARD  # type: ignore
PointerAction.screenshot = PointerAction.SCREENSHOT  # type: ignore


# Groupings for UI menus matching Swift PointerAction.groups
ACTION_GROUPS = [
    ("", [PointerAction.NONE]),
    (
        "Mouse",
        [
            PointerAction.LEFT_CLICK,
            PointerAction.RIGHT_CLICK,
            PointerAction.DOUBLE_CLICK,
            PointerAction.MIDDLE_CLICK,
            PointerAction.TOGGLE_DRAG,
        ],
    ),
    (
        "AirCursor",
        [
            PointerAction.TOGGLE_SCROLL_MODE,
            PointerAction.TOGGLE_TRACKING,
            PointerAction.RECENTER,
        ],
    ),
    (
        "System",
        [
            PointerAction.MISSION_CONTROL,
            PointerAction.APP_WINDOWS,
            PointerAction.PREVIOUS_SPACE,
            PointerAction.NEXT_SPACE,
            PointerAction.BACK,
            PointerAction.FORWARD,
            PointerAction.SCREENSHOT,
        ],
    ),
]


class ActionMap:
    """Trigger -> action bindings. Unknown or missing entries fall back to defaults.

    Matches Swift ActionMap struct.
    """

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
    defaults = DEFAULTS

    def __init__(self, bindings: Optional[Dict[Any, Any]] = None):
        self._bindings: Dict[Trigger, PointerAction] = dict(self.DEFAULTS)
        if bindings:
            for k, v in bindings.items():
                t = Trigger.parse(k)
                a = PointerAction.parse(v)
                if t is not None and a is not None:
                    self._bindings[t] = a

    def __getitem__(self, trigger: Any) -> PointerAction:
        t = Trigger.parse(trigger)
        if t is None:
            return PointerAction.NONE
        return self._bindings.get(t, self.DEFAULTS.get(t, PointerAction.NONE))

    def __setitem__(self, trigger: Any, action: Any) -> None:
        t = Trigger.parse(trigger)
        a = PointerAction.parse(action)
        if t is None:
            raise KeyError(f"Invalid trigger: {trigger}")
        if a is None:
            raise ValueError(f"Invalid action: {action}")
        self._bindings[t] = a

    @property
    def enabled_head_gestures(self) -> Set[HeadGesture]:
        """Head gestures that should be detected at all (bound to an action other than .none)."""
        result: Set[HeadGesture] = set()
        for t in Trigger:
            g = t.head_gesture
            if g is not None and self[t] != PointerAction.NONE:
                result.add(g)
        return result

    enabledHeadGestures = enabled_head_gestures

    def triggers(self, action: Any) -> List[Trigger]:
        """Returns all triggers mapped to the given action."""
        target_action = PointerAction.parse(action)
        return [t for t in Trigger if self[t] == target_action]

    @property
    def head_gesture_can_toggle_tracking(self) -> bool:
        """True if some head gesture can resume tracking while paused."""
        return any(t.head_gesture is not None for t in self.triggers(PointerAction.TOGGLE_TRACKING))

    headGestureCanToggleTracking = head_gesture_can_toggle_tracking

    @property
    def stem_can_toggle_tracking(self) -> bool:
        """True if some stem press can resume tracking while paused."""
        return any(t.is_stem for t in self.triggers(PointerAction.TOGGLE_TRACKING))

    stemCanToggleTracking = stem_can_toggle_tracking

    def to_dict(self) -> Dict[str, str]:
        return {t.value: self[t].value for t in Trigger}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ActionMap:
        result = cls()
        if isinstance(data, dict):
            for k, v in data.items():
                t = Trigger.parse(k)
                a = PointerAction.parse(v)
                if t is not None and a is not None:
                    result[t] = a
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> ActionMap:
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except Exception:
            return cls()

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, ActionMap):
            return all(self[t] == other[t] for t in Trigger)
        return False

    def __repr__(self) -> str:
        return f"ActionMap({self.to_dict()})"
