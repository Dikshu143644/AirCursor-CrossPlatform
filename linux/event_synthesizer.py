"""
Linux Event Synthesizer for AirCursor.
Synthesizes virtual mouse movements, button clicks, wheel scrolling, and key strokes
cleanly across both X11 and Wayland using /dev/uinput (with python-evdev or raw kernel ioctls).
"""

from __future__ import annotations
import math
import os
import struct
import sys
import time
from typing import Optional, Tuple


# ==============================================================================
# Linux Input Event Constants (linux/input.h & linux/input-event-codes.h)
# ==============================================================================

EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

SYN_REPORT = 0x00

# Relative axes
REL_X      = 0x00
REL_Y      = 0x01
REL_WHEEL  = 0x08
REL_HWHEEL = 0x06

# Button codes
BTN_LEFT   = 0x110  # 272
BTN_RIGHT  = 0x111  # 273
BTN_MIDDLE = 0x112  # 274

# Key codes
KEY_ESC        = 1
KEY_ENTER      = 28
KEY_LEFTMETA   = 125  # Super / Windows key
KEY_RIGHTMETA  = 126
KEY_LEFTBRACE  = 26   # [
KEY_RIGHTBRACE = 27   # ]
KEY_TAB        = 15
KEY_LEFTALT    = 56
KEY_PRINT      = 99   # PrintScreen

# /dev/uinput ioctl constants
UI_SET_EVBIT   = 0x40045564
UI_SET_KEYBIT  = 0x40045565
UI_SET_RELBIT  = 0x40045566
UI_DEV_CREATE  = 0x5501
UI_DEV_DESTROY = 0x5502

BUS_USB = 0x03


# ==============================================================================
# Event Synthesizer Interface
# ==============================================================================

class LinuxEventSynthesizer:
    """
    Virtual input device manager creating a virtual mouse and keyboard device.
    Compatible with Wayland (Sway, GNOME, KDE) and X11 through libinput.
    """

    def __init__(self, device_name: str = "AirCursor Virtual Mouse") -> None:
        self.device_name = device_name
        self._is_left_button_down = False
        self._use_evdev = False
        self._evdev_device = None
        self._raw_fd: Optional[int] = None

        # Virtual pointer tracking
        self.screen_width = 1920
        self.screen_height = 1080
        self.current_x = self.screen_width / 2.0
        self.current_y = self.screen_height / 2.0

        self._probe_screen_size()
        self._init_device()

    @property
    def is_left_button_down(self) -> bool:
        return self._is_left_button_down

    def _probe_screen_size(self) -> None:
        """Attempts to probe screen size from DRM sysfs or command utilities."""
        # 1. Try reading from DRM sysfs modes
        try:
            drm_path = "/sys/class/drm"
            if os.path.exists(drm_path):
                for card in os.listdir(drm_path):
                    mode_file = os.path.join(drm_path, card, "modes")
                    if os.path.isfile(mode_file):
                        with open(mode_file, "r") as f:
                            first_line = f.readline().strip()
                            if "x" in first_line:
                                w_str, h_str = first_line.split("x")[:2]
                                self.screen_width = int(w_str)
                                self.screen_height = int(h_str)
                                self.current_x = self.screen_width / 2.0
                                self.current_y = self.screen_height / 2.0
                                return
        except Exception:
            pass

    def _init_device(self) -> None:
        """Initializes virtual uinput device via python-evdev or raw ioctls."""
        # 1. Try python-evdev first
        try:
            import evdev
            capabilities = {
                evdev.ecodes.EV_REL: [
                    evdev.ecodes.REL_X,
                    evdev.ecodes.REL_Y,
                    evdev.ecodes.REL_WHEEL,
                    evdev.ecodes.REL_HWHEEL,
                ],
                evdev.ecodes.EV_KEY: [
                    evdev.ecodes.BTN_LEFT,
                    evdev.ecodes.BTN_RIGHT,
                    evdev.ecodes.BTN_MIDDLE,
                    evdev.ecodes.KEY_LEFTMETA,
                    evdev.ecodes.KEY_LEFTBRACE,
                    evdev.ecodes.KEY_RIGHTBRACE,
                    evdev.ecodes.KEY_TAB,
                    evdev.ecodes.KEY_LEFTALT,
                    evdev.ecodes.KEY_PRINT,
                ],
            }
            self._evdev_device = evdev.UInput(
                events=capabilities,
                name=self.device_name,
                vendor=0x05AC,  # Apple Inc.
                product=0x0220,
            )
            self._use_evdev = True
            return
        except (ImportError, Exception):
            pass

        # 2. Fallback to raw /dev/uinput ioctl calls
        try:
            import fcntl
            uinput_paths = ["/dev/uinput", "/dev/input/uinput"]
            fd = None
            for p in uinput_paths:
                if os.path.exists(p):
                    fd = os.open(p, os.O_WRONLY | os.O_NONBLOCK)
                    break

            if fd is not None:
                # Enable EV_SYN, EV_KEY, EV_REL
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)

                # Relative axes
                for rel in (REL_X, REL_Y, REL_WHEEL, REL_HWHEEL):
                    fcntl.ioctl(fd, UI_SET_RELBIT, rel)

                # Buttons and Keys
                for key in (
                    BTN_LEFT, BTN_RIGHT, BTN_MIDDLE,
                    KEY_LEFTMETA, KEY_LEFTBRACE, KEY_RIGHTBRACE,
                    KEY_TAB, KEY_LEFTALT, KEY_PRINT
                ):
                    fcntl.ioctl(fd, UI_SET_KEYBIT, key)

                # struct uinput_user_dev layout:
                # char name[UINPUT_MAX_NAME_SIZE (80)]
                # struct input_id id (bustype u16, vendor u16, product u16, version u16)
                # int ff_effects_max (i32)
                # int absmax[64]
                # int absmin[64]
                # int absfuzz[64]
                # int absflat[64]
                name_bytes = self.device_name.encode("utf-8")[:79].ljust(80, b"\x00")
                input_id = struct.pack("HHHH", BUS_USB, 0x05AC, 0x0220, 1)
                user_dev_prefix = name_bytes + input_id + struct.pack("i", 0)
                # Pad to fill full structure size (~1000 bytes)
                pad_len = 1024 - len(user_dev_prefix)
                user_dev = user_dev_prefix + (b"\x00" * pad_len)

                os.write(fd, user_dev)
                fcntl.ioctl(fd, UI_DEV_CREATE)
                self._raw_fd = fd
                self._use_evdev = False
                return
        except Exception as err:
            # Running in non-Linux or simulated environment
            pass

    def close(self) -> None:
        """Destroys virtual input device."""
        if self._use_evdev and self._evdev_device:
            try:
                self._evdev_device.close()
            except Exception:
                pass
            self._evdev_device = None

        if self._raw_fd is not None:
            try:
                import fcntl
                fcntl.ioctl(self._raw_fd, UI_DEV_DESTROY)
                os.close(self._raw_fd)
            except Exception:
                pass
            self._raw_fd = None

    # --------------------------------------------------------------------------
    # Raw Event Emission
    # --------------------------------------------------------------------------

    def _write_event(self, ev_type: int, code: int, value: int) -> None:
        """Writes an input_event struct and flushes with SYN_REPORT."""
        if self._use_evdev and self._evdev_device:
            self._evdev_device.write(ev_type, code, value)
            return

        if self._raw_fd is not None:
            # struct input_event:
            # struct timeval time (long tv_sec, long tv_usec)
            # __u16 type
            # __u16 code
            # __s32 value
            now = time.time()
            sec = int(now)
            usec = int((now - sec) * 1_000_000)
            fmt = "llHHi" if struct.calcsize("l") == 8 else "iiHHi"
            payload = struct.pack(fmt, sec, usec, ev_type, code, value)
            try:
                os.write(self._raw_fd, payload)
            except OSError:
                pass

    def syn(self) -> None:
        if self._use_evdev and self._evdev_device:
            self._evdev_device.syn()
        elif self._raw_fd is not None:
            self._write_event(EV_SYN, SYN_REPORT, 0)

    # --------------------------------------------------------------------------
    # Pointer Actions
    # --------------------------------------------------------------------------

    def move_relative(self, dx: float, dy: float) -> None:
        """
        Moves pointer relatively by (dx, dy) pixels.
        Accumulates position within display bounds.
        """
        self.current_x = max(0.0, min(float(self.screen_width), self.current_x + dx))
        self.current_y = max(0.0, min(float(self.screen_height), self.current_y + dy))

        idx = int(round(dx))
        idy = int(round(dy))

        if idx != 0:
            self._write_event(EV_REL, REL_X, idx)
        if idy != 0:
            self._write_event(EV_REL, REL_Y, idy)
        if idx != 0 or idy != 0:
            self.syn()

    def get_current_location(self) -> Tuple[float, float]:
        """Returns virtual pointer coordinates."""
        return (self.current_x, self.current_y)

    def click(self, button: str = "left", count: int = 1) -> None:
        """Performs one or multiple clicks with the requested button."""
        btn_code = BTN_LEFT
        if button == "right":
            btn_code = BTN_RIGHT
        elif button == "middle":
            btn_code = BTN_MIDDLE

        for _ in range(count):
            self._write_event(EV_KEY, btn_code, 1)
            self.syn()
            time.sleep(0.015)
            self._write_event(EV_KEY, btn_code, 0)
            self.syn()
            if count > 1:
                time.sleep(0.05)

    def left_down(self) -> None:
        """Holds left mouse button down (drag start)."""
        if not self._is_left_button_down:
            self._write_event(EV_KEY, BTN_LEFT, 1)
            self.syn()
            self._is_left_button_down = True

    def left_up(self) -> None:
        """Releases left mouse button (drag finish)."""
        if self._is_left_button_down:
            self._write_event(EV_KEY, BTN_LEFT, 0)
            self.syn()
            self._is_left_button_down = False

    def toggle_drag(self) -> bool:
        """Toggles drag lock."""
        if self._is_left_button_down:
            self.left_up()
            return False
        else:
            self.left_down()
            return True

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        """
        Synthesizes wheel scroll events.
        Positive vertical scrolls UP, positive horizontal scrolls LEFT.
        """
        if vertical != 0:
            self._write_event(EV_REL, REL_WHEEL, int(vertical))
        if horizontal != 0:
            self._write_event(EV_REL, REL_HWHEEL, int(horizontal))
        if vertical != 0 or horizontal != 0:
            self.syn()

    def key_combo(self, keys: list[int]) -> None:
        """Presses and releases a key combination."""
        for k in keys:
            self._write_event(EV_KEY, k, 1)
        self.syn()
        time.sleep(0.02)
        for k in reversed(keys):
            self._write_event(EV_KEY, k, 0)
        self.syn()

    def mission_control(self) -> None:
        """Triggers GNOME Activities or Wayland workspace overview (Super)."""
        self.key_combo([KEY_LEFTMETA])

    def browser_back(self) -> None:
        """Back navigation: Alt + Left."""
        self.key_combo([KEY_LEFTALT, KEY_LEFTBRACE])

    def browser_forward(self) -> None:
        """Forward navigation: Alt + Right."""
        self.key_combo([KEY_LEFTALT, KEY_RIGHTBRACE])

    def screenshot(self) -> None:
        """Takes screenshot (PrintScreen)."""
        self.key_combo([KEY_PRINT])
