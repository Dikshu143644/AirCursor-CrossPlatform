"""AirCursor Windows Stem Listener.

Global media key hook on Windows to capture AirPods stem squeezes / clicks:
- 1 press -> Play/Pause (VK_MEDIA_PLAY_PAUSE = 0xB3) -> Trigger.STEM_SINGLE
- 2 presses -> Next Track (VK_MEDIA_NEXT_TRACK = 0xB0) -> Trigger.STEM_DOUBLE
- 3 presses -> Previous Track (VK_MEDIA_PREV_TRACK = 0xB1) -> Trigger.STEM_TRIPLE

Uses a low-level keyboard hook (WH_KEYBOARD_LL) via ctypes with debouncing and
configurable event interception (swallowing media keys so they do not interrupt music).
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import threading
import time
from typing import Callable, Optional

# Import Core Trigger definitions
sys.path.insert(0, r"c:\Users\omkar\TV\AirCursor_CrossPlatform")
from aircursor_core.actions import Trigger

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

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


class StemListener:
    """Monitors AirPods stem presses routed as Bluetooth media keys on Windows."""

    def __init__(
        self,
        on_trigger: Optional[Callable[[Trigger], None]] = None,
        intercept: bool = True,
        debounce_seconds: float = 0.18,
    ):
        self.on_trigger: Optional[Callable[[Trigger], None]] = on_trigger
        self.intercept: bool = intercept
        self.debounce_seconds: float = debounce_seconds

        self._hook_id: Optional[int] = None
        self._thread_id: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._hook_proc = None  # Keep reference alive
        self._last_event_time: float = 0.0
        self._last_vk: int = 0
        self._is_running: bool = False

    @property
    def is_active(self) -> bool:
        return self._is_running and self._hook_id is not None

    def start(self) -> None:
        """Starts the global low-level keyboard hook thread."""
        if self._is_running:
            return
        self._is_running = True
        ready_event = threading.Event()

        self._thread = threading.Thread(
            target=self._hook_thread_main,
            args=(ready_event,),
            daemon=True,
            name="AirCursor-StemListener",
        )
        self._thread.start()
        ready_event.wait(timeout=1.0)

    def stop(self) -> None:
        """Unhooks and shuts down the listener thread."""
        if not self._is_running:
            return
        self._is_running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_id = None
        self._hook_id = None

    def _hook_thread_main(self, ready_event: threading.Event) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()

        def _low_level_proc(nCode: int, wParam: int, lParam: int) -> int:
            if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kbd.vkCode
                now = time.time()

                trigger: Optional[Trigger] = None
                if vk == VK_MEDIA_PLAY_PAUSE:
                    trigger = Trigger.STEM_SINGLE
                elif vk == VK_MEDIA_NEXT_TRACK:
                    trigger = Trigger.STEM_DOUBLE
                elif vk == VK_MEDIA_PREV_TRACK:
                    trigger = Trigger.STEM_TRIPLE

                if trigger is not None:
                    # Debounce
                    if (
                        now - self._last_event_time > self.debounce_seconds
                        or vk != self._last_vk
                    ):
                        self._last_event_time = now
                        self._last_vk = vk
                        if self.on_trigger:
                            try:
                                self.on_trigger(trigger)
                            except Exception:
                                pass

                    if self.intercept:
                        return 1  # Swallow event so other media players do not react

            return user32.CallNextHookEx(self._hook_id, nCode, wParam, lParam)

        self._hook_proc = HOOKPROC(_low_level_proc)
        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, None, 0
        )

        ready_event.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
