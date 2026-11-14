"""AirCursor Windows HUD Overlay.

A transparent, click-through, always-on-top HUD overlay window for Windows using ctypes / Win32 GDI:
- Extended styles: WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
- Click-through: never intercepts user mouse clicks, scroll events, or keyboard focus
- Dwell Progress Ring: smooth expanding circular progress arc around the cursor as dwell time elapses
- Click Feedback Pulse: expanding circle animation on click
- HUD Toast Notifications: pill badge with symbols and status text (e.g., "Tracking on", "Recentered")
- Zero lag double-buffered GDI rendering
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import queue
import threading
import time
from typing import Optional, Tuple

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Set proper 64-bit argument/return types for Win32 functions
LRESULT = ctypes.c_int64
HWND = ctypes.c_void_p
UINT = ctypes.c_uint32
WPARAM = ctypes.c_uint64
LPARAM = ctypes.c_int64

user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = wintypes.BOOL

user32.SetLayeredWindowAttributes.argtypes = [HWND, wintypes.COLORREF, wintypes.BYTE, wintypes.DWORD]
user32.SetLayeredWindowAttributes.restype = wintypes.BOOL

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

# Window Styles
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

LWA_COLORKEY = 0x00000001
SW_SHOWNOACTIVATE = 4
WM_DESTROY = 0x0002
WM_USER_RENDER = 0x0400 + 1

# System Metrics
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HANDLE),
    ]


class OverlayController:
    """Controls the transparent HUD overlay displaying dwell progress and system toasts."""

    CLASS_NAME = "AirCursorOverlayWindow"

    def __init__(self, enabled: bool = True):
        self.enabled: bool = enabled
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._ready_event = threading.Event()
        self._wnd_proc_ref = None

        # State to render
        self._lock = threading.Lock()
        self._dwell_progress: Optional[float] = None
        self._dwell_pos: Tuple[int, int] = (0, 0)
        self._pulse_start: Optional[float] = None
        self._pulse_pos: Tuple[int, int] = (0, 0)
        self._toast_text: Optional[str] = None
        self._toast_until: float = 0.0

        if self.enabled:
            self.start()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._ready_event.clear()
        self._thread = threading.Thread(
            target=self._window_thread, daemon=True, name="AirCursor-OverlayHUD"
        )
        self._thread.start()
        self._ready_event.wait(timeout=1.5)

    def close(self) -> None:
        """Closes the overlay window."""
        self._running = False
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._hwnd = None
        self._thread = None

    def update_dwell(
        self, progress: Optional[float], x: float, y: float
    ) -> None:
        """Updates dwell click progress (0.0 to 1.0 or None) at cursor position (x, y)."""
        if not self.enabled or not self._hwnd:
            return
        with self._lock:
            self._dwell_progress = progress
            self._dwell_pos = (int(round(x)), int(round(y)))
        user32.PostMessageW(self._hwnd, WM_USER_RENDER, 0, 0)

    def pulse(self, x: float, y: float) -> None:
        """Triggers click ripple pulse feedback at (x, y)."""
        if not self.enabled or not self._hwnd:
            return
        with self._lock:
            self._pulse_start = time.time()
            self._pulse_pos = (int(round(x)), int(round(y)))
        user32.PostMessageW(self._hwnd, WM_USER_RENDER, 0, 0)

    def show_toast(
        self, text: str, symbol: str = "🎯", duration: float = 1.8
    ) -> None:
        """Displays a HUD notification pill banner on screen."""
        if not self.enabled or not self._hwnd:
            return
        display_str = f"{symbol}  {text}" if symbol else text
        with self._lock:
            self._toast_text = display_str
            self._toast_until = time.time() + duration
        user32.PostMessageW(self._hwnd, WM_USER_RENDER, 0, 0)

    def hide(self) -> None:
        """Clears all dwell rings, pulses, and notifications."""
        if not self._hwnd:
            return
        with self._lock:
            self._dwell_progress = None
            self._pulse_start = None
            self._toast_text = None
        user32.PostMessageW(self._hwnd, WM_USER_RENDER, 0, 0)

    def _window_thread(self) -> None:
        hinstance = kernel32.GetModuleHandleW(None)

        def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_USER_RENDER:
                self._render()
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(_wnd_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinstance
        wc.lpszClassName = self.CLASS_NAME
        wc.hbrBackground = gdi32.GetStockObject(4)  # BLACK_BRUSH = 4 (0 is WHITE_BRUSH!)
        user32.RegisterClassExW(ctypes.byref(wc))

        # Virtual Screen covers all monitors
        vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if vw <= 0 or vh <= 0:
            vw = user32.GetSystemMetrics(0)
            vh = user32.GetSystemMetrics(1)
            vx, vy = 0, 0

        self._vx, self._vy, self._vw, self._vh = vx, vy, vw, vh

        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOPMOST
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )

        self._hwnd = user32.CreateWindowExW(
            ex_style,
            self.CLASS_NAME,
            "AirCursor HUD",
            WS_POPUP,
            vx,
            vy,
            vw,
            vh,
            None,
            None,
            hinstance,
            None,
        )

        # Set transparent color key: black (RGB 0, 0, 0) is 100% transparent
        user32.SetLayeredWindowAttributes(self._hwnd, 0x00000000, 255, LWA_COLORKEY)
        user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)

        self._ready_event.set()

        # Window message pump with timer for pulse/toast animation updates
        msg = wintypes.MSG()
        last_anim_check = time.time()

        while self._running:
            # Check for messages
            while user32.PeekMessageW(ctypes.byref(msg), self._hwnd, 0, 0, 1):
                if msg.message == 0x0012:  # WM_QUIT
                    self._running = False
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            now = time.time()
            needs_anim = False
            with self._lock:
                if self._pulse_start and (now - self._pulse_start < 0.25):
                    needs_anim = True
                elif self._pulse_start:
                    self._pulse_start = None
                    needs_anim = True

                if self._toast_text and now < self._toast_until:
                    pass
                elif self._toast_text:
                    self._toast_text = None
                    needs_anim = True

            if needs_anim:
                self._render()

            time.sleep(0.016)  # ~60 Hz animation cadence

        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        user32.UnregisterClassW(self.CLASS_NAME, hinstance)

    def _render(self) -> None:
        """Paints the current HUD overlay states into a backbuffer and blits."""
        if not self._hwnd:
            return

        with self._lock:
            dwell_prog = self._dwell_progress
            dx, dy = self._dwell_pos
            pulse_start = self._pulse_start
            px, py = self._pulse_pos
            toast_text = self._toast_text
            toast_until = self._toast_until

        now = time.time()
        # Adjust screen offset for multi-monitor virtual screen
        dx -= self._vx
        dy -= self._vy
        px -= self._vx
        py -= self._vy

        hdc = user32.GetDC(self._hwnd)
        if not hdc:
            return

        memdc = gdi32.CreateCompatibleDC(hdc)
        hbmp = gdi32.CreateCompatibleBitmap(hdc, self._vw, self._vh)
        old_bmp = gdi32.SelectObject(memdc, hbmp)

        # Clear background to black (transparent colorkey)
        black_brush = gdi32.GetStockObject(4)  # BLACK_BRUSH = 4 (0 is WHITE_BRUSH!)
        rect = wintypes.RECT(0, 0, self._vw, self._vh)
        user32.FillRect(memdc, ctypes.byref(rect), black_brush)

        null_brush = gdi32.GetStockObject(5)  # NULL_BRUSH
        old_brush = gdi32.SelectObject(memdc, null_brush)

        # 1. Dwell Progress Ring
        if dwell_prog is not None:
            r = 22
            # Faint background track
            track_pen = gdi32.CreatePen(0, 2, 0x00444444)  # Dark Gray
            gdi32.SelectObject(memdc, track_pen)
            gdi32.Ellipse(memdc, dx - r, dy - r, dx + r, dy + r)
            gdi32.DeleteObject(track_pen)

            # Center dot
            dot_brush = gdi32.CreateSolidBrush(0x00FFE500)  # Cyan
            old_b = gdi32.SelectObject(memdc, dot_brush)
            gdi32.Ellipse(memdc, dx - 2, dy - 2, dx + 2, dy + 2)
            gdi32.SelectObject(memdc, old_b)
            gdi32.DeleteObject(dot_brush)

            # Progress arc
            prog = min(max(dwell_prog, 0.0), 1.0)
            if prog > 0.01:
                arc_pen = gdi32.CreatePen(0, 4, 0x00FFE500)  # Bright Cyan (BGR: 00 E5 FF)
                gdi32.SelectObject(memdc, arc_pen)
                # AngleArc starts at top (90 deg) and sweeps clockwise (-360 * prog)
                start_angle = 90.0
                sweep_angle = -float(prog * 360.0)
                # Move to start of arc
                rad = math.radians(start_angle)
                sx = int(dx + r * math.cos(rad))
                sy = int(dy - r * math.sin(rad))
                gdi32.MoveToEx(memdc, sx, sy, None)
                gdi32.AngleArc(
                    memdc,
                    dx,
                    dy,
                    r,
                    ctypes.c_float(start_angle),
                    ctypes.c_float(sweep_angle),
                )
                gdi32.DeleteObject(arc_pen)

        # 2. Click Feedback Pulse
        if pulse_start and (now - pulse_start < 0.22):
            t = (now - pulse_start) / 0.22
            pr = int(10 + t * 28)
            pulse_pen = gdi32.CreatePen(0, 3, 0x00FFFFFF)  # White/Bright Cyan
            gdi32.SelectObject(memdc, pulse_pen)
            gdi32.Ellipse(memdc, px - pr, py - pr, px + pr, py + pr)
            gdi32.DeleteObject(pulse_pen)

        # 3. Toast Notification Banner
        if toast_text and (now < toast_until):
            banner_w = 340
            banner_h = 42
            bx = (self._vw - banner_w) // 2
            by = 48  # 48px from top of screen

            # Dark rounded card background
            bg_brush = gdi32.CreateSolidBrush(0x00221E1A)  # Deep Charcoal
            border_pen = gdi32.CreatePen(0, 2, 0x00665544)
            gdi32.SelectObject(memdc, bg_brush)
            gdi32.SelectObject(memdc, border_pen)
            gdi32.RoundRect(
                memdc, bx, by, bx + banner_w, by + banner_h, 16, 16
            )
            gdi32.DeleteObject(bg_brush)
            gdi32.DeleteObject(border_pen)

            # Text
            gdi32.SetBkMode(memdc, 1)  # TRANSPARENT
            gdi32.SetTextColor(memdc, 0x00FFFFFF)  # White

            hfont = gdi32.CreateFontW(
                17,
                0,
                0,
                0,
                700,
                0,
                0,
                0,
                1,
                0,
                0,
                5,
                0,
                "Segoe UI",
            )
            old_font = gdi32.SelectObject(memdc, hfont)

            text_rect = wintypes.RECT(bx, by + 10, bx + banner_w, by + banner_h)
            DT_CENTER = 0x0001
            DT_SINGLELINE = 0x0020
            user32.DrawTextW(
                memdc,
                toast_text,
                -1,
                ctypes.byref(text_rect),
                DT_CENTER | DT_SINGLELINE,
            )
            gdi32.SelectObject(memdc, old_font)
            gdi32.DeleteObject(hfont)

        # Blit backbuffer onto screen
        gdi32.BitBlt(
            hdc,
            0,
            0,
            self._vw,
            self._vh,
            memdc,
            0,
            0,
            0x00CC0020,  # SRCCOPY
        )

        # Cleanup GDI handles
        gdi32.SelectObject(memdc, old_brush)
        gdi32.SelectObject(memdc, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(self._hwnd, hdc)
