# AirCursor: Cross-Platform Suite (Windows, Linux, Android)

High-precision head-tracking cursor and hands-free gesture control powered by Apple AirPods and local vision / touch / gyroscope input.

This repository contains the AirCursor cross-platform suite:
- **Windows 10 / 11:** native Win32 input, tray controls, HUD, hotkeys and local camera fallback.
- **Linux:** BlueZ AirPods input and /dev/uinput cursor injection.
- **Android:** Accessibility Service companion and device motion support.
- **Core engine:** motion differentiation, pointer mapping, gestures, dwell and source arbitration.
- **Universal remote:** mobile PWA touchpad and phone gyroscope over HTTP/WebSocket.
- **Deployment:** Docker, offline packaging and Kubernetes manifests.
- **Hardware concepts:** five procedural Blender remote designs with render and export assets.

## Secure mobile pairing

The Web Remote is protected by a random bearer token.

1. Start AirCursor on the host computer.
2. On Windows desktop mode, open **http://127.0.0.1:8765/pair** on the host PC and scan the QR code from the phone.
3. For Docker/headless mode, copy the token printed by **docker logs aircursor**, open **http://HOST-LAN-IP:8765** on the phone, and enter the token when prompted.
4. Keep the token private. Restart the process to rotate an automatically generated token.

The QR endpoint is host-local only. The status endpoint remains read-only; all control endpoints require bearer authentication. Use only a trusted LAN, VPN, or TLS-protected Ingress.

## Windows quick start

Double-click **Start-AirCursor.bat**, or:

~~~powershell
cd windows
python main.py --tray
~~~

## Linux quick start

~~~bash
cd linux
python3 main_linux.py --scan
~~~

## Tests

Install development dependencies and run platform-appropriate suites:

~~~bash
python -m pip install -e ".[dev]"
python -m unittest tests.test_core tests.test_web_remote tests.test_vision_tracker tests.test_subjects tests.test_devops tests.test_cad_blender -v
~~~

Windows-specific suites should be run on Windows; Linux input tests should be run on Linux. CI is configured for Python 3.10–3.12 on Ubuntu and Windows.

## Deployment

See **docs/OFFLINE_GUIDE.md** for Docker, Compose, Kubernetes, offline distribution and secure pairing instructions.

## 3D remote concepts

See **cad/REMOTE_CONCEPTS.md** and **cad/remote_showcase.html** for the five hardware concepts and model exports.

## License

MIT License. Based on [AirCursor](https://github.com/m-afham/AirCursor) by Muhammad Afham.
