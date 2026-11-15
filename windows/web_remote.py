"""AirCursor Web Remote & REST API Server.

Provides a lightweight, zero-dependency embedded HTTP server for remote
monitoring and control of AirCursor from web browsers, smartphones, or scripts.
Supports manual camera toggle, tracking pause/resume, mode switching, and live telemetry.
"""

from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import socketserver
import threading
from typing import TYPE_CHECKING, Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:
    from app_controller import AppController


class WebRemoteServer:
    """Embedded HTTP server hosting AirCursor REST API and HTML Remote."""

    def __init__(
        self,
        controller: AppController,
        host: str = "0.0.0.0",
        port: int = 8765,
    ):
        self.controller = controller
        self.host = host
        self.port = port
        self._server: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Starts the Web Remote server in a background daemon thread."""
        if self._running:
            return True

        controller = self.controller

        class _Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress verbose HTTP access logs in console
                pass

            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path in ("/api/status", "/status"):
                    self._send_json(self._get_status())
                elif path.startswith("/cad/"):
                    rel = path[len("/cad/"):].lstrip("/")
                    target = ROOT_DIR / "cad" / rel
                    if target.exists() and target.is_file() and ".." not in Path(rel).parts:
                        suffix = target.suffix.lower()
                        mime = {
                            ".html": "text/html; charset=utf-8",
                            ".css": "text/css; charset=utf-8",
                            ".js": "application/javascript; charset=utf-8",
                            ".png": "image/png",
                            ".glb": "model/gltf-binary",
                            ".obj": "text/plain",
                            ".stl": "application/sla",
                            ".md": "text/markdown; charset=utf-8",
                        }.get(suffix, "application/octet-stream")
                        data = target.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", mime)
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(data)
                    else:
                        self.send_error(404, "CAD Asset Not Found")
                elif path in ("/button-remote", "/tv", "/deck", "/screen-remote"):
                    btn_remote_path = ROOT_DIR / "aircursor_core" / "static" / "button_remote.html"
                    if btn_remote_path.exists():
                        self._send_html(btn_remote_path.read_text(encoding="utf-8"))
                    else:
                        self.send_error(404, "Button Remote Not Found")
                elif path in ("/", "/index.html"):
                    static_remote = ROOT_DIR / "aircursor_core" / "static" / "remote.html"
                    if static_remote.exists():
                        self._send_html(static_remote.read_text(encoding="utf-8"))
                    else:
                        self._send_html(self._render_remote_html())
                else:
                    self.send_error(404, "Endpoint Not Found")

            def do_POST(self) -> None:
                path = self.path.split("?")[0]
                try:
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                    data = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    data = {}

                if path in ("/api/action", "/action"):
                    action = str(data.get("action", "")).strip().lower()
                    dx = float(data.get("dx", 0.0))
                    dy = float(data.get("dy", 0.0))
                    handled = controller.handle_remote_action(action, dx=dx, dy=dy, extra=data)
                    self._send_json({"success": handled, "action": action, **self._get_status()})
                elif path in ("/api/motion", "/motion"):
                    handled = controller.handle_remote_motion(data)
                    self._send_json({"success": handled, **self._get_status()})
                elif path in ("/api/camera/toggle", "/camera/toggle"):
                    new_state = controller.toggle_camera()
                    self._send_json({"success": True, "camera_active": new_state, **self._get_status()})
                elif path in ("/api/tracking/toggle", "/tracking/toggle"):
                    controller.toggle_tracking()
                    self._send_json({"success": True, "tracking_enabled": controller.tracking_enabled, **self._get_status()})
                elif path in ("/api/mode/toggle", "/mode/toggle"):
                    controller.toggle_mode()
                    self._send_json({"success": True, "mode": controller.mode.value, **self._get_status()})
                elif path in ("/api/recenter", "/recenter"):
                    controller.recenter()
                    self._send_json({"success": True, "message": "Recentered", **self._get_status()})
                else:
                    self.send_error(404, "Endpoint Not Found")

            def _get_status(self) -> Dict[str, Any]:
                cam_running = (
                    controller.vision_tracker.is_running
                    if controller.vision_tracker
                    else False
                )
                cam_avail = (
                    controller.vision_tracker.is_available
                    if controller.vision_tracker
                    else False
                )
                return {
                    "tracking_enabled": controller.tracking_enabled,
                    "mode": controller.mode.value,
                    "active_source": controller.arbiter.active_source.value,
                    "camera_active": cam_running,
                    "camera_available": cam_avail,
                    "is_dragging": controller.is_dragging,
                    "motion_streaming": controller.motion_streaming,
                    "live_yaw": round(controller.live_yaw, 1),
                    "live_pitch": round(controller.live_pitch, 1),
                    "live_roll": round(controller.live_roll, 1),
                    "live_fps": round(controller.live_fps, 1),
                }

            def _send_json(self, data: Dict[str, Any], code: int = 200) -> None:
                body = json.dumps(data).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html: str, code: int = 200) -> None:
                body = html.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _render_remote_html(self) -> str:
                return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AirCursor Web Remote</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 90vh; }
        .card { background: #1e293b; border-radius: 16px; padding: 24px; max-width: 400px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.5); text-align: center; }
        h1 { margin-top: 0; font-size: 22px; color: #38bdf8; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: bold; margin-bottom: 20px; }
        .badge-active { background: #166534; color: #86efac; }
        .badge-paused { background: #854d0e; color: #fde047; }
        .btn-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }
        button { background: #334155; color: #fff; border: 1px solid #475569; padding: 14px; border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        button:hover { background: #475569; transform: translateY(-2px); }
        button:active { transform: translateY(0); }
        .btn-primary { background: #0284c7; border-color: #38bdf8; grid-column: span 2; }
        .btn-primary:hover { background: #0369a1; }
        .btn-camera { background: #7c3aed; border-color: #a78bfa; grid-column: span 2; }
        .btn-camera:hover { background: #6d28d9; }
        .stats { background: #0f172a; border-radius: 8px; padding: 12px; font-size: 13px; color: #94a3b8; text-align: left; }
    </style>
</head>
<body>
    <div class="card">
        <h1>AirCursor Web Remote</h1>
        <div id="statusBadge" class="badge badge-paused">Connecting...</div>
        <div class="btn-grid">
            <button id="btnTracking" class="btn-primary" onclick="postAction('/api/tracking/toggle')">Toggle Tracking</button>
            <button id="btnCamera" class="btn-camera" onclick="postAction('/api/camera/toggle')">Toggle Camera Vision</button>
            <button onclick="postAction('/api/mode/toggle')">Switch Mode</button>
            <button onclick="postAction('/api/recenter')">Recenter Cursor</button>
        </div>
        <div class="stats" id="telemetryBox">
            Source: <span id="telSource">-</span><br>
            Mode: <span id="telMode">-</span><br>
            Yaw: <span id="telYaw">0°</span> | Pitch: <span id="telPitch">0°</span><br>
            FPS: <span id="telFps">0</span>
        </div>
        <a href="/cad/remote_showcase.html" target="_blank" style="display:block; margin-top:14px; text-decoration:none; background:#372714; color:#fdba74; padding:10px; border-radius:8px; font-weight:bold; border:1px solid #7c2d12;">
            🌐 3D Physical Remotes Showcase (5 Products)
        </a>
    </div>
    <script>
        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                const badge = document.getElementById('statusBadge');
                badge.innerText = data.tracking_enabled ? 'TRACKING ACTIVE' : 'TRACKING PAUSED';
                badge.className = 'badge ' + (data.tracking_enabled ? 'badge-active' : 'badge-paused');
                document.getElementById('telSource').innerText = data.active_source.toUpperCase();
                document.getElementById('telMode').innerText = data.mode.toUpperCase();
                document.getElementById('telYaw').innerText = data.live_yaw + '°';
                document.getElementById('telPitch').innerText = data.live_pitch + '°';
                document.getElementById('telFps').innerText = data.live_fps;
            } catch(e) {}
        }
        async function postAction(endpoint) {
            try {
                await fetch(endpoint, { method: 'POST' });
                fetchStatus();
            } catch(e) {}
        }
        setInterval(fetchStatus, 500);
        fetchStatus();
    </script>
</body>
</html>"""

        try:
            class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
                allow_reuse_address = True
                daemon_threads = True

            self._server = _ThreadedTCPServer((self.host, self.port), _Handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="AirCursor-WebRemoteAPI",
            )
            self._thread.start()
            self._running = True
            return True
        except Exception as e:
            print(f"[AirCursor Web Remote] Failed to bind port {self.port}: {e}")
            self._running = False
            return False

    def stop(self) -> None:
        """Shuts down the Web Remote HTTP server."""
        if not self._running:
            return
        self._running = False
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None
