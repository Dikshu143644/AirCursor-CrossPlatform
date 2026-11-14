"""
AirPods BlueZ L2CAP Driver for Linux.
Direct BlueZ L2CAP socket connector with MTU 2582 (required for AirPods Pro and AirPods 3+
to stream motion without truncation), handling Apple AAP / RemoteHID handshake (devmotion6 /
SensorDataWX service channels) and decoding binary packets into yaw, pitch, roll.
"""

from __future__ import annotations
import math
import os
import re
import socket
import struct
import subprocess
import threading
import time
from typing import Callable, List, Optional, Tuple

from aircursor_core import MotionSample


# ==============================================================================
# Protocol Constants & Configuration
# ==============================================================================

# Linux Bluetooth socket constants
AF_BLUETOOTH = getattr(socket, "AF_BLUETOOTH", 31)
BTPROTO_L2CAP = getattr(socket, "BTPROTO_L2CAP", 0)
SOL_L2CAP = 6
L2CAP_OPTIONS = 1

# Apple Accessory Protocol / RemoteHID L2CAP PSMs
L2CAP_PSM_AAP = 0x1001          # 4097 - Primary Apple Accessory Protocol PSM
FALLBACK_PSMS = [0x1001, 0x1000, 0x1002]

# REQUIRED MTU: Default Linux L2CAP receive MTU is 672, which causes AirPods to
# drop or fail to announce high-bandwidth sensor descriptors (devmotion6 is >800 bytes).
# Setting imtu to 2582 (the exact value used by iOS/macOS) enables full sensor streaming.
AIRPODS_L2CAP_MTU = 2582

# RemoteHID / RTBuddy service channel descriptors
DESCRIPTOR_REMOTEHID_SENSOR = 0x00000800   # AirPods 3 Sensor channel (0x800)
DESCRIPTOR_SENSORDATA_WX    = 0x00100000   # AirPods Pro / 4 SensorDataWX channel
OPCODE_RTBUDDY              = 0x0017       # 23 (RTBuddy transport opcode)

# RemoteHID Sub-packet definitions
KIND_DEVICE_CONNECT    = 0
KIND_DEVICE_DISCONNECT = 1
KIND_INPUT_REPORT      = 2
KIND_SET_REPORT        = 3
KIND_GET_REPORT        = 4

# Device IDs
DEVICE_ID_DEVMOTION6   = 7    # AirPods 3 fused motion service (devmotion6)


# ==============================================================================
# Coordinate Transformations & Math Helpers
# ==============================================================================

def decode_q15_quaternion(raw_x: int, raw_y: int, raw_z: int) -> Tuple[float, float, float, float]:
    """
    Decodes 3 x int16 vector part in Q15 format into a normalized quaternion (w, x, y, z).
    In Apple's wire format, components are divided by 32768.0 and scalar w = sqrt(max(0, 1 - |v|^2)).
    """
    x = raw_x / 32768.0
    y = raw_y / 32768.0
    z = raw_z / 32768.0
    v_sq = x * x + y * y + z * z
    w = math.sqrt(max(0.0, 1.0 - v_sq))
    
    # Re-normalize for numerical stability
    norm = math.hypot(w, math.hypot(x, math.hypot(y, z)))
    if norm > 0.0:
        w /= norm
        x /= norm
        y /= norm
        z /= norm
    return (w, x, y, z)


def quaternion_to_euler(w: float, x: float, y: float, z: float) -> Tuple[float, float, float]:
    """
    Converts orientation quaternion to (yaw, pitch, roll) in radians
    matching Apple CoreMotion CMDeviceMotion.attitude conventions:
    - Yaw: head turn left/right (rotation about gravity-aligned vertical axis)
    - Pitch: head look up/down (rotation about transverse axis)
    - Roll: head tilt left/right (rotation about longitudinal axis)
    """
    # Yaw (Z-axis rotation, heading in horizontal plane)
    siny = 2.0 * (w * z + x * y)
    cosy = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny, cosy)

    # Pitch (X/Y-axis rotation, elevation)
    sinp = 2.0 * (w * y - z * x)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    # Roll (tilt)
    sinr = 2.0 * (w * x + y * z)
    cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)

    return (yaw, pitch, roll)


# ==============================================================================
# AirPods Discovery & Pairing Inspection
# ==============================================================================

class BluetoothScanner:
    """Discovers paired AirPods devices using BlueZ commands or D-Bus."""

    @staticmethod
    def find_paired_airpods() -> List[Tuple[str, str]]:
        """
        Returns list of (mac_address, device_name) for paired AirPods / Beats devices.
        """
        results: List[Tuple[str, str]] = []
        try:
            # Query bluetoothctl for paired devices
            out = subprocess.check_output(
                ["bluetoothctl", "paired-devices"],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=3.0
            )
            for line in out.strip().splitlines():
                # Format: Device XX:XX:XX:XX:XX:XX Name Of Device
                parts = line.split(maxsplit=2)
                if len(parts) >= 3 and parts[0] == "Device":
                    mac = parts[1].strip()
                    name = parts[2].strip()
                    # Filter for Apple AirPods or Beats
                    lower_name = name.lower()
                    if any(k in lower_name for k in ("airpod", "airpods", "beats fit", "beats studio", "powerbeats")):
                        results.append((mac, name))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return results


# ==============================================================================
# AirPods BlueZ L2CAP Driver
# ==============================================================================

class AirPodsBlueZDriver:
    """
    Direct BlueZ L2CAP socket connector with MTU 2582 for Apple AirPods.
    Handles handshake for RemoteHID (AirPods 3) and SensorDataWX (AirPods Pro / 4),
    streams motion reports, and invokes on_sample callback with MotionSample.
    """

    def __init__(
        self,
        mac_address: str,
        on_sample: Callable[[MotionSample], None],
        on_status: Optional[Callable[[str, bool], None]] = None,
        sample_interval_us: int = 10000,  # 10,000 us = 100 Hz
    ) -> None:
        self.mac_address = mac_address.upper()
        self.on_sample = on_sample
        self.on_status = on_status
        self.sample_interval_us = sample_interval_us

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._generation = 0
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AirPodsBlueZWorker")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._sock:
            try:
                self._send_stop_report()
            except Exception:
                pass
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._is_connected = False
        if self.on_status:
            self.on_status("Disconnected", False)

    # --------------------------------------------------------------------------
    # L2CAP Socket Setup & MTU Configuration
    # --------------------------------------------------------------------------

    def _create_and_configure_socket(self) -> socket.socket:
        """
        Creates a raw AF_BLUETOOTH SOCK_SEQPACKET L2CAP socket and configures
        the receive MTU (imtu) to 2582 bytes using getsockopt/setsockopt.
        """
        sock = socket.socket(AF_BLUETOOTH, socket.SOCK_SEQPACKET, BTPROTO_L2CAP)
        sock.settimeout(4.0)

        # Set L2CAP MTU to 2582 bytes before connect()
        try:
            # Query current options: struct l2cap_options (12 bytes: HHHBBBH)
            opt_data = sock.getsockopt(SOL_L2CAP, L2CAP_OPTIONS, 12)
            omtu, imtu, flush_to, mode, fcs, max_tx, txwin_size = struct.unpack("HHHBBBH", opt_data)
            # Reconfigure imtu and omtu to AIRPODS_L2CAP_MTU (2582)
            packed = struct.pack("HHHBBBH", AIRPODS_L2CAP_MTU, AIRPODS_L2CAP_MTU, flush_to, mode, fcs, max_tx, txwin_size)
            sock.setsockopt(SOL_L2CAP, L2CAP_OPTIONS, packed)
        except OSError:
            try:
                # Fallback to older 8-byte struct l2cap_options (HHHB)
                opt_data = sock.getsockopt(SOL_L2CAP, L2CAP_OPTIONS, 8)
                omtu, imtu, flush_to, mode = struct.unpack("HHHB", opt_data)
                packed = struct.pack("HHHB", AIRPODS_L2CAP_MTU, AIRPODS_L2CAP_MTU, flush_to, mode)
                sock.setsockopt(SOL_L2CAP, L2CAP_OPTIONS, packed)
            except OSError:
                # If OS denies custom MTU modification, proceed with socket default
                pass

        return sock

    # --------------------------------------------------------------------------
    # Packet Serialization & RemoteHID Handshake
    # --------------------------------------------------------------------------

    def _build_aacp_rtbuddy_packet(self, channel_descriptor: int, payload: bytes) -> bytes:
        """
        Wraps an RTBuddy message payload into an Apple Accessory Protocol (AACP) frame.
        Format: [AACP Header (4B)] | [Opcode 0x17 (2B)] | [Descriptor u32 LE] | [Length u16 LE] | [Body]
        """
        rtbuddy_header = struct.pack("<HIH", OPCODE_RTBUDDY, channel_descriptor, len(payload))
        packet_body = rtbuddy_header + payload
        aacp_header = struct.pack(">HH", 0xFF55, len(packet_body))
        return aacp_header + packet_body

    def _build_remotehid_body(self, subpackets: List[bytes]) -> bytes:
        """
        Constructs the RemoteHID transport body on channel 0x800:
        Offset 0: transport version (0)
        Offset 1: generation (+1 per message)
        Offset 2: 0
        Offset 3: side flags (host = 0)
        Offset 4+: subpackets back-to-back
        """
        self._generation = (self._generation + 1) & 0xFF
        header = struct.pack("BBBB", 0x00, self._generation, 0x00, 0x00)
        return header + b"".join(subpackets)

    def _build_set_report_subpacket(self, device_id: int, report_id: int, payload: bytes) -> bytes:
        """
        Builds a RemoteHID SetReport sub-packet:
        u32 LE Header:
          bits 0..6: deviceID (7 for devmotion6)
          bits 7..16: length in bytes (including 4B header)
          bits 17..19: kind (3 = SetReport)
          bit 20: 0
          bit 21: 0 (response)
          bit 22: 0 (status byte present)
        """
        data = struct.pack("B", report_id) + payload
        total_len = 4 + len(data)
        header_val = (device_id & 0x7F) | ((total_len & 0x3FF) << 7) | ((KIND_SET_REPORT & 0x07) << 17)
        return struct.pack("<I", header_val) + data

    def _send_start_handshake(self) -> None:
        """
        Sends activation commands for both RemoteHID (AirPods 3) and SensorDataWX (AirPods Pro).
        RemoteHID: devmotion6 SetReport with sample interval (e.g. 10,000us = 100Hz).
        SensorDataWX: RTBuddy channel 0x100000 stream start request.
        """
        if not self._sock:
            return

        # 1. RemoteHID (AirPods 3) handshake
        interval_bytes = struct.pack("<I", self.sample_interval_us)
        subpacket = self._build_set_report_subpacket(
            device_id=DEVICE_ID_DEVMOTION6,
            report_id=0x01,
            payload=interval_bytes,
        )
        remotehid_body = self._build_remotehid_body([subpacket])
        remotehid_packet = self._build_aacp_rtbuddy_packet(DESCRIPTOR_REMOTEHID_SENSOR, remotehid_body)
        try:
            self._sock.sendall(remotehid_packet)
        except Exception:
            pass

        # 2. SensorDataWX (AirPods Pro / 4) handshake
        sensordata_cmd = bytes([
            0x01, 0x00, 0x00, 0x00,
            0x08, 0x01, 0x12, 0x04, 0x08, 0x06, 0x10, 0x01,
        ])
        sensordata_packet = self._build_aacp_rtbuddy_packet(DESCRIPTOR_SENSORDATA_WX, sensordata_cmd)
        try:
            self._sock.sendall(sensordata_packet)
        except Exception:
            pass

    def _send_stop_report(self) -> None:
        """Sends interval=0 to devmotion6 to stop sensor power draw."""
        if not self._sock:
            return
        interval_bytes = struct.pack("<I", 0)
        subpacket = self._build_set_report_subpacket(
            device_id=DEVICE_ID_DEVMOTION6,
            report_id=0x01,
            payload=interval_bytes,
        )
        remotehid_body = self._build_remotehid_body([subpacket])
        packet = self._build_aacp_rtbuddy_packet(DESCRIPTOR_REMOTEHID_SENSOR, remotehid_body)
        try:
            self._sock.sendall(packet)
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # Packet Parsing & Motion Extraction
    # --------------------------------------------------------------------------

    def parse_motion_block(self, block: bytes) -> Optional[MotionSample]:
        """
        Parses a 58-byte motion block:
        - Bytes [0]: status / marker (0x01)
        - Bytes [1:9]: timestamp in nanoseconds (u64 LE)
        - Bytes [20:26]: orientation quaternion vector part (3 x int16 LE in Q15)
        - Converts quaternion to yaw, pitch, roll
        """
        if len(block) < 26:
            return None

        # Parse Q15 quaternion vector part at offsets [20:26]
        raw_x, raw_y, raw_z = struct.unpack_from("<hhh", block, 20)
        w, x, y, z = decode_q15_quaternion(raw_x, raw_y, raw_z)

        # Convert to Euler angles
        yaw, pitch, roll = quaternion_to_euler(w, x, y, z)
        timestamp = time.time()

        return MotionSample(timestamp=timestamp, yaw=yaw, pitch=pitch, roll=roll)

    def parse_incoming_packet(self, data: bytes) -> None:
        """
        Parses incoming L2CAP packet data for RemoteHID input reports
        or SensorDataWX motion streams.
        """
        if len(data) < 10:
            return

        # Check for AACP Header (0xFF 0x55)
        offset = 0
        if data[0:2] == b"\xff\x55":
            offset = 4  # Skip AACP header

        # Check for RTBuddy Opcode 0x17
        if offset + 8 <= len(data):
            opcode, descriptor, length = struct.unpack_from("<HIH", data, offset)
            if opcode == OPCODE_RTBUDDY:
                offset += 8
                payload = data[offset : offset + length]
                
                # Check if this is RemoteHID channel (0x800)
                if descriptor == DESCRIPTOR_REMOTEHID_SENSOR and len(payload) >= 4:
                    sub_offset = 4
                    while sub_offset + 4 <= len(payload):
                        header_val = struct.unpack_from("<I", payload, sub_offset)[0]
                        device_id = header_val & 0x7F
                        sub_len = (header_val >> 7) & 0x3FF
                        kind = (header_val >> 17) & 0x07
                        has_ts = (header_val >> 20) & 0x01

                        if sub_len < 4 or sub_offset + sub_len > len(payload):
                            break

                        sub_payload = payload[sub_offset + 4 : sub_offset + sub_len]
                        if kind == KIND_INPUT_REPORT and device_id == DEVICE_ID_DEVMOTION6:
                            motion_data = sub_payload[8:] if has_ts and len(sub_payload) > 8 else sub_payload
                            if len(motion_data) >= 58:
                                sample = self.parse_motion_block(motion_data[:58])
                                if sample and self.on_sample:
                                    self.on_sample(sample)
                        sub_offset += sub_len
                    return

                # Check if SensorDataWX channel (0x100000)
                if descriptor == DESCRIPTOR_SENSORDATA_WX:
                    if len(payload) >= 58:
                        sample = self.parse_motion_block(payload[:58])
                        if sample and self.on_sample:
                            self.on_sample(sample)
                    return

        # Fallback raw pattern search if packet arrived without AACP framing
        if len(data) >= 58:
            sample = self.parse_motion_block(data[:58])
            if sample and self.on_sample:
                self.on_sample(sample)

    # --------------------------------------------------------------------------
    # Connection Worker Loop
    # --------------------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Main background connection loop with auto-reconnect."""
        while self._running:
            try:
                if self.on_status:
                    self.on_status(f"Connecting to {self.mac_address} (PSM 0x1001, MTU 2582)...", False)

                sock = self._create_and_configure_socket()
                
                # Attempt connection on PSM 0x1001
                connected = False
                for psm in FALLBACK_PSMS:
                    try:
                        sock.connect((self.mac_address, psm))
                        connected = True
                        break
                    except OSError:
                        continue

                if not connected:
                    sock.close()
                    time.sleep(2.0)
                    continue

                self._sock = sock
                self._is_connected = True
                sock.settimeout(0.5)

                if self.on_status:
                    self.on_status(f"Connected to AirPods ({self.mac_address})", True)

                # Send activation handshake
                self._send_start_handshake()

                # Stream reception loop
                last_keepalive = time.time()
                while self._running:
                    try:
                        packet = sock.recv(AIRPODS_L2CAP_MTU)
                        if not packet:
                            break
                        self.parse_incoming_packet(packet)
                    except socket.timeout:
                        now = time.time()
                        if now - last_keepalive > 3.0:
                            self._send_start_handshake()
                            last_keepalive = now
                        continue
                    except OSError:
                        break

            except Exception as e:
                if self.on_status:
                    self.on_status(f"Connection error: {e}", False)
            finally:
                self._is_connected = False
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None

            if self._running:
                time.sleep(1.5)  # Reconnect backoff
