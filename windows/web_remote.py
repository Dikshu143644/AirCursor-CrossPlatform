"""AirCursor Web Remote & REST API Server.

Provides a lightweight, zero-dependency embedded HTTP server for remote
monitoring and control of AirCursor from web browsers, smartphones, or scripts.
Supports manual camera toggle, tracking pause/resume, mode switching, and live telemetry.
"""

from __future__ import annotations

import http.server
import hmac
import ipaddress
import json
import os
import secrets
import socketserver
import threading
import urllib.parse
from typing import TYPE_CHECKING, Any, Dict, Optional

from aircursor_core.pairing_qr import generate_qr_matrix, get_local_ip, matrix_to_html

if TYPE_CHECKING:
    from app_controller import AppController


class WebRemoteServer:
    """Embedded HTTP server hosting AirCursor REST API and HTML Remote."""

    def __init__(
        self,
        controller: AppController,
        host: str = "0.0.0.0",
        port: int = 8765,
        access_token: Optional[str] = None,
    ):
        self.controller = controller
        self.host = host
        self.port = port
        self.access_token = access_token or os.environ.get("AIRCURSOR_REMOTE_TOKEN") or secrets.token_urlsafe(32)
        if len(self.access_token) < 20:
            raise ValueError("access_token must contain at least 20 characters")
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
        outer = self

        class _Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                # Suppress verbose HTTP access logs in console
                pass

            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path in ("/api/status", "/status"):
                    self._send_json(self._get_status())
                elif path == "/pair":
                    try:
                        is_local = ipaddress.ip_address(self.client_address[0]).is_loopback
                    except (ValueError, IndexError):
                        is_local = False
                    if not is_local:
                        self._send_json({"error": "pairing QR is available from the host computer only"}, code=403)
                        return
                    pair_url = (
                        f"http://{get_local_ip()}:{outer.port}/#token="
                        + urllib.parse.quote(outer.access_token, safe="")
                    )
                    html = matrix_to_html(
                        generate_qr_matrix(pair_url), pair_url, title="AirCursor Secure Pairing"
                    )
                    self._send_html(html)
                elif path in ("/", "/index.html"):
                    self._send_html(self._render_remote_html())
                else:
                    self.send_error(404, "Endpoint Not Found")

            def do_POST(self) -> None:
                path = self.path.split("?")[0]
                scheme, separator, supplied = self.headers.get("Authorization", "").partition(" ")
                authorized = (
                    bool(separator)
                    and scheme.lower() == "bearer"
                    and hmac.compare_digest(supplied.strip(), outer.access_token)
                )
                if not authorized:
                    self._send_json({"error": "unauthorized", "message": "Enter the host pairing token."}, code=401)
                    return
                if path in ("/api/camera/toggle", "/camera/toggle"):
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
        .pairing { text-align:left; margin:0 0 18px; }
        .pairing label { display:block; color:#bae6fd; font-size:13px; margin-bottom:6px; }
        .pairing input { width:100%; padding:12px; border-radius:8px; border:1px solid #475569; background:#0f172a; color:#fff; margin-bottom:8px; }
        .pairing button { width:100%; background:#075985; }
        .pairing p { color:#94a3b8; font-size:11px; margin-top:6px; }
    </style>
</head>
<body>
    <div class="card">
        <h1>AirCursor Web Remote</h1>
        <div id="statusBadge" class="badge badge-paused">Connecting...</div>
        <div class="pairing">
            <label for="pairingToken">Host pairing token</label>
            <input id="pairingToken" type="password" autocomplete="one-time-code" placeholder="Paste token from host console">
            <button id="savePairing" type="button">Connect this device</button>
            <p>Token is shown once in the AirCursor host console. Keep it private.</p>
        </div>
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
    </div>
    <script>
        const fragmentToken = new URLSearchParams(location.hash.replace(/^#/, '')).get('token');
        let accessToken = fragmentToken || sessionStorage.getItem('aircursor-access-token') || '';
        const pairingInput = document.getElementById('pairingToken');
        if (accessToken && location.hash) {
            sessionStorage.setItem('aircursor-access-token', accessToken);
            history.replaceState(null, '', location.pathname + location.search);
        }
        pairingInput.value = accessToken;
        document.getElementById('savePairing').addEventListener('click', () => {
            accessToken = pairingInput.value.trim();
            if (accessToken.length < 20) {
                alert('Enter the complete pairing token shown on the AirCursor host.');
                return;
            }
            sessionStorage.setItem('aircursor-access-token', accessToken);
            fetchStatus();
        });

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
            if (!accessToken) {
                alert('Enter the pairing token from the AirCursor host console first.');
                return;
            }
            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Authorization': 'Bearer ' + accessToken }
                });
                if (response.status === 401) {
                    accessToken = '';
                    sessionStorage.removeItem('aircursor-access-token');
                    pairingInput.value = '';
                    alert('Pairing token rejected. Enter the current token from the host console.');
                    return;
                }
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
            print(f"[AirCursor Web Remote] Access token (keep private): {self.access_token}")
            print(f"[AirCursor Web Remote] On this computer open http://127.0.0.1:{self.port}/pair for a secure QR code.")
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
