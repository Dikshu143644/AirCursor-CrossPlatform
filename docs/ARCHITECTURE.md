# AirCursor Cross-Platform System Architecture

```mermaid
flowchart TD
    subgraph Sensors["Sensor Ingestion Layer"]
        A1["Apple AirPods IMU (BlueZ L2CAP MTU 2582)"]
        A2["OpenTrack UDP Stream (Port 4242)"]
        A3["Web Remote Gyro / Virtual Touchpad (Port 8765)"]
        A4["Synthetic Kinematic Generator (Simulation)"]
    end

    subgraph Pipeline["120Hz Kinematics Pipeline"]
        B1["Motion Differentiator (Angle Unwrapping & Rates)"]
        B2["Pointer Mapper (Deadzone 3°/s, Sensitivity, Acceleration)"]
        B3["Pointer Smoother (α = 1 - s^(dt*60))"]
        B4["Cursor History Ring Buffer (360 samples)"]
        B5["Gesture Detector (Nod, Shake, Roll Tilt)"]
        B6["Smart Dwell Detector (16px radius, 0.8s hold)"]
    end

    subgraph Output["Event Synthesis & Display Layer"]
        C1["Win32 SendInput (Windows)"]
        C2["Linux /dev/uinput or X11 Synthetic"]
        C3["Android AccessibilityService Gestures"]
        C4["Virtual Display (Xvfb + x11vnc + noVNC :6080)"]
        C5["Web Remote PWA & Status Server (:8765)"]
    end

    A1 --> B1
    A2 --> B1
    A3 --> B1
    A4 --> B1

    B1 --> B2 --> B3 --> B4
    B1 --> B5
    B3 --> B6

    B3 --> C1
    B3 --> C2
    B3 --> C3
    B3 --> C4
    B3 --> C5
```

## Zero-Internet Architecture Guarantee
1. **No External CDNs**: All PWA HTML, JavaScript, CSS, and icons are embedded locally in `web/`.
2. **Pure Python Core**: All math, kinematics, actions, dwell logic, and REST server run on standard Python 3.10+ libraries.
3. **Air-Gapped Containerization**: Docker and Kubernetes manifests configure `imagePullPolicy: IfNotPresent` and standalone healthchecks.
