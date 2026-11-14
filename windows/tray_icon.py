"""AirCursor Windows System Tray Integration.

Provides a notification area tray icon with a popup context menu:
- Toggle Tracking (Pause / Resume)
- Toggle Mode (Pointer / Scroll)
- Recenter Cursor
- Exit AirCursor
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable, Optional

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_QUIT = 0x0012

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
TPM_RIGHTBUTTON = 0x0002

IDI_APPLICATION = 32512

user32.DefWindowProcW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.DefWindowProcW.restype = wintypes.LPARAM

WNDPROC = ctypes.WINFUNCTYPE(
    wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", wintypes.BYTE * 16),
        ("hBalloonIcon", wintypes.HANDLE),
    ]


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


class TrayIcon:
    """Windows Notification Area System Tray Icon."""

    CLASS_NAME = "AirCursorTrayIconWindow"
    ID_TOGGLE_TRACKING = 1001
    ID_TOGGLE_MODE = 1002
    ID_RECENTER = 1003
    ID_EXIT = 1004

    def __init__(
        self,
        on_toggle_tracking: Optional[Callable[[], None]] = None,
        on_toggle_mode: Optional[Callable[[], None]] = None,
        on_recenter: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
        is_tracking_fn: Optional[Callable[[], bool]] = None,
        get_mode_fn: Optional[Callable[[], str]] = None,
    ):
        self.on_toggle_tracking = on_toggle_tracking
        self.on_toggle_mode = on_toggle_mode
        self.on_recenter = on_recenter
        self.on_exit = on_exit
        self.is_tracking_fn = is_tracking_fn
        self.get_mode_fn = get_mode_fn

        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._nid = NOTIFYICONDATAW()
        self._wnd_proc_ref = None

    def start(self) -> None:
        """Starts the tray icon in a dedicated message pump thread."""
        if self._running:
            return
        self._running = True
        ready = threading.Event()
        self._thread = threading.Thread(
            target=self._tray_thread, args=(ready,), daemon=True, name="AirCursor-Tray"
        )
        self._thread.start()
        ready.wait(timeout=1.0)

    def stop(self) -> None:
        """Removes the tray icon and exits."""
        if not self._running:
            return
        self._running = False
        if self._hwnd:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            user32.PostMessageW(self._hwnd, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        self._hwnd = None

    def update_tooltip(self, text: str) -> None:
        """Updates the tray icon hover text."""
        if self._hwnd:
            self._nid.szTip = text[:127]
            self._nid.uFlags = NIF_TIP
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def _tray_thread(self, ready: threading.Event) -> None:
        hinstance = kernel32.GetModuleHandleW(None)

        def _wnd_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_TRAYICON:
                if lparam == WM_LBUTTONUP:
                    if self.on_toggle_tracking:
                        self.on_toggle_tracking()
                    return 0
                elif lparam == WM_RBUTTONUP:
                    self._show_context_menu(hwnd)
                    return 0
            elif msg == 0x0111:  # WM_COMMAND
                cmd_id = wparam & 0xFFFF
                if cmd_id == self.ID_TOGGLE_TRACKING and self.on_toggle_tracking:
                    self.on_toggle_tracking()
                elif cmd_id == self.ID_TOGGLE_MODE and self.on_toggle_mode:
                    self.on_toggle_mode()
                elif cmd_id == self.ID_RECENTER and self.on_recenter:
                    self.on_recenter()
                elif cmd_id == self.ID_EXIT and self.on_exit:
                    self.on_exit()
                return 0
            elif msg == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(_wnd_proc)

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinstance
        wc.lpszClassName = self.CLASS_NAME
        user32.RegisterClassExW(ctypes.byref(wc))

        # Message-only or hidden window
        self._hwnd = user32.CreateWindowExW(
            0,
            self.CLASS_NAME,
            "AirCursorTrayHidden",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            hinstance,
            None,
        )

        hicon = user32.LoadIconW(None, IDI_APPLICATION)

        self._nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._nid.hWnd = self._hwnd
        self._nid.uID = 1
        self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self._nid.uCallbackMessage = WM_TRAYICON
        self._nid.hIcon = hicon
        self._nid.szTip = "AirCursor (Windows Head Tracking)"

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))
        ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
        user32.UnregisterClassW(self.CLASS_NAME, hinstance)

    def _show_context_menu(self, hwnd: int) -> None:
        hmenu = user32.CreatePopupMenu()

        is_tracking = self.is_tracking_fn() if self.is_tracking_fn else True
        mode_str = self.get_mode_fn() if self.get_mode_fn else "pointer"

        track_label = "Pause Tracking (Ctrl+Alt+T)" if is_tracking else "Resume Tracking (Ctrl+Alt+T)"
        user32.AppendMenuW(hmenu, MF_STRING, self.ID_TOGGLE_TRACKING, track_label)

        mode_label = (
            "Switch to Pointer Mode (Ctrl+Alt+S)"
            if mode_str == "scroll"
            else "Switch to Scroll Mode (Ctrl+Alt+S)"
        )
        user32.AppendMenuW(hmenu, MF_STRING, self.ID_TOGGLE_MODE, mode_label)
        user32.AppendMenuW(hmenu, MF_STRING, self.ID_RECENTER, "Recenter Cursor (Ctrl+Alt+C)")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, self.ID_EXIT, "Exit AirCursor")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        # Windows requires SetForegroundWindow before TrackPopupMenu
        user32.SetForegroundWindow(hwnd)
        user32.TrackPopupMenu(
            hmenu,
            TPM_RIGHTBUTTON,
            pt.x,
            pt.y,
            0,
            hwnd,
            None,
        )
        user32.PostMessageW(hwnd, 0, 0, 0)
        user32.DestroyMenu(hmenu)
