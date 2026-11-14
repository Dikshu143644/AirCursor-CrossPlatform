"""
Lightweight Linux GTK/Cairo Transparent Click-Through Overlay.
Renders the circular dwell progress ring, click ripple pulse, and HUD toasts
without stealing focus or intercepting mouse events.
"""

from __future__ import annotations
import math
import threading
import time
from typing import Optional, Tuple


# ==============================================================================
# GTK & Cairo Overlay Controller
# ==============================================================================

class LinuxOverlayController:
    """
    Transparent, click-through overlay window using GTK 3 and Cairo.
    Draws a smooth circular dwell ring around the pointer and click pulse ripples.
    """

    def __init__(self, size: int = 72) -> None:
        self.size = size
        self.cur_x = 0.0
        self.cur_y = 0.0
        self.dwell_progress: Optional[float] = None
        self.pulse_active = False
        self.pulse_start_time = 0.0
        self.pulse_duration = 0.40

        self.hud_text: Optional[str] = None
        self.hud_hide_time = 0.0

        self._available = False
        self._window = None
        self._drawing_area = None
        self._thread: Optional[threading.Thread] = None

        self._init_gtk()

    def _init_gtk(self) -> None:
        """Initializes GTK window with transparent RGBA visual and input shape passthrough."""
        try:
            import gi
            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk, GLib
            import cairo

            self._Gtk = Gtk
            self._Gdk = Gdk
            self._GLib = GLib
            self._cairo = cairo

            # Create popup window (no window manager decorations)
            win = Gtk.Window(type=Gtk.WindowType.POPUP)
            win.set_app_paintable(True)
            win.set_size_request(self.size, self.size)
            win.set_position(Gtk.WindowPosition.NONE)
            win.set_accept_focus(False)
            win.set_keep_above(True)
            win.stick()

            # Set RGBA visual for per-pixel transparency
            screen = win.get_screen()
            visual = screen.get_rgba_visual()
            if visual is not None:
                win.set_visual(visual)

            # Input shape passthrough: empty region makes window 100% click-through
            empty_region = cairo.Region()
            win.input_shape_combine_region(empty_region)

            drawing_area = Gtk.DrawingArea()
            drawing_area.connect("draw", self._on_draw)
            win.add(drawing_area)

            self._window = win
            self._drawing_area = drawing_area
            self._available = True

            # Start GTK loop in dedicated background thread
            self._thread = threading.Thread(target=self._run_gtk_loop, daemon=True, name="GTKOverlayLoop")
            self._thread.start()
        except (ImportError, Exception):
            # GTK not present or running headless
            self._available = False

    def _run_gtk_loop(self) -> None:
        try:
            self._Gtk.main()
        except Exception:
            pass

    def _on_draw(self, widget, cr) -> bool:
        """Cairo drawing callback: renders ring, pulse, and HUD."""
        # Clear background to transparent
        cr.set_operator(self._cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(self._cairo.OPERATOR_OVER)

        center_x = self.size / 2.0
        center_y = self.size / 2.0
        radius = (self.size / 2.0) - 8.0

        now = time.time()

        # 1. Click Ripple Pulse Animation
        if self.pulse_active:
            elapsed = now - self.pulse_start_time
            if elapsed < self.pulse_duration:
                t = elapsed / self.pulse_duration
                pulse_r = radius * (0.5 + 1.2 * t)
                alpha = max(0.0, 0.8 * (1.0 - t))
                cr.set_line_width(2.5)
                cr.set_source_rgba(0.0, 0.48, 1.0, alpha)
                cr.arc(center_x, center_y, pulse_r, 0, 2 * math.pi)
                cr.stroke()
            else:
                self.pulse_active = False

        # 2. Circular Dwell Progress Ring
        if self.dwell_progress is not None:
            # Draw dark background track
            cr.set_line_width(4.0)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.25)
            cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
            cr.stroke()

            # Draw progress arc (start at 12 o'clock: -pi/2, sweep clockwise)
            progress = min(max(self.dwell_progress, 0.0), 1.0)
            start_angle = -math.pi / 2.0
            end_angle = start_angle + (2.0 * math.pi * progress)

            cr.set_line_width(4.0)
            cr.set_line_cap(self._cairo.LINE_CAP_ROUND)
            # Vibrant accent color: Apple-style electric blue / cyan
            cr.set_source_rgba(0.0, 0.55, 1.0, 0.95)
            cr.arc(center_x, center_y, radius, start_angle, end_angle)
            cr.stroke()

        return False

    # --------------------------------------------------------------------------
    # Public Controller API
    # --------------------------------------------------------------------------

    def update(self, dwell_progress: Optional[float], x: float, y: float) -> None:
        """Updates cursor dwell progress and position."""
        if not self._available or not self._window:
            return

        self.cur_x = x
        self.cur_y = y
        self.dwell_progress = dwell_progress

        def _gui_update():
            # Reposition window centered at (x, y)
            wx = int(round(self.cur_x - (self.size / 2.0)))
            wy = int(round(self.cur_y - (self.size / 2.0)))
            self._window.move(wx, wy)

            should_show = (self.dwell_progress is not None) or self.pulse_active
            if should_show and not self._window.is_visible():
                self._window.show_all()
            elif not should_show and self._window.is_visible():
                self._window.hide()

            if self._drawing_area:
                self._drawing_area.queue_draw()
            return False

        self._GLib.idle_add(_gui_update)

    def pulse(self, x: float, y: float) -> None:
        """Fires expanding ripple pulse at the click coordinate."""
        if not self._available or not self._window:
            return

        self.cur_x = x
        self.cur_y = y
        self.pulse_active = True
        self.pulse_start_time = time.time()

        def _gui_pulse():
            wx = int(round(self.cur_x - (self.size / 2.0)))
            wy = int(round(self.cur_y - (self.size / 2.0)))
            self._window.move(wx, wy)
            self._window.show_all()
            if self._drawing_area:
                self._drawing_area.queue_draw()
            return False

        self._GLib.idle_add(_gui_pulse)

    def show_hud(self, text: str, duration_sec: float = 1.5) -> None:
        """Displays small status text in terminal/logger or window."""
        self.hud_text = text
        self.hud_hide_time = time.time() + duration_sec
        print(f"[AirCursor HUD] {text}")

    def hide(self) -> None:
        """Hides overlay."""
        if self._available and self._window:
            self._GLib.idle_add(self._window.hide)

    def close(self) -> None:
        """Clean shutdown."""
        if self._available and self._window:
            self._GLib.idle_add(self._Gtk.main_quit)
