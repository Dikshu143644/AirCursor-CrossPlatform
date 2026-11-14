# AirCursor for Linux

> Hands-free head-tracking mouse for Linux powered by Apple AirPods (AirPods Pro, AirPods Max, AirPods 3rd gen+, Beats Fit Pro).

AirCursor enables full hands-free cursor navigation, click gestures (nodding, shaking, head tilts), and smart hover clicking directly on Linux desktop environments (both **Wayland** and **X11**).

---

## 🌟 Key Architecture

1. **BlueZ L2CAP Driver with MTU 2582 (`airpods_bluez.py`)**
   - By default, Linux sets the Bluetooth L2CAP receive MTU to 672 bytes. Under this limit, AirPods drop or hide their high-bandwidth sensor service descriptors (such as the 833-byte `devmotion6` descriptor).
   - AirCursor forces the L2CAP receive MTU (`imtu`) to **2,582 bytes** (the iOS/macOS standard) on L2CAP PSM `0x1001` before connecting.
   - Handshakes with both Apple RemoteHID (AirPods 3 on channel `0x800`) and SensorDataWX (AirPods Pro / 4 on channel `0x100000`).
   - Decodes the 58-byte motion packet containing Q15 fixed-point orientation quaternions into yaw, pitch, and roll in real-time (~100 Hz).

2. **Universal Virtual Input Synthesizer (`event_synthesizer.py`)**
   - Emits virtual mouse movements (`REL_X`, `REL_Y`), button clicks (`BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE`), scroll wheels (`REL_WHEEL`, `REL_HWHEEL`), and keyboard shortcuts via `/dev/uinput`.
   - Native integration with `python-evdev` with an automated fallback to raw kernel ioctls.
   - Compatible with **Wayland** (GNOME Mutter, KDE KWin, Sway/wlroots) and **X11** through `libinput`.

3. **Smart Hover Click Probe via AT-SPI (`clickable_probe.py`)**
   - Queries the Linux desktop accessibility bus (`org.a11y.Bus` / `pyatspi`) to probe elements under the pointer.
   - Rest on buttons, links, tabs, and input fields to automatically trigger a dwell click; resting on paragraphs of text you are reading will never click.

4. **Transparent Click-Through Overlay (`overlay.py`)**
   - Lightweight GTK 3 & Cairo overlay displaying a circular dwell countdown ring around the pointer.
   - Configured with an empty input shape region so 100% of mouse and touch events pass directly through to background applications.
   - Renders animated expanding click ripple ripples.

---

## 🚀 Installation & System Setup

### 1. Prerequisites & Dependencies

On Debian / Ubuntu / Linux Mint:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-evdev python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-pyatspi bluetooth bluez
```

On Fedora / RHEL:
```bash
sudo dnf install -y python3 python3-pip python3-evdev python3-gobject gtk3 pyatspi bluez
```

On Arch Linux / Manjaro:
```bash
sudo pacman -S python python-pip python-evdev python-gobject gtk3 python-pyatspi bluez bluez-utils
```

---

### 2. Configure `/dev/uinput` Permissions (No Root Required)

To allow AirCursor to synthesize mouse and keyboard events without running as `root`, add a udev rule:

```bash
# 1. Create the uinput udev rule
echo 'KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/99-uinput.rules

# 2. Add your user to the input group
sudo usermod -aG input $USER

# 3. Reload udev rules and load uinput module
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo modprobe uinput
```
*(Log out and log back in for group membership to take effect).*

---

### 3. Bluetooth L2CAP Socket Permissions

Linux restricts raw L2CAP socket creation to users with the `CAP_NET_RAW` capability. You can either:

**Option A (Recommended: grant capability to Python binary):**
```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f $(which python3))
```

**Option B:** Run the daemon with `sudo`:
```bash
sudo python3 main_linux.py
```

---

### 4. Enable Desktop Accessibility (AT-SPI)

For Smart Dwell click to detect buttons and hyperlinks:

**GNOME / Cinnamon / MATE:**
```bash
gsettings set org.gnome.desktop.interface toolkit-accessibility true
```

**KDE Plasma:**
Enable Accessibility under *System Settings → Accessibility → Support*.

---

## 🎧 Pairing Your AirPods

1. Open your Linux Bluetooth settings (or run `bluetoothctl`).
2. Put your AirPods into pairing mode (hold the button on the back of the charging case until the LED flashes white).
3. Pair and connect to your AirPods.
4. Verify audio output is routed to your AirPods (AirPods require active audio connection to power their motion sensors).

---

## 🎮 Usage

### 1. Scan for Paired AirPods
```bash
python3 main_linux.py --scan
```
Output:
```text
[*] Scanning paired AirPods / Beats devices...
[+] Found 1 device(s):
    - Omkar's AirPods Pro (9C:FC:01:8A:2B:3C)
```

### 2. Start the AirCursor Daemon
```bash
# Auto-connects to the first paired AirPods
python3 main_linux.py

# Or specify your AirPods MAC explicitly
python3 main_linux.py --address 9C:FC:01:8A:2B:3C
```

### 3. Command Line Options

| Flag | Description | Default |
| :--- | :--- | :--- |
| `--address`, `-a` | Bluetooth MAC address of AirPods | Auto-detected |
| `--scan`, `-s` | Scan for paired devices and exit | - |
| `--sensitivity` | Pointer speed multiplier | `1.0` |
| `--deadzone` | Tremor filter deadzone (degrees/s) | `3.0` |
| `--dwell-duration`| Hover duration before dwell click (seconds) | `0.8` |
| `--no-dwell` | Disable hover clicking entirely | Off |
| `--no-smart-dwell`| Dwell click anywhere without AT-SPI probing | Off |
| `--no-overlay` | Disable GTK transparent dwell ring window | Off |
| `--no-atspi` | Disable AT-SPI accessibility inspection | Off |
| `--config`, `-c` | Load customized JSON settings file | None |

---

## 🕹️ Gestures & Controls

| Action / Gesture | Physical Head Motion | Default Trigger |
| :--- | :--- | :--- |
| **Move Pointer** | Smooth head turn (pitch / yaw) | Relative velocity mapping |
| **Left Click** | Quick down-and-up head nod | Head Nod |
| **Pause / Resume** | Rapid left-right-left-right shake | Head Shake |
| **Hover Click** | Rest cursor on a button or link for 0.8s | Dwell Detector |
| **Scroll Mode** | Toggle via custom trigger / stem press | Head pitch scrolls vertically |
| **Drag Lock** | Hold button down across movements | Toggle Drag action |

---

## 🧪 Running Unit Tests

The test suite validates the math engine, angular differentiators, gesture detectors, binary packet parsers, and event synthesis:

```bash
python3 test_linux.py
```
Output:
```text
..........
----------------------------------------------------------------------
Ran 10 tests in 0.001s

OK
```

---

## 🔧 Troubleshooting

1. **`PermissionError: [Errno 13] Permission denied: '/dev/uinput'`**
   - Ensure the udev rule was created and your user belongs to the `input` group:
     `sudo usermod -aG input $USER` (then log out and log back in).
   - Verify `uinput` module is loaded: `sudo modprobe uinput`.

2. **`OSError: [Errno 1] Operation not permitted (L2CAP socket)`**
   - Grant network raw capability to Python:
     `sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f $(which python3))`
   - Or run the script with `sudo python3 main_linux.py`.

3. **AirPods connect but send no motion samples**
   - AirPods power down their IMU when no audio session is open. Play audio or start a media player in the background (e.g., Spotify, YouTube, or VLC).
   - Ensure the Bluetooth receive MTU was successfully configured to 2582 (AirCursor handles this automatically).
