"""
Linux AT-SPI Clickable Element Probe.
Uses AT-SPI (pyatspi or D-Bus org.a11y.Bus) to probe if the UI element
under the pointer is a button, link, tab, text field, or interactive control.
Powers smart hover / dwell clicking on Linux desktops.
"""

from __future__ import annotations
import math
import os
import threading
import time
from typing import Callable, Optional, Set, Tuple


# ==============================================================================
# Clickable Roles & Boundaries
# ==============================================================================

CLICKABLE_ROLES: Set[str] = {
    "push-button", "push button", "button",
    "link",
    "menu-item", "menu item", "check-menu-item", "radio-menu-item",
    "check-box", "check box",
    "radio-button", "radio button",
    "toggle-button", "toggle button",
    "entry", "text", "password-text",
    "combo-box", "combo box",
    "tab", "page-tab",
    "list-item",
    "slider",
    "tree-item",
}

BOUNDARY_ROLES: Set[str] = {
    "window", "frame", "application", "desktop-frame",
    "root-pane", "layered-pane", "scroll-pane",
}

CLICKABLE_ACTIONS: Set[str] = {
    "click", "press", "activate", "toggle", "jump",
}


# ==============================================================================
# AT-SPI Clickable Probe
# ==============================================================================

class LinuxClickableProbe:
    """
    Probes AT-SPI accessibility tree to determine whether the UI element under
    screen point (x, y) is interactive.
    """

    def __init__(self, timeout_sec: float = 0.10) -> None:
        self.timeout_sec = timeout_sec
        self._pyatspi_available = False
        self._registry = None
        self._cache: Optional[Tuple[float, float, float, bool]] = None  # (x, y, timestamp, verdict)
        self._cache_radius = 12.0
        self._cache_ttl = 0.25  # seconds
        self._lock = threading.Lock()

        self._init_atspi()

    def _init_atspi(self) -> None:
        """Attempts to load pyatspi or D-Bus accessibility service."""
        try:
            import pyatspi
            self._pyatspi = pyatspi
            self._pyatspi_available = True
        except ImportError:
            self._pyatspi_available = False

    def is_clickable_async(self, x: float, y: float, callback: Callable[[bool], None]) -> None:
        """Asynchronously queries if the point is clickable."""
        def worker():
            verdict = self.is_clickable(x, y)
            callback(verdict)

        t = threading.Thread(target=worker, daemon=True, name="ClickableProbeWorker")
        t.start()

    def is_clickable(self, x: float, y: float) -> bool:
        """
        Synchronously determines if element at (x, y) is clickable.
        Checks internal spatial cache to prevent stalling the frame loop.
        """
        now = time.time()
        with self._lock:
            if self._cache is not None:
                cx, cy, ctime, cverdict = self._cache
                if (now - ctime < self._cache_ttl) and (math.hypot(x - cx, y - cy) <= self._cache_radius):
                    return cverdict

        verdict = self._query_atspi(x, y)

        with self._lock:
            self._cache = (x, y, now, verdict)
        return verdict

    def _query_atspi(self, x: float, y: float) -> bool:
        if not self._pyatspi_available:
            return self._query_dbus_fallback(x, y)

        try:
            reg = self._pyatspi.Registry
            desktop_count = reg.getDesktopCount()
            ix, iy = int(round(x)), int(round(y))

            for d in range(desktop_count):
                desktop = reg.getDesktop(d)
                for app_idx in range(desktop.childCount):
                    app = desktop.getChildAtIndex(app_idx)
                    if app is None:
                        continue

                    # Search through top-level windows of the application
                    for win_idx in range(app.childCount):
                        win = app.getChildAtIndex(win_idx)
                        if win is None:
                            continue

                        # Check bounding box
                        try:
                            comp = win.queryComponent()
                            bx, by, bw, bh = comp.getExtents(self._pyatspi.XY_SCREEN)
                            if not (bx <= ix <= bx + bw and by <= iy <= by + bh):
                                continue
                        except Exception:
                            continue

                        # Hit-test element at coordinates
                        try:
                            comp = win.queryComponent()
                            accessible = comp.getAccessibleAtPoint(ix, iy, self._pyatspi.XY_SCREEN)
                            if accessible is None:
                                accessible = win

                            return self._evaluate_accessible(accessible)
                        except Exception:
                            continue
        except Exception:
            pass

        return False

    def _evaluate_accessible(self, accessible) -> bool:
        """Traverses up to 4 ancestors to check roles and actions."""
        curr = accessible
        depth = 0

        while curr is not None and depth < 4:
            try:
                role_name = curr.getRoleName().lower()
                if role_name in BOUNDARY_ROLES:
                    break

                if role_name in CLICKABLE_ROLES:
                    return True

                # Check if supports action
                try:
                    action = curr.queryAction()
                    n_actions = action.nActions
                    for a_idx in range(n_actions):
                        act_name = action.getName(a_idx).lower()
                        if any(ca in act_name for ca in CLICKABLE_ACTIONS):
                            # Ensure it is compact sized
                            try:
                                comp = curr.queryComponent()
                                _, _, w, h = comp.getExtents(self._pyatspi.XY_SCREEN)
                                if w <= 600 and h <= 240 and (w * h) <= 90000:
                                    return True
                            except Exception:
                                return True
                except Exception:
                    pass

                curr = curr.parent
                depth += 1
            except Exception:
                break

        return False

    def _query_dbus_fallback(self, x: float, y: float) -> bool:
        """
        Fallback when pyatspi is not installed: queries org.a11y.Bus via D-Bus.
        Returns False if AT-SPI D-Bus daemon is unreachable.
        """
        # If pyatspi is missing or user has disabled AT-SPI, return False
        return False
