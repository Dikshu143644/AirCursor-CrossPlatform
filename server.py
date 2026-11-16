#!/usr/bin/env python3
"""
AirCursor Headless & Container Server Daemon.
Provides:
1. Web Remote PWA & REST API on port 8765 (with /status healthcheck).
2. OpenTrack / AirPods UDP sensor listener on port 4242/udp.
3. Synthetic sensor generator for container/cloud simulation mode.
4. Seamless compatibility with virtual display servers (Xvfb / noVNC).
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import math
import mimetypes
import os
from pathlib import Path
import select
import signal
import socket
import struct
import sys
import threading
import time
from typing import Any, Dict, Optional, Tuple

# Ensure package roots are discoverable
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from aircursor_core.actions import ActionMap, PointerAction, Trigger
from aircursor_core.dwell import DwellDetector
from aircursor_core.gestures import GestureDetector, HeadGesture
from aircursor_core.math_util import AngleMath, Vec2
from aircursor_core.motion import MotionDifferentiator, MotionSample
from aircursor_core.pointer import CursorHistory, PointerMapper, PointerSmoother
from aircursor_core.settings import AppSettings


class AirCursorServerController:
    """Core state and motion orchestrator for headless / server deployments."""

    def __init__(
        self,
        settings: Optional[AppSettings] = None,
        mode: str = "synthetic",
        autorun: bool = True,
        udp_host: str = "0.0.0.0",
        udp_port: int = 4242,
    ) -> None:
        self.settings = settings or AppSettings()
        self.mode = mode.lower()
        self.autorun = autorun
        self.udp_host = udp_host
        self.udp_port = udp_port

        self.tracking_enabled: bool = autorun
        self.scroll_mode: bool = False
        self.is_dragging: bool = False
        self.start_time: float = time.time()
        self._running: bool = False

        # Virtual pointer position
        self.screen_width: int = int(os.environ.get("SCREEN_WIDTH", "1920"))
        self.screen_height: int = int(os.environ.get("SCREEN_HEIGHT", "1080"))
        self.cursor_x: float = self.screen_width / 2.0
        self.cursor_y: float = self.screen_height / 2.0

        # Kinematics pipeline
        self.differentiator = MotionDifferentiator()
        self.smoother = PointerSmoother()
        self.history = CursorHistory(capacity=360)
        self.gesture_detector = GestureDetector(self.settings.gestures)
        self.dwell_detector = DwellDetector(self.settings.dwell)

        # Telemetry readouts
        self.live_yaw: float = 0.0
        self.live_pitch: float = 0.0
        self.live_roll: float = 0.0
        self.samples_received: int = 0
        self.fps: float = 120.0
        self._frame_count: int = 0
        self._last_fps_time: float = time.time()

        # UDP Socket & Threads
        self._udp_socket: Optional[socket.socket] = None
        self._udp_thread: Optional[threading.Thread] = None
        self._pipeline_thread: Optional[threading.Thread] = None
        self._sim_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts background processing loops."""
        if self._running:
            return
        self._running = True

        # 1. Start UDP receiver
        self._start_udp_listener()

        # 2. Start Pipeline Frame Loop (100-120Hz)
        self._pipeline_thread = threading.Thread(
            target=self._pipeline_loop,
            daemon=True,
            name="AirCursor-ServerPipeline",
        )
        self._pipeline_thread.start()

        # 3. Start Synthetic generator if in synthetic mode
        if self.mode == "synthetic":
            self._sim_thread = threading.Thread(
                target=self._synthetic_loop,
                daemon=True,
                name="AirCursor-ServerSynthetic",
            )
            self._sim_thread.start()

    def stop(self) -> None:
        """Stops background threads and cleans up resources."""
        self._running = False
        if self._udp_socket:
            try:
                self._udp_socket.close()
            except Exception:
                pass
            self._udp_socket = None

    def _start_udp_listener(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.udp_host, self.udp_port))
            sock.setblocking(False)
            self._udp_socket = sock

            self._udp_thread = threading.Thread(
                target=self._udp_loop,
                daemon=True,
                name="AirCursor-ServerUDP",
            )
            self._udp_thread.start()
        except Exception as e:
            print(f"[Warning] Could not bind UDP port {self.udp_port}: {e}")

    def _udp_loop(self) -> None:
        """Decodes OpenTrack 48-byte packets (<6d: x,y,z,yaw,pitch,roll) and responds to UDP discovery."""
        format_str = "<6d"
        packet_size = struct.calcsize(format_str)

        while self._running and self._udp_socket:
            try:
                r, _, _ = select.select([self._udp_socket], [], [], 0.1)
                if not r:
                    continue
                data, addr = self._udp_socket.recvfrom(512)
                if len(data) >= packet_size:
                    now = time.time()
                    _, _, _, yaw_deg, pitch_deg, roll_deg = struct.unpack(
                        format_str, data[:packet_size]
                    )
                    sample = MotionSample(
                        timestamp=now,
                        yaw=AngleMath.radians(yaw_deg),
                        pitch=AngleMath.radians(pitch_deg),
                        roll=AngleMath.radians(roll_deg),
                    )
                    self.push_sample(sample)
                elif b"discover" in data.lower() or b"aircursor" in data.lower():
                    # Reply with discovery announcement
                    resp = json.dumps({
                        "service": "aircursor",
                        "status": "ok",
                        "http_port": 8765,
                        "udp_port": self.udp_port,
                        "version": "1.0.5"
                    }).encode("utf-8")
                    self._udp_socket.sendto(resp, addr)
            except Exception:
                pass

    def push_sample(self, sample: MotionSample) -> None:
        """Pushes an incoming orientation sample into the motion pipeline."""
        self.samples_received += 1
        self.live_yaw = AngleMath.degrees(sample.yaw)
        self.live_pitch = AngleMath.degrees(sample.pitch)
        self.live_roll = AngleMath.degrees(sample.roll)

        rates = self.differentiator.push(sample)
        if rates and self.tracking_enabled:
            target_vel = PointerMapper.cursor_velocity(rates, self.settings.pointer)
            self.smoother.set_target(target_vel, sample.timestamp)

        # Gestures
        enabled_gestures = self.settings.actions.enabled_head_gestures
        gesture_evt = self.gesture_detector.process(sample, enabled_gestures)
        if gesture_evt:
            trigger = Trigger(gesture_evt.gesture)
            action = self.settings.actions.get(trigger)
            self.execute_action(action)

    def execute_action(self, action: PointerAction) -> None:
        """Executes pointer action or state change."""
        if action == PointerAction.TOGGLE_TRACKING:
            self.tracking_enabled = not self.tracking_enabled
        elif action == PointerAction.TOGGLE_SCROLL_MODE:
            self.scroll_mode = not self.scroll_mode
        elif action == PointerAction.TOGGLE_DRAG:
            self.is_dragging = not self.is_dragging
        elif action == PointerAction.RECENTER:
            self.cursor_x = self.screen_width / 2.0
            self.cursor_y = self.screen_height / 2.0
            self.smoother.reset()

    def _pipeline_loop(self) -> None:
        """Advances pointer smoother at ~100Hz."""
        last_time = time.time()
        while self._running:
            now = time.time()
            dt = max(0.001, now - last_time)
            last_time = now

            if self.tracking_enabled:
                disp = self.smoother.step(now, dt, self.settings.pointer.smoothing)
                self.cursor_x = max(0.0, min(float(self.screen_width), self.cursor_x + disp.x))
                self.cursor_y = max(0.0, min(float(self.screen_height), self.cursor_y + disp.y))
                self.history.append(Vec2(self.cursor_x, self.cursor_y), now)

            # Frame rate tracking
            self._frame_count += 1
            if now - self._last_fps_time >= 1.0:
                self.fps = self._frame_count / (now - self._last_fps_time)
                self._frame_count = 0
                self._last_fps_time = now

            time.sleep(0.01)

    def _synthetic_loop(self) -> None:
        """Generates realistic synthetic sensor waves for automated testing and cloud demo."""
        t = 0.0
        while self._running:
            now = time.time()
            t += 0.02
            # Smooth figures-of-eight motion
            yaw = math.sin(t * 0.7) * 8.0
            pitch = math.sin(t * 1.4) * 4.0
            roll = math.cos(t * 0.5) * 2.0

            sample = MotionSample(
                timestamp=now,
                yaw=AngleMath.radians(yaw),
                pitch=AngleMath.radians(pitch),
                roll=AngleMath.radians(roll),
            )
            self.push_sample(sample)
            time.sleep(0.02)

    def get_status_dict(self) -> Dict[str, Any]:
        """Builds status dictionary matching Docker & K8s healthcheck specs."""
        now = time.time()
        return {
            "status": "ok",
            "service": "aircursor",
            "version": "1.0.5",
            "mode": self.mode,
            "tracking": self.tracking_enabled,
            "scroll_mode": self.scroll_mode,
            "is_dragging": self.is_dragging,
            "uptime_seconds": round(now - self.start_time, 2),
            "fps": round(self.fps, 1),
            "telemetry": {
                "yaw": round(self.live_yaw, 2),
                "pitch": round(self.live_pitch, 2),
                "roll": round(self.live_roll, 2),
            },
            "cursor": {
                "x": round(self.cursor_x, 1),
                "y": round(self.cursor_y, 1),
                "screen_width": self.screen_width,
                "screen_height": self.screen_height,
            },
            "sensors": {
                "samples_received": self.samples_received,
                "udp_port": self.udp_port,
            },
            "system": {
                "platform": sys.platform,
                "display": os.environ.get("DISPLAY", "headless"),
                "novnc_enabled": os.environ.get("ENABLE_NOVNC", "true").lower() in ("true", "1", "yes"),
            },
        }


class AirCursorRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler serving Web Remote PWA, REST APIs, and healthchecks."""

    controller: Optional[AirCursorServerController] = None
    web_dir: Path = ROOT_DIR / "web"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.web_dir), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy healthcheck access logs in quiet mode
        if os.environ.get("QUIET_LOGS", "true").lower() in ("true", "1", "yes"):
            return
        super().log_message(format, *args)

    def send_json_response(self, data: Any, status_code: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _handle_websocket_handshake(self, ws_key: str) -> None:
        import hashlib
        import base64
        guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept_token = base64.b64encode(hashlib.sha1((ws_key.strip() + guid).encode("utf-8")).digest()).decode("utf-8")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_token)
        self.end_headers()
        self._serve_websocket()

    def _serve_websocket(self) -> None:
        """Handles RFC 6455 framed WebSocket messages for bidirectional telemetry and control."""
        try:
            hello_json = json.dumps({"type": "server_hello", "service": "aircursor", "status": "ok"}).encode("utf-8")
            frame = (
                bytearray([0x81, len(hello_json)]) + hello_json
                if len(hello_json) < 126
                else bytearray([0x81, 126]) + struct.pack(">H", len(hello_json)) + hello_json
            )
            self.wfile.write(frame)
            self.wfile.flush()

            while True:
                header = self.rfile.read(2)
                if not header or len(header) < 2:
                    break
                b1, b2 = header[0], header[1]
                opcode = b1 & 0x0F
                if opcode == 0x08:  # Close opcode
                    break
                is_masked = (b2 & 0x80) != 0
                payload_len = b2 & 0x7F
                if payload_len == 126:
                    payload_len = struct.unpack(">H", self.rfile.read(2))[0]
                elif payload_len == 127:
                    payload_len = struct.unpack(">Q", self.rfile.read(8))[0]

                masks = self.rfile.read(4) if is_masked else b""
                raw_payload = self.rfile.read(payload_len)
                payload = bytes(b ^ masks[i % 4] for i, b in enumerate(raw_payload)) if is_masked else raw_payload

                if opcode == 0x01:  # Text frame
                    try:
                        data = json.loads(payload.decode("utf-8"))
                        if self.controller:
                            if "yaw" in data and "pitch" in data and "roll" in data:
                                sample = MotionSample(
                                    timestamp=time.time(),
                                    yaw=AngleMath.radians(float(data["yaw"])),
                                    pitch=AngleMath.radians(float(data["pitch"])),
                                    roll=AngleMath.radians(float(data["roll"])),
                                )
                                self.controller.push_sample(sample)
                            elif "action" in data:
                                act = str(data["action"]).lower()
                                if act == "click" or act == "left_click":
                                    self.controller.execute_action(PointerAction.LEFT_CLICK)
                                elif act == "recenter":
                                    self.controller.execute_action(PointerAction.RECENTER)
                    except Exception:
                        pass
                elif opcode == 0x09:  # Ping
                    pong = bytearray([0x8A, len(payload)]) + payload
                    self.wfile.write(pong)
                    self.wfile.flush()
        except Exception:
            pass

    def do_GET(self) -> None:
        parsed_path = self.path.split("?")[0].rstrip("/")
        if parsed_path == "":
            parsed_path = "/"

        # 1. Healthcheck / Status Endpoint
        if parsed_path in ("/status", "/health", "/api/status"):
            status_data = self.controller.get_status_dict() if self.controller else {"status": "ok"}
            self.send_json_response(status_data)
            return

        # 2. Get Settings API
        if parsed_path == "/api/settings":
            if self.controller:
                self.send_json_response(self.controller.settings.to_dict())
            else:
                self.send_json_response({})
            return

        # 3. WebSocket Endpoint (/ws)
        if parsed_path == "/ws":
            ws_key = self.headers.get("Sec-WebSocket-Key")
            if ws_key:
                self._handle_websocket_handshake(ws_key)
                return
            else:
                status_data = self.controller.get_status_dict() if self.controller else {"status": "ok"}
                self.send_json_response({"service": "aircursor_ws", "websocket": "ready", **status_data})
                return

        # 3. Static Web PWA Assets
        target_file = None
        if parsed_path in ("/", "/index.html"):
            target_file = self.web_dir / "index.html"
        else:
            rel_path = self.path.lstrip("/").split("?")[0]
            candidate = self.web_dir / rel_path
            if candidate.is_file():
                target_file = candidate

        if target_file and target_file.is_file():
            try:
                mime_type, _ = mimetypes.guess_type(str(target_file))
                if target_file.name.endswith(".webmanifest"):
                    mime_type = "application/manifest+json"
                elif not mime_type:
                    mime_type = "application/octet-stream"

                content = target_file.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-cache" if target_file.name.endswith(".html") else "max-age=3600")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
                return

        # Fallback to standard handler or 404
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:
        parsed_path = self.path.split("?")[0].rstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        if parsed_path == "/api/action":
            action_name = payload.get("action", "")
            if self.controller:
                if action_name == "toggle_tracking":
                    self.controller.execute_action(PointerAction.TOGGLE_TRACKING)
                elif action_name == "recenter":
                    self.controller.execute_action(PointerAction.RECENTER)
                elif action_name == "toggle_scroll":
                    self.controller.execute_action(PointerAction.TOGGLE_SCROLL_MODE)
                elif action_name == "toggle_drag":
                    self.controller.execute_action(PointerAction.TOGGLE_DRAG)
                elif action_name == "left_click":
                    self.controller.execute_action(PointerAction.LEFT_CLICK)
                elif action_name == "right_click":
                    self.controller.execute_action(PointerAction.RIGHT_CLICK)
                elif action_name == "double_click":
                    self.controller.execute_action(PointerAction.DOUBLE_CLICK)
            status_data = self.controller.get_status_dict() if self.controller else {"status": "ok"}
            self.send_json_response(status_data)
            return

        if parsed_path == "/api/telemetry":
            yaw = float(payload.get("yaw", 0.0))
            pitch = float(payload.get("pitch", 0.0))
            roll = float(payload.get("roll", 0.0))
            if self.controller:
                sample = MotionSample(
                    timestamp=time.time(),
                    yaw=AngleMath.radians(yaw),
                    pitch=AngleMath.radians(pitch),
                    roll=AngleMath.radians(roll),
                )
                self.controller.push_sample(sample)
            self.send_json_response({"status": "received"})
            return

        if parsed_path == "/api/settings":
            if self.controller:
                if "sensitivity" in payload:
                    self.controller.settings.pointer.sensitivity = float(payload["sensitivity"])
                if "deadzone" in payload:
                    self.controller.settings.pointer.deadzone = float(payload["deadzone"])
                if "dwell_duration" in payload:
                    self.controller.settings.dwell.duration = float(payload["dwell_duration"])
                if "smart_dwell" in payload:
                    self.controller.settings.dwell.smart = bool(payload["smart_dwell"])
                self.send_json_response(self.controller.settings.to_dict())
            else:
                self.send_json_response({"status": "ok"})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


class AirCursorServer:
    """Thread-safe, self-contained HTTP + UDP AirCursor Server."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        http_port: int = 8765,
        udp_port: int = 4242,
        mode: str = "synthetic",
        autorun: bool = True,
        settings: Optional[AppSettings] = None,
    ) -> None:
        self.host = host
        self.http_port = http_port
        self.udp_port = udp_port
        self.mode = mode
        self.autorun = autorun

        self.controller = AirCursorServerController(
            settings=settings,
            mode=mode,
            autorun=autorun,
            udp_host=host,
            udp_port=udp_port,
        )

        AirCursorRequestHandler.controller = self.controller
        self._httpd: Optional[HTTPServer] = None
        self._http_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts both Controller and HTTP Server."""
        self.controller.start()

        self._httpd = HTTPServer((self.host, self.http_port), AirCursorRequestHandler)
        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="AirCursor-HTTPServer",
        )
        self._http_thread.start()
        print(f"[+] AirCursor Server running on http://{self.host}:{self.http_port}")
        print(f"[+] UDP sensor listener active on {self.host}:{self.udp_port}/udp")
        print(f"[+] Mode: {self.mode.upper()}, Tracking: {'ON' if self.autorun else 'STANDBY'}")

    def stop(self) -> None:
        """Shuts down HTTP and Controller gracefully."""
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        self.controller.stop()


def parse_args():
    parser = argparse.ArgumentParser(description="AirCursor Headless & Cloud Server")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HTTP_PORT", "8765")),
        help="HTTP Web Remote & API port (default: 8765)",
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=int(os.environ.get("UDP_PORT", "4242")),
        help="OpenTrack UDP sensor port (default: 4242)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=os.environ.get("MODE", "synthetic"),
        choices=["synthetic", "airpods", "camera"],
        help="Operational mode (synthetic, airpods, camera)",
    )
    parser.add_argument(
        "--autorun",
        action="store_true",
        default=os.environ.get("AUTORUN", "true").lower() in ("true", "1", "yes"),
        help="Auto-start tracking immediately on launch",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=os.environ.get("CONFIG_PATH", None),
        help="Path to custom settings.json",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    settings = AppSettings()
    if args.config and os.path.isfile(args.config):
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                settings = AppSettings.from_dict(json.load(f))
            print(f"[+] Loaded config from {args.config}")
        except Exception as e:
            print(f"[!] Warning loading config: {e}")

    server = AirCursorServer(
        host="0.0.0.0",
        http_port=args.port,
        udp_port=args.udp_port,
        mode=args.mode,
        autorun=args.autorun,
        settings=settings,
    )

    def shutdown_handler(signum, frame):
        print("\n[*] Received shutdown signal. Closing AirCursor Server...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    server.start()

    # Block main thread
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        shutdown_handler(None, None)


if __name__ == "__main__":
    main()
