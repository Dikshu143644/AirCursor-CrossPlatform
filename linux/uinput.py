"""
Linux uinput Driver for AirCursor.
Handles absolute and relative motion packets smoothly with fallback for non-root
/dev/uinput udev rules, evdev integration, raw kernel ioctl fallback, and simulated sinks.
"""

from __future__ import annotations
import math
import os
import shutil
import struct
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union


# ==============================================================================
# Linux Input Constants (linux/input.h & linux/input-event-codes.h)
# ==============================================================================

EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03

SYN_REPORT = 0x00

# Relative axes
REL_X           = 0x00
REL_Y           = 0x01
REL_HWHEEL      = 0x06
REL_DIAL        = 0x07
REL_WHEEL       = 0x08
REL_WHEEL_HI_RES = 0x0B
REL_HWHEEL_HI_RES = 0x0C

# Absolute axes
ABS_X          = 0x00
ABS_Y          = 0x01
ABS_Z          = 0x02
ABS_PRESSURE   = 0x18

# Button codes
BTN_MISC       = 0x100
BTN_0          = 0x100
BTN_1          = 0x101
BTN_MOUSE      = 0x110
BTN_LEFT       = 0x110
BTN_RIGHT      = 0x111
BTN_MIDDLE     = 0x112
BTN_SIDE       = 0x113
BTN_EXTRA      = 0x114
BTN_TOUCH      = 0x14A

# Keyboard keys
KEY_ESC        = 1
KEY_ENTER      = 28
KEY_LEFTMETA   = 125
KEY_RIGHTMETA  = 126
KEY_LEFTBRACE  = 26
KEY_RIGHTBRACE = 27
KEY_TAB        = 15
KEY_LEFTALT    = 56
KEY_PRINT      = 99

# /dev/uinput ioctl constants
UI_SET_EVBIT   = 0x40045564
UI_SET_KEYBIT  = 0x40045565
UI_SET_RELBIT  = 0x40045566
UI_SET_ABSBIT  = 0x40045567
UI_DEV_CREATE  = 0x5501
UI_DEV_DESTROY = 0x5502

BUS_USB = 0x03

# Udev rule definition for non-root access
UDEV_RULE_CONTENT = 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"\n'
UDEV_RULE_PATH = "/etc/udev/rules.d/99-uinput.rules"


# ==============================================================================
# Permission Diagnostic & Udev Helpers
# ==============================================================================

def check_uinput_permissions() -> Tuple[bool, str]:
    """
    Checks if /dev/uinput or /dev/input/uinput is writable by the current process.
    Returns (is_writable, diagnostic_message).
    """
    candidates = ["/dev/uinput", "/dev/input/uinput"]
    found_path = None
    for path in candidates:
        if os.path.exists(path):
            found_path = path
            break

    if not found_path:
        return False, (
            "No uinput device node found (/dev/uinput does not exist). "
            "Load the kernel module via: sudo modprobe uinput"
        )

    if os.access(found_path, os.R_OK | os.O_WRONLY):
        return True, f"Full read/write access to {found_path}."

    return False, (
        f"Permission denied accessing {found_path}. Non-root access requires udev rule:\n"
        f"1. echo '{UDEV_RULE_CONTENT.strip()}' | sudo tee {UDEV_RULE_PATH}\n"
        f"2. sudo usermod -aG input $USER\n"
        f"3. sudo udevadm control --reload-rules && sudo udevadm trigger\n"
        f"4. Log out and log back in."
    )


def generate_udev_rule() -> str:
    """Returns the recommended udev rule string for non-root /dev/uinput access."""
    return UDEV_RULE_CONTENT


# ==============================================================================
# UInput Device Manager
# ==============================================================================

class UInputDevice:
    """
    Production-grade uinput virtual device manager.
    Handles both relative and absolute motion packets with fallback for non-root permissions.
    """

    def __init__(
        self,
        name: str = "AirCursor Virtual Input",
        screen_width: int = 1920,
        screen_height: int = 1080,
        enable_absolute: bool = True,
        enable_relative: bool = True,
        vendor_id: int = 0x05AC,  # Apple Inc.
        product_id: int = 0x0220,
    ) -> None:
        self.name = name
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.enable_absolute = enable_absolute
        self.enable_relative = enable_relative
        self.vendor_id = vendor_id
        self.product_id = product_id

        # Internal pointer position tracking
        self.cur_x = float(screen_width) / 2.0
        self.cur_y = float(screen_height) / 2.0
        self.is_left_button_down = False
        self.is_right_button_down = False

        # Driver state
        self.is_simulated = False
        self._use_evdev = False
        self._evdev_device = None
        self._raw_fd: Optional[int] = None
        self._tool_fallback = None  # 'ydotool' or 'xdotool' if uinput denied

        self._init_device()

    def _init_device(self) -> None:
        """Initializes device using evdev, raw ioctl, or tool/simulated fallback."""
        # 1. Check permissions first
        has_perm, msg = check_uinput_permissions()
        if not has_perm:
            # Check for command-line tool fallbacks (ydotool for Wayland, xdotool for X11)
            if shutil.which("ydotool"):
                self._tool_fallback = "ydotool"
            elif shutil.which("xdotool") and os.environ.get("DISPLAY"):
                self._tool_fallback = "xdotool"
            else:
                self.is_simulated = True
            return

        # 2. Try python-evdev
        try:
            import evdev
            caps: Dict[int, List[Any]] = {
                evdev.ecodes.EV_KEY: [
                    evdev.ecodes.BTN_LEFT,
                    evdev.ecodes.BTN_RIGHT,
                    evdev.ecodes.BTN_MIDDLE,
                    evdev.ecodes.BTN_TOUCH,
                    evdev.ecodes.KEY_LEFTMETA,
                    evdev.ecodes.KEY_LEFTALT,
                    evdev.ecodes.KEY_LEFTBRACE,
                    evdev.ecodes.KEY_RIGHTBRACE,
                    evdev.ecodes.KEY_PRINT,
                ]
            }

            if self.enable_relative:
                caps[evdev.ecodes.EV_REL] = [
                    evdev.ecodes.REL_X,
                    evdev.ecodes.REL_Y,
                    evdev.ecodes.REL_WHEEL,
                    evdev.ecodes.REL_HWHEEL,
                ]

            if self.enable_absolute:
                abs_x = evdev.AbsInfo(value=int(self.cur_x), min=0, max=self.screen_width, fuzz=0, flat=0, resolution=1)
                abs_y = evdev.AbsInfo(value=int(self.cur_y), min=0, max=self.screen_height, fuzz=0, flat=0, resolution=1)
                caps[evdev.ecodes.EV_ABS] = [
                    (evdev.ecodes.ABS_X, abs_x),
                    (evdev.ecodes.ABS_Y, abs_y),
                ]

            self._evdev_device = evdev.UInput(
                events=caps,
                name=self.name,
                vendor=self.vendor_id,
                product=self.product_id,
            )
            self._use_evdev = True
            return
        except (ImportError, Exception):
            pass

        # 3. Fallback to raw /dev/uinput ioctls
        try:
            import fcntl
            uinput_paths = ["/dev/uinput", "/dev/input/uinput"]
            fd = None
            for p in uinput_paths:
                if os.path.exists(p) and os.access(p, os.O_WRONLY):
                    fd = os.open(p, os.O_WRONLY | os.O_NONBLOCK)
                    break

            if fd is not None:
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_SYN)
                fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)

                for k in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_TOUCH, KEY_LEFTMETA, KEY_LEFTALT, KEY_PRINT):
                    fcntl.ioctl(fd, UI_SET_KEYBIT, k)

                if self.enable_relative:
                    fcntl.ioctl(fd, UI_SET_EVBIT, EV_REL)
                    for r in (REL_X, REL_Y, REL_WHEEL, REL_HWHEEL):
                        fcntl.ioctl(fd, UI_SET_RELBIT, r)

                if self.enable_absolute:
                    fcntl.ioctl(fd, UI_SET_EVBIT, EV_ABS)
                    fcntl.ioctl(fd, UI_SET_ABSBIT, ABS_X)
                    fcntl.ioctl(fd, UI_SET_ABSBIT, ABS_Y)

                name_bytes = self.name.encode("utf-8")[:79].ljust(80, b"\x00")
                input_id = struct.pack("HHHH", BUS_USB, self.vendor_id, self.product_id, 1)
                prefix = name_bytes + input_id + struct.pack("i", 0)
                pad = 1024 - len(prefix)
                user_dev = prefix + (b"\x00" * pad)

                os.write(fd, user_dev)
                fcntl.ioctl(fd, UI_DEV_CREATE)
                self._raw_fd = fd
                self._use_evdev = False
                return
        except Exception:
            pass

        # 4. Simulation fallback
        self.is_simulated = True

    def close(self) -> None:
        """Cleans up and destroys virtual input device."""
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
    # Low-Level Event Writing
    # --------------------------------------------------------------------------

    def write_event(self, ev_type: int, code: int, value: int) -> None:
        """Emits an event to evdev or raw /dev/uinput fd."""
        if self._use_evdev and self._evdev_device:
            self._evdev_device.write(ev_type, code, value)
            return

        if self._raw_fd is not None:
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
        """Flushes buffered input events with SYN_REPORT."""
        if self._use_evdev and self._evdev_device:
            self._evdev_device.syn()
        elif self._raw_fd is not None:
            self.write_event(EV_SYN, SYN_REPORT, 0)

    # --------------------------------------------------------------------------
    # Motion Handling: Absolute and Relative
    # --------------------------------------------------------------------------

    def move_relative(self, dx: float, dy: float) -> Tuple[float, float]:
        """
        Moves cursor relatively by (dx, dy) pixels.
        Emits REL_X and REL_Y events and keeps track of bounded screen position.
        """
        self.cur_x = max(0.0, min(float(self.screen_width), self.cur_x + dx))
        self.cur_y = max(0.0, min(float(self.screen_height), self.cur_y + dy))

        idx = int(round(dx))
        idy = int(round(dy))

        if idx != 0:
            self.write_event(EV_REL, REL_X, idx)
        if idy != 0:
            self.write_event(EV_REL, REL_Y, idy)
        if idx != 0 or idy != 0:
            self.syn()

        # Tool fallback (ydotool / xdotool)
        if self._tool_fallback == "xdotool" and (idx != 0 or idy != 0):
            try:
                subprocess.run(["xdotool", "mousemove_relative", "--", str(idx), str(idy)], check=False, stdout=subprocess.DEVNULL)
            except Exception:
                pass
        elif self._tool_fallback == "ydotool" and (idx != 0 or idy != 0):
            try:
                subprocess.run(["ydotool", "mousemove", "-r", str(idx), str(idy)], check=False, stdout=subprocess.DEVNULL)
            except Exception:
                pass

        return (self.cur_x, self.cur_y)

    def move_absolute(self, x: float, y: float) -> Tuple[float, float]:
        """
        Moves cursor directly to absolute coordinates (x, y) on display.
        Emits ABS_X and ABS_Y events.
        """
        self.cur_x = max(0.0, min(float(self.screen_width), float(x)))
        self.cur_y = max(0.0, min(float(self.screen_height), float(y)))

        ix = int(round(self.cur_x))
        iy = int(round(self.cur_y))

        self.write_event(EV_ABS, ABS_X, ix)
        self.write_event(EV_ABS, ABS_Y, iy)
        self.syn()

        if self._tool_fallback == "xdotool":
            try:
                subprocess.run(["xdotool", "mousemove", str(ix), str(iy)], check=False, stdout=subprocess.DEVNULL)
            except Exception:
                pass
        elif self._tool_fallback == "ydotool":
            try:
                subprocess.run(["ydotool", "mousemove", "-a", str(ix), str(iy)], check=False, stdout=subprocess.DEVNULL)
            except Exception:
                pass

        return (self.cur_x, self.cur_y)

    def handle_motion_packet(self, packet: Union[Dict[str, Any], Tuple[Any, ...]]) -> Tuple[float, float]:
        """
        Universal packet dispatcher handling both absolute and relative motion packets.
        Accepts:
          - {"type": "relative", "dx": 5.0, "dy": -2.0}
          - {"type": "absolute", "x": 960, "y": 540}
          - {"dx": 5.0, "dy": -2.0} (defaults to relative)
          - {"x": 960, "y": 540} (defaults to absolute)
          - Tuple: (dx, dy) relative
        """
        if isinstance(packet, (tuple, list)) and len(packet) >= 2:
            return self.move_relative(float(packet[0]), float(packet[1]))

        if isinstance(packet, dict):
            pkt_type = packet.get("type", "").lower()
            if pkt_type == "absolute" or ("x" in packet and "y" in packet and "dx" not in packet):
                x = float(packet.get("x", self.cur_x))
                y = float(packet.get("y", self.cur_y))
                # Check for normalized coordinates (0.0 to 1.0)
                if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and self.screen_width > 1:
                    x *= self.screen_width
                    y *= self.screen_height
                return self.move_absolute(x, y)
            else:
                dx = float(packet.get("dx", 0.0))
                dy = float(packet.get("dy", 0.0))
                return self.move_relative(dx, dy)

        return (self.cur_x, self.cur_y)

    # --------------------------------------------------------------------------
    # Clicks & Buttons
    # --------------------------------------------------------------------------

    def click(self, button: str = "left", count: int = 1) -> None:
        """Dispatches button clicks."""
        code = BTN_LEFT
        if button.lower() == "right":
            code = BTN_RIGHT
        elif button.lower() == "middle":
            code = BTN_MIDDLE

        for _ in range(count):
            self.write_event(EV_KEY, code, 1)
            self.syn()
            time.sleep(0.015)
            self.write_event(EV_KEY, code, 0)
            self.syn()
            if count > 1:
                time.sleep(0.04)

        if self._tool_fallback == "xdotool":
            btn_num = "1" if button.lower() == "left" else ("3" if button.lower() == "right" else "2")
            try:
                subprocess.run(["xdotool", "click", "--repeat", str(count), btn_num], check=False, stdout=subprocess.DEVNULL)
            except Exception:
                pass

    def left_down(self) -> None:
        """Holds left button down."""
        if not self.is_left_button_down:
            self.write_event(EV_KEY, BTN_LEFT, 1)
            self.syn()
            self.is_left_button_down = True

    def left_up(self) -> None:
        """Releases left button."""
        if self.is_left_button_down:
            self.write_event(EV_KEY, BTN_LEFT, 0)
            self.syn()
            self.is_left_button_down = False

    def toggle_drag(self) -> bool:
        """Toggles drag lock state."""
        if self.is_left_button_down:
            self.left_up()
            return False
        else:
            self.left_down()
            return True

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        """Synthesizes vertical and horizontal wheel scrolling."""
        if vertical != 0:
            self.write_event(EV_REL, REL_WHEEL, int(vertical))
        if horizontal != 0:
            self.write_event(EV_REL, REL_HWHEEL, int(horizontal))
        if vertical != 0 or horizontal != 0:
            self.syn()

        if self._tool_fallback == "xdotool":
            btn = "4" if vertical > 0 else "5"
            try:
                subprocess.run(["xdotool", "click", btn], check=False, stdout=subprocess.DEVNULL)
            except Exception:
                pass

    def key_combo(self, keys: List[int]) -> None:
        """Presses and releases key combination."""
        for k in keys:
            self.write_event(EV_KEY, k, 1)
        self.syn()
        time.sleep(0.02)
        for k in reversed(keys):
            self.write_event(EV_KEY, k, 0)
        self.syn()
