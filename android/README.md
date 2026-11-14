# AirCursor for Android

> Hands-free head-tracking mouse & touch accessibility service for Android powered by Apple AirPods and device IMU sensors.

AirCursor allows users to navigate Android completely hands-free using head rotation, physical earbud stem squeezes, and intuitive head gestures (nodding, shaking, tilting), requiring **no root access**.

---

## 🏗️ Architecture Overview

The Android package is designed with clean modularity:

| Component | Role | Android API / Technique |
| :--- | :--- | :--- |
| **`AirCursorAccessibilityService.kt`** | Pointer movement & touch synthesis | `AccessibilityService.dispatchGesture()` with `Path` (taps, drags, double-clicks without root) |
| **`AirPodsMotionService.kt`** | Sensor streaming & attitude decoding | `BluetoothSocket` over L2CAP (PSM `0x1001`, MTU `2582`) with fallback to `Sensor.TYPE_ROTATION_VECTOR` |
| **`DwellOverlayService.kt`** | Touch pointer & dwell progress ring | `WindowManager` with `TYPE_APPLICATION_OVERLAY` & hardware-accelerated Cairo/Canvas |
| **`StemReceiver.kt`** | AirPods stem presses | BroadcastReceiver for `ACTION_MEDIA_BUTTON` (1-press = Left Click, 2-press = Right Click, 3-press = Scroll) |
| **`AirCursorCore.kt`** | Mathematical & gesture engine | Exponential velocity smoothing, shape-based nod/shake/tilt detection, dwell tracking |
| **`MainActivity.kt`** | Setup & live calibration | Material 3 UI with permissions checklist, sensitivity sliders, and live orientation telemetry |

---

## 🛠️ Build & Installation

### Option 1: Open in Android Studio
1. Launch **Android Studio (Giraffe / Hedgehog / Iguana / Ladybug+)**.
2. Select **Open** and choose `c:\Users\omkar\TV\AirCursor_CrossPlatform\android`.
3. Let Gradle sync project dependencies.
4. Connect an Android device (Android 8.0 / API 26 or higher, Android 14+ recommended) with USB Debugging enabled.
5. Click **Run 'app'** (`Shift + F10`).

### Option 2: Build with Gradle via Command Line
```bash
cd c:\Users\omkar\TV\AirCursor_CrossPlatform\android

# Build Debug APK
./gradlew assembleDebug

# Install to connected device via ADB
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

## 📱 First-Time Permissions Checklist

AirCursor requires three permissions, each accessible directly from the app's setup screen:

1. **Accessibility Service (`Settings → Accessibility → AirCursor`)**
   - Enables `dispatchGesture` to simulate screen taps, clicks, and navigation without needing root or USB debugging.
2. **Display Over Other Apps (`SYSTEM_ALERT_WINDOW`)**
   - Allows AirCursor to display the floating touch cursor dot, circular dwell progress ring, and click pulse animations over all running apps.
3. **Bluetooth Connect (`BLUETOOTH_CONNECT`)**
   - Grants permission to discover and connect to paired AirPods over Bluetooth L2CAP.

---

## 🎧 Pairing & Connecting AirPods

1. In Android **Settings → Connected Devices → Pair new device**, pair your AirPods.
2. Open AirCursor and toggle the master switch **Start AirCursor**.
3. AirCursor opens an L2CAP channel on PSM `0x1001` with MTU 2582:
   - **AirPods 3**: Activates the `devmotion6` virtual sensor channel (`0x800`).
   - **AirPods Pro / 4**: Activates the `SensorDataWX` streaming protocol (`0x100000`).
4. **Automatic IMU Fallback**: If AirPods are disconnected or if an OEM ROM restricts custom Bluetooth L2CAP sockets, AirCursor automatically falls back to the phone's internal rotation vector sensor (`Sensor.TYPE_ROTATION_VECTOR`), ensuring 100% functionality at all times!

---

## 🕹️ Gestures & Controls

| Action / Gesture | Physical Motion | Result |
| :--- | :--- | :--- |
| **Move Pointer** | Head rotation (pitch / yaw) | Moves floating cursor across screen |
| **Tap / Left Click** | Quick down-and-up head nod | Restores pre-nod coordinates and simulates tap |
| **Pause / Resume** | Rapid left-right-left-right shake | Pauses/resumes cursor tracking |
| **Hover / Dwell Click** | Rest cursor over a button for 0.8s | Fills dwell ring and dispatches click |
| **Stem Single Press** | Squeeze AirPods stem once | Dispatches tap |
| **Stem Double Press** | Squeeze AirPods stem twice | Dispatches right-click / context action |
| **Stem Triple Press** | Squeeze AirPods stem three times | Toggles scroll mode (head movement scrolls content) |
| **Recenter** | Tap "Recenter" in app | Resets head neutral zero pose |

---

## 🧪 Unit Tests

Run the Kotlin unit test suite validating vector math, angle wrapping, differentiators, gestures, and dwell detection:

```bash
cd c:\Users\omkar\TV\AirCursor_CrossPlatform\android
./gradlew test
```
Test results will be available at `app/build/reports/tests/testDebugUnitTest/index.html`.

---

## 🔋 Battery Optimization Note

To prevent Android from killing AirCursor's motion tracking in the background:
- Go to **Settings → Apps → AirCursor → Battery → Unrestricted**.
