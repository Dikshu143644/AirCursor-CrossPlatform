# AirCursor for Windows

High-precision head tracking cursor and hands-free gesture control for Microsoft Windows, powered by Apple AirPods (AirPods Pro, AirPods Max, AirPods 3/4) or OpenTrack-compatible motion sensors.

---

## Key Features

1. **Native Win32 Input Synthesis (`event_synthesizer.py`)**:
   - Zero-latency Win32 `SendInput` and `SetCursorPos` wrappers using `ctypes`.
   - Multi-monitor virtual desktop bounds calculation and clamping.
   - Smooth relative and absolute mouse positioning.
   - Left click, right click, double click, middle click.
   - Drag-lock toggle (`toggle_drag` holds left mouse down across motion until released).
   - Mouse wheel vertical and horizontal scrolling (`MOUSEEVENTF_WHEEL`, `MOUSEEVENTF_HWHEEL`).
   - System shortcuts: Task View (Win+Tab), App Switcher (Alt+Tab), Virtual Desktop switching (Win+Ctrl+Left/Right), Browser Back/Forward, and Snipping Tool (Win+Shift+S).

2. **Smart Clickable Probe (`clickable_probe.py`)**:
   - Inspects whether UI elements under the cursor are interactive so dwell hover clicks never fire accidentally on plain text.
   - Uses Windows UI Automation (UIA) COM interfaces (`IUIAutomation::ElementFromPoint`) to verify `ControlType` (Button, Hyperlink, MenuItem, TabItem, Edit, CheckBox, RadioButton, SplitButton) and patterns (`InvokePattern`, `TogglePattern`, `SelectionItemPattern`).
   - Climbs up to 3 ancestors in the control hierarchy (e.g. text or icons inside buttons).
   - High-speed fallback: checks system pointer shape via `GetCursorInfo` for `IDC_HAND` (pointing hand).
   - Runs off-thread so probe queries never stall the 120Hz tracking loop.

3. **Global Stem Key Detection (`stem_listener.py`)**:
   - Intercepts AirPods stem squeezes via a low-level keyboard hook (`WH_KEYBOARD_LL`):
     - **1 press** (Play/Pause `VK_MEDIA_PLAY_PAUSE` / 0xB3) → Left click
     - **2 presses** (Next Track `VK_MEDIA_NEXT_TRACK` / 0xB0) → Right click
     - **3 presses** (Prev Track `VK_MEDIA_PREV_TRACK` / 0xB1) → Toggle Scroll Mode
   - Features built-in debouncing and optional event swallowing so media playback in external apps is not interrupted.

4. **Transparent Click-Through HUD Overlay (`overlay.py`)**:
   - Always-on-top, click-through layered window (`WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`).
   - Never steals keyboard focus or mouse clicks from active applications.
   - Renders a circular dwell progress ring around the cursor as hover time elapses, filling from 20% to 100% before firing.
   - Click feedback ripple animation.
   - Modern HUD toast notification pill badges for mode changes and recentering.
   - Double-buffered Win32 GDI rendering for 0% CPU overhead.

5. **Flexible Dual Sensor Ingestion (`sensor_receiver.py`)**:
   - **OpenTrack UDP Receiver (Port 4242)**: Standard 48-byte binary format (6 doubles: X, Y, Z in cm; Yaw, Pitch, Roll in degrees). Compatible with `aap-head-tracker` (MagicAAP), `MousePods`, SmoothTrack, FreePIE, or network bridge.
   - **Synthetic Simulation Generator**: Realistic simulation stream generating figure-8 motion, nods, shakes, and dwell rests for testing without physical AirPods connected.
   - **Bluetooth AirPods Helper**: Queries Windows registry (`BTHPORT`) to detect paired AirPods devices.

6. **120Hz AppController (`app_controller.py`)**:
   - Complete pipeline matching macOS AirCursor: `Sensor Stream -> MotionDifferentiator -> PointerMapper -> PointerSmoother -> GestureDetector -> DwellDetector -> ClickableProbe -> EventSynthesizer`.
   - **Cursor Rollback**: When a nod or shake is detected, rolls the cursor back to where the user was looking 60ms *before* the gesture began, ensuring laser-accurate clicks.
   - Pointer and Scroll tracking modes.

7. **Modern Dark Control Center GUI & System Tray (`control_center.py`, `tray_icon.py`, `autostart.py`)**:
   - Sleek Tkinter/ttk dark-themed desktop dashboard:
     - Header AirPods Pro status badge (`AirPods Pro 41424f2041e4 Connected`).
     - Big Master Start / Pause Toggle Button.
     - Real-time telemetry meters (Pitch, Yaw, Roll, FPS, Mode).
     - Live tuning sliders: Pointer Sensitivity (0.4x - 2.5x), Dwell Duration (0.5s - 2.0s), Nod Amplitude (3° - 12°).
     - Accessibility checkboxes: Hover Dwell Click, Nod to Click, Shake to Pause, Start with Windows.
     - Action buttons: Recenter Cursor (`Ctrl+Alt+C`), Save Settings.
     - On close (X button), minimizes silently to System Tray with balloon notification.
   - Global Hotkeys:
     - `Ctrl + Alt + T`: Pause / Resume Tracking
     - `Ctrl + Alt + S`: Toggle Scroll / Pointer Mode
     - `Ctrl + Alt + C`: Recenter Cursor
     - `Ctrl + Alt + D`: Toggle Left Mouse Drag Lock
     - `Ctrl + C`: Exit Application
   - Windows notification area tray icon with context menu to restore Control Center or toggle tracking.
   - Windows boot autostart manager (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AirCursor`).
   - One-click Installer (`Install-AirCursor.bat`) & Uninstaller (`Uninstall-AirCursor.bat`) creating Start Menu and Desktop shortcuts.

---

## Installation & Requirements

AirCursor for Windows is built with pure Python and standard Win32 APIs via `ctypes`. No compilation or C++ build tools required.

- Windows 10 or Windows 11 (64-bit)
- Python 3.10+ (Standard Library only: `ctypes`, `socket`, `threading`, `time`, `winreg`, `struct`)

---

## Quick Start

### 1. Test in Simulation Mode (No AirPods Required)
Run AirCursor with the built-in synthetic telemetry generator:
```powershell
python windows\main.py --synthetic
```

### 2. View Paired AirPods & Setup Guide
```powershell
python windows\main.py --setup-info
```

### 3. Run with Physical AirPods via OpenTrack UDP (Default Port 4242)
```powershell
python windows\main.py
```

### 4. Enable System Tray Icon
```powershell
python windows\main.py --synthetic --tray
```

### 5. Run Self-Test Suite
```powershell
python windows\test_windows_app.py
```

---

## CLI Options

| Option | Description |
|---|---|
| `--synthetic` | Run using the synthetic head motion generator (ideal for testing). |
| `--port <int>` | UDP port to listen for OpenTrack telemetry (default: `4242`). |
| `--bind <ip>` | Network address to bind UDP receiver (default: `0.0.0.0`). |
| `--no-overlay` | Run headless without the HUD overlay window. |
| `--no-stem` | Disable the global media key stem hook. |
| `--tray` | Enable Windows system tray icon in the notification area. |
| `--sensitivity <float>` | Override pointer sensitivity multiplier (default: `1.0`). |
| `--smoothing <float>` | Override pointer smoothing factor (`0.0` to `0.95`, default: `0.55`). |
| `--dwell-duration <float>` | Override hover click duration in seconds (default: `0.8`). |
| `--nod-amplitude <float>` | Override nod gesture angle in degrees (default: `5.5`). |
| `--config <path>` | Path to custom JSON configuration file. |
| `--setup-info` | Display AirPods pairing and Bluetooth setup guide, then exit. |
| `--version` | Display version information. |

---

## AirPods Setup on Windows

1. **Bluetooth Pairing**:
   - Place both AirPods in their charging case with the lid open.
   - Press and hold the button on the back of the case until the status LED pulses white.
   - In Windows, go to **Settings > Bluetooth & devices > Add device > Bluetooth** and pair your AirPods.
2. **Audio Routing**:
   - Press `Win + Ctrl + V` or open Windows Sound settings and set AirPods as your **Default Audio Output**.
3. **Head Tracking Telemetry Stream**:
   - Run `aap-head-tracker` (MagicAAP driver on Windows) to capture AirPods spatial audio IMU packets over Bluetooth and forward them to `127.0.0.1:4242`.
   - Alternatively, connect a phone or Raspberry Pi running an OpenTrack UDP forwarder.
