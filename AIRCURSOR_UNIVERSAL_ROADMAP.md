# AirCursor Universal Ecosystem — Verified Build Roadmap

This roadmap distinguishes existing repository capabilities from work still required. "Present" means source code exists; it does not imply every device combination has been hardware-validated.

## Existing capabilities discovered on the main branch

| Workstream | Existing implementation | Remaining validation / gaps |
|---|---|---|
| Core motion engine | Motion differentiation, pointer mapping/smoothing, gestures, dwell | Calibration and multi-device regression |
| Input arbitration | `aircursor_core/arbiter.py` switches between Bluetooth and vision | Add source-health edge-case tests |
| Webcam vision | `vision_tracker.py` uses local OpenCV face/nose estimation and hand-contour gesture classification | Improve tracking robustness; evaluate varied lighting/cameras; MediaPipe can be an optional future backend |
| Mobile web remote | `web_remote_server.py` provides stdlib HTTP + RFC 6455 WebSocket | Validate real device/browser combinations |
| Mobile PWA | `static/remote.html` includes touchpad, gyroscope, clutch, haptics, settings and install flow | Verify iOS permission UX and Android browser behavior |
| Bluetooth | Windows OpenTrack/receiver and Linux BlueZ components | Hardware matrix and reconnection soak tests |
| Windows | Controller, tray, hotkeys, autostart and Win32 input | Verify start-on-launch policy and signed installer |
| Android | Native companion project and accessibility service | Build/sign APK and test API-level compatibility |
| Linux | BlueZ and uinput input stack | Validate permissions, Wayland/X11 and supported distributions |
| QR pairing | Pure-Python QR engine and pairing helper | Validate LAN isolation and pairing lifecycle |
| Test suites | Core, subject simulation, Windows and Linux tests | Run tests on matching operating-system runners |

## Remaining expansion work

1. **Cross-platform quality:** complete source-arbitration and vision regression tests; run Windows and Linux suites on their native CI runners; add macOS support only after a native input backend is available.
2. **Secure remote pairing:** add pairing authorization / expiry, safe binding defaults, origin validation, and explicit remote-control enablement before exposing a LAN endpoint.
3. **Deployment:** add Docker image and Compose profile for headless/synthetic operation; document that container cursor injection does not automatically control the host desktop.
4. **Kubernetes:** add headless deployment/service manifests and optional ingress guidance. Hardware access via host devices must remain opt-in and tightly scoped.
5. **Offline distribution:** create an offline wheelhouse/bundle and verify a clean install without network access.
6. **Blender CAD:** create five parametric concept models and exports. These are ergonomic prototypes, not production-certified hardware.

## Safety and implementation notes

- Camera processing is local; do not add cloud inference to the default path.
- The mobile remote controls a host input device and must not be exposed to the public internet without a secure authenticated transport.
- LAN pairing should use explicit user approval, a short-lived token, and a visible active-remote indicator.
- Docker/Xvfb/noVNC is a virtual desktop for testing and remote visualization. It is not a magic bridge into the physical host desktop.
- Do not grant privileged container mode by default. Linux uinput access should be a documented, opt-in device mapping with host permissions.
