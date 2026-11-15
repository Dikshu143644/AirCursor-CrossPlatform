"""AirCursor Windows HUD Overlay.

A lightweight, transparent, click-through HUD overlay system for Windows:
- Dedicated 72x72 floating popup window centered at cursor (x - 36, y - 36) for dwell progress and pulse
- Dedicated compact 280x42 notification toast window at top-center of screen
- Extended styles: WS_POPUP, WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
- Click-through: never intercepts user mouse clicks, scroll events, or keyboard focus
- Zero screen coverage when idle: windows start hidden (SW_HIDE) and only show when active
- Zero DWM desktop interference and zero compositor lag
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import threading
import time
from typing import Optional, Tuple

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# 64-bit compatible Win32 types
LRESULT = ctypes.c_int64
HWND = ctypes.c_void_p
UINT = ctypes.c_uint32
WPARAM = ctypes.c_uint64
LPARAM = ctypes.c_int64
COLORREF = wintypes.COLORREF
BYTE = wintypes.BYTE
DWORD = wintypes.DWORD
BOOL = wintypes.BOOL
INT = ctypes.c_int

user32.DefWindowProcW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.DefWindowProcW.restype = LRESULT

user32.PostMessageW.argtypes = [HWND, UINT, WPARAM, LPARAM]
user32.PostMessageW.restype = BOOL

user32.SetLayeredWindowAttributes.argtypes = [HWND, COLORREF, BYTE, DWORD]
user32.SetLayeredWindowAttributes.restype = BOOL

user32.ShowWindow.argtypes = [HWND, INT]
user32.ShowWindow.restype = BOOL

user32.SetWindowPos.argtypes = [HWND, HWND, INT, INT, INT, INT, UINT]
user32.SetWindowPos.restype = BOOL

user32.GetDC.argtypes = [HWND]
user32.GetDC.restype = ctypes.c_void_p

user32.ReleaseDC.argtypes = [HWND, ctypes.c_void_p]
user32.ReleaseDC.restype = INT

user32.FillRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p]
user32.FillRect.restype = INT

user32.DrawTextW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, INT, ctypes.POINTER(wintypes.RECT), UINT]
user32.DrawTextW.restype = INT

user32.GetSystemMetrics.argtypes = [INT]
user32.GetSystemMetrics.restype = INT

user32.DestroyWindow.argtypes = [HWND]
user32.DestroyWindow.restype = BOOL

user32.PostQuitMessage.argtypes = [INT]
user32.PostQuitMessage.restype = None

gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p

gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, INT, INT]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p

gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p

gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteObject.restype = BOOL

gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.restype = BOOL

gdi32.GetStockObject.argtypes = [INT]
gdi32.GetStockObject.restype = ctypes.c_void_p

gdi32.CreateSolidBrush.argtypes = [COLORREF]
gdi32.CreateSolidBrush.restype = ctypes.c_void_p

gdi32.CreatePen.argtypes = [INT, INT, COLORREF]
gdi32.CreatePen.restype = ctypes.c_void_p

gdi32.Ellipse.argtypes = [ctypes.c_void_p, INT, INT, INT, INT]
gdi32.Ellipse.restype = BOOL

gdi32.MoveToEx.argtypes = [ctypes.c_void_p, INT, INT, ctypes.c_void_p]
gdi32.MoveToEx.restype = BOOL

gdi32.AngleArc.argtypes = [ctypes.c_void_p, INT, INT, DWORD, ctypes.c_float, ctypes.c_float]
gdi32.AngleArc.restype = BOOL

gdi32.RoundRect.argtypes = [ctypes.c_void_p, INT, INT, INT, INT, INT, INT]
gdi32.RoundRect.restype = BOOL

gdi32.SetBkMode.argtypes = [ctypes.c_void_p, INT]
gdi32.SetBkMode.restype = INT

gdi32.SetTextColor.argtypes = [ctypes.c_void_p, COLORREF]
gdi32.SetTextColor.restype = COLORREF

gdi32.CreateFontW.argtypes = [
    INT, INT, INT, INT, INT, DWORD, DWORD, DWORD,
    DWORD, DWORD, DWORD, DWORD, DWORD, wintypes.LPCWSTR,
]
gdi32.CreateFontW.restype = ctypes.c_void_p

gdi32.BitBlt.argtypes = [
    ctypes.c_void_p, INT, INT, INT, INT,
    ctypes.c_void_p, INT, INT, DWORD,
]
gdi32.BitBlt.restype = BOOL

WNDPROC = ctypes.WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)

# Window Styles
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

LWA_COLORKEY = 0x00000001
SW_HIDE = 0
SW_SHOWNOACTIVATE = 4

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_HIDEWINDOW = 0x0080

HWND_TOPMOST = ctypes.c_void_p(-1)

WM_DESTROY = 0x0002
WM_USER_RENDER = 0x0400 + 1

# Dimensions
DWELL_SIZE = 72
DWELL_HALF = 36
TOAST_WIDTH = 280
TOAST_HEIGHT = 42


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
    """Controls the lightweight 72x72 cursor dwell ring and top toast notifications."""

    CLASS_NAME = "AirCursorOverlayWindow"
    SIZE = DWELL_SIZE

    def __init__(self, enabled: bool = True):
        self.enabled: bool = enabled
        self._dwell_hwnd: Optional[int] = None
        self._toast_hwnd: Optional[int] = None
        self._hwnd: Optional[int] = None  # Backwards compatibility alias to _dwell_hwnd
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
        """Starts the background window thread and creates HUD windows."""
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
        """Closes all HUD overlay windows."""
        self._running = False
        if self._dwell_hwnd:
            user32.PostMessageW(self._dwell_hwnd, WM_DESTROY, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._dwell_hwnd = None
        self._toast_hwnd = None
        self._hwnd = None
        self._thread = None

    def update_dwell(
        self, progress: Optional[float], x: float, y: float
    ) -> None:
        """Updates dwell click progress (0.0 to 1.0 or None) at cursor position (x, y).

        - If progress is not None and progress >= 0.15: shows 72x72 window at (x-36, y-36).
        - If progress is None: immediately hides the window.
        """
        if not self.enabled or not self._dwell_hwnd:
            return
        with self._lock:
            self._dwell_progress = progress
            self._dwell_pos = (int(round(x)), int(round(y)))
        user32.PostMessageW(self._dwell_hwnd, WM_USER_RENDER, 0, 0)

    def pulse(self, x: float, y: float) -> None:
        """Triggers click ripple pulse feedback at (x, y) for 0.2s then hides."""
        if not self.enabled or not self._dwell_hwnd:
            return
        with self._lock:
            self._pulse_start = time.time()
            self._pulse_pos = (int(round(x)), int(round(y)))
        user32.PostMessageW(self._dwell_hwnd, WM_USER_RENDER, 0, 0)

    def show_toast(
        self, text: str, symbol: str = "🎯", duration: float = 1.8
    ) -> None:
        """Displays a compact 280x42 HUD notification pill at top-center of screen."""
        if not self.enabled or not self._toast_hwnd:
            return
        display_str = f"{symbol}  {text}" if symbol else text
        with self._lock:
            self._toast_text = display_str
            self._toast_until = time.time() + duration
        user32.PostMessageW(self._toast_hwnd, WM_USER_RENDER, 0, 0)

    def hide(self) -> None:
        """Clears all dwell rings, pulses, and notifications."""
        with self._lock:
            self._dwell_progress = None
            self._pulse_start = None
            self._toast_text = None
        if self._dwell_hwnd:
            user32.PostMessageW(self._dwell_hwnd, WM_USER_RENDER, 0, 0)
        if self._toast_hwnd:
            user32.PostMessageW(self._toast_hwnd, WM_USER_RENDER, 0, 0)

    def _window_thread(self) -> None:
        """Background Win32 message loop managing 72x72 dwell popup and toast pill."""
        hinstance = kernel32.GetModuleHandleW(None)

        def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_USER_RENDER:
                if hwnd == self._dwell_hwnd:
                    self._render_dwell()
                elif hwnd == self._toast_hwnd:
                    self._render_toast()
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
        wc.hbrBackground = gdi32.GetStockObject(4)  # BLACK_BRUSH = 4
        user32.RegisterClassExW(ctypes.byref(wc))

        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOPMOST
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )

        # 1. 72x72 Floating Dwell Popup Window (centered around mouse cursor)
        self._dwell_hwnd = user32.CreateWindowExW(
            ex_style,
            self.CLASS_NAME,
            "AirCursor Dwell Ring",
            WS_POPUP,
            0,
            0,
            DWELL_SIZE,
            DWELL_SIZE,
            None,
            None,
            hinstance,
            None,
        )
        user32.SetLayeredWindowAttributes(self._dwell_hwnd, 0x00000000, 255, LWA_COLORKEY)
        user32.ShowWindow(self._dwell_hwnd, SW_HIDE)
        self._hwnd = self._dwell_hwnd

        # 2. 280x42 Compact Toast HUD Window (top-center of primary display)
        sw = user32.GetSystemMetrics(0)
        tx = (sw - TOAST_WIDTH) // 2
        ty = 48
        self._toast_hwnd = user32.CreateWindowExW(
            ex_style,
            self.CLASS_NAME,
            "AirCursor Toast HUD",
            WS_POPUP,
            tx,
            ty,
            TOAST_WIDTH,
            TOAST_HEIGHT,
            None,
            None,
            hinstance,
            None,
        )
        user32.SetLayeredWindowAttributes(self._toast_hwnd, 0x00000000, 255, LWA_COLORKEY)
        user32.ShowWindow(self._toast_hwnd, SW_HIDE)

        self._ready_event.set()

        # Window message pump with timer for pulse/toast animation updates
        msg = wintypes.MSG()

        while self._running:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == 0x0012:  # WM_QUIT
                    self._running = False
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            now = time.time()
            needs_dwell = False
            needs_toast = False

            with self._lock:
                if self._pulse_start:
                    if now - self._pulse_start < 0.20:
                        needs_dwell = True
                    else:
                        self._pulse_start = None
                        needs_dwell = True

                if self._toast_text:
                    if now >= self._toast_until:
                        self._toast_text = None
                        needs_toast = True

            if needs_dwell:
                self._render_dwell()
            if needs_toast:
                self._render_toast()

            time.sleep(0.016)  # ~60 Hz animation cadence

        if self._dwell_hwnd:
            user32.DestroyWindow(self._dwell_hwnd)
            self._dwell_hwnd = None
        if self._toast_hwnd:
            user32.DestroyWindow(self._toast_hwnd)
            self._toast_hwnd = None
        self._hwnd = None
        user32.UnregisterClassW(self.CLASS_NAME, hinstance)

    def _render_dwell(self) -> None:
        """Renders the 72x72 dwell progress circle or click ripple pulse."""
        if not self._dwell_hwnd:
            return

        with self._lock:
            dwell_prog = self._dwell_progress
            dx, dy = self._dwell_pos
            pulse_start = self._pulse_start
            px, py = self._pulse_pos

        now = time.time()
        pulsing = pulse_start is not None and (now - pulse_start < 0.20)
        show_dwell = dwell_prog is not None and dwell_prog >= 0.15

        # If dwell is None / < 0.15 and no ripple pulse is active, hide window immediately
        if not show_dwell and not pulsing:
            user32.ShowWindow(self._dwell_hwnd, SW_HIDE)
            return

        # Position centered at cursor (x - 36, y - 36)
        target_x = (dx if show_dwell else px) - DWELL_HALF
        target_y = (dy if show_dwell else py) - DWELL_HALF

        user32.SetWindowPos(
            self._dwell_hwnd,
            HWND_TOPMOST,
            target_x,
            target_y,
            DWELL_SIZE,
            DWELL_SIZE,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

        hdc = user32.GetDC(self._dwell_hwnd)
        if not hdc:
            return

        memdc = gdi32.CreateCompatibleDC(hdc)
        hbmp = gdi32.CreateCompatibleBitmap(hdc, DWELL_SIZE, DWELL_SIZE)
        old_bmp = gdi32.SelectObject(memdc, hbmp)

        # Clear background to black (transparent colorkey)
        black_brush = gdi32.GetStockObject(4)  # BLACK_BRUSH = 4
        rect = wintypes.RECT(0, 0, DWELL_SIZE, DWELL_SIZE)
        user32.FillRect(memdc, ctypes.byref(rect), black_brush)

        cx, cy = DWELL_HALF, DWELL_HALF
        r = 20

        null_brush = gdi32.GetStockObject(5)  # NULL_BRUSH = 5
        old_brush = gdi32.SelectObject(memdc, null_brush)

        # 1. Dwell Progress Ring
        if show_dwell and dwell_prog is not None:
            # Faint background track
            track_pen = gdi32.CreatePen(0, 2, 0x00444444)  # Dark Gray
            old_pen = gdi32.SelectObject(memdc, track_pen)
            gdi32.Ellipse(memdc, cx - r, cy - r, cx + r, cy + r)
            gdi32.SelectObject(memdc, old_pen)
            gdi32.DeleteObject(track_pen)

            # Center dot (Cyan)
            dot_brush = gdi32.CreateSolidBrush(0x00FFE500)  # Cyan (BGR: 0x00FFE500)
            old_b = gdi32.SelectObject(memdc, dot_brush)
            dot_pen = gdi32.GetStockObject(8)  # NULL_PEN = 8
            old_p = gdi32.SelectObject(memdc, dot_pen)
            gdi32.Ellipse(memdc, cx - 2, cy - 2, cx + 2, cy + 2)
            gdi32.SelectObject(memdc, old_p)
            gdi32.SelectObject(memdc, old_b)
            gdi32.DeleteObject(dot_brush)

            # Progress arc
            prog = min(max(dwell_prog, 0.0), 1.0)
            arc_pen = gdi32.CreatePen(0, 4, 0x00FFE500)  # Bright Cyan
            gdi32.SelectObject(memdc, arc_pen)
            start_angle = 90.0
            sweep_angle = -float(prog * 360.0)
            rad = math.radians(start_angle)
            sx = int(cx + r * math.cos(rad))
            sy = int(cy - r * math.sin(rad))
            gdi32.MoveToEx(memdc, sx, sy, None)
            gdi32.AngleArc(
                memdc,
                cx,
                cy,
                r,
                ctypes.c_float(start_angle),
                ctypes.c_float(sweep_angle),
            )
            gdi32.DeleteObject(arc_pen)

        # 2. Click Feedback Pulse (expanding ripple animation for 0.2s)
        if pulsing and pulse_start is not None:
            t = (now - pulse_start) / 0.20
            pr = int(8 + t * 24)
            pulse_pen = gdi32.CreatePen(0, 3, 0x00FFFFFF)  # White
            gdi32.SelectObject(memdc, pulse_pen)
            gdi32.Ellipse(memdc, cx - pr, cy - pr, cx + pr, cy + pr)
            gdi32.DeleteObject(pulse_pen)

        # Blit 72x72 backbuffer onto window
        gdi32.BitBlt(hdc, 0, 0, DWELL_SIZE, DWELL_SIZE, memdc, 0, 0, 0x00CC0020)

        # Cleanup
        gdi32.SelectObject(memdc, old_brush)
        gdi32.SelectObject(memdc, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(self._dwell_hwnd, hdc)

    def _render_toast(self) -> None:
        """Renders the compact 280x42 toast notification pill banner at top-center."""
        if not self._toast_hwnd:
            return

        with self._lock:
            toast_text = self._toast_text
            toast_until = self._toast_until

        now = time.time()
        if not toast_text or now >= toast_until:
            user32.ShowWindow(self._toast_hwnd, SW_HIDE)
            return

        sw = user32.GetSystemMetrics(0)
        tx = (sw - TOAST_WIDTH) // 2
        ty = 48

        user32.SetWindowPos(
            self._toast_hwnd,
            HWND_TOPMOST,
            tx,
            ty,
            TOAST_WIDTH,
            TOAST_HEIGHT,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

        hdc = user32.GetDC(self._toast_hwnd)
        if not hdc:
            return

        memdc = gdi32.CreateCompatibleDC(hdc)
        hbmp = gdi32.CreateCompatibleBitmap(hdc, TOAST_WIDTH, TOAST_HEIGHT)
        old_bmp = gdi32.SelectObject(memdc, hbmp)

        # Clear background to black (colorkey transparent)
        black_brush = gdi32.GetStockObject(4)
        rect = wintypes.RECT(0, 0, TOAST_WIDTH, TOAST_HEIGHT)
        user32.FillRect(memdc, ctypes.byref(rect), black_brush)

        # Rounded pill card background
        bg_brush = gdi32.CreateSolidBrush(0x00221E1A)  # Deep Charcoal
        border_pen = gdi32.CreatePen(0, 2, 0x00665544)
        old_brush = gdi32.SelectObject(memdc, bg_brush)
        old_pen = gdi32.SelectObject(memdc, border_pen)
        gdi32.RoundRect(memdc, 2, 2, TOAST_WIDTH - 2, TOAST_HEIGHT - 2, 16, 16)
        gdi32.SelectObject(memdc, old_brush)
        gdi32.SelectObject(memdc, old_pen)
        gdi32.DeleteObject(bg_brush)
        gdi32.DeleteObject(border_pen)

        # Draw toast text
        gdi32.SetBkMode(memdc, 1)  # TRANSPARENT
        gdi32.SetTextColor(memdc, 0x00FFFFFF)  # White

        hfont = gdi32.CreateFontW(
            17,
            0,
            0,
            0,
            600,
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

        text_rect = wintypes.RECT(6, 0, TOAST_WIDTH - 6, TOAST_HEIGHT)
        DT_CENTER = 0x0001
        DT_VCENTER = 0x0004
        DT_SINGLELINE = 0x0020
        user32.DrawTextW(
            memdc,
            toast_text,
            -1,
            ctypes.byref(text_rect),
            DT_CENTER | DT_VCENTER | DT_SINGLELINE,
        )

        gdi32.SelectObject(memdc, old_font)
        gdi32.DeleteObject(hfont)

        # Blit 280x42 backbuffer
        gdi32.BitBlt(hdc, 0, 0, TOAST_WIDTH, TOAST_HEIGHT, memdc, 0, 0, 0x00CC0020)

        # Cleanup
        gdi32.SelectObject(memdc, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(self._toast_hwnd, hdc)
