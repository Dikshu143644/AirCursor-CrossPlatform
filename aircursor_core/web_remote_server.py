"""AirCursor Mobile Web Remote Server.

A lightweight, robust pure-Python HTTP and WebSocket server running on port 8765:
- Zero external dependencies (uses standard library http.server, socket, threading).
- RFC 6455 compliant WebSocket upgrade handler for real-time 60-120Hz motion streaming.
- RESTful HTTP fallback endpoints for wide browser and proxy compatibility.
- Interactive pairing QR code endpoint pointing to the local LAN IPv4 address.
- Thread-safe action and motion dispatch directly to AppController or custom callbacks.
"""

from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import urllib.parse

from .pairing_qr import PairingQR, get_local_ip, get_pairing_url

# Standard WebSocket RFC 6455 Magic GUID
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebRemoteRequestHandler(BaseHTTPRequestHandler):
    """HTTP and WebSocket Request Handler for the AirCursor Web Remote."""

    # Suppress verbose default request logging to keep console clean
    def log_message(self, format: str, *args: Any) -> None:
        pass

    @property
    def server_instance(self) -> WebRemoteServer:
        return self.server.web_remote_server  # type: ignore

    # -------------------------------------------------------------------------
    # CORS & Header Helpers
    # -------------------------------------------------------------------------
    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With"
        )
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, status_code: int, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        """Handles CORS pre-flight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    # -------------------------------------------------------------------------
    # HTTP GET & WebSocket Upgrade Handler
    # -------------------------------------------------------------------------
    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # 1. WebSocket Upgrade check (on /ws or any path requesting websocket)
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._handle_websocket_upgrade()
            return

        # 2. Status Endpoint: GET /status or GET /api/status
        if path in ("/status", "/api/status"):
            status_data = self.server_instance.get_status_dict()
            self._send_json(200, status_data)
            return

        # 3. QR Endpoint: GET /api/qr
        if path in ("/api/qr", "/qr"):
            qr_data = self.server_instance.get_qr_dict()
            self._send_json(200, qr_data)
            return

        # 4. Web App Manifest
        if path in ("/manifest.json", "/manifest.webmanifest"):
            self._serve_static_file(path.lstrip("/"), "application/manifest+json; charset=utf-8")
            return

        # 5. Service Worker: GET /sw.js
        if path == "/sw.js":
            self._serve_static_file("sw.js", "application/javascript; charset=utf-8")
            return

        # 6. Static / Web Assets: css, js, icons, static, cad
        if path.startswith(("/css/", "/js/", "/icons/", "/static/", "/cad/")):
            rel = path.lstrip("/")
            self._serve_static_file(rel)
            return

        # 7. Button Remote / Screen Controller: GET /button-remote, /tv, /deck, /screen-remote
        if path in (
            "/button-remote",
            "/button-remote.html",
            "/button_remote",
            "/button_remote.html",
            "/tv",
            "/deck",
            "/screen-remote",
        ):
            self._serve_static_file("button_remote.html", "text/html; charset=utf-8")
            return

        # 8. Root Web Remote: GET / or GET /index.html or /remote.html
        if path in ("/", "/index.html", "/remote", "/remote.html"):
            for candidate in ("remote.html", "index.html"):
                if self._can_serve(candidate):
                    self._serve_static_file(candidate, "text/html; charset=utf-8")
                    return
            self._serve_static_file("remote.html", "text/html; charset=utf-8")
            return

        # Not Found
        self._send_json(404, {"error": "Endpoint not found", "path": path})

    # -------------------------------------------------------------------------
    # HTTP POST Handler (/api/action, /api/motion)
    # -------------------------------------------------------------------------
    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_len)
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception as e:
            self._send_json(400, {"error": "Invalid JSON body", "detail": str(e)})
            return

        # Action Endpoint: POST /api/action
        if path == "/api/action":
            action = str(payload.get("action", "")).strip().lower()
            dx = float(payload.get("dx", 0.0))
            dy = float(payload.get("dy", 0.0))
            self.server_instance.dispatch_action(action, dx=dx, dy=dy, extra=payload)
            self._send_json(200, {"status": "ok", "action": action})
            return

        # Motion Endpoint: POST /api/motion
        if path == "/api/motion":
            self.server_instance.dispatch_motion(payload)
            self._send_json(200, {"status": "ok"})
            return

        # Legacy convenience endpoints
        if path in ("/api/camera/toggle", "/camera/toggle"):
            self.server_instance.dispatch_action("camera_toggle")
            self._send_json(200, {"success": True, **self.server_instance.get_status_dict()})
            return

        if path in ("/api/tracking/toggle", "/tracking/toggle"):
            self.server_instance.dispatch_action("toggle_tracking")
            self._send_json(200, {"success": True, **self.server_instance.get_status_dict()})
            return

        if path in ("/api/mode/toggle", "/mode/toggle"):
            self.server_instance.dispatch_action("toggle_mode")
            self._send_json(200, {"success": True, **self.server_instance.get_status_dict()})
            return

        if path in ("/api/recenter", "/recenter"):
            self.server_instance.dispatch_action("recenter")
            self._send_json(200, {"success": True, **self.server_instance.get_status_dict()})
            return

        self._send_json(404, {"error": "POST endpoint not found", "path": path})

    # -------------------------------------------------------------------------
    # Static File Serving Helpers
    # -------------------------------------------------------------------------
    def _resolve_file_path(self, rel_path: str) -> Optional[Path]:
        norm = Path(rel_path.lstrip("/\\"))
        if ".." in norm.parts:
            return None

        # Check in static_dir
        candidate = self.server_instance.static_dir / norm
        if candidate.exists() and candidate.is_file():
            return candidate

        # Check in web dir
        repo_web = Path(__file__).resolve().parent.parent / "web" / norm
        if repo_web.exists() and repo_web.is_file():
            return repo_web

        # Check in cad or repo dir
        repo_cad = Path(__file__).resolve().parent.parent / norm
        if repo_cad.exists() and repo_cad.is_file():
            return repo_cad

        return None

    def _can_serve(self, rel_path: str) -> bool:
        return self._resolve_file_path(rel_path) is not None

    def _serve_static_file(self, filename: str, content_type: Optional[str] = None) -> None:
        file_path = self._resolve_file_path(filename)
        if not file_path:
            self._send_json(404, {"error": f"File '{filename}' not found"})
            return

        if content_type is None:
            suffix = file_path.suffix.lower()
            mime_map = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".json": "application/json; charset=utf-8",
                ".webmanifest": "application/manifest+json; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".glb": "model/gltf-binary",
                ".obj": "text/plain",
                ".stl": "application/sla",
                ".blend": "application/octet-stream",
            }
            content_type = mime_map.get(suffix, "application/octet-stream")

        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_json(500, {"error": "Failed reading static asset", "detail": str(e)})

    # -------------------------------------------------------------------------
    # RFC 6455 Pure-Python WebSocket Protocol Handler
    # -------------------------------------------------------------------------
    def _handle_websocket_upgrade(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(400, "Missing Sec-WebSocket-Key")
            return

        # Calculate accept hash
        accept_token = base64.b64encode(
            hashlib.sha1((key.strip() + WS_GUID).encode("utf-8")).digest()
        ).decode("utf-8")

        # Handshake response
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_token)
        self.end_headers()

        # Enter WebSocket bidirectional framing loop
        sock: socket.socket = self.connection
        sock.settimeout(60.0)  # 60s idle timeout
        self.server_instance._register_ws_client(sock)

        try:
            while self.server_instance.is_running:
                frame_data = self._read_ws_frame(sock)
                if frame_data is None:
                    break

                opcode, payload = frame_data

                # Close frame (Opcode 0x8)
                if opcode == 0x8:
                    self._send_ws_frame(sock, 0x8, b"")
                    break

                # Ping frame (Opcode 0x9) -> respond with Pong (Opcode 0xA)
                elif opcode == 0x9:
                    self._send_ws_frame(sock, 0xA, payload)

                # Text frame (Opcode 0x1)
                elif opcode == 0x1:
                    try:
                        text = payload.decode("utf-8")
                        msg = json.loads(text)
                        msg_type = msg.get("type", "")

                        if msg_type == "action" or "action" in msg:
                            act = str(msg.get("action", ""))
                            dx = float(msg.get("dx", 0.0))
                            dy = float(msg.get("dy", 0.0))
                            self.server_instance.dispatch_action(act, dx=dx, dy=dy, extra=msg)

                        elif msg_type == "motion" or "gyro" in msg or "dx" in msg or "dy" in msg:
                            self.server_instance.dispatch_motion(msg)

                        elif msg_type == "ping":
                            resp = json.dumps({"type": "pong", "ts": msg.get("ts", 0)})
                            self._send_ws_frame(sock, 0x1, resp.encode("utf-8"))

                        elif msg_type == "get_status":
                            resp = json.dumps({"type": "status", **self.server_instance.get_status_dict()})
                            self._send_ws_frame(sock, 0x1, resp.encode("utf-8"))

                    except Exception:
                        pass

        except Exception:
            pass
        finally:
            self.server_instance._unregister_ws_client(sock)
            try:
                sock.close()
            except Exception:
                pass

    def _read_ws_frame(self, sock: socket.socket) -> Optional[Tuple[int, bytes]]:
        """Reads and unmasks an incoming RFC 6455 client WebSocket frame."""
        def recv_exact(n: int) -> Optional[bytes]:
            buf = bytearray()
            while len(buf) < n:
                chunk = sock.recv(n - len(buf))
                if not chunk:
                    return None
                buf.extend(chunk)
            return bytes(buf)

        head = recv_exact(2)
        if not head:
            return None

        b0, b1 = head[0], head[1]
        opcode = b0 & 0x0F
        is_masked = bool(b1 & 0x80)
        plen = b1 & 0x7F

        if plen == 126:
            ext = recv_exact(2)
            if not ext:
                return None
            plen = struct.unpack("!H", ext)[0]
        elif plen == 127:
            ext = recv_exact(8)
            if not ext:
                return None
            plen = struct.unpack("!Q", ext)[0]

        mask_key = None
        if is_masked:
            mask_key = recv_exact(4)
            if not mask_key:
                return None

        payload = recv_exact(plen)
        if payload is None:
            return None

        if is_masked and mask_key:
            unmasked = bytearray(payload)
            for i in range(len(unmasked)):
                unmasked[i] ^= mask_key[i % 4]
            payload = bytes(unmasked)

        return opcode, payload

    def _send_ws_frame(self, sock: socket.socket, opcode: int, data: bytes) -> None:
        """Sends an unmasked RFC 6455 frame to client from server."""
        length = len(data)
        b0 = 0x80 | (opcode & 0x0F)  # FIN=1 + Opcode

        if length <= 125:
            header = bytes([b0, length])
        elif length <= 65535:
            header = bytes([b0, 126]) + struct.pack("!H", length)
        else:
            header = bytes([b0, 127]) + struct.pack("!Q", length)

        sock.sendall(header + data)


# -----------------------------------------------------------------------------
# WebRemoteServer Main Controller Class
# -----------------------------------------------------------------------------

class WebRemoteServer:
    """Embedded, pure-Python HTTP + WebSocket server for mobile pairing & control."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        controller: Optional[Any] = None,
        static_dir: Optional[Path | str] = None,
    ):
        self.host = host
        self.port = int(port)
        self.controller = controller

        # Locate static directory
        if static_dir is not None:
            self.static_dir = Path(static_dir)
        else:
            self.static_dir = Path(__file__).resolve().parent / "static"

        # Thread-safety and lifecycle
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._is_running = False

        # Active WebSocket clients
        self._ws_clients: Set[socket.socket] = set()

        # Telemetry / Source Tracking
        # Sources: 'airpods', 'camera', 'remote', 'synthetic'
        self.current_source: str = "synthetic"
        self._last_remote_motion_time: float = 0.0

        # Optional custom callbacks
        self.on_action: Optional[Callable[[str, float, float, dict], Any]] = None
        self.on_motion: Optional[Callable[[dict], Any]] = None
        self.status_provider: Optional[Callable[[], dict]] = None

        # Pairing QR generator
        self.qr = PairingQR(port=self.port)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def connection_count(self) -> int:
        with self._lock:
            return len(self._ws_clients)

    @property
    def url(self) -> str:
        ip = get_local_ip()
        return f"http://{ip}:{self.port}"

    def attach_controller(self, controller: Any) -> None:
        """Binds an AppController instance to the web server."""
        with self._lock:
            self.controller = controller

    def set_action_callback(self, cb: Callable[[str, float, float, dict], Any]) -> None:
        """Registers a custom callback for remote actions."""
        self.on_action = cb

    def set_motion_callback(self, cb: Callable[[dict], Any]) -> None:
        """Registers a custom callback for remote motion events."""
        self.on_motion = cb

    def set_status_provider(self, cb: Callable[[], dict]) -> None:
        """Registers a custom status dict provider."""
        self.status_provider = cb

    def start(self) -> None:
        """Starts the server in a background daemon thread."""
        if self._is_running:
            return

        # Initialize ThreadingHTTPServer
        server_address = (self.host, self.port)
        httpd = ThreadingHTTPServer(server_address, WebRemoteRequestHandler)
        httpd.daemon_threads = True
        httpd.web_remote_server = self  # type: ignore

        # Update port in case port 0 (ephemeral) was requested
        self.port = httpd.server_address[1]
        self.qr = PairingQR(port=self.port)

        self._server = httpd
        self._is_running = True

        self._server_thread = threading.Thread(
            target=httpd.serve_forever,
            daemon=True,
            name=f"AirCursor-WebRemote-{self.port}",
        )
        self._server_thread.start()

    def stop(self) -> None:
        """Stops the server, disconnects clients, and releases the listening port."""
        if not self._is_running:
            return
        self._is_running = False

        # Close all active WebSockets
        with self._lock:
            for sock in list(self._ws_clients):
                try:
                    sock.close()
                except Exception:
                    pass
            self._ws_clients.clear()

        # Shutdown HTTP server
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=1.0)
            self._server_thread = None

    def __enter__(self) -> WebRemoteServer:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # -------------------------------------------------------------------------
    # WebSocket Client Registration
    # -------------------------------------------------------------------------
    def _register_ws_client(self, sock: socket.socket) -> None:
        with self._lock:
            self._ws_clients.add(sock)

    def _unregister_ws_client(self, sock: socket.socket) -> None:
        with self._lock:
            self._ws_clients.discard(sock)

    # -------------------------------------------------------------------------
    # Thread-Safe Action & Motion Dispatch
    # -------------------------------------------------------------------------
    def dispatch_action(
        self, action: str, dx: float = 0.0, dy: float = 0.0, extra: Optional[dict] = None
    ) -> Any:
        """Thread-safely executes an action received from the mobile remote."""
        act = action.strip().lower()
        extra_data = extra or {}

        # 1. Custom callback hook if registered
        if self.on_action:
            try:
                self.on_action(act, dx, dy, extra_data)
            except Exception:
                pass

        # 2. Attached Controller dispatch
        if self.controller:
            try:
                # Prefer controller's dedicated remote handler if present
                if hasattr(self.controller, "handle_remote_action"):
                    try:
                        return self.controller.handle_remote_action(
                            act, dx=dx, dy=dy, extra=extra_data
                        )
                    except TypeError:
                        return self.controller.handle_remote_action(act, dx=dx, dy=dy)

                # Fallback to direct controller methods
                if act in ("click", "left_click"):
                    if getattr(self.controller, "is_dragging", False):
                        self.controller.end_drag()
                    elif hasattr(self.controller, "synth"):
                        self.controller.synth.click(button="left")

                elif act == "right_click":
                    if getattr(self.controller, "is_dragging", False):
                        self.controller.end_drag()
                    elif hasattr(self.controller, "synth"):
                        self.controller.synth.click(button="right")

                elif act == "middle_click":
                    if hasattr(self.controller, "synth"):
                        self.controller.synth.click(button="middle")

                elif act == "double_click":
                    if getattr(self.controller, "is_dragging", False):
                        self.controller.end_drag()
                    elif hasattr(self.controller, "synth"):
                        self.controller.synth.double_click()

                elif act in ("drag_toggle", "drag"):
                    if getattr(self.controller, "is_dragging", False):
                        self.controller.end_drag()
                    elif hasattr(self.controller, "begin_drag"):
                        self.controller.begin_drag()

                elif act == "recenter":
                    if hasattr(self.controller, "recenter"):
                        self.controller.recenter()

                elif act == "scroll":
                    if hasattr(self.controller, "synth"):
                        self.controller.synth.scroll(vertical=int(dy), horizontal=int(dx))

                elif act in ("toggle_tracking", "pause", "resume"):
                    if hasattr(self.controller, "set_tracking"):
                        if act == "pause":
                            self.controller.set_tracking(False)
                        elif act == "resume":
                            self.controller.set_tracking(True)
                        else:
                            self.controller.toggle_tracking()

                elif act in ("toggle_mode", "scroll_mode", "pointer_mode"):
                    if hasattr(self.controller, "toggle_mode"):
                        self.controller.toggle_mode()

            except Exception:
                pass

    def dispatch_motion(self, data: dict) -> Any:
        """Thread-safely routes motion (dx, dy or gyro) to the controller."""
        self._last_remote_motion_time = time.time()
        self.current_source = "remote"

        # 1. Custom callback hook if registered
        if self.on_motion:
            try:
                self.on_motion(data)
            except Exception:
                pass

        # 2. Attached Controller dispatch
        if self.controller:
            try:
                # Prefer controller's dedicated remote motion handler
                if hasattr(self.controller, "handle_remote_motion"):
                    return self.controller.handle_remote_motion(data)

                # Relative movement dx, dy
                dx = float(data.get("dx", 0.0))
                dy = float(data.get("dy", 0.0))
                if (abs(dx) > 0.001 or abs(dy) > 0.001) and hasattr(self.controller, "synth"):
                    self.controller.synth.move_relative(dx, dy)
                    if hasattr(self.controller, "_cursor"):
                        mx, my = self.controller.synth.current_location()
                        from .math_util import Vec2
                        self.controller._cursor = Vec2(float(mx), float(my))

                # Gyro orientation
                gyro = data.get("gyro")
                if gyro and isinstance(gyro, dict) and hasattr(self.controller, "handle_sample"):
                    from .motion import MotionSample
                    from .math_util import AngleMath

                    pitch = float(gyro.get("pitch", 0.0))
                    yaw = float(gyro.get("yaw", 0.0))
                    roll = float(gyro.get("roll", 0.0))
                    # Convert to radians if needed
                    if abs(pitch) > math.pi or abs(yaw) > math.pi:
                        pitch = AngleMath.radians(pitch)
                        yaw = AngleMath.radians(yaw)
                        roll = AngleMath.radians(roll)

                    sample = MotionSample(
                        timestamp=time.time(), yaw=yaw, pitch=pitch, roll=roll
                    )
                    self.controller.handle_sample(sample)

            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Telemetry & Status Formatter
    # -------------------------------------------------------------------------
    def get_status_dict(self) -> dict:
        """Returns JSON status matching cross-platform AirCursor status specification."""
        # Custom status provider override if registered
        if self.status_provider:
            try:
                return self.status_provider()
            except Exception:
                pass

        cursor = {"x": 0.0, "y": 0.0}
        tracking_enabled = True
        mode = "pointer"
        source = self.current_source

        # Watchdog: if remote motion hasn't arrived in 3 seconds, revert source
        now = time.time()
        if source == "remote" and (now - self._last_remote_motion_time > 3.0):
            source = "synthetic"

        if self.controller:
            # Synchronize cursor coordinates
            if hasattr(self.controller, "synth"):
                try:
                    mx, my = self.controller.synth.current_location()
                    cursor = {"x": float(mx), "y": float(my)}
                except Exception:
                    pass
            elif hasattr(self.controller, "_cursor") and self.controller._cursor is not None:
                cursor = {"x": float(self.controller._cursor.x), "y": float(self.controller._cursor.y)}

            if hasattr(self.controller, "tracking_enabled"):
                tracking_enabled = bool(self.controller.tracking_enabled)

            if hasattr(self.controller, "mode"):
                mode_val = getattr(self.controller.mode, "value", str(self.controller.mode))
                mode = str(mode_val)

            # Determine primary source
            if source != "remote":
                if getattr(self.controller, "use_synthetic", False):
                    source = "synthetic"
                elif getattr(self.controller, "motion_streaming", False):
                    source = "airpods"

        screen = {"x": 0, "y": 0, "width": 1920, "height": 1080}
        if self.controller and hasattr(self.controller, "synth") and hasattr(self.controller.synth, "get_screen_bounds"):
            try:
                vx, vy, vw, vh = self.controller.synth.get_screen_bounds()
                screen = {"x": int(vx), "y": int(vy), "width": int(vw), "height": int(vh)}
            except Exception:
                pass

        return {
            "cursor": cursor,
            "source": source,
            "connection_count": self.connection_count,
            "tracking_enabled": tracking_enabled,
            "mode": mode,
            "screen": screen,
            "timestamp": now,
        }

    def get_qr_dict(self) -> dict:
        """Returns dictionary containing URL and pairing QR codes."""
        return {
            "url": self.url,
            "ip": self.qr.ip,
            "port": self.port,
            "qr_ascii": self.qr.to_ascii(),
            "qr_svg": self.qr.to_svg(),
        }
