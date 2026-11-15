# AirCursor: Offline & Air-Gapped Deployment Guide

## Overview

AirCursor is architected with a strict **Zero-Internet, Zero-Telemetry, Zero-External-Dependency** philosophy. All core algorithms, mathematical smoothing, gesture recognition, PWA Web Remote assets, and input synthesizer routines run 100% locally on your machine or private intranet.

---

## 1. Standalone Execution (No Internet Required)

### Windows
1. Unzip the distribution bundle `aircursor_offline_bundle.zip` into any directory.
2. Launch the Web Remote & API:
   ```cmd
   Start-WebRemote.bat
   ```
3. Or launch native Windows desktop mode with system tray:
   ```cmd
   Start-AirCursor.bat
   ```
4. Point your browser or smartphone (on the same local Wi-Fi / hotspot) to:
   ```
   http://localhost:8765
   ```

### Linux / macOS
1. Ensure Python 3.10+ is installed.
2. Make shell launchers executable:
   ```bash
   chmod +x start-aircursor.sh start-webremote.sh
   ```
3. Launch Web Remote:
   ```bash
   ./start-webremote.sh
   ```

---

## 2. Docker Container Deployment

The multi-arch Docker image bundles a virtual X11 display server (`Xvfb`), `x11vnc`, and HTML5 `noVNC`.

### Running with Docker:
```bash
# Build image locally from source (or load offline tar archive):
docker build -t aircursor:latest .

# Run with Web Remote (8765), OpenTrack UDP (4242), and noVNC Display (6080):
docker run -d \
  --name aircursor \
  -p 8765:8765 \
  -p 4242:4242/udp \
  -p 6080:6080 \
  -e MODE=synthetic \
  aircursor:latest
```

### Running with Docker Compose:
```bash
docker compose up -d
```

---

## 3. Kubernetes (K8s) Production Deployment

Deploy seamlessly into offline / air-gapped clusters using Kustomize:
```bash
kubectl apply -k k8s/
```

Verify pod health and readiness:
```bash
kubectl get pods -l app.kubernetes.io/name=aircursor
kubectl get svc -l app.kubernetes.io/name=aircursor
```

The liveness and readiness probes query `http://localhost:8765/status` without requiring external network connectivity.

---

## 4. Hardware Sensor Connectivity

* **OpenTrack UDP Protocol**:
  - Send 48-byte UDP telemetry packets (`<6d`: 3 translations + yaw, pitch, roll in degrees) to port `4242/udp`.
* **AirPods Native Bluetooth (Linux)**:
  - Connect via BlueZ L2CAP (PSM `0x1001`, MTU `2582`).
* **Smartphone Wi-Fi Gyroscope**:
  - Open the Web Remote PWA (`http://<server-ip>:8765`) on your phone.
  - Tap **"Stream Phone Gyro"** to bridge device motion directly over the local network.
