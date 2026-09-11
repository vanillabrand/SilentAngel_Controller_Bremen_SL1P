# Silent Angel Bremen SL1P — Control Suite & Specification

Welcome to the **Bremen Studio** project repository for controlling the **Silent Angel Bremen SL1 / SL1 Plus (SL1P)** streamer and DAC over your local area network (LAN) from any laptop (Windows, macOS, Linux) or mobile phone (iOS, Android).

---

## 1. Project Contents

* [`SILENT_ANGEL_BREMEN_SL1P_SPECIFICATION.md`](file:///c:/Users/bruce/Documents/Code/SilentAngel/SILENT_ANGEL_BREMEN_SL1P_SPECIFICATION.md): The complete engineering specification document covering hardware architecture, controllable parameters, VitOS analysis, open-source library survey, and UI/UX design.
* [`bremen_controller.py`](file:///c:/Users/bruce/Documents/Code/SilentAngel/bremen_controller.py): Standalone local controller bridge with automated port clearing, multi-protocol device discovery, official vector SVGs, and an embedded audiophile web server.
* [`start_controller.bat`](file:///c:/Users/bruce/Documents/Code/SilentAngel/start_controller.bat): 1-click Windows batch launcher.
* [`start_controller.ps1`](file:///c:/Users/bruce/Documents/Code/SilentAngel/start_controller.ps1): 1-click PowerShell launcher.

---

## 2. Quick Start: Controlling your Bremen SL1P

### Option A: 1-Click Launch (Recommended)
Simply double-click **`start_controller.bat`** (or right-click `start_controller.ps1` and choose *Run with PowerShell*).
The script automatically:
1. Clears any zombie controller processes from the port.
2. Starts the server on clean port **8090** (avoiding system service conflicts like EDB Postgres on 8080).
3. Automatically launches your default web browser directly to the dashboard.

### Option B: Terminal Launch
```powershell
python bremen_controller.py
```
* **Laptop Browser:** `http://localhost:8090`
* **Mobile Phone on LAN:** `http://<your-laptop-ip>:8090` (e.g. `http://192.168.1.188:8090`)

---

## 3. Features & Enhancements

### 🔍 Multi-Method Device Discovery
If you do not know the IP address of your streamer:
1. Open the web interface and click **"🔍 Discover Devices"** (or **"Start Network Scan"**).
2. The controller conducts a multi-tier network scan combining:
   * **SSDP Multicast Discovery** (`AVTransport:1`, `MediaRenderer:1`, `OpenHome`)
   * **Local Subnet & ARP Table Sweep** (probing VitOS HTTP, MPD port 6600, UPnP ports 49152+)
3. When your Silent Angel Bremen SL1P is identified, it is highlighted with a gold **"SILENT ANGEL"** badge. Click **"Connect"** to pair instantly.
4. If preferred, you can also enter your device's static IP directly into the manual override field.

### 🎨 Official Audiophile Vector SVGs
The user interface incorporates authentic, crisp vector SVGs for all major protocols and industry standards:
* **Streaming Protocols:** Official UPnP, DLNA Certified, Apple AirPlay 2, Spotify Connect, Tidal Connect, Roon Ready, and Qobuz logos.
* **Audio Format Badges:** Japan Audio Society **Hi-Res Audio** gold emblem, **DSD Direct Stream Digital**, and **MQA Studio Master**.
* **Chassis Emblem:** Authentic Silent Angel wing emblem matching the physical Bremen SL1P front plate.

### 🎛️ Full Transport & Attenuation
* **Playback Controls:** Play, Pause, Stop, Seek, Next Track, Previous Track.
* **Smooth Scrub Bar:** Click anywhere on the progress bar to seek accurately (`HH:MM:SS`).
* **Desktop Hotkeys:**
  * `Spacebar`: Play / Pause toggle
  * `Ctrl` / `Cmd` + `Right Arrow`: Next track
  * `Ctrl` / `Cmd` + `Left Arrow`: Previous track
  * `Up Arrow` / `Down Arrow`: Volume up / down by 2%
  * `M`: Mute / Unmute toggle
