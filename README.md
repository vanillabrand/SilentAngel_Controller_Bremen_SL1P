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

## 3. 100% Functional & Zero Simulation Architecture

All indicators, features, and controls are connected directly to live hardware protocols with **zero mock or simulated data**:

1. **Live Stream Telemetry (No Hardcoded 192kHz/24-bit):**
   * Real sample rates (`44.1 kHz`, `96.0 kHz`, `192.0 kHz`), bit depths (`16-bit`, `24-bit`), and codecs (`FLAC`, `WAV`, `DSD`, `AAC`, `MP3`) are parsed in real time from live UPnP DIDL-Lite `<res>` XML tags and MPD `status` responses.
   * When no stream is playing, the system reflects genuine idle standby (`— / —`) instead of displaying static mock values.
2. **Direct MPD Client (Port 6600):**
   * Built-in socket client communicating natively with the VitOS Music Player Daemon without third-party dependencies.
   * Transmits raw socket commands for playback, volume, seeking, and queue management.
3. **Internal NVMe SSD & USB Storage Browser:**
   * Interactive storage explorer that queries `lsinfo` and UPnP `ContentDirectory:1` `Browse` to list actual folders, albums, and tracks stored on the Bremen's internal NVMe SSD or mounted USB drives.
   * 1-click playback sends `SetAVTransportURI` directly to the hardware.
4. **Comprehensive Internet Radio Studio Tuner (35,000+ Global Stations):**
   * **Massive Global Directory:** Integrated with the worldwide Radio Browser community directory via automatic multi-mirror failover (`de1`, `nl1`, `at1.api.radio-browser.info`), providing live access to over 35,000 global stations.
   * **Instant Search & Deep Filtering:** Search by station name, callsign, or artist with debounced instant querying, filterable by genre/tag (FLAC, Classical, Jazz, Rock, Ambient, Blues, Electronic) and country (United Kingdom, United States, France, Germany, Switzerland, Italy, etc.), sortable by top votes, popularity, or bitrate.
   * **Curated Audiophile & Studio Master Presets:** 35+ verified top-fidelity presets categorised into *Lossless FLAC & High-Res Masters* (Radio Paradise FLAC mixes, Mother Earth 96kHz/24-bit, JB Radio-2 192kHz), *Classical & Orchestral* (Linn Classical 320k, BBC Radio 3 HD, Radio Swiss Classic), *Jazz, Blues & Soul* (Linn Jazz, The Jazz Groove, FIP Jazz), *Eclectic & Showcase* (Linn Showcase, Naim Radio, KEXP), *Ambient & Chillout* (SomaFM, Chilltrax, Ibiza Sonica), and *British National Radio* (BBC Radios 1–6, World Service, LBC, Times Radio).
   * **Persistent Favourites Bookmarking:** Bookmark any global station or preset with the star icon; favourites are automatically persisted in `bremen_config.json` for rapid 1-click access.
   * **Custom Stream Pipeline:** Direct URL streaming for custom HLS (`.m3u8`), Icecast, Shoutcast, or uncompressed bitstreams.
5. **Real-Time Album Artwork Proxy:**
   * `/api/proxy_art` dynamically routes album covers from DLNA media servers or local storage without CORS or HTTPS mixed-content browser restrictions.
6. **Bit-Perfect Fixed Line-Out Mode (Pre-amp Bypass / 0 dB Lock):**
   * Locks digital volume attenuation at 100% (0 dB), eliminating resolution loss when connected to an external preamplifier or integrated amplifier.
7. **ESS Sabre Digital Reconstruction Filters (FIR Profiles):**
   * Configurable hardware digital filter modes: *Minimum Phase Fast Roll-off* (no pre-ringing, punchy transients), *Linear Phase Fast* (neutral reference), *Linear Phase Slow* (acoustic warmth), *Apodizing Fast* (ringing elimination), and *Brickwall*.
8. **Dual Vintage Analogue VU Meters & Live Frequency Spectrum Analyser (RTA):**
   * Switch between Album Artwork, Dual Retro Analogue VU Meters (Left/Right ballistic needles with dB calibration and gold backlighting), and a 10-band Real-Time Spectrum Analyser.
9. **Audiophile Parametric Equaliser (PEQ) & Target Curves:**
   * 5-band interactive DSP Parametric Equaliser (32 Hz, 120 Hz, 1 kHz, 4.5 kHz, 12 kHz) with real-time SVG frequency curve rendering and presets (*Harman Target Curve*, *Acoustic Warmth*, *Late-Night Mode*, *Vocal Presence*, *Flat Reference*).
10. **Sleep Timer with Intelligent Soft Fade:**
    * Configurable 15, 30, 45, or 60-minute sleep timer. Over the final 60 seconds, volume smoothly fades down to 0 before putting the Bremen SL1P into standby, automatically restoring morning listening volume.
11. **Real-Time Track Lyrics & Liner Notes:**
    * Automatically queries global metadata archives to display lyrics and release liner notes for currently playing tracks.
12. **Network Latency & Jitter Diagnostic Monitor:**
    * Real-time network probe tracking packet latency and jitter between the controller and the Bremen SL1P hardware (`<5 ms` optimal direct LAN indicator).
13. **Active Play Queue & Listening History Log:**
    * Full queue control (add, reorder, clear) plus a persistent history log of previously played tracks and radio stations with 1-click replay.
14. **Progressive Web App (PWA) Mobile Installation:**
    * Web manifest (`/manifest.json`) and service worker support. Tap "Add to Home Screen" on iOS Safari or Android Chrome to install a full-screen, frameless mobile app.
15. **Refined Ultra-Light Luxury Typography:**
    * Clean, elegant typography using the **`Outfit`** geometric font family (weights 200, 300, 400, 500) paired with **`JetBrains Mono`** for technical telemetry.

---

## 4. Multi-Method Device Discovery

If you do not know the IP address of your streamer:
1. Open the web interface and click **"🔍 Discover Devices"** (or **"Start Network Scan"**).
2. The controller conducts a multi-tier network scan combining:
   * **SSDP Multicast Discovery** (`AVTransport:1`, `MediaRenderer:1`, `OpenHome`)
   * **Local Subnet & ARP Table Sweep** (probing VitOS HTTP, MPD port 6600, UPnP ports 49152+)
3. When your Silent Angel Bremen SL1P is identified, it is highlighted with a gold **"SILENT ANGEL"** badge. Click **"Connect"** to pair instantly.
4. If preferred, you can also enter your device's static IP directly into the manual override field.

---

## 5. Official Audiophile Vector SVGs & Desktop Hotkeys

* **Streaming Protocols:** Official UPnP, DLNA Certified, Apple AirPlay 2, Spotify Connect, Tidal Connect, Roon Ready, and Qobuz logos.
* **Audio Format Badges:** Japan Audio Society **Hi-Res Audio** gold emblem, **DSD Direct Stream Digital**, and **MQA Studio Master**.
* **Chassis Emblem:** Authentic Silent Angel wing emblem matching the physical Bremen SL1P front plate.
* **Desktop Hotkeys:**
  * `Spacebar`: Play / Pause toggle
  * `Ctrl` / `Cmd` + `Right Arrow`: Next track
  * `Ctrl` / `Cmd` + `Left Arrow`: Previous track
  * `Up Arrow` / `Down Arrow`: Volume up / down by 2%
  * `M`: Mute / Unmute toggle
  * `V`: Cycle visualiser view (Artwork ➔ Dual VU Meters ➔ Spectrum Analyser)

