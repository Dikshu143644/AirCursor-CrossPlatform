# AirCursor API & Protocol Specification

## REST & Healthcheck Endpoints (Port 8765)

### `GET /status` (or `/health`, `/api/status`)
Kubernetes liveness/readiness probe and Docker healthcheck endpoint.

**Response `200 OK`**:
```json
{
  "status": "ok",
  "service": "aircursor",
  "version": "1.0.5",
  "mode": "synthetic",
  "tracking": true,
  "scroll_mode": false,
  "is_dragging": false,
  "uptime_seconds": 128.45,
  "fps": 120.0,
  "telemetry": {
    "yaw": 2.45,
    "pitch": -1.10,
    "roll": 0.32
  },
  "cursor": {
    "x": 960.0,
    "y": 540.0,
    "screen_width": 1920,
    "screen_height": 1080
  },
  "sensors": {
    "samples_received": 1450,
    "udp_port": 4242
  },
  "system": {
    "platform": "linux",
    "display": ":99",
    "novnc_enabled": true
  }
}
```

---

### `GET /api/settings`
Returns current configuration in JSON.

### `POST /api/settings`
Updates kinematics parameters dynamically.

**Request body**:
```json
{
  "sensitivity": 1.2,
  "deadzone": 2.5,
  "dwell_duration": 0.75,
  "smart_dwell": true
}
```

---

### `POST /api/action`
Triggers pointer or system actions.

**Request body**:
```json
{
  "action": "recenter"
}
```

Supported actions:
* `toggle_tracking`: Pauses or resumes head tracking.
* `recenter`: Centers cursor and zeroes velocity buffers.
* `toggle_scroll`: Toggles between Pointer Mode and Scroll Mode.
* `toggle_drag`: Toggles left mouse button drag lock.
* `left_click`, `right_click`, `double_click`: Synthesizes instant clicks.

---

### `POST /api/telemetry`
Injects real-time motion coordinates directly over HTTP.

**Request body**:
```json
{
  "yaw": 12.5,
  "pitch": -4.2,
  "roll": 1.1
}
```

---

## UDP Protocol (Port 4242)

AirCursor listens for OpenTrack telemetry packets:
* **Protocol**: UDP datagram
* **Size**: 48 bytes
* **Struct format**: `<6d` (Little-endian 6 double-precision floats)
  * `d[0]`: X translation (unused / reserved)
  * `d[1]`: Y translation (unused / reserved)
  * `d[2]`: Z translation (unused / reserved)
  * `d[3]`: Yaw angle in degrees
  * `d[4]`: Pitch angle in degrees
  * `d[5]`: Roll angle in degrees
