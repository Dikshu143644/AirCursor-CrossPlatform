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
import hmac
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import socket
import struct
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import urllib.parse

from .pairing_qr import (
    PairingQR,
    get_local_ip,
    get_pairing_url,
    generate_qr_matrix,
    matrix_to_ascii,
    matrix_to_svg,
    matrix_to_html,
)

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
        # The PWA is same-origin; do not grant arbitrary websites cross-origin access.
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With"
        )

    def _is_loopback_client(self) -> bool:
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, IndexError):
            return False

    def _is_authorized(self) -> bool:
        scheme, separator, supplied = self.headers.get("Authorization", "").partition(" ")
        return (
            bool(separator)
            and scheme.lower() == "bearer"
            and hmac.compare_digest(supplied.strip(), self.server_instance.access_token)
        )

    def _require_authorization(self) -> bool:
        if self._is_authorized():
            return True
        self._send_json(401, {"error": "unauthorized", "message": "Pair this device with the host QR code."})
        return False

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

        # Pairing QR reveals the bearer credential, so it is host-local only.
        if path == "/pair":
            if not self._is_loopback_client():
                self._send_json(403, {"error": "pairing QR is available from the host computer only"})
                return
            qr_data = self.server_instance.get_qr_dict()
            matrix = generate_qr_matrix(qr_data["url"])
            html = matrix_to_html(matrix, qr_data["url"], title="AirCursor Secure Pairing")
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        # QR API also reveals the bearer credential; restrict it to the host.
        if path in ("/api/qr", "/qr"):
            if not self._is_loopback_client():
                self._send_json(403, {"error": "pairing QR is available from the host computer only"})
                return
            self._send_json(200, self.server_instance.get_qr_dict())
            return

        # 4. Web App Manifest: GET /manifest.json
        if path == "/manifest.json":
            self._serve_static_file("manifest.json", "application/manifest+json; charset=utf-8")
            return

        # 5. Service Worker: GET /sw.js
        if path == "/sw.js":
            self._serve_static_file("sw.js", "application/javascript; charset=utf-8")
            return

        # 6. Static files: GET /static/<filename>
        if path.startswith("/static/"):
            filename = path[len("/static/") :]
            # Basic path traversal guard
            safe_name = os.path.basename(filename)
            content_type = "text/plain"
            if safe_name.endswith(".html"):
                content_type = "text/html; charset=utf-8"
            elif safe_name.endswith(".css"):
                content_type = "text/css; charset=utf-8"
            elif safe_name.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            elif safe_name.endswith(".json"):
                content_type = "application/json; charset=utf-8"
            elif safe_name.endswith(".svg"):
                content_type = "image/svg+xml"
            self._serve_static_file(safe_name, content_type)
            return

        # 7. Root Web Remote: GET / or GET /index.html
        if path in ("/", "/index.html", "/remote", "/remote.html"):
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

        if not self._require_authorization():
            return

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
    # Static File Serving Helper
    # -------------------------------------------------------------------------
    def _serve_static_file(self, filename: str, content_type: str) -> None:
        file_path = self.server_instance.static_dir / filename
        if not file_path.exists():
            self._send_json(404, {"error": f"File '{filename}' not found"})
            return

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

        accept_token = base64.b64encode(
            hashlib.sha1((key.strip() + WS_GUID).encode("utf-8")).digest()
        ).decode("utf-8")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_token)
        self.end_headers()

        sock: socket.socket = self.connection
        try:
            # Browsers cannot set Authorization headers on WebSocket. Require
            # a bearer-auth message as the first frame before any control data.
            sock.settimeout(5.0)
            first_frame = self._read_ws_frame(sock)
            if first_frame is None or first_frame[0] != 0x1:
                self._send_ws_frame(sock, 0x8, struct.pack("!H", 4003) + b"Authentication required")
                return
            try:
                auth_message = json.loads(first_frame[1].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                auth_message = {}
            supplied = auth_message.get("token", "") if isinstance(auth_message, dict) else ""
            if (
                not isinstance(auth_message, dict)
                or auth_message.get("type") != "auth"
                or not isinstance(supplied, str)
                or not hmac.compare_digest(supplied, self.server_instance.access_token)
            ):
                self._send_ws_frame(sock, 0x8, struct.pack("!H", 4003) + b"Unauthorized")
                return

            self.server_instance._register_ws_client(sock)
            self._send_ws_frame(sock, 0x1, json.dumps({"type": "ready"}).encode("utf-8"))
            sock.settimeout(60.0)

            while self.server_instance.is_running:
                frame_data = self._read_ws_frame(sock)
                if frame_data is None:
                    break
                opcode, payload = frame_data
                if opcode == 0x8:
                    self._send_ws_frame(sock, 0x8, b"")
                    break
                if opcode == 0x9:
                    self._send_ws_frame(sock, 0xA, payload)
                    continue
                if opcode != 0x1:
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8"))
                    if not isinstance(msg, dict):
                        continue
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
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
                    continue
        except (OSError, TimeoutError, socket.timeout):
            pass
        finally:
            self.server_instance._unregister_ws_client(sock)
            try:
                sock.close()
            except OSError:
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

        if plen > 65536:
            return None
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
        access_token: Optional[str] = None,
    ):
        self.host = host
        self.port = int(port)
        self.controller = controller
        self.access_token = access_token or os.environ.get("AIRCURSOR_REMOTE_TOKEN") or secrets.token_urlsafe(32)
        if len(self.access_token) < 20:
            raise ValueError("access_token must contain at least 20 characters")

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
        print(f"[AirCursor Pairing] On this computer open http://127.0.0.1:{self.port}/pair to display the secure QR code.")
        print(f"[AirCursor Pairing] Pairing token (keep private): {self.access_token}")

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

        return {
            "cursor": cursor,
            "source": source,
            "connection_count": self.connection_count,
            "tracking_enabled": tracking_enabled,
            "mode": mode,
            "timestamp": now,
        }

    def get_qr_dict(self) -> dict:
        """Returns a token-bearing pairing URL; HTTP access is restricted to loopback."""
        base_url = self.url.rstrip("/")
        pairing_url = base_url + "/#token=" + urllib.parse.quote(self.access_token, safe="")
        matrix = generate_qr_matrix(pairing_url)
        return {
            "url": pairing_url,
            "ip": self.qr.ip,
            "port": self.port,
            "qr_ascii": matrix_to_ascii(matrix),
            "qr_svg": matrix_to_svg(matrix),
        }
