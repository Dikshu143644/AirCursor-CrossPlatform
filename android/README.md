# AirCursor Android Companion & Driver Package

> Native Android companion application and accessibility driver for AirCursor.
> Provides full hands-free cursor navigation, touch simulation without root,
> bidirectional WebSocket streaming, automatic UDP discovery, and AirPods Bluetooth LE/L2CAP motion capture.

---

## 📋 Table of Contents
1. [Architecture & System Flow](#-architecture--system-flow)
2. [Prerequisites & Environment](#-prerequisites--environment)
3. [Building the Android Package (Gradle & APK Assembly)](#-building-the-android-package-gradle--apk-assembly)
4. [Permissions Configuration Guide](#-permissions-configuration-guide)
   - [Accessibility Service (Touch Simulation)](#1-accessibility-service-touch-simulation-without-root)
   - [System Overlay (Dwell Ring Display)](#2-system-alert-window-display-over-other-apps)
   - [Bluetooth LE Scan & Connect (AirPods IMU)](#3-bluetooth-low-energy-ble-scan--connect)
   - [Wi-Fi Multicast & Local Network (UDP Discovery)](#4-local-network--wi-fi-multicast-for-udp-discovery)
5. [Automatic UDP Discovery & WebSocket Architecture](#-automatic-udp-discovery--websocket-architecture)
6. [AirPods Bluetooth L2CAP & Fallback IMU](#-airpods-bluetooth-l2cap--fallback-imu)
7. [Automated Testing & Verification](#-automated-testing--verification)

---

## 🏛️ Architecture & System Flow

```
                      ┌────────────────────────────────────────┐
                      │        AirCursor Desktop Server        │
                      │  REST / WebSocket (8765) | UDP (4242)  │
                      └───────────────────▲────────────────────┘
                                          │
                         UDP Discovery (4242) & WebSocket (8765/ws)
                                          │
┌─────────────────────────────────────────▼────────────────────────────────────────┐
│                        Android Companion Application                             │
│                                                                                  │
│  ┌────────────────────────┐  ┌───────────────────────┐  ┌─────────────────────┐  │
│  │   AirCursorA11yService │  │  AirPodsMotionService │  │ DwellOverlayService │  │
│  │  --------------------  │  │  -------------------- │  │ ------------------- │  │
│  │  • dispatchGesture()   │  │  • L2CAP PSM 0x1001   │  │ • Hardware Canvas   │  │
│  │  • UDP Port 4242 Scan  │  │  • MTU 2582 Decoder   │  │ • 72dp Ring Overlay │  │
│  │  • WebSocket /ws Client│  │  • Fallback Phone IMU │  │ • Click Ripple      │  │
│  │  • A11y Tree Probing   │  │  • Gesture Engine     │  │ • Dwell Countdown   │  │
│  └────────────────────────┘  └───────────────────────┘  └─────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │                        StemReceiver (Media Buttons)                        │  │
│  │           Single Squeeze = Tap | Double = Right-Click | Triple = Scroll    │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🧰 Prerequisites & Environment

- **Android SDK:** Compile SDK 34 (Android 14), Minimum SDK 26 (Android 8.0 Oreo).
- **JDK:** Java 17 or Java 21 LTS (`export JAVA_HOME=/path/to/jdk-17`).
- **Build Tools:** Android Gradle Plugin 8.5+, Gradle 8.7+.
- **Android Device:** Physical device with Bluetooth 5.0+ and Wi-Fi enabled.

---

## 🔨 Building the Android Package (Gradle & APK Assembly)

### Option 1: Command Line Build (Gradle Wrapper)

Navigate to the android project root:
```bash
cd c:\Users\omkar\TV\AirCursor_CrossPlatform\android
```

1. **Assemble Debug APK:**
   ```bash
   ./gradlew assembleDebug
   # On Windows:
   gradlew.bat assembleDebug
   ```
   **Output APK Location:**
   ```
   app/build/outputs/apk/debug/app-debug.apk
   ```

2. **Assemble Release APK:**
   ```bash
   ./gradlew assembleRelease
   ```
   **Output APK Location:**
   ```
   app/build/outputs/apk/release/app-release-unsigned.apk
   ```

3. **Install Directly to Connected Device via ADB:**
   ```bash
   adb install -r -d app/build/outputs/apk/debug/app-debug.apk
   ```

---

### Option 2: Android Studio Build & Run

1. Open **Android Studio** (Hedgehog / Iguana / Ladybug or newer).
2. Click **Open** and select the folder `c:\Users\omkar\TV\AirCursor_CrossPlatform\android`.
3. Allow Gradle to sync dependencies (`androidx.core`, `okhttp3`, `lifecycle-service`, `material`).
4. Select `app` in the run configuration dropdown.
5. Connect your device via USB or Wi-Fi ADB (`adb devices`).
6. Press **Run** (`Shift + F10`) or click the green Play icon.

---

## 🔐 Permissions Configuration Guide

AirCursor requires specific permissions to perform rootless cursor control, render overlays, scan Bluetooth LE sensors, and communicate across the local network.

### 1. Accessibility Service (Touch Simulation without Root)
Allows AirCursor to dispatch clicks, double-taps, drags, and scrolls using `dispatchGesture(Path)`.

- **GUI Setup:**
  1. Open phone **Settings**.
  2. Navigate to **Accessibility** $\rightarrow$ **Installed Apps** (or **Downloaded Services**).
  3. Locate **AirCursor** and switch it **ON**.
  4. Confirm the system security prompt.

- **Fast ADB Developer Setup:**
  ```bash
  adb shell settings put secure enabled_accessibility_services io.github.aircursor/.AirCursorAccessibilityService
  adb shell settings put secure accessibility_enabled 1
  ```

---

### 2. System Alert Window (Display Over Other Apps)
Required by `DwellOverlayService` to draw the 72dp floating touch indicator, circular dwell progress ring, and touch pulse ripple over other apps.

- **GUI Setup:**
  1. Go to **Settings** $\rightarrow$ **Apps** $\rightarrow$ **Special App Access**.
  2. Tap **Display over other apps** (or **Appear on top**).
  3. Select **AirCursor** and toggle **Allow display over other apps**.

- **Fast ADB Developer Setup:**
  ```bash
  adb shell appops set io.github.aircursor SYSTEM_ALERT_WINDOW allow
  ```

---

### 3. Bluetooth Low Energy (BLE) Scan & Connect
Required to discover paired AirPods, connect to L2CAP PSM `0x1001`, and read motion packets.

- **Permissions in AndroidManifest.xml:**
  ```xml
  <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />
  <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" />
  <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
  <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
  ```

- **Runtime Prompt:**
  When launched, `MainActivity` prompts for `BLUETOOTH_CONNECT` and `BLUETOOTH_SCAN`. Tap **Allow**.

- **Fast ADB Developer Setup:**
  ```bash
  adb shell pm grant io.github.aircursor android.permission.BLUETOOTH_CONNECT
  adb shell pm grant io.github.aircursor android.permission.BLUETOOTH_SCAN
  adb shell pm grant io.github.aircursor android.permission.ACCESS_FINE_LOCATION
  ```

---

### 4. Local Network & Wi-Fi Multicast (for UDP Discovery)
Allows AirCursor to broadcast and receive UDP discovery packets on port 4242 across the local Wi-Fi subnet.

- **Permissions in AndroidManifest.xml:**
  ```xml
  <uses-permission android:name="android.permission.INTERNET" />
  <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
  <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
  <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />
  ```
- Handled automatically; the app acquires `WifiManager.MulticastLock` on service startup.

---

## 🌐 Automatic UDP Discovery & WebSocket Architecture

### 1. Automatic UDP Discovery (Port 4242)
When `AirCursorAccessibilityService` starts:
1. It sends a UDP broadcast probe to `255.255.255.255:4242` and all local interface broadcast addresses:
   ```json
   {
     "type": "discover",
     "service": "aircursor_android",
     "client": "accessibility_companion",
     "port": 4242
   }
   ```
2. The AirCursor server (running on desktop or Docker) listens on `0.0.0.0:4242/udp` and responds:
   ```json
   {
     "service": "aircursor",
     "status": "ok",
     "http_port": 8765,
     "udp_port": 4242,
     "version": "1.0.5"
   }
   ```
3. The Android client extracts the server IP address and HTTP port (`8765`).

### 2. Full WebSocket Client (`ws://<host>:8765/ws`)
1. Once discovered, the client opens a WebSocket connection to `ws://<host>:8765/ws`.
2. **Auto-Reconnect:** If connection drops, exponential backoff retries every 3 seconds.
3. **Incoming Remote Control Commands:**
   | JSON Command Payload | Action Executed on Android |
   | :--- | :--- |
   | `{"action": "click", "x": 500, "y": 800}` | Dispatches rootless single tap at $(500, 800)$ |
   | `{"action": "double_click", "x": 500, "y": 800}` | Dispatches double-click at $(500, 800)$ |
   | `{"action": "move", "dx": 10, "dy": -5}` | Moves virtual pointer relatively by $(\Delta x, \Delta y)$ |
   | `{"action": "scroll", "dx": 0, "dy": 150}` | Dispatches rootless scroll swipe gesture |
   | `{"action": "recenter"}` | Centers pointer to screen midpoint |
   | `{"action": "back"}` | Executes global Android BACK navigation |
   | `{"action": "home"}` | Executes global Android HOME navigation |
   | `{"action": "recents"}` | Opens Android Overview / Recents screen |

4. **Outgoing Telemetry Stream:**
   The Android companion streams attitude (yaw, pitch, roll) and touch events back to the server:
   ```json
   {
     "type": "telemetry",
     "yaw": -12.4,
     "pitch": 4.1,
     "roll": 0.8
   }
   ```

---

## 🎧 AirPods Bluetooth L2CAP & Fallback IMU

1. **Direct L2CAP Connection:**
   - Targets L2CAP PSM `0x1001` with MTU **2582 bytes** (`createInsecureL2capChannel`).
   - Sends the Apple RemoteHID handshake on RTBuddy channel `0x800` (AirPods 3) or `SensorDataWX` on `0x100000` (AirPods Pro / 4).
   - Decodes 58-byte motion block into normalized Q15 quaternions.
2. **Automatic Phone IMU Fallback:**
   - If no AirPods are connected or if an OEM ROM restricts custom L2CAP sockets, `AirPodsMotionService` automatically switches to `Sensor.TYPE_ROTATION_VECTOR` via `SensorManager`.
   - Rotation matrix is converted to Euler angles (yaw, pitch, roll) at up to $100\text{ Hz}$.

---

## 🧪 Automated Testing & Verification

Run the native Kotlin test suite:
```bash
./gradlew test
```
**Test Coverage:**
- `testVec2Operations`: Vector distance, addition, length.
- `testAngleMathWrapping`: Modulo boundary wrap $(-180^\circ, 180^\circ]$.
- `testMotionDifferentiator`: Angular rate calculation and gap rejection.
- `testPointerMapperDeadzone`: Tremor filter verification.
- `testNodDetection`: Down-and-up head nod gesture detection.
- `testDwellDetector`: Spatial anchoring, reveal fraction, and dwell trigger.
- `testActionMapDefaults`: Trigger-to-action bindings.
