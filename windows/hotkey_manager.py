"""AirCursor Windows Global HotKey Manager.

Registers and monitors global shortcuts via low-level keyboard hook or RegisterHotKey:
- Ctrl + Alt + T: Toggle Tracking (Pause / Resume)
- Ctrl + Alt + S: Toggle Scroll Mode (Pointer / Scroll)
- Ctrl + Alt + C: Recenter Cursor
- Ctrl + Alt + D: Toggle Drag Lock
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
from typing import Callable, Dict, Optional, Tuple

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_QUIT = 0x0012

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HotKeyManager:
    """Listens for global shortcut combinations to control AirCursor."""

    def __init__(self):
        # Maps (vkCode, need_ctrl, need_alt, need_shift) -> callback
        self._bindings: Dict[Tuple[int, bool, bool, bool], Callable[[], None]] = {}
        self._hook_id: Optional[int] = None
        self._thread_id: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._hook_proc = None
        self._running: bool = False

    def register(
        self,
        vk_code: int,
        ctrl: bool = True,
        alt: bool = True,
        shift: bool = False,
        callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """Registers a key shortcut handler."""
        if callback:
            self._bindings[(vk_code, ctrl, alt, shift)] = callback

    def start(self) -> None:
        """Starts monitoring global hotkeys."""
        if self._running:
            return
        self._running = True
        ready = threading.Event()
        self._thread = threading.Thread(
            target=self._hook_thread, args=(ready,), daemon=True, name="AirCursor-HotKeys"
        )
        self._thread.start()
        ready.wait(timeout=1.0)

    def stop(self) -> None:
        """Stops the hotkey monitor."""
        if not self._running:
            return
        self._running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        self._thread_id = None
        self._hook_id = None

    def _hook_thread(self, ready: threading.Event) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()

        def _low_level_proc(nCode: int, wParam: int, lParam: int) -> int:
            if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kbd.vkCode

                # Check modifier states
                ctrl_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
                alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
                shift_down = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)

                key_combo = (vk, ctrl_down, alt_down, shift_down)
                if key_combo in self._bindings:
                    cb = self._bindings[key_combo]
                    try:
                        threading.Thread(target=cb, daemon=True).start()
                    except Exception:
                        pass
                    return 1  # Intercept shortcut

            return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

        self._hook_proc = HOOKPROC(_low_level_proc)
        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, None, 0
        )
        ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
