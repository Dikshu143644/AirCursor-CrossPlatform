"""AirCursor Windows Sensor Receiver & Ingestion Engine.

Provides dual-input sensor telemetry:
1. OpenTrack UDP Receiver (Port 4242 standard):
   Receives 48-byte binary packets (6 doubles: x, y, z in cm; yaw, pitch, roll in degrees).
   Compatible with:
   - aap-head-tracker / MagicAAP driver on Windows (AirPods spatial audio IMU over Bluetooth)
   - MousePods Linux/Raspberry Pi bridge
   - Mobile head trackers (SmoothTrack, FreePIE IMU, TrackIR UDP)
   Converts angular data to radians and emits `MotionSample`.

2. SyntheticSensorGenerator:
   Simulates realistic head tracking motion without requiring hardware connected:
   - Smooth figure-8 / Lissajous motion
   - Synthetic Nod gestures
   - Synthetic Shake gestures
   - Synthetic Tilt gestures
   - Synthetic Dwell rest

3. BluetoothAirPodsHelper:
   Scans paired Windows Bluetooth devices for AirPods (AirPods Pro, AirPods Max, AirPods 3)
   and provides connection status & instructions.
"""

from __future__ import annotations

import math
import select
import socket
import struct
import sys
import threading
import time
from typing import Callable, Dict, List, Optional
import winreg

# Import Core models
sys.path.insert(0, r"c:\Users\omkar\TV\AirCursor_CrossPlatform")
from aircursor_core.math_util import AngleMath
from aircursor_core.motion import MotionSample


class OpenTrackReceiver:
    """Listens on UDP (default port 4242) for OpenTrack format telemetry packets."""

    PACKET_FORMAT = "<6d"
    PACKET_SIZE = struct.calcsize(PACKET_FORMAT)  # 48 bytes

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4242,
        on_sample: Optional[Callable[[MotionSample], None]] = None,
    ):
        self.host = host
        self.port = port
        self.on_sample: Optional[Callable[[MotionSample], None]] = on_sample

        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False

        self.samples_received: int = 0
        self.last_sample_time: float = 0.0
        self.last_rates_hz: float = 0.0
        self._rate_count: int = 0
        self._rate_timer: float = 0.0

    @property
    def is_active(self) -> bool:
        return self._running and self._socket is not None

    def start(self) -> None:
        """Binds the UDP socket and starts the listener loop."""
        if self._running:
            return
        self._running = True

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind((self.host, self.port))
        self._socket.setblocking(False)

        self._rate_timer = time.time()
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="AirCursor-OpenTrackUDP"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stops the UDP listener."""
        if not self._running:
            return
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def _listen_loop(self) -> None:
        while self._running and self._socket:
            try:
                r, _, _ = select.select([self._socket], [], [], 0.1)
                if not r:
                    continue

                data, _ = self._socket.recvfrom(128)
                if len(data) >= self.PACKET_SIZE:
                    now = time.time()
                    x, y, z, yaw_deg, pitch_deg, roll_deg = struct.unpack(
                        self.PACKET_FORMAT, data[: self.PACKET_SIZE]
                    )

                    # OpenTrack protocol specifies angles in degrees:
                    # Convert to radians for AirCursor Core MotionSample
                    yaw_rad = AngleMath.radians(yaw_deg)
                    pitch_rad = AngleMath.radians(pitch_deg)
                    roll_rad = AngleMath.radians(roll_deg)

                    sample = MotionSample(
                        timestamp=now,
                        yaw=yaw_rad,
                        pitch=pitch_rad,
                        roll=roll_rad,
                    )

                    self.samples_received += 1
                    self.last_sample_time = now
                    self._rate_count += 1

                    if now - self._rate_timer >= 1.0:
                        self.last_rates_hz = self._rate_count / (now - self._rate_timer)
                        self._rate_count = 0
                        self._rate_timer = now

                    if self.on_sample:
                        try:
                            self.on_sample(sample)
                        except Exception:
                            pass
            except Exception:
                if self._running:
                    time.sleep(0.01)


class SyntheticSensorGenerator:
    """Generates synthetic head motion telemetry for testing and simulation."""

    def __init__(
        self,
        fps: float = 120.0,
        on_sample: Optional[Callable[[MotionSample], None]] = None,
    ):
        self.fps: float = fps
        self.on_sample: Optional[Callable[[MotionSample], None]] = on_sample

        self._running: bool = False
        self._thread: Optional[threading.Thread] = None

        # Base angles in degrees
        self.base_yaw: float = 0.0
        self.base_pitch: float = 0.0
        self.base_roll: float = 0.0

        # Dynamic mode: "idle", "lissajous", "nod", "shake", "tilt_left", "tilt_right"
        self._mode: str = "lissajous"
        self._gesture_start: float = 0.0

    @property
    def is_active(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._generator_loop,
            daemon=True,
            name="AirCursor-SyntheticSensors",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None

    def trigger_nod(self) -> None:
        """Injects a nod gesture (pitch downward by 7 degrees and return over 0.6s)."""
        self._gesture_start = time.time()
        self._mode = "nod"

    def trigger_shake(self) -> None:
        """Injects a head shake gesture (yaw oscillation +-14 deg over 1.2s)."""
        self._gesture_start = time.time()
        self._mode = "shake"

    def trigger_tilt(self, direction: str = "left") -> None:
        """Injects a head tilt gesture (held for 0.4s)."""
        self._gesture_start = time.time()
        self._mode = "tilt_left" if direction == "left" else "tilt_right"

    def trigger_dwell(self) -> None:
        """Holds head motionless to trigger dwell hover click."""
        self._gesture_start = time.time()
        self._mode = "dwell"

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def _generator_loop(self) -> None:
        dt = 1.0 / self.fps
        t0 = time.time()

        while self._running:
            t = time.time()
            elapsed = t - t0
            now = t

            yaw_deg = self.base_yaw
            pitch_deg = self.base_pitch
            roll_deg = self.base_roll

            if self._mode == "lissajous":
                # Smooth figure-8 head turn
                yaw_deg += 8.0 * math.sin(elapsed * 1.5)
                pitch_deg += 5.0 * math.sin(elapsed * 3.0)
                roll_deg += 1.0 * math.sin(elapsed * 0.8)

            elif self._mode == "nod":
                dur = now - self._gesture_start
                if dur <= 0.6:
                    # Bell curve dip
                    phase = math.pi * (dur / 0.6)
                    pitch_deg += 8.0 * math.sin(phase)
                else:
                    self._mode = "lissajous"

            elif self._mode == "shake":
                dur = now - self._gesture_start
                if dur <= 1.2:
                    # 4 swings = 2 full cycles (4 pi)
                    phase = 2.0 * math.pi * (dur / 0.6)
                    yaw_deg += 14.0 * math.sin(phase)
                else:
                    self._mode = "lissajous"

            elif self._mode == "tilt_left":
                dur = now - self._gesture_start
                if dur <= 0.5:
                    roll_deg -= 26.0
                else:
                    self._mode = "lissajous"

            elif self._mode == "tilt_right":
                dur = now - self._gesture_start
                if dur <= 0.5:
                    roll_deg += 26.0
                else:
                    self._mode = "lissajous"

            elif self._mode == "dwell":
                # Stationary with micro jitter
                yaw_deg += 0.02 * math.sin(elapsed * 10)
                pitch_deg += 0.02 * math.cos(elapsed * 10)

            sample = MotionSample(
                timestamp=now,
                yaw=AngleMath.radians(yaw_deg),
                pitch=AngleMath.radians(pitch_deg),
                roll=AngleMath.radians(roll_deg),
            )

            if self.on_sample:
                try:
                    self.on_sample(sample)
                except Exception:
                    pass

            time.sleep(dt)


class BluetoothAirPodsHelper:
    """Helper to detect AirPods paired to Windows and provide setup instructions."""

    KNOWN_AIRPODS_NAMES = (
        "airpods",
        "airpods pro",
        "airpods max",
        "airpods 3",
        "airpods 4",
    )

    @classmethod
    def list_paired_headphones(cls) -> List[Dict[str, str]]:
        """Queries Windows registry for paired Bluetooth devices."""
        devices = []
        path = r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                count, _, _ = winreg.QueryInfoKey(key)
                for i in range(count):
                    sub = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(key, sub) as dev_key:
                            raw_name, _ = winreg.QueryValueEx(dev_key, "Name")
                            if isinstance(raw_name, bytes):
                                name = raw_name.decode("utf-8", errors="ignore").rstrip("\x00")
                            else:
                                name = str(raw_name)
                            is_airpods = any(
                                tag in name.lower() for tag in cls.KNOWN_AIRPODS_NAMES
                            )
                            devices.append(
                                {
                                    "address": sub,
                                    "name": name,
                                    "is_airpods": is_airpods,
                                }
                            )
                    except Exception:
                        pass
        except Exception:
            pass
        return devices

    @classmethod
    def get_paired_airpods(cls) -> List[Dict[str, str]]:
        """Returns paired Apple AirPods devices."""
        return [d for d in cls.list_paired_headphones() if d.get("is_airpods")]

    @classmethod
    def get_setup_instructions(cls) -> str:
        return (
            "=== AirPods Setup on Windows ===\n"
            "1. Put both AirPods in their charging case and open the lid.\n"
            "2. Press and hold the button on the back of the case until the status light pulses white.\n"
            "3. On Windows, open Settings > Bluetooth & devices > Add device > Bluetooth.\n"
            "4. Select your AirPods from the list to pair.\n"
            "5. Audio Output: Press Win + Ctrl + V and select your AirPods as the output device.\n"
            "6. Head Tracking Telemetry:\n"
            "   - Run 'aap-head-tracker' (MagicAAP) on Windows, or\n"
            "   - Run 'AirCursor' in --synthetic mode for testing without hardware, or\n"
            "   - Connect an OpenTrack UDP stream on port 4242 from a phone or companion bridge.\n"
        )
