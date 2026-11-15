# AirCursor: Cross-Platform Suite (Windows, Linux, macOS Input Adapter, Android)

High-precision head-tracking cursor and hands-free gesture control powered by Apple AirPods (AirPods Pro, AirPods Max, AirPods 3/4) and OpenTrack-compatible motion sensors.

Originally created for macOS by [Muhammad Afham](https://github.com/m-afham/AirCursor), this repository contains a cross-platform suite targeting:
* **Windows 10 / 11** (Native Win32 input, UI Automation smart dwell, transparent click-through HUD)
* **Linux** (BlueZ L2CAP MTU 2582 Apple RemoteHID/AAP stream + kernel `/dev/uinput` mouse)
* **macOS input adapter** (CoreGraphics mouse events through the optional PyObjC Quartz framework; separate from the AirPods sensor receiver and desktop-app integration)
* **Android** (Kotlin `AccessibilityService` tap dispatch + `WindowManager` overlay)
* **Core Engine** (Python 3 motion, pointer, gesture, and dwell processing)

---

## Architecture & Reverse-Engineered Algorithms

AirCursor transforms AirPods IMU telemetry (accelerometer + gyroscope) into an intuitive, drift-free virtual mouse:

```
[AirPods IMU Sensors] (25Hz - 210Hz)
        │
        ▼
[Motion Differentiator] (Angle unwrapping, gap rejection 2ms - 250ms)
        │
        ▼
[Pointer Mapper] (Tremor deadzone 3°/s, non-linear acceleration boost up to 3x)
        │
        ▼
[120Hz Pointer Smoother] (Frame-rate independent exponential interpolation: α = 1 - s^(dt*60))
        │
        ├──▶ [Cursor History Ring Buffer] (Stores 360 timestamped coordinates)
        │           │ (Pre-gesture rollback)
        │           ▼
        ├──▶ [Gesture Detector] (Shape-based Nod dip/return, 4-swing Shake, 22° Roll Tilt)
        │           │
        │           ▼
        ├──▶ [Smart Dwell Detector] (16px radius, 0.8s hold + UI Accessibility Probe)
        │
        ▼
[Platform Input Adapter] (Win32 / Linux uinput / macOS CoreGraphics / Android AccessibilityService)
```

### Key Technical Innovations
1. **Velocity ("Ratchet") Mapping**: Instead of absolute angle mapping which causes neck strain, AirCursor calculates head angular velocity ($\text{deg/s}$) at $28\text{ px/deg}$, allowing you to navigate across multi-monitor setups effortlessly.
2. **Pre-Gesture Coordinate Rollback**: When a nod or shake is detected, the cursor jumps back to where you were looking $60\text{ ms}$ **before** the gesture started, eliminating the pointer displacement caused by head movement.
3. **Smart Hover / Dwell Click**: Clicks only when resting on interactive UI elements (buttons, links, textboxes, tabs). Resting on plain reading text never triggers accidental clicks.
4. **AirPods Stem Squeezes (AVRCP Media Keys)**:
   * **1 press** (Play/Pause) $\to$ Left Click
   * **2 presses** (Next Track) $\to$ Right Click
   * **3 presses** (Prev Track) $\to$ Toggle Scroll Mode

---

## Windows Quick Start

### 1. One-Click Launcher
Double-click [`Start-AirCursor.bat`](Start-AirCursor.bat) to launch the interactive menu.

### 2. Command Line Usage
```powershell
cd windows

# Run in Live Mode (waits for AirPods / OpenTrack UDP on port 4242):
python main.py --tray

# Run in Demo / Simulation Mode:
python main.py --synthetic --tray

# View Paired AirPods & Bluetooth Setup Guide:
python main.py --setup-info
```

### Global Hotkeys
* `Ctrl + Alt + T` : Pause / Resume Tracking
* `Ctrl + Alt + S` : Toggle Scroll Mode / Pointer Mode
* `Ctrl + Alt + C` : Recenter Cursor
* `Ctrl + Alt + D` : Toggle Left-Mouse Drag Lock
* `Ctrl + C`       : Exit AirCursor

---

## Linux Quick Start

Linux uses direct BlueZ L2CAP sockets with an expanded MTU of **2,582 bytes** to handle Apple's RemoteHID / `devmotion6` descriptor without truncation, and `/dev/uinput` for kernel mouse injection.

```bash
cd linux

# Grant uinput permissions (if needed):
sudo usermod -a -G input $USER

# Run with paired AirPods:
python3 main_linux.py --scan
```

---

## macOS Input Adapter

The CoreGraphics adapter is available as a separately installable backend. It currently provides pointer positioning, relative movement, left/right/middle click and drag, scroll, and cursor-position queries. The camera/AirPods sensing pipeline and a complete macOS desktop controller are not yet integrated with this adapter.

Install on macOS:

```bash
python -m pip install -e ".[macos]"
```

macOS requires the app, terminal, or Python launcher to be approved under **System Settings → Privacy & Security → Accessibility** before it can synthesize mouse input. See [`macos/README.md`](macos/README.md) for the adapter API and an example.

---

## Android Quick Start

The Android implementation in [`android/`](android/) is an Android Studio Gradle project:
* **`AirCursorAccessibilityService`**: Injects cursor movement and simulated clicks using `dispatchGesture()` without needing root.
* **`DwellOverlayService`**: Renders a floating, click-through circular dwell progress ring via `WindowManager`.
* **`AirPodsMotionService`**: Connects to AirPods over Bluetooth L2CAP channel `0x1001` with seamless fallback to the phone's internal rotation vector sensor (`Sensor.TYPE_ROTATION_VECTOR`).

---

## Verification & Test Results

Run platform-neutral and platform-specific tests with standard `unittest`:

```bash
# Core Engine:
python -m unittest tests.test_core -v

# macOS CoreGraphics adapter tests (uses a fake Quartz API on non-macOS hosts):
python -m unittest tests.test_macos_driver -v

# Windows Native Suite (run on Windows):
python windows/test_windows_app.py

# Linux Native Suite:
PYTHONPATH=linux python -m unittest linux/test_linux.py -v
```

The GitHub Actions workflow tests Linux and Windows on Python 3.10, 3.11, and 3.12, and runs the macOS adapter suite on macOS with Python 3.12. Hardware-specific camera, Bluetooth, and accessibility behavior still requires testing on the target device and operating system.

---

## License

MIT License. Based on [AirCursor](https://github.com/m-afham/AirCursor) by Muhammad Afham.
