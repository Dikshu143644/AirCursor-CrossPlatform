"""Unit tests for Subject 03, Subject 04, and Subject 14:
- Subject 03: aircursor_core/web_remote_server.py
- Subject 04: aircursor_core/static/remote.html
- Subject 14: aircursor_core/pairing_qr.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time
import unittest
import urllib.request
import urllib.error

# Ensure root workspace is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
WINDOWS_DIR = ROOT_DIR / "windows"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

from aircursor_core.pairing_qr import (
    PairingQR,
    get_local_ip,
    get_pairing_url,
    generate_qr_matrix,
    matrix_to_ascii,
    matrix_to_svg,
    matrix_to_html,
    _pure_python_qr,
)
from aircursor_core.web_remote_server import WebRemoteServer, WebRemoteRequestHandler, WS_GUID


class TestPairingQR(unittest.TestCase):
    """Subject 14: Rigorous tests for pairing QR generator and network discovery."""

    def test_local_ip_discovery(self):
        """Verifies that get_local_ip returns a valid, non-empty IPv4 address."""
        ip = get_local_ip()
        self.assertIsInstance(ip, str)
        self.assertTrue(len(ip) > 0)
        parts = ip.split(".")
        self.assertEqual(len(parts), 4, f"IP {ip} should have 4 octets")
        for p in parts:
            val = int(p)
            self.assertTrue(0 <= val <= 255, f"Octet {p} out of range in {ip}")

    def test_pairing_url_generation(self):
        """Verifies URL generation with default and custom IP/port."""
        default_url = get_pairing_url()
        self.assertTrue(default_url.startswith("http://"))
        self.assertTrue(default_url.endswith(":8765"))

        custom_url = get_pairing_url(port=9000, ip="192.168.1.50")
        self.assertEqual(custom_url, "http://192.168.1.50:9000")

    def test_qr_matrix_generation(self):
        """Verifies 2D boolean matrix properties."""
        qr = PairingQR(port=8765, ip="192.168.1.100")
        matrix = qr.matrix
        self.assertIsInstance(matrix, list)
        n = len(matrix)
        self.assertGreaterEqual(n, 21, "QR matrix should be at least Version 1 (21x21)")
        for row in matrix:
            self.assertEqual(len(row), n, "QR matrix must be perfectly square")
            for cell in row:
                self.assertIsInstance(cell, bool, "Matrix cells must be booleans")

        # Verify finder pattern at top-left: 7x7 outer square is dark
        # Module (0,0) must be dark
        self.assertTrue(matrix[0][0])
        # Center of finder pattern (3,3) must be dark
        self.assertTrue(matrix[3][3])
        # Ring around center (2,2) is white
        self.assertFalse(matrix[1][1])

    def test_pure_python_qr_engine(self):
        """Verifies that the standalone zero-dependency pure Python QR engine works."""
        test_data = "http://10.0.0.1:8765"
        pure_m = _pure_python_qr(test_data)
        self.assertIsInstance(pure_m, list)
        size = len(pure_m)
        self.assertGreaterEqual(size, 21)
        self.assertEqual(len(pure_m[0]), size)
        # Check that top-left finder pattern exists
        self.assertTrue(pure_m[0][0])
        self.assertTrue(pure_m[0][6])
        self.assertTrue(pure_m[6][0])
        self.assertTrue(pure_m[6][6])

    def test_ascii_rendering(self):
        """Verifies ASCII / Unicode rendering of QR code."""
        qr = PairingQR(port=8765, ip="192.168.1.1")
        # Compact half-block
        compact_ascii = qr.to_ascii(border=2, compact=True)
        self.assertIsInstance(compact_ascii, str)
        self.assertTrue(len(compact_ascii) > 0)
        self.assertIn("\n", compact_ascii)
        # Verify Unicode characters are present
        has_blocks = any(ch in compact_ascii for ch in ("█", "▀", "▄", " "))
        self.assertTrue(has_blocks, "ASCII QR must contain half-block glyphs")

        # Full blocks
        full_ascii = qr.to_ascii(border=2, compact=False)
        self.assertIsInstance(full_ascii, str)
        self.assertIn("██", full_ascii)

    def test_svg_rendering(self):
        """Verifies SVG format rendering."""
        qr = PairingQR(port=8765, ip="192.168.1.1")
        svg = qr.to_svg(box_size=10, border=4, fg="#00f0ff", bg="#060913")
        self.assertIsInstance(svg, str)
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertIn('viewBox="0 0', svg)
        self.assertIn('fill="#060913"', svg)
        self.assertIn('fill="#00f0ff"', svg)
        self.assertIn("<path", svg)

    def test_html_card_rendering(self):
        """Verifies interactive HTML pairing card markup."""
        qr = PairingQR(port=8765, ip="192.168.1.1")
        html = qr.to_html(title="AirCursor Pairing")
        self.assertIsInstance(html, str)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("AirCursor Pairing", html)
        self.assertIn("<svg", html)
        self.assertIn("http://192.168.1.1:8765", html)

    def test_dict_serialization(self):
        """Verifies to_dict output contains all expected keys."""
        qr = PairingQR(port=8765, ip="192.168.1.1")
        d = qr.to_dict()
        for k in ("url", "ip", "port", "qr_ascii", "qr_svg"):
            self.assertIn(k, d)
        self.assertEqual(d["ip"], "192.168.1.1")
        self.assertEqual(d["port"], 8765)


class TestWebRemoteServer(unittest.TestCase):
    """Subject 03 & Subject 04: Tests for HTTP/WebSocket endpoints and mobile remote."""

    @classmethod
    def setUpClass(cls):
        # Start server on an ephemeral port (port=0 lets OS choose free port)
        cls.server = WebRemoteServer(host="127.0.0.1", port=0)
        cls.server.start()
        cls.port = cls.server.port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        # Give thread a moment to bind
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_server_lifecycle(self):
        """Verifies start and stop lifecycle."""
        self.assertTrue(self.server.is_running)
        self.assertGreater(self.port, 0)
        self.assertTrue(self.server.url.startswith("http://"))

    def test_websocket_rejects_oversized_extended_frames(self):
        """Rejects oversized RFC 6455 payloads after decoding extended lengths."""
        receiver, sender = socket.socketpair()
        try:
            sender.sendall(bytes((0x81, 0x7F)) + struct.pack("!Q", 65537))
            handler = object.__new__(WebRemoteRequestHandler)
            self.assertIsNone(handler._read_ws_frame(receiver))
        finally:
            receiver.close()
            sender.close()

    def test_get_root_serves_remote_html(self):
        """Subject 04: GET / serves aircursor_core/static/remote.html."""
        req = urllib.request.Request(f"{self.base_url}/")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 200)
            content_type = res.headers.get("Content-Type", "")
            self.assertIn("text/html", content_type)
            body = res.read().decode("utf-8")
            # Verify Subject 04 features in HTML
            self.assertIn("AirCursor Remote", body)
            self.assertIn("Touchpad", body)
            self.assertIn("Air Mouse", body)
            self.assertIn("HOLD TO MOVE", body)
            self.assertIn("DeviceOrientation", body)
            self.assertIn("manifest.json", body)

    def test_get_manifest(self):
        """GET /manifest.json serves Web App Manifest for PWA."""
        req = urllib.request.Request(f"{self.base_url}/manifest.json")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 200)
            manifest = json.loads(res.read().decode("utf-8"))
            self.assertEqual(manifest.get("name"), "AirCursor Mobile Remote")
            self.assertEqual(manifest.get("short_name"), "AirCursor")
            self.assertEqual(manifest.get("display"), "standalone")

    def test_get_service_worker(self):
        """GET /sw.js serves Service Worker for PWA offline capability."""
        req = urllib.request.Request(f"{self.base_url}/sw.js")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 200)
            content_type = res.headers.get("Content-Type", "")
            self.assertIn("javascript", content_type)
            body = res.read().decode("utf-8")
            self.assertIn("addEventListener", body)

    def test_get_status_endpoint(self):
        """GET /status returns JSON with cursor pos, tracking source, connection count."""
        req = urllib.request.Request(f"{self.base_url}/status")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIn("cursor", data)
            self.assertIn("x", data["cursor"])
            self.assertIn("y", data["cursor"])
            self.assertIn("source", data)
            self.assertIn(data["source"], ("airpods", "camera", "remote", "synthetic"))
            self.assertIn("connection_count", data)
            self.assertIsInstance(data["connection_count"], int)
            self.assertIn("tracking_enabled", data)
            self.assertIn("mode", data)

    def test_get_qr_endpoint(self):
        """GET /api/qr returns JSON with local IP URL and ASCII QR code."""
        req = urllib.request.Request(f"{self.base_url}/api/qr")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertIn("url", data)
            self.assertIn("ip", data)
            self.assertIn("port", data)
            self.assertIn("qr_ascii", data)
            self.assertIn("qr_svg", data)
            self.assertTrue(len(data["qr_ascii"]) > 0)
            self.assertTrue("<svg" in data["qr_svg"])
            self.assertIn("#token=", data["url"])
            self.assertIn(self.server.access_token, data["url"])

    def test_control_endpoints_require_bearer_token(self):
        """Unauthenticated control requests are rejected before dispatch."""
        dispatched = []
        self.server.set_action_callback(lambda *args: dispatched.append(args))
        request = urllib.request.Request(
            f"{self.base_url}/api/action",
            data=json.dumps({"action": "left_click"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3.0)
        self.assertEqual(caught.exception.code, 401)
        self.assertEqual(dispatched, [])

    def test_post_action_endpoint(self):
        """POST /api/action dispatches actions and returns JSON."""
        dispatched_actions = []

        def _action_cb(action, dx, dy, extra):
            dispatched_actions.append((action, dx, dy, extra))

        self.server.set_action_callback(_action_cb)

        actions_to_test = [
            ("click", 0.0, 0.0),
            ("right_click", 0.0, 0.0),
            ("middle_click", 0.0, 0.0),
            ("double_click", 0.0, 0.0),
            ("drag_toggle", 0.0, 0.0),
            ("recenter", 0.0, 0.0),
            ("scroll", 10.0, -25.0),
        ]

        for act, dx, dy in actions_to_test:
            payload = json.dumps({"action": act, "dx": dx, "dy": dy}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/action",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + self.server.access_token,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3.0) as res:
                self.assertEqual(res.status, 200)
                data = json.loads(res.read().decode("utf-8"))
                self.assertEqual(data.get("status"), "ok")
                self.assertEqual(data.get("action"), act)

        # Verify all actions reached the callback
        self.assertEqual(len(dispatched_actions), len(actions_to_test))
        # Check scroll parameters
        scroll_entry = dispatched_actions[-1]
        self.assertEqual(scroll_entry[0], "scroll")
        self.assertEqual(scroll_entry[1], 10.0)
        self.assertEqual(scroll_entry[2], -25.0)

    def test_post_motion_endpoint(self):
        """POST /api/motion dispatches relative motion and gyro readings."""
        dispatched_motion = []

        def _motion_cb(data):
            dispatched_motion.append(data)

        self.server.set_motion_callback(_motion_cb)

        payload = {
            "source": "remote",
            "dx": 15.5,
            "dy": -8.25,
            "gyro": {"pitch": 4.5, "yaw": -12.0, "roll": 1.2},
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/motion",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.server.access_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 200)
            data = json.loads(res.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")

        self.assertEqual(len(dispatched_motion), 1)
        received = dispatched_motion[0]
        self.assertEqual(received["source"], "remote")
        self.assertEqual(received["dx"], 15.5)
        self.assertEqual(received["dy"], -8.25)
        self.assertEqual(received["gyro"]["pitch"], 4.5)
        self.assertEqual(received["gyro"]["yaw"], -12.0)

        # Verify tracking source switched to 'remote'
        status = self.server.get_status_dict()
        self.assertEqual(status["source"], "remote")

    def test_cors_options_preflight(self):
        """OPTIONS request returns 204 with CORS allow headers."""
        req = urllib.request.Request(f"{self.base_url}/api/action", method="OPTIONS")
        with urllib.request.urlopen(req, timeout=3.0) as res:
            self.assertEqual(res.status, 204)
            self.assertIsNone(res.headers.get("Access-Control-Allow-Origin"))
            self.assertIn("POST", res.headers.get("Access-Control-Allow-Methods", ""))

    def test_websocket_stream_and_actions(self):
        """Verifies pure-Python RFC 6455 WebSocket connection and framing."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(("127.0.0.1", self.port))

        # Perform RFC 6455 handshake
        nonce = "dGhlIHNhbXBsZSBub25jZQ=="
        expected_accept = base64.b64encode(
            hashlib.sha1((nonce + WS_GUID).encode("utf-8")).digest()
        ).decode("utf-8")

        handshake_req = (
            f"GET /ws HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{self.port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {nonce}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(handshake_req.encode("utf-8"))

        response = sock.recv(2048).decode("utf-8")
        self.assertIn("101 Switching Protocols", response)
        self.assertIn(f"Sec-WebSocket-Accept: {expected_accept}", response)

        # The socket is not registered as a control client until it authenticates.
        time.sleep(0.05)
        self.assertEqual(self.server.connection_count, 0)

        # Helper to send masked client frame
        def send_client_frame(text: str):
            payload = text.encode("utf-8")
            mask_key = b"\x13\x37\x42\x99"
            masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            plen = len(payload)
            if plen <= 125:
                hdr = bytes([0x81, 0x80 | plen])
            else:
                hdr = bytes([0x81, 0x80 | 126]) + struct.pack("!H", plen)
            sock.sendall(hdr + mask_key + bytes(masked))

        def read_server_frame():
            def recv_exact(size):
                data = bytearray()
                while len(data) < size:
                    part = sock.recv(size - len(data))
                    if not part:
                        raise ConnectionError("WebSocket closed")
                    data.extend(part)
                return bytes(data)
            first, second = recv_exact(2)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", recv_exact(8))[0]
            return first & 0x0F, recv_exact(length)

        # Authenticate as the very first WebSocket application frame.
        send_client_frame(json.dumps({"type": "auth", "token": self.server.access_token}))
        opcode, ready_payload = read_server_frame()
        self.assertEqual(opcode, 0x1)
        self.assertEqual(json.loads(ready_payload.decode("utf-8"))["type"], "ready")
        time.sleep(0.05)
        self.assertEqual(self.server.connection_count, 1)

        # Test action dispatch over WebSocket
        ws_actions = []
        self.server.set_action_callback(lambda a, dx, dy, extra: ws_actions.append((a, dx, dy)))

        action_msg = json.dumps({"type": "action", "action": "middle_click", "dx": 0.0, "dy": 0.0})
        send_client_frame(action_msg)
        time.sleep(0.05)

        self.assertEqual(len(ws_actions), 1)
        self.assertEqual(ws_actions[0][0], "middle_click")

        # Test motion dispatch over WebSocket
        ws_motions = []
        self.server.set_motion_callback(lambda data: ws_motions.append(data))

        motion_msg = json.dumps({"type": "motion", "dx": 5.0, "dy": -3.0})
        send_client_frame(motion_msg)
        time.sleep(0.05)

        self.assertEqual(len(ws_motions), 1)
        self.assertEqual(ws_motions[0]["dx"], 5.0)
        self.assertEqual(ws_motions[0]["dy"], -3.0)

        # Close WebSocket connection
        sock.close()
        time.sleep(0.1)
        self.assertEqual(self.server.connection_count, 0)

    @unittest.skipUnless(sys.platform == "win32", "AppController integration requires Windows input APIs")
    def test_app_controller_integration(self):
        """Verifies direct binding of AppController with WebRemoteServer."""
        from app_controller import AppController

        # Create headless synthetic controller
        controller = AppController(
            use_synthetic=True,
            show_overlay=False,
            enable_stem_hook=False,
        )

        try:
            self.server.attach_controller(controller)

            # Test remote action execution
            res = self.server.dispatch_action("drag_toggle")
            self.assertTrue(controller.is_dragging)

            res = self.server.dispatch_action("drag_toggle")
            self.assertFalse(controller.is_dragging)

            # Test remote motion execution
            self.server.dispatch_motion({"dx": 10.0, "dy": 10.0})
            self.assertIsNotNone(controller._cursor)

            # Test status reporting with controller attached
            status = self.server.get_status_dict()
            self.assertEqual(status["source"], "remote")
            self.assertIn("cursor", status)
            self.assertIsInstance(status["cursor"]["x"], float)
            self.assertIsInstance(status["cursor"]["y"], float)

        finally:
            controller.stop()


if __name__ == "__main__":
    unittest.main()
