# AirCursor Universal Ecosystem — Build Roadmap

This repository is an existing cross-platform AirCursor implementation. The 15 workstreams are expansion targets, not claims that every feature is already implemented.

## Delivery sequence
1. Foundation: source arbitration, authenticated local remote protocol, pairing and protocol tests.
2. Vision: optional local camera dependencies, face/nose mapping, hand gestures, privacy indicator and camera-off control.
3. Desktop integration: wire arbitration and remote events into existing Windows/Linux/macOS input adapters; add safe startup and tray controls.
4. Mobile: installable PWA, orientation permission flow, gyroscope air-mouse and Android companion integration.
5. Deployment: offline dependency bundle, Docker image and headless virtual-display profile; Kubernetes manifests for supported headless deployments.
6. CAD: Blender 5.1 parametric generators and five concept exports. These are prototypes, not production-ready hardware.
7. Validation: CI matrix, hardware-in-the-loop instructions and platform-specific limitations.

## Protocol safety
- Clients authenticate with a random bearer token in the first WebSocket message.
- Pairing URLs put the token in the URL fragment, which browsers do not include in HTTP requests.
- Pointer coordinates are normalized to 0..1 and validated server-side.
- The gateway delegates OS input injection to a platform adapter supplied by the host app.
- Bind the gateway to a trusted LAN only. Do not expose port 8765 to the public internet.

## Implemented foundation slice
- aircursor_core/arbiter.py: priority-based source selection and stale-heartbeat failover.
- aircursor_core/web_remote_server.py: optional aiohttp HTTP/WebSocket gateway and command validation.
- aircursor_core/static/: initial touchpad web client.
- aircursor_core/pairing_qr.py: pairing URL and optional terminal QR helper.
- tests/test_universal_ecosystem.py: arbitration and pairing unit tests.

## Not yet implemented
Camera inference, gyroscope sensor bridge, OS cursor adapter wiring, native Android changes, Bluetooth broker changes, Docker/Kubernetes packaging, offline dependency bundling, Blender CAD generation and full end-to-end tests.
