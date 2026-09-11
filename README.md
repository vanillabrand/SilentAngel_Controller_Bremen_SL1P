# Silent Angel Bremen SL1P — Control Suite & Specification

Welcome to the **Bremen Studio** project repository for controlling the **Silent Angel Bremen SL1 / SL1 Plus (SL1P)** streamer and DAC over your local area network (LAN) from any laptop (Windows, macOS, Linux) or mobile phone (iOS, Android).

---

## 1. Project Contents

* [`SILENT_ANGEL_BREMEN_SL1P_SPECIFICATION.md`](file:///c:/Users/bruce/Documents/Code/SilentAngel/SILENT_ANGEL_BREMEN_SL1P_SPECIFICATION.md): The complete, rigorous engineering specification document covering hardware architecture, controllable parameters, VitOS analysis, open-source library survey, and UI/UX design.
* [`bremen_controller.py`](file:///c:/Users/bruce/Documents/Code/SilentAngel/bremen_controller.py): A lightweight, zero-dependency Python-based local controller bridge and embedded audiophile web server.

---

## 2. Quick Start: Controlling your Bremen SL1P Right Now

You can launch and use the control centre immediately with zero installation required:

### 1. Launch the Controller Server on your Laptop
Open PowerShell or your command prompt in this directory and execute:
```powershell
python bremen_controller.py
```
By default, the server runs on port **8080**:
* Access from your **Laptop Browser**: Open `http://localhost:8080`
* Access from your **Mobile Phone**: Open `http://<your-laptop-ip>:8080` (e.g. `http://192.168.1.188:8080`)

### 2. Connect to your Bremen SL1P
1. In the top-left or sidebar of the interface, click **"Change Device"** or **"Device Discovery"**.
2. Click **"Scan Network"** to automatically discover the Bremen SL1P via SSDP multicast, **or** enter its IP address directly (e.g. `192.168.1.X`).
3. Click **Connect**. Your configuration will be saved automatically in `bremen_config.json` so you never have to re-enter it.

### 3. Controllable Features via the Web Interface
* **Transport Controls:** Play, Pause, Stop, Seek along the track timeline, Next Track, Previous Track.
* **Volume Control:** Master volume slider, Mute/Unmute toggle.
* **Live Scrubbing:** Interactive timeline with real-time elapsed and total duration tracking.
* **Desktop Keyboard Shortcuts:**
  * `Spacebar`: Play / Pause toggle
  * `Ctrl` / `Cmd` + `Right Arrow`: Next track
  * `Ctrl` / `Cmd` + `Left Arrow`: Previous track
  * `Up Arrow` / `Down Arrow`: Volume up / down by 2%
  * `M`: Mute toggle
* **Hi-Res Audio Telemetry:** Live format indicator, sample rate, bit depth, output route, and clock status.

---

## 3. Key Advantages over the VitOS Orbit App

1. **Universal Access:** Fully functional on Windows, macOS, and Linux laptop browsers without requiring an emulator.
2. **Mobile Responsive PWA:** Perfectly adapts to mobile phone screens without app store restrictions or battery-saving connection drops.
3. **Zero-Drop Discovery:** Automatically remembers the device's IP address and reconnects immediately.
4. **Desktop Ergonomics:** Full support for spacebar, arrow keys, and keyboard media buttons.
5. **High-End Audiophile Styling:** Matches the brushed aluminium and luxury finish of the Silent Angel chassis.
