# Silent Angel Bremen SL1P — Network Control Architecture & System Specification

**Document Version:** 1.0.0  
**Language Standard:** UK English  
**Target Hardware:** Silent Angel Bremen SL1 / SL1 Plus (SL1P) High-Performance Network Streamer & DAC  
**Operating System:** VitOS (Thunder Data Co., Ltd. Audiophile Linux)  
**Target Platforms:** Laptops (Windows, macOS, Linux browsers / native apps) & Mobile Phones (iOS, Android responsive PWA)

---

## 1. Executive Summary & Objective

The **Silent Angel Bremen SL1 Plus (SL1P)** is a flagship digital network music streamer and balanced DAC powered by a custom hex-core ARM processing platform, dedicated internal DAC board, M.2 NVMe SSD expansion bay (up to 4TB), dual-band Wi-Fi, Gigabit Ethernet, and balanced XLR/RCA and digital outputs. 

Presently, the manufacturer relies on two mobile-only applications:
1. **VitOS Manager:** Intended for low-level system configuration, disk formatting, and package deployment.
2. **VitOS Orbiter (often referred to as VitOS Orbit):** Intended for daily playback, queue, and streaming management.

### The Problem
* **No Laptop / Desktop Interface:** There is no official Windows, macOS, or Linux application, nor is there a built-in browser-based web dashboard (`http://<device-ip>` returns no management interface). Users working on laptops are completely locked out of direct control unless they reach for a smartphone.
* **Volatile Discovery & Handshake Drops:** The mobile application frequently loses connectivity during network handovers, subnet changes, or when the phone enters battery-saving sleep mode.
* **Fragile Queue Management:** Queues are largely client-managed or subject to desynchronisation, lacking persistent on-device state or cross-device synchronisation.
* **Sluggish Library Browsing:** Indexing large local libraries (especially multi-terabyte NVMe SSDs or attached USB storage) regularly causes UI lag or crashes in the VitOS Orbit application.
* **Opaque Telemetry:** The stock application provides minimal insight into real-time DAC lock status, exact bit-depth, PCM/DSD sampling rate, buffer levels, thermal conditions, or external clock synchronisation.

### The Objective
To specify and engineer **"Bremen Studio"** (working title: *OrbitWeb / Bremen Control Centre*), a modern, high-res audiophile control suite that runs as a lightweight, zero-latency local web application and Progressive Web App (PWA). It empowers the user to control their Bremen SL1P seamlessly from any laptop browser or mobile device, delivering instant responsiveness, persistent gapless queueing, rich audio telemetry, and rock-solid network resilience.

---

## 2. Hardware Architecture & Controllable Features

### 2.1 Hardware Capabilities of the Bremen SL1P
* **Compute Engine:** Dual-core ARM Cortex-A72 @ 1.8 GHz + Quad-core Cortex-A53 @ 1.4 GHz.
* **Memory & System Storage:** 4 GB low-noise RAM, 32 GB high-speed flash storage.
* **Local Storage Expansion:** 1x internal M.2 NVMe SSD slot (2280 form factor, up to 4 TB) plus 2x USB 3.0 and 1x USB 2.0 ports.
* **Network Interfaces:** 1 Gbps Gigabit Ethernet RJ45, 802.11ac dual-band Wi-Fi, Bluetooth 5.0.
* **Analog Audio Outputs:** Balanced XLR stereo pair, Single-ended RCA stereo pair (switchable fixed line-out or variable pre-amp volume).
* **Digital Audio Outputs:** 
  * S/PDIF Coaxial RCA (up to PCM 384 kHz, DSD128 via DoP).
  * TOSLINK Optical (up to PCM 192 kHz / 24-bit).
  * USB Audio Class 2.0 (up to PCM 768 kHz, Native DSD512 / DSD256).
* **Clock Synchronisation:** High-precision internal TCXO crystal oscillator with BNC input for an external 10 MHz master clock (e.g. Silent Angel Genesis GX).

---

### 2.2 Comprehensive Controllable Feature Matrix

The table below categorises every feature on the Bremen SL1P, the underlying network protocol enabling it, and the control behaviour:

| Feature Category | Controllable Parameter | Available Protocol / Interface | Controllable Range / Behaviour |
| :--- | :--- | :--- | :--- |
| **Transport** | Play / Pause / Stop | UPnP `AVTransport:1` / OpenHome `Playlist` / MPD | Toggle state, bit-perfect stream initiation |
| **Transport** | Track Seek | `AVTransport::Seek` / OpenHome `Time` / MPD `seek` | Absolute time seek (`HH:MM:SS`) or relative percentage |
| **Transport** | Next / Previous Track | `AVTransport::Next` / `Previous` / OpenHome | Instant transition with gapless lookahead |
| **Transport** | Play Modes | `AVTransport::SetPlayMode` / OpenHome / MPD | `NORMAL`, `SHUFFLE`, `REPEAT_ONE`, `REPEAT_ALL`, `RANDOM` |
| **Volume & Attenuation** | Volume Level | UPnP `RenderingControl:1` / OpenHome `Volume` | Linear / logarithmic scale `0` to `100`% (with safety cap) |
| **Volume & Attenuation** | Mute / Unmute | `RenderingControl::SetMute` / OpenHome `Volume` | Boolean toggle with smooth ramp-down / ramp-up |
| **Audio Routing** | Output Selection | VitOS Audio HAL / OpenHome `Product:1` | Internal DAC (XLR/RCA), USB DAC, S/PDIF Coax, TOSLINK |
| **Audio Routing** | Pre-amp Mode | VitOS System Engine | Variable Volume (Pre-amp) vs Fixed Line-Level (Bypass) |
| **Source Selection** | Active Input Mode | OpenHome `Product::SetSource` / VitOS Engine | Local Storage, UPnP/DLNA, Internet Radio, AirPlay, Roon, Spotify |
| **Queue Management** | Active Queue Manipulation | OpenHome `Playlist:1` / MPD port `6600` | Insert, Append, Reorder, Delete, Clear, Save as Playlist |
| **Queue Management** | Gapless Playback | OpenHome `Playlist` / MPD internal scheduler | Native hardware gapless transition between consecutive tracks |
| **Library Browsing** | Local Storage Navigation | UPnP `ContentDirectory:1` / MPD Database | Hierarchical & metadata search (Artist, Album, Genre, Folder) |
| **Library Browsing** | Fast Search & Filtering | Local In-Memory Index / MPD `search` | Instant fuzzy query across track titles, composers, and years |
| **Internet Radio** | Stream Tuning | OpenHome `Radio:1` / Custom URL Injection | TuneIn, vTuner, Radio Paradise, custom Icecast/FLAC URLs |
| **Hardware Telemetry** | Stream & DAC Monitor | UPnP `GetMediaInfo` / OpenHome `Info` | Bit depth (16/24/32), Sample rate (44.1–768kHz), DSD, MQA |
| **Hardware Telemetry** | System Diagnostics | VitOS Telemetry / Linux Sysfs / SNMP | CPU temp, NVMe free space, RAM, network link, clock lock |
| **Power Management** | Reboot / Standby | VitOS Management API / ACPI Daemon | Graceful filesystem unmount, reboot, standby low-power mode |

---

## 3. Critical Critique of Existing VitOS Orbit App

To construct a demonstrably superior solution, the following architectural flaws and usability deficiencies in the existing VitOS Orbit application have been directly targeted for elimination:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           VITOS ORBIT DEFICIENCY AUDIT                          │
├───────────────────────────────┬─────────────────────────────────────────────────┤
│ Flaw in VitOS Orbit           │ Architectural Consequence                       │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 1. Platform Lock-in           │ Mobile-only (iOS/Android). No desktop laptop    │
│                               │ web client or native application exists.        │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 2. Unicast / Multicast Drift  │ Relies purely on fragile broadcast discovery    │
│                               │ with no fallback IP caching or reconnection.   │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 3. Client-Side Queue State    │ If the phone sleeps or terminates the app, the  │
│                               │ active queue context becomes desynchronised.    │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 4. Slow NVMe SSD Indexing     │ Synchronous parsing of large USB/SSD storage    │
│                               │ blocks the UI thread, causing stutter & crash.  │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 5. Coarse Volume Resolution   │ Jump increments without software limiter or     │
│                               │ fine-step rotary attenuation protection.        │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 6. Minimal Audio Telemetry    │ Does not clearly present real-time DAC lock,    │
│                               │ clock synchronisation, or stream bit-rates.     │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 7. Zero Desktop Ergonomics    │ No keyboard shortcuts (Space=Play, Arrows=Seek, │
│                               │ M=Mute), no OS MediaSession or tray controls.   │
└───────────────────────────────┴─────────────────────────────────────────────────┘
```

---

## 4. Proposed Solution Architecture: "Bremen Studio"

### 4.1 System Overview
**Bremen Studio** is engineered as a hybrid local controller comprising:
1. **Lightweight Controller Bridge (Daemon):** A tiny, efficient service (written in Node.js/TypeScript or Python) that runs either directly on the user's laptop, on a local network host (e.g. NAS, home server, Raspberry Pi), or as a standalone zero-install Windows binary.
2. **Universal Responsive Web Client / PWA:** An ultra-fast, modern web interface served locally over HTTP/WebSocket. It renders an expansive multi-column dashboard on laptop widescreen displays and automatically adapts into a touch-optimised mobile layout when accessed from an iPhone or Android phone.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                CLIENT DEVICES                                   │
│                                                                                 │
│   ┌───────────────────────────────┐           ┌─────────────────────────────┐   │
│   │   Laptop (Windows / macOS)    │           │    Mobile Phone (iOS / Android│  │
│   │   Widescreen Dashboard / PWA  │           │    Responsive Mobile PWA    │   │
│   └───────────────┬───────────────┘           └──────────────┬──────────────┘   │
└───────────────────┼──────────────────────────────────────────┼──────────────────┘
                    │             HTTP / WebSocket             │
                    ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    BREMEN STUDIO CONTROLLER BRIDGE (LOCAL DAEMON)               │
│                                                                                 │
│   ┌────────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐   │
│   │ Fast SSDP / mDNS   │   │  Multi-Client Sync  │   │ High-Res Metadata &  │   │
│   │ Discovery Engine   │   │  WebSocket Gateway  │   │ Cover Art Image Cache│   │
│   └─────────┬──────────┘   └──────────┬──────────┘   └──────────┬───────────┘   │
│             │                         │                         │               │
│   ┌─────────▼─────────────────────────▼─────────────────────────▼───────────┐   │
│   │                     PROTOCOL DRIVER SUBSYSTEM                           │   │
│   │                                                                         │   │
│   │  • UPnP AVTransport Driver     • OpenHome (Linn) AV Driver              │   │
│   │  • UPnP RenderingControl       • MPD Port 6600 Driver                   │   │
│   │  • UPnP ContentDirectory       • VitOS System Telemetry Driver          │   │
│   └───────────────────────────────────┬─────────────────────────────────────┘   │
└───────────────────────────────────────┼─────────────────────────────────────────┘
                                        │ Local Subnet (Gigabit / Wi-Fi)
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                 SILENT ANGEL BREMEN SL1P (RUNNING VITOS FIRMWARE)               │
│                                                                                 │
│   ┌────────────────────┐  ┌──────────────────────┐  ┌───────────────────────┐   │
│   │ UPnP / DLNA Engine │  │ MPD Daemon (Port 6600│  │ Shairport / Spotify   │   │
│   │ (AVTransport/Media)│  │ (SSD / USB Index)    │  │ Connect / Tidal / Roon│   │
│   └─────────┬──────────┘  └──────────┬───────────┘  └───────────┬───────────┘   │
│             │                        │                          │               │
│             └────────────────────────▼──────────────────────────┘               │
│                                      │                                          │
│                           ┌──────────▼───────────┐                              │
│                           │ VitOS Audio Core HAL │                              │
│                           └──────────┬───────────┘                              │
│                                      │                                          │
│       ┌──────────────────────────────┼──────────────────────────────┐           │
│       ▼                              ▼                              ▼           │
│  Internal DAC (XLR/RCA)      USB Audio Output (DAC)       Coaxial / Optical S/PDIF
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Technical Specification of Subsystems

### 5.1 Discovery Engine (Zero-Drop Detection)
The discovery engine implements a three-tier discovery strategy to guarantee that the Bremen SL1P is immediately detected and permanently retained:
1. **Tier 1 — SSDP Multicast Search:**
   * Broadcasts `M-SEARCH` packets to `239.255.255.250:1900` querying:
     * `urn:schemas-upnp-org:device:MediaRenderer:1`
     * `urn:av-openhome-org:service:Playlist:1`
     * `ssdp:all`
2. **Tier 2 — mDNS / DNS-SD Service Query:**
   * Multicasts DNS queries to `224.0.0.251:5353` for `_raat._tcp.local`, `_spotify-connect._tcp.local`, and `_airplay._tcp.local`.
3. **Tier 3 — Static IP & ARP Subnet Cache:**
   * Persists the last confirmed device IP address in a local configuration file (`config.json`). On startup, the bridge immediately attempts a direct HTTP/TCP handshake to the cached IP while running background multicast discovery. This eliminates the 5–10 second delay common in VitOS Orbit.

---

### 5.2 Protocol Driver Implementations

#### A. UPnP / DLNA Driver (AVTransport & RenderingControl)
* **Transport Control:** Formats SOAP XML envelopes sent via HTTP POST to the Bremen SL1P's AVTransport endpoint.
* **Sample Action Envelope (`Play`):**
  ```xml
  POST /AVTransport/control HTTP/1.1
  Host: 192.168.1.X:PORT
  SOAPACTION: "urn:schemas-upnp-org:service:AVTransport:1#Play"
  Content-Type: text/xml; charset="utf-8"

  <?xml version="1.0" encoding="utf-8"?>
  <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
    <s:Body>
      <u:Play xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
        <InstanceID>0</InstanceID>
        <Speed>1</Speed>
      </u:Play>
    </s:Body>
  </s:Envelope>
  ```
* **Precise Volume Control:** Maps the UI slider to `RenderingControl::SetVolume` with safety clamping:
  ```xml
  <u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
    <InstanceID>0</InstanceID>
    <Channel>Master</Channel>
    <DesiredVolume>42</DesiredVolume>
  </u:SetVolume>
  ```

#### B. OpenHome (OH) Protocol Driver
* When VitOS runs `upmpdcli` or OpenHome services, Bremen Studio prioritises the OpenHome `Playlist` and `Volume` interfaces.
* **Advantage:** OpenHome stores the track list and index *on the Bremen SL1P*. Even if every laptop and mobile phone is powered off, the device continues playing the queue seamlessly.
* Subscribed via UPnP GENA eventing (`SUBSCRIBE` header) to receive push updates whenever track index or volume changes.

#### C. MPD Protocol Driver (Port 6600)
* Connects via raw asynchronous TCP socket to `Bremen-SL1P-IP:6600`.
* Commands executed:
  * `status`: Retrieves instantaneous playback state, elapsed time, bitrate, and audio format (e.g. `44100:24:2`).
  * `currentsong`: Returns full tag metadata including embedded album art URI.
  * `playlistinfo`: Fetches the entire queue in a single ultra-compact payload (<50 ms).
  * `idle`: Low-overhead socket blocking that receives instant notifications when the player, mixer, or database changes.

---

### 5.3 UI & UX Design Specification

#### A. Design Aesthetic & Theme
* **Visual Identity:** Luxury audiophile dark theme reminiscent of brushed aircraft-grade aluminium and obsidian glass, matching the physical chassis of the Bremen SL1P.
* **Colour Palette:**
  * Background Base: `#0d0f12` (Deep Charcoal Obsidian)
  * Surface Container: `#16191f` (Machined Aluminium Slate)
  * Accent Primary: `#c99d52` (High-End Hi-Fi Champagne Gold)
  * Accent Secondary: `#4a90e2` (Studio Master Blue)
  * Text Primary: `#f0f2f5` (Crisp Studio White)
  * Text Muted: `#8b949e` (Soft Silver)
  * Telemetry Green: `#3fb950` (MQA / Hi-Res Indicator)
* **Typography:** `Inter`, `SF Pro Display`, or system sans-serif font stack with tabular numbers (`font-variant-numeric: tabular-nums`) for jitter-free timecode rendering.

#### B. Laptop / Desktop Widescreen Layout (Dual / Three-Pane View)
1. **Left Navigation Rail (Width: 240px):**
   * Device Status Card (Bremen SL1P connection status, IP, output mode).
   * Library Sources (Internal NVMe SSD, USB Drives, DLNA Servers).
   * Streaming Hub (Radio Stations, Spotify, Tidal, Qobuz shortcuts).
   * Settings & Hardware Diagnostics.
2. **Main Browsing Canvas (Fluid Flex):**
   * High-speed grid/list view with virtualised scrolling (capable of rendering 100,000+ tracks smoothly).
   * Real-time search filter bar with instant tag filtering (Hi-Res 24-bit, DSD, FLAC).
   * Album view featuring high-resolution cached cover art, artist biography, and track listing.
3. **Right-Hand Queue Drawer (Width: 360px, Collapsible):**
   * Live track queue with drag-and-drop reordering.
   * "Play Next", "Clear Queue", and "Save to Playlist" actions.
4. **Bottom Master Transport Bar (Height: 88px, Persistent):**
   * **Left:** Thumbnail art, Track title, Artist, Album, and clickable **Hi-Res Audio Badge** (e.g. `FLAC 192kHz/24bit` or `DSD128`).
   * **Centre:** Scrub bar with elapsed/remaining timecodes, Shuffle, Previous, Play/Pause, Next, Repeat.
   * **Right:** Rotary / linear volume slider, Mute toggle, **Max-Volume Limiter Guard**, Output Selector dropdown, Fullscreen "Now Playing" toggle.

#### C. Mobile Phone Layout (Responsive PWA)
1. **Header Bar:** Bremen SL1P status indicator, source dropdown, and global search icon.
2. **Tabbed Content Navigation:**
   * Bottom Navigation Bar with 4 touch targets (minimum 48x48px): **Now Playing**, **Library**, **Queue**, **Settings**.
3. **Now Playing Screen (Full Bleed):**
   * Edge-to-edge album cover art with subtle drop shadow.
   * Floating Hi-Res audio chip indicator.
   * Large thumb-friendly scrub bar and transport controls.
   * Tactile volume slider with single-dB step buttons (`+` / `-`).
4. **Lock Screen & Media Notification Integration:**
   * Fully integrates with the mobile browser `navigator.mediaSession` API to allow lock-screen Play/Pause/Track Skipping and artwork display on iOS and Android.

#### D. Desktop Ergonomics & Keyboard Shortcuts
* `Spacebar`: Play / Pause toggle.
* `Arrow Right` / `Arrow Left`: Seek forward / backward 5 seconds (`Shift` + `Arrow` = 15 seconds).
* `Cmd/Ctrl` + `Arrow Right`: Next track.
* `Cmd/Ctrl` + `Arrow Left`: Previous track.
* `Arrow Up` / `Arrow Down`: Volume increment / decrement by 2%.
* `M`: Mute / Unmute toggle.
* `F`: Fullscreen Now Playing stage view (ideal for dedicated living room display).
* `/`: Focus library search bar.

---

### 5.4 Audio Telemetry & Stream Diagnostics HUD

Unlike VitOS Orbit, Bremen Studio exposes a dedicated **Audio Telemetry Modal & Status Bar**:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   STREAM & HARDWARE TELEMETRY HUD                      │
├──────────────────────┬─────────────────────────────────────────────────┤
│ Container / Codec    │ FLAC (Free Lossless Audio Codec)                │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Resolution / Rate    │ 192.0 kHz / 24-bit PCM                          │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Stream Bitrate       │ 5,842 kbps (Variable Bitrate)                   │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Master Clock Status  │ Internal TCXO Locked (or 10MHz Ext Clock Sync)  │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Active Output Route  │ Balanced XLR (Internal DAC Engine)              │
├──────────────────────┼─────────────────────────────────────────────────┤
│ NVMe Storage Space   │ 1.42 TB used / 2.00 TB total (71%)              │
├──────────────────────┼─────────────────────────────────────────────────┤
│ Network Throughput   │ 1000 Mbps Full Duplex (Ethernet RJ45)           │
├──────────────────────┼─────────────────────────────────────────────────┤
│ CPU Core Temp        │ 41.8 °C (Within optimal low-noise thermal zone) │
└──────────────────────┴─────────────────────────────────────────────────┘
```

---

## 6. Survey of Assistive Tools & Code Libraries (GitHub & Open Source)

To accelerate implementation and eliminate redundant development, the following robust, battle-tested open-source libraries have been evaluated for integration:

### 6.1 Discovery & Network Control
1. **`async_upnp_client` (Python):**
   * *GitHub:* `StevenLooman/async_upnp_client`
   * *Strengths:* Implements complete UPnP/DLNA Device Architecture, asynchronous SSDP discovery, service description parsing, SOAP action calls, and GENA event subscription. Widely deployed within Home Assistant.
2. **`upnp-client-ts` (TypeScript / Node.js):**
   * *GitHub:* `Mikescops/upnp-client-ts`
   * *Strengths:* Modern TypeScript implementation with native support for `UpnpMediaRendererClient` and `AVTransport` / `RenderingControl` action builders.
3. **`node-ssdp` (Node.js):**
   * *GitHub:* `diversario/node-ssdp`
   * *Strengths:* Fast multicast UDP implementation using Node's `dgram` module for rapid M-SEARCH and NOTIFY listeners.

### 6.2 Music Player Daemon (MPD) Clients
1. **`mpdapi` / `mpd-api` (TypeScript):**
   * Provides typed abstractions for communicating with MPD on port 6600, including TCP connection pools, queue modifications, and song queries.
2. **`myMPD` (C / Modern Web UI):**
   * *GitHub:* `jcorporation/myMPD`
   * *Inspiration:* Lightweight, mobile-friendly audiophile web client with album art caching and smart playlist generation.

### 6.3 Frontend & UI Frameworks
1. **React / Preact + Tailwind CSS:**
   * Delivers instantaneous UI rendering with minimal footprint.
2. **`lucide-react`:**
   * Clean, consistent SVG icon system for audiophile transports and controls.
3. **HTML5 `MediaSession` API:**
   * Browser-standard API binding playback state to the operating system's native media overlays and keyboard media buttons.

---

## 7. Implementation Roadmap & Verification Plan

### Phase 1: Prototype Discovery & Core Transport (Immediate)
* Implement a standalone discovery script that locates the Bremen SL1P via SSDP and validates TCP communication on ports `49152`, `6600`, and UPnP endpoints.
* Implement basic Play, Pause, Stop, Seek, Volume, and Mute controls.

### Phase 2: Lightweight Bridge & WebSocket Gateway
* Build the local backend server (Node.js or Python) providing:
  * Persistent caching of the Bremen SL1P IP address.
  * Real-time WebSocket event broadcaster syncing all connected browser windows (laptop + phone).
  * REST API endpoints (`/api/transport`, `/api/volume`, `/api/queue`, `/api/library`).

### Phase 3: Responsive Audiophile Frontend (PWA)
* Develop the dark-theme UI with dual widescreen/mobile views.
* Implement keyboard shortcuts, smooth volume slider with safety limiter, and MediaSession integration.
* Implement the Audio Telemetry HUD.

### Phase 4: Local NVMe Library & Streaming Integration
* Integrate MPD / UPnP ContentDirectory browsing for the internal M.2 NVMe SSD.
* Add support for internet radio presets and streaming shortcuts.

---

## 8. Summary of Advantages over VitOS Orbit

| Feature | VitOS Orbit (Existing App) | Bremen Studio (New Specification) |
| :--- | :--- | :--- |
| **Supported Devices** | iOS and Android phones only | Any Laptop (Windows/Mac/Linux) + Mobile PWA |
| **Connection Stability** | Frequent dropouts when phone sleeps | Zero-drop connection with IP caching & auto-retry |
| **Queue Synchronisation** | Single client, volatile local state | Multi-client synchronised via WebSockets |
| **Volume Safety** | Raw jumps, risk of speaker overload | Software safety limiter + fine-step control |
| **Library Browsing** | Stutters on multi-terabyte SSDs | Virtualised rendering of 100k+ track libraries |
| **Audio Telemetry** | Basic track name and simple bitrate | Complete HUD (Exact rate, DSD/MQA, Clock lock) |
| **Desktop Ergonomics** | None (no desktop app exists) | Full keyboard shortcuts, media keys, multi-column |
