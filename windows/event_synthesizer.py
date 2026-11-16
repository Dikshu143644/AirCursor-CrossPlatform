"""AirCursor Windows Event Synthesizer.

Provides high-performance Win32 input injection via ctypes / SendInput:
- Absolute and relative mouse cursor movement across multi-monitor setups
- Mouse button down/up, click, double click, middle click
- Persistent drag toggle (holding left mouse down across moves until released)
- Vertical (wheel) and horizontal (h-wheel) scrolling
- Keyboard key strokes, modifiers, and system shortcut macros
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import webbrowser

# Win32 Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

# Mouse flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000

WHEEL_DELTA = 120

# Keyboard flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Virtual Screen Metrics
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# Virtual Key Codes
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt key
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_PRIOR = 0x21  # Page Up
VK_NEXT = 0x22   # Page Down
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_SNAPSHOT = 0x2C  # PrintScreen
VK_F11 = 0x7A
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_BROWSER_BACK = 0xA6
VK_BROWSER_FORWARD = 0xA7
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


# 64-bit aligned Win32 Structures
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


MonitorEnumProc = ctypes.WINFUNCTYPE(
    ctypes.c_int,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(RECT),
    wintypes.LPARAM,
)


user32 = ctypes.windll.user32
user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


class EventSynthesizer:
    """Win32 SendInput input injection engine for AirCursor."""

    def __init__(self):
        self._is_left_down: bool = False
        self._is_right_down: bool = False
        self._is_middle_down: bool = False

    @property
    def is_left_button_down(self) -> bool:
        return self._is_left_down

    @property
    def is_right_button_down(self) -> bool:
        return self._is_right_down

    @property
    def is_middle_button_down(self) -> bool:
        return self._is_middle_down

    @staticmethod
    def current_location() -> Tuple[int, int]:
        """Returns the current mouse cursor coordinates (x, y) in screen space."""
        pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y
        return 0, 0

    @staticmethod
    def get_screen_bounds() -> Tuple[int, int, int, int]:
        """Returns (x, y, width, height) of the virtual desktop covering all monitors."""
        x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if w <= 0 or h <= 0:
            w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
            h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            x, y = 0, 0
        return x, y, w, h

    @staticmethod
    def get_monitors() -> List[Dict[str, Any]]:
        """Returns list of connected display monitors with their bounding rectangles and primary status."""
        monitors: List[Dict[str, Any]] = []

        try:
            def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                info = MONITORINFOEXW()
                info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                if user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
                    w = int(info.rcMonitor.right - info.rcMonitor.left)
                    h = int(info.rcMonitor.bottom - info.rcMonitor.top)
                    monitors.append({
                        "id": len(monitors),
                        "name": str(info.szDevice) if info.szDevice else f"Display {len(monitors) + 1}",
                        "x": int(info.rcMonitor.left),
                        "y": int(info.rcMonitor.top),
                        "width": w,
                        "height": h,
                        "primary": bool(info.dwFlags & 1),
                    })
                return 1

            cb = MonitorEnumProc(_callback)
            user32.EnumDisplayMonitors(None, None, cb, 0)
        except Exception:
            pass

        if not monitors:
            vx, vy, vw, vh = EventSynthesizer.get_screen_bounds()
            monitors.append({
                "id": 0,
                "name": "Display 1",
                "x": vx,
                "y": vy,
                "width": vw,
                "height": vh,
                "primary": True,
            })
        return monitors

    def switch_monitor(self, monitor_id: int) -> bool:
        """Jumps the cursor to the center of the specified monitor index."""
        monitors = self.get_monitors()
        for mon in monitors:
            if mon["id"] == int(monitor_id):
                cx = mon["x"] + mon["width"] // 2
                cy = mon["y"] + mon["height"] // 2
                self.move_to(cx, cy)
                return True
        return False

    def move_to(self, x: float, y: float, use_send_input: bool = False) -> None:
        """Moves cursor to absolute screen coordinates (x, y).

        By default uses SetCursorPos for 0-latency pixel-accurate positioning,
        with optional SendInput absolute normalized positioning for compatibility.
        """
        ix = int(round(x))
        iy = int(round(y))

        if not use_send_input:
            user32.SetCursorPos(ix, iy)
            return

        vx, vy, vw, vh = self.get_screen_bounds()
        if vw <= 0 or vh <= 0:
            user32.SetCursorPos(ix, iy)
            return

        norm_x = int(((ix - vx) * 65535) / (vw - 1)) if vw > 1 else 0
        norm_y = int(((iy - vy) * 65535) / (vh - 1)) if vh > 1 else 0

        flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dx = norm_x
        inp.mi.dy = norm_y
        inp.mi.mouseData = 0
        inp.mi.dwFlags = flags
        inp.mi.time = 0
        inp.mi.dwExtraInfo = 0
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def move_relative(self, dx: int, dy: int) -> None:
        """Moves cursor relatively by (dx, dy) pixels."""
        if dx == 0 and dy == 0:
            return
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dx = int(dx)
        inp.mi.dy = int(dy)
        inp.mi.mouseData = 0
        inp.mi.dwFlags = MOUSEEVENTF_MOVE
        inp.mi.time = 0
        inp.mi.dwExtraInfo = 0
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def left_down(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Presses and holds the left mouse button."""
        if x is not None and y is not None:
            self.move_to(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self._is_left_down = True

    def left_up(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Releases the left mouse button."""
        if x is not None and y is not None:
            self.move_to(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_LEFTUP
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self._is_left_down = False

    def right_down(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Presses and holds the right mouse button."""
        if x is not None and y is not None:
            self.move_to(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_RIGHTDOWN
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self._is_right_down = True

    def right_up(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Releases the right mouse button."""
        if x is not None and y is not None:
            self.move_to(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_RIGHTUP
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self._is_right_down = False

    def middle_down(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Presses and holds the middle mouse button."""
        if x is not None and y is not None:
            self.move_to(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_MIDDLEDOWN
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self._is_middle_down = True

    def middle_up(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Releases the middle mouse button."""
        if x is not None and y is not None:
            self.move_to(x, y)
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.mi.dwFlags = MOUSEEVENTF_MIDDLEUP
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self._is_middle_down = False

    def click(
        self,
        button: str = "left",
        x: Optional[float] = None,
        y: Optional[float] = None,
        count: int = 1,
    ) -> None:
        """Clicks a mouse button (left, right, middle) `count` times."""
        if x is not None and y is not None:
            self.move_to(x, y)

        btn = button.lower()
        if btn == "left":
            down_flag = MOUSEEVENTF_LEFTDOWN
            up_flag = MOUSEEVENTF_LEFTUP
        elif btn == "right":
            down_flag = MOUSEEVENTF_RIGHTDOWN
            up_flag = MOUSEEVENTF_RIGHTUP
        elif btn in ("middle", "center"):
            down_flag = MOUSEEVENTF_MIDDLEDOWN
            up_flag = MOUSEEVENTF_MIDDLEUP
        else:
            down_flag = MOUSEEVENTF_LEFTDOWN
            up_flag = MOUSEEVENTF_LEFTUP

        for i in range(max(1, count)):
            inputs = (INPUT * 2)()
            inputs[0].type = INPUT_MOUSE
            inputs[0].mi.dwFlags = down_flag
            inputs[1].type = INPUT_MOUSE
            inputs[1].mi.dwFlags = up_flag
            user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
            if count > 1 and i < count - 1:
                time.sleep(0.04)

    def double_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Executes a left double click."""
        self.click(button="left", x=x, y=y, count=2)

    def right_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Executes a right click."""
        self.click(button="right", x=x, y=y, count=1)

    def middle_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Executes a middle click."""
        self.click(button="middle", x=x, y=y, count=1)

    def toggle_drag(self, x: Optional[float] = None, y: Optional[float] = None) -> bool:
        """Toggles drag-lock on/off.

        If currently not dragging, holds left button down.
        If currently dragging, releases left button.
        Returns the new dragging state (True if now dragging).
        """
        if self._is_left_down:
            self.left_up(x, y)
            return False
        else:
            self.left_down(x, y)
            return True

    def release_all_buttons(self) -> None:
        """Safety release: ensures no mouse buttons remain pressed."""
        if self._is_left_down:
            self.left_up()
        if self._is_right_down:
            self.right_up()
        if self._is_middle_down:
            self.middle_up()

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        """Synthesizes mouse wheel scrolling.

        `vertical`: positive scrolls UP (away from user), negative scrolls DOWN.
        `horizontal`: positive scrolls RIGHT, negative scrolls LEFT.
        """
        inputs_list = []
        if vertical != 0:
            inp_v = INPUT()
            inp_v.type = INPUT_MOUSE
            inp_v.mi.dwFlags = MOUSEEVENTF_WHEEL
            inp_v.mi.mouseData = int(vertical * WHEEL_DELTA)
            inputs_list.append(inp_v)

        if horizontal != 0:
            inp_h = INPUT()
            inp_h.type = INPUT_MOUSE
            inp_h.mi.dwFlags = MOUSEEVENTF_HWHEEL
            inp_h.mi.mouseData = int(horizontal * WHEEL_DELTA)
            inputs_list.append(inp_h)

        if inputs_list:
            n = len(inputs_list)
            arr = (INPUT * n)(*inputs_list)
            user32.SendInput(n, arr, ctypes.sizeof(INPUT))

    def key_down(self, vk_code: int, extended: bool = False) -> None:
        """Sends key down event for virtual key `vk_code`."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk_code
        inp.ki.wScan = user32.MapVirtualKeyW(vk_code, 0)
        inp.ki.dwFlags = KEYEVENTF_EXTENDEDKEY if extended else 0
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def key_up(self, vk_code: int, extended: bool = False) -> None:
        """Sends key up event for virtual key `vk_code`."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk_code
        inp.ki.wScan = user32.MapVirtualKeyW(vk_code, 0)
        inp.ki.dwFlags = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if extended else 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def key_stroke(self, vk_code: int, modifiers: Optional[Sequence[int]] = None) -> None:
        """Types a virtual key with optional modifier keys (e.g. VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN)."""
        mods = list(modifiers) if modifiers else []
        for m in mods:
            self.key_down(m)
        time.sleep(0.01)

        self.key_down(vk_code)
        time.sleep(0.01)
        self.key_up(vk_code)

        time.sleep(0.01)
        for m in reversed(mods):
            self.key_up(m)

    # Windows System Shortcuts
    def mission_control(self) -> None:
        """Task View on Windows (Win + Tab)."""
        self.key_stroke(VK_TAB, modifiers=[VK_LWIN])

    def app_windows(self) -> None:
        """App Switcher on Windows (Alt + Tab)."""
        self.key_stroke(VK_TAB, modifiers=[VK_MENU])

    def previous_space(self) -> None:
        """Switch to previous virtual desktop (Win + Ctrl + Left)."""
        self.key_stroke(VK_LEFT, modifiers=[VK_LWIN, VK_CONTROL])

    def next_space(self) -> None:
        """Switch to next virtual desktop (Win + Ctrl + Right)."""
        self.key_stroke(VK_RIGHT, modifiers=[VK_LWIN, VK_CONTROL])

    def browser_back(self) -> None:
        """Browser Back (Alt + Left or VK_BROWSER_BACK)."""
        self.key_stroke(VK_BROWSER_BACK)

    def browser_forward(self) -> None:
        """Browser Forward (Alt + Right or VK_BROWSER_FORWARD)."""
        self.key_stroke(VK_BROWSER_FORWARD)

    def screenshot(self) -> None:
        """Snipping tool (Win + Shift + S)."""
        self.key_stroke(ord("S"), modifiers=[VK_LWIN, VK_SHIFT])

    # TV & Media Remote Controls
    def volume_up(self) -> None:
        """Increases system volume."""
        self.key_stroke(VK_VOLUME_UP)

    def volume_down(self) -> None:
        """Decreases system volume."""
        self.key_stroke(VK_VOLUME_DOWN)

    def volume_mute(self) -> None:
        """Toggles system audio mute."""
        self.key_stroke(VK_VOLUME_MUTE)

    def media_play_pause(self) -> None:
        """Toggles media playback (Play/Pause)."""
        self.key_stroke(VK_MEDIA_PLAY_PAUSE)

    def media_next(self) -> None:
        """Skips to next media track."""
        self.key_stroke(VK_MEDIA_NEXT_TRACK)

    def media_prev(self) -> None:
        """Skips to previous media track."""
        self.key_stroke(VK_MEDIA_PREV_TRACK)

    def fullscreen(self) -> None:
        """Toggles display fullscreen (F11)."""
        self.key_stroke(VK_F11)

    def show_desktop(self) -> None:
        """Minimizes all windows to show desktop (Win + D)."""
        self.key_stroke(ord("D"), modifiers=[VK_LWIN])

    def launch_app(self, app_name: str) -> bool:
        """Instant media and navigation macro launcher.
        
        Supports YouTube, Netflix, Prime Video, Web Browser, and File Explorer.
        """
        name = app_name.strip().lower()
        try:
            if name in ("youtube", "yt"):
                webbrowser.open("https://www.youtube.com")
                return True
            elif name in ("netflix", "net"):
                if sys.platform == "win32":
                    try:
                        os.startfile("netflix:")
                        return True
                    except OSError:
                        pass
                webbrowser.open("https://www.netflix.com")
                return True
            elif name in ("prime", "primevideo", "amazon_prime", "prime_video"):
                if sys.platform == "win32":
                    try:
                        os.startfile("primevideo:")
                        return True
                    except OSError:
                        pass
                webbrowser.open("https://www.primevideo.com")
                return True
            elif name in ("browser", "web", "chrome", "edge", "web_browser"):
                webbrowser.open("https://www.google.com")
                return True
            elif name in ("explorer", "files", "file_explorer"):
                if sys.platform == "win32":
                    subprocess.Popen(["explorer.exe"])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", os.path.expanduser("~")])
                else:
                    subprocess.Popen(["xdg-open", os.path.expanduser("~")])
                return True
        except Exception:
            return False
        return False

    def press_key(self, key_name: str) -> None:
        """Dispatches a named navigation key for D-pad or TV remote navigation."""
        k = key_name.strip().lower()
        key_map = {
            "up": VK_UP,
            "down": VK_DOWN,
            "left": VK_LEFT,
            "right": VK_RIGHT,
            "enter": VK_RETURN,
            "ok": VK_RETURN,
            "select": VK_RETURN,
            "return": VK_RETURN,
            "esc": VK_ESCAPE,
            "escape": VK_ESCAPE,
            "space": VK_SPACE,
            "tab": VK_TAB,
            "backspace": VK_BACK,
            "back": VK_BACK,
            "home": VK_HOME,
            "end": VK_END,
            "page_up": VK_PRIOR,
            "page_down": VK_NEXT,
            "f11": VK_F11,
        }
        if k in key_map:
            self.key_stroke(key_map[k])
        elif len(k) == 1 and k.isalnum():
            # Single character (e.g. number pad 0-9)
            self.key_stroke(ord(k.upper()))

    def type_text(self, text: str) -> None:
        """Types unicode string into the active window."""
        for ch in text:
            code = ord(ch)
            inp_down = INPUT()
            inp_down.type = INPUT_KEYBOARD
            inp_down.ki.wScan = code
            inp_down.ki.dwFlags = KEYEVENTF_UNICODE

            inp_up = INPUT()
            inp_up.type = INPUT_KEYBOARD
            inp_up.ki.wScan = code
            inp_up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

            arr = (INPUT * 2)(inp_down, inp_up)
            user32.SendInput(2, arr, ctypes.sizeof(INPUT))
            time.sleep(0.005)
