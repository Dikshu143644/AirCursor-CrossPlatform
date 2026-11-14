"""AirCursor Windows Clickable Element Probe.

Answers "is the UI element under the pointer clickable / interactive?" for smart dwell click.
Uses Windows UI Automation (UIA) via ctypes COM:
- Queries IUIAutomation::ElementFromPoint
- Checks ControlType (Button, Hyperlink, MenuItem, SplitButton, TabItem, Edit, CheckBox, RadioButton, etc.)
- Checks Pattern availability (InvokePattern, TogglePattern, SelectionItemPattern)
- Climbs up to 3 ancestors in the control tree (e.g., text/icons inside buttons)
- Fallback: Checks system cursor shape (GetCursorInfo) for IDC_HAND (pointing hand cursor)
- Asynchronous querying queue so probe calls never stall the 120Hz tracking loop
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes, POINTER, c_void_p, Structure, byref, WINFUNCTYPE, HRESULT
import os
import queue
import threading
import time
from typing import Callable, Optional, Set

# COM & Win32 definitions
ole32 = ctypes.windll.ole32
user32 = ctypes.windll.user32

COINIT_MULTITHREADED = 0x0
IDC_HAND = 32649


class GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


CLSID_CUIAutomation = GUID(
    0xFF48DBA4,
    0x60EF,
    0x4201,
    (wintypes.BYTE * 8)(0xAA, 0x87, 0x54, 0x10, 0x3E, 0xEF, 0x59, 0x4E),
)
IID_IUIAutomation = GUID(
    0x30CBE57D,
    0xD9D0,
    0x452A,
    (wintypes.BYTE * 8)(0xAB, 0x13, 0x7A, 0xC5, 0xAC, 0x48, 0x25, 0xEE),
)

# Control Type IDs (UIAutomationClient.h)
UIA_ButtonControlTypeId = 50000
UIA_CalendarControlTypeId = 50001
UIA_CheckBoxControlTypeId = 50002
UIA_ComboBoxControlTypeId = 50003
UIA_EditControlTypeId = 50004
UIA_HyperlinkControlTypeId = 50005
UIA_ImageControlTypeId = 50006
UIA_ListItemControlTypeId = 50007
UIA_ListControlTypeId = 50008
UIA_MenuControlTypeId = 50009
UIA_MenuBarControlTypeId = 50010
UIA_MenuItemControlTypeId = 50011
UIA_ProgressBarControlTypeId = 50012
UIA_RadioButtonControlTypeId = 50013
UIA_ScrollBarControlTypeId = 50014
UIA_SliderControlTypeId = 50015
UIA_SpinnerControlTypeId = 50016
UIA_StatusBarControlTypeId = 50017
UIA_TabControlTypeId = 50018
UIA_TabItemControlTypeId = 50019
UIA_TextControlTypeId = 50020
UIA_ToolBarControlTypeId = 50021
UIA_ToolTipControlTypeId = 50022
UIA_TreeControlTypeId = 50023
UIA_TreeItemControlTypeId = 50024
UIA_CustomControlTypeId = 50025
UIA_GroupControlTypeId = 50026
UIA_ThumbControlTypeId = 50027
UIA_DataGridControlTypeId = 50028
UIA_DataItemControlTypeId = 50029
UIA_DocumentControlTypeId = 50030
UIA_SplitButtonControlTypeId = 50031
UIA_WindowControlTypeId = 50032
UIA_PaneControlTypeId = 50033
UIA_HeaderControlTypeId = 50034
UIA_HeaderItemControlTypeId = 50035
UIA_TableControlTypeId = 50036
UIA_TitleBarControlTypeId = 50037
UIA_SeparatorControlTypeId = 50038
UIA_SemanticZoomControlTypeId = 50039
UIA_AppBarControlTypeId = 50040

CLICKABLE_CONTROL_TYPES: Set[int] = {
    UIA_ButtonControlTypeId,
    UIA_CheckBoxControlTypeId,
    UIA_ComboBoxControlTypeId,
    UIA_EditControlTypeId,
    UIA_HyperlinkControlTypeId,
    UIA_ListItemControlTypeId,
    UIA_MenuItemControlTypeId,
    UIA_RadioButtonControlTypeId,
    UIA_SliderControlTypeId,
    UIA_SpinnerControlTypeId,
    UIA_TabItemControlTypeId,
    UIA_SplitButtonControlTypeId,
    UIA_HeaderItemControlTypeId,
    UIA_DataItemControlTypeId,
}

# Pattern IDs
UIA_InvokePatternId = 10000
UIA_SelectionItemPatternId = 10010
UIA_TogglePatternId = 10015
UIA_ExpandCollapsePatternId = 10005

CLICKABLE_PATTERNS = [
    UIA_InvokePatternId,
    UIA_TogglePatternId,
    UIA_SelectionItemPatternId,
    UIA_ExpandCollapsePatternId,
]


class CURSORINFO(Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


class ClickableProbe:
    """Probes Windows UI elements to determine whether the cursor is over an interactive target."""

    def __init__(self):
        self._own_pid: int = os.getpid()
        self._h_hand_cursor: Optional[int] = user32.LoadCursorW(None, IDC_HAND)
        self._request_queue: queue.Queue = queue.Queue(maxsize=16)
        self._running: bool = True
        self._worker_thread: threading.Thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="AirCursor-ClickableProbe"
        )
        self._worker_thread.start()

    def close(self) -> None:
        """Stops the probe background thread."""
        self._running = False
        try:
            self._request_queue.put(None, timeout=0.2)
            self._worker_thread.join(timeout=0.5)
        except Exception:
            pass

    def check(self, x: float, y: float, callback: Callable[[bool], None]) -> None:
        """Asynchronously probes the element at (x, y) and invokes callback with the verdict."""
        try:
            # Drop stale pending queries if user is moving cursor fast
            while not self._request_queue.empty():
                try:
                    self._request_queue.get_nowait()
                except queue.Empty:
                    break
            self._request_queue.put_nowait((x, y, callback))
        except queue.Full:
            pass

    def is_clickable_sync(self, x: float, y: float, timeout: float = 0.05) -> bool:
        """Synchronously probes whether (x, y) is clickable with a fallback to cursor shape."""
        res_box = [None]
        evt = threading.Event()

        def _cb(val: bool):
            res_box[0] = val
            evt.set()

        self.check(x, y, _cb)
        if evt.wait(timeout):
            return bool(res_box[0])
        # On timeout, check cursor shape immediately
        return self.cursor_looks_clickable()

    def cursor_looks_clickable(self) -> bool:
        """Checks if Windows system cursor is currently the IDC_HAND (pointing hand) cursor."""
        try:
            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            if user32.GetCursorInfo(byref(ci)):
                # If pointing hand cursor or loaded hand handle matches
                if self._h_hand_cursor and ci.hCursor == self._h_hand_cursor:
                    return True
        except Exception:
            pass
        return False

    def _worker_loop(self) -> None:
        """Dedicated COM thread for UIA queries."""
        try:
            ole32.CoInitializeEx(None, COINIT_MULTITHREADED)
        except Exception:
            try:
                ole32.CoInitialize(None)
            except Exception:
                pass

        pUIA = c_void_p()
        pWalker = c_void_p()
        ElementFromPointFunc = None
        GetControlWalkerFunc = None
        GetParentFunc = None

        try:
            hr = ole32.CoCreateInstance(
                byref(CLSID_CUIAutomation),
                None,
                1,
                byref(IID_IUIAutomation),
                byref(pUIA),
            )
            if hr == 0 and pUIA.value:
                uia_vtbl = ctypes.cast(pUIA.value, POINTER(POINTER(c_void_p))).contents
                # Index 7: ElementFromPoint
                ElementFromPointFunc = WINFUNCTYPE(
                    HRESULT, c_void_p, wintypes.POINT, POINTER(c_void_p)
                )(uia_vtbl[7])
                # Index 14: get_ControlViewWalker
                GetControlWalkerFunc = WINFUNCTYPE(
                    HRESULT, c_void_p, POINTER(c_void_p)
                )(uia_vtbl[14])
                hr2 = GetControlWalkerFunc(pUIA, byref(pWalker))
                if hr2 == 0 and pWalker.value:
                    walker_vtbl = ctypes.cast(
                        pWalker.value, POINTER(POINTER(c_void_p))
                    ).contents
                    # Index 3: GetParentElement
                    GetParentFunc = WINFUNCTYPE(
                        HRESULT, c_void_p, c_void_p, POINTER(c_void_p)
                    )(walker_vtbl[3])
        except Exception:
            pass

        while self._running:
            try:
                item = self._request_queue.get(timeout=0.1)
                if item is None:
                    break
                x, y, callback = item
                verdict = self._evaluate_point(
                    pUIA,
                    pWalker,
                    ElementFromPointFunc,
                    GetParentFunc,
                    int(round(x)),
                    int(round(y)),
                )
                try:
                    callback(verdict)
                except Exception:
                    pass
            except queue.Empty:
                continue
            except Exception:
                time.sleep(0.01)

        # Release COM interfaces
        try:
            if pWalker.value:
                w_vtbl = ctypes.cast(pWalker.value, POINTER(POINTER(c_void_p))).contents
                WINFUNCTYPE(wintypes.ULONG, c_void_p)(w_vtbl[2])(pWalker)
            if pUIA.value:
                u_vtbl = ctypes.cast(pUIA.value, POINTER(POINTER(c_void_p))).contents
                WINFUNCTYPE(wintypes.ULONG, c_void_p)(u_vtbl[2])(pUIA)
            ole32.CoUninitialize()
        except Exception:
            pass

    def _evaluate_point(
        self,
        pUIA: c_void_p,
        pWalker: c_void_p,
        ElementFromPointFunc,
        GetParentFunc,
        x: int,
        y: int,
    ) -> bool:
        """Queries UIA at (x, y) with fallback to cursor shape."""
        # Fallback 1: Cursor shape check
        if self.cursor_looks_clickable():
            return True

        if not pUIA.value or ElementFromPointFunc is None:
            return False

        pElem = c_void_p()
        pt = wintypes.POINT(x, y)
        try:
            hr = ElementFromPointFunc(pUIA, pt, byref(pElem))
            if hr != 0 or not pElem.value:
                return False

            curr = pElem
            # Inspect up to 3 levels (hit element + up to 2 ancestors)
            for _ in range(3):
                elem_vtbl = ctypes.cast(curr.value, POINTER(POINTER(c_void_p))).contents
                release_func = WINFUNCTYPE(wintypes.ULONG, c_void_p)(elem_vtbl[2])

                # Check process id (ignore our own UI / overlays)
                get_pid_func = WINFUNCTYPE(
                    HRESULT, c_void_p, POINTER(wintypes.DWORD)
                )(elem_vtbl[20])
                pid = wintypes.DWORD()
                if get_pid_func(curr, byref(pid)) == 0 and pid.value == self._own_pid:
                    release_func(curr)
                    return False

                # Check ControlType
                get_ct_func = WINFUNCTYPE(
                    HRESULT, c_void_p, POINTER(wintypes.INT)
                )(elem_vtbl[21])
                ct = wintypes.INT()
                if get_ct_func(curr, byref(ct)) == 0:
                    if ct.value in CLICKABLE_CONTROL_TYPES:
                        release_func(curr)
                        return True

                # Check Patterns (Invoke, Toggle, SelectionItem, ExpandCollapse)
                get_pat_func = WINFUNCTYPE(
                    HRESULT, c_void_p, wintypes.INT, POINTER(c_void_p)
                )(elem_vtbl[16])
                for pat_id in CLICKABLE_PATTERNS:
                    pPat = c_void_p()
                    if get_pat_func(curr, pat_id, byref(pPat)) == 0 and pPat.value:
                        pat_vtbl = ctypes.cast(
                            pPat.value, POINTER(POINTER(c_void_p))
                        ).contents
                        WINFUNCTYPE(wintypes.ULONG, c_void_p)(pat_vtbl[2])(pPat)
                        release_func(curr)
                        return True

                # Walk to parent
                if GetParentFunc is not None and pWalker.value:
                    pParent = c_void_p()
                    hr_parent = GetParentFunc(pWalker, curr, byref(pParent))
                    release_func(curr)
                    if hr_parent == 0 and pParent.value:
                        curr = pParent
                    else:
                        break
                else:
                    release_func(curr)
                    break
        except Exception:
            pass

        return False
