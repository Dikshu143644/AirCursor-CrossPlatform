# AirCursor: Cross-Platform Suite (Windows, Linux, Android)

High-precision head-tracking cursor and hands-free gesture control powered by Apple AirPods (AirPods Pro, AirPods Max, AirPods 3/4) and OpenTrack-compatible motion sensors.

Originally created for macOS by [Muhammad Afham](https://github.com/m-afham/AirCursor), this repository contains the complete **reverse-engineered and recoded cross-platform suite** targeting:
* **Windows 10 / 11** (Native Win32 input, UI Automation smart dwell, transparent click-through HUD)
* **Linux** (BlueZ L2CAP MTU 2582 Apple RemoteHID/AAP stream + kernel `/dev/uinput` mouse)
* **Android** (Kotlin `AccessibilityService` tap dispatch + `WindowManager` overlay)
* **Core Engine** (Pure Python 3, zero external dependencies, 100% test coverage)

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
[Event Synthesizer] (Win32 SendInput / Linux uinput / Android AccessibilityService)
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

## Android Quick Start

The Android implementation in [`android/`](android/) is a complete Android Studio Gradle project:
* **`AirCursorAccessibilityService`**: Injects cursor movement and simulated clicks using `dispatchGesture()` without needing root.
* **`DwellOverlayService`**: Renders a floating, click-through circular dwell progress ring via `WindowManager`.
* **`AirPodsMotionService`**: Connects to AirPods over Bluetooth L2CAP channel `0x1001` with seamless fallback to the phone's internal rotation vector sensor (`Sensor.TYPE_ROTATION_VECTOR`).

---

## Verification & Test Results

Run tests with standard `unittest`:

```bash
# Core Engine (50 tests):
python -m unittest tests/test_core.py

# Windows Native Suite (13 tests):
python windows/test_windows_app.py

# Linux Native Suite (10 tests):
PYTHONPATH=linux python -m unittest linux/test_linux.py
```

**Overall Status: 73/73 tests passing (100% OK)**

---

## License

MIT License. Based on [AirCursor](https://github.com/m-afham/AirCursor) by Muhammad Afham.
