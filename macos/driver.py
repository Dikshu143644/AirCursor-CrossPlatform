"""macOS input synthesis through Apple's CoreGraphics event API.

Install on macOS with: pip install 'aircursor_core[macos]'.
Grant AirCursor Accessibility permission in System Settings before posting events.
"""
from __future__ import annotations

import math
from typing import Any, Optional

try:  # Lazy-compatible optional dependency; importing the core works off macOS.
    import Quartz as _QUARTZ
except ImportError:  # pragma: no cover - platform dependent
    _QUARTZ = None


class MacOSDriverUnavailableError(RuntimeError):
    """Raised when the native Quartz framework is unavailable."""


class MacOSEventSynthesizer:
    """CoreGraphics-backed mouse driver with a Windows/Linux-style API."""

    _BUTTONS = {
        "left": ("kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGMouseButtonLeft"),
        "right": ("kCGEventRightMouseDown", "kCGEventRightMouseUp", "kCGMouseButtonRight"),
        "middle": ("kCGEventOtherMouseDown", "kCGEventOtherMouseUp", "kCGMouseButtonCenter"),
    }

    def __init__(self, quartz: Any = None) -> None:
        self._q = _QUARTZ if quartz is None else quartz
        if self._q is None:
            raise MacOSDriverUnavailableError(
                "CoreGraphics is unavailable. On macOS install with "
                "pip install 'aircursor_core[macos]'."
            )
        self._pressed_buttons: set[str] = set()

    @staticmethod
    def _number(value: float, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be a number")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        return result

    def _post(self, event: Any) -> None:
        if event is None:
            raise RuntimeError("CoreGraphics failed to create an input event")
        self._q.CGEventPost(self._q.kCGHIDEventTap, event)

    def current_location(self) -> tuple[int, int]:
        """Return the current global cursor position in macOS display coordinates."""
        source = self._q.CGEventCreate(None)
        if source is None:
            raise RuntimeError("CoreGraphics could not read the current cursor position")
        point = self._q.CGEventGetLocation(source)
        return int(round(point.x)), int(round(point.y))

    def get_current_location(self) -> tuple[int, int]:
        """Compatibility alias matching the Linux synthesizer."""
        return self.current_location()

    def _resolve_point(
        self, x: Optional[float] = None, y: Optional[float] = None
    ) -> tuple[float, float]:
        if (x is None) != (y is None):
            raise ValueError("x and y must either both be provided or both be omitted")
        if x is None:
            px, py = self.current_location()
            return float(px), float(py)
        return self._number(x, "x"), self._number(y, "y")

    def _mouse_event(self, type_name: str, button_name: str, x: float, y: float) -> None:
        event = self._q.CGEventCreateMouseEvent(
            None,
            getattr(self._q, type_name),
            (x, y),
            getattr(self._q, button_name),
        )
        self._post(event)

    def move_to(self, x: float, y: float, use_send_input: bool = False) -> None:
        """Move the pointer to global display coordinates."""
        del use_send_input  # API compatibility with the Windows synthesizer.
        px, py = self._number(x, "x"), self._number(y, "y")
        self._mouse_event("kCGEventMouseMoved", "kCGMouseButtonLeft", px, py)

    def move_relative(self, dx: float, dy: float) -> None:
        """Move the pointer by a relative delta in display points."""
        dx_value, dy_value = self._number(dx, "dx"), self._number(dy, "dy")
        x, y = self.current_location()
        self.move_to(x + dx_value, y + dy_value)

    def _button_event(
        self, button: str, down: bool, x: Optional[float] = None, y: Optional[float] = None
    ) -> None:
        name = button.strip().lower()
        if name not in self._BUTTONS:
            raise ValueError("button must be left, right, or middle")
        px, py = self._resolve_point(x, y)
        down_type, up_type, button_type = self._BUTTONS[name]
        self._mouse_event(down_type if down else up_type, button_type, px, py)
        if down:
            self._pressed_buttons.add(name)
        else:
            self._pressed_buttons.discard(name)

    def left_down(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self._button_event("left", True, x, y)

    def left_up(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self._button_event("left", False, x, y)

    def right_down(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self._button_event("right", True, x, y)

    def right_up(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self._button_event("right", False, x, y)

    def middle_down(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self._button_event("middle", True, x, y)

    def middle_up(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self._button_event("middle", False, x, y)

    def click(
        self, button: str = "left", x: Optional[float] = None,
        y: Optional[float] = None, count: int = 1
    ) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be a positive integer")
        for _ in range(count):
            self._button_event(button, True, x, y)
            self._button_event(button, False, x, y)

    def double_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self.click("left", x, y, count=2)

    def right_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self.click("right", x, y)

    def middle_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        self.click("middle", x, y)

    def release_all_buttons(self) -> None:
        """Release any button held by this driver, avoiding a stuck drag."""
        for button in tuple(self._pressed_buttons):
            self._button_event(button, False)

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        """Scroll in line units; positive vertical values scroll upward."""
        if isinstance(vertical, bool) or not isinstance(vertical, int):
            raise TypeError("vertical scroll must be an integer")
        if isinstance(horizontal, bool) or not isinstance(horizontal, int):
            raise TypeError("horizontal scroll must be an integer")
        event = self._q.CGEventCreateScrollWheelEvent(
            None, self._q.kCGScrollEventUnitLine, 2, vertical, horizontal
        )
        self._post(event)


# Explicit alias for integrations that prefer a platform-driver name.
MacOSInputDriver = MacOSEventSynthesizer
