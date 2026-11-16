"""
Linux Event Synthesizer for AirCursor.
Wraps UInputDevice to synthesize virtual mouse movements, clicks, wheel scrolls,
and keys cleanly on both X11 and Wayland.
"""

from __future__ import annotations
import math
import os
import sys
import time
from typing import Optional, Tuple

from uinput import (
    UInputDevice,
    check_uinput_permissions,
    generate_udev_rule,
    KEY_ESC,
    KEY_ENTER,
    KEY_LEFTMETA,
    KEY_LEFTALT,
    KEY_LEFTBRACE,
    KEY_RIGHTBRACE,
    KEY_PRINT,
    BTN_LEFT,
    BTN_RIGHT,
    BTN_MIDDLE,
)


class LinuxEventSynthesizer:
    """
    Synthesizes virtual mouse and keyboard events on Linux desktops.
    Supports relative and absolute movements across Wayland and X11.
    """

    def __init__(self, device_name: str = "AirCursor Virtual Mouse") -> None:
        self.device_name = device_name
        self.screen_width = 1920
        self.screen_height = 1080
        self._probe_screen_size()

        self._uinput = UInputDevice(
            name=device_name,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
            enable_relative=True,
            enable_absolute=True,
        )

    @property
    def is_left_button_down(self) -> bool:
        return self._uinput.is_left_button_down

    @property
    def current_x(self) -> float:
        return self._uinput.cur_x

    @property
    def current_y(self) -> float:
        return self._uinput.cur_y

    def _probe_screen_size(self) -> None:
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
                                return
        except Exception:
            pass

    def move_relative(self, dx: float, dy: float) -> Tuple[float, float]:
        return self._uinput.move_relative(dx, dy)

    def move_absolute(self, x: float, y: float) -> Tuple[float, float]:
        return self._uinput.move_absolute(x, y)

    def handle_packet(self, packet) -> Tuple[float, float]:
        return self._uinput.handle_motion_packet(packet)

    def get_current_location(self) -> Tuple[float, float]:
        return (self._uinput.cur_x, self._uinput.cur_y)

    def click(self, button: str = "left", count: int = 1) -> None:
        self._uinput.click(button=button, count=count)

    def left_down(self) -> None:
        self._uinput.left_down()

    def left_up(self) -> None:
        self._uinput.left_up()

    def toggle_drag(self) -> bool:
        return self._uinput.toggle_drag()

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        self._uinput.scroll(vertical=vertical, horizontal=horizontal)

    def key_combo(self, keys: list[int]) -> None:
        self._uinput.key_combo(keys)

    def mission_control(self) -> None:
        self._uinput.key_combo([KEY_LEFTMETA])

    def browser_back(self) -> None:
        self._uinput.key_combo([KEY_LEFTALT, KEY_LEFTBRACE])

    def browser_forward(self) -> None:
        self._uinput.key_combo([KEY_LEFTALT, KEY_RIGHTBRACE])

    def screenshot(self) -> None:
        self._uinput.key_combo([KEY_PRINT])

    def close(self) -> None:
        self._uinput.close()
