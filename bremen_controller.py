#!/usr/bin/env python3
"""
Silent Angel Bremen SL1P — High-Fidelity Local Network Controller
Universal Web & Mobile Interface for Laptops and Smartphones
UK English Standard
"""

import http.server
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bremen_config.json")

class BremenDeviceManager:
    """Manages discovery, UPnP communication, and state polling for Silent Angel Bremen SL1P."""

    def __init__(self):
        self.lock = threading.Lock()
        self.target_ip = ""
        self.control_url_transport = ""
        self.control_url_rendering = ""
        self.device_name = "Silent Angel Bremen SL1P"
        self.model_name = "Bremen SL1P"
        self.is_connected = False
        self.last_seen = 0

        # State cache
        self.state = {
            "connected": False,
            "device_name": "No Device Connected",
            "device_ip": "",
            "transport_state": "STOPPED", # PLAYING, PAUSED_PLAYBACK, STOPPED
            "track_title": "No Track Loaded",
            "track_artist": "Silent Angel",
            "track_album": "VitOS Audio Core",
            "track_duration": "00:00",
            "rel_time": "00:00",
            "progress_percent": 0.0,
            "volume": 35,
            "mute": False,
            "sample_rate": "192.0 kHz",
            "bit_depth": "24-bit",
            "codec": "FLAC",
            "output_route": "Balanced XLR / RCA",
            "discovered_devices": []
        }

        self.load_config()
        self.start_background_poll()

    def load_config(self):
        """Loads cached device information if available."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.target_ip = cfg.get("target_ip", "")
                    self.control_url_transport = cfg.get("control_url_transport", "")
                    self.control_url_rendering = cfg.get("control_url_rendering", "")
                    self.device_name = cfg.get("device_name", "Silent Angel Bremen SL1P")
                    if self.target_ip:
                        self.state["device_ip"] = self.target_ip
                        self.state["device_name"] = self.device_name
            except Exception as e:
                print(f"[Config] Error loading config: {e}", flush=True)

    def save_config(self):
        """Persists device configuration for instant zero-drop startup."""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "target_ip": self.target_ip,
                    "control_url_transport": self.control_url_transport,
                    "control_url_rendering": self.control_url_rendering,
                    "device_name": self.device_name
                }, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving config: {e}", flush=True)

    def discover_ssdp(self, timeout=3.5):
        """Performs SSDP multicast discovery for MediaRenderers and Silent Angel hardware."""
        ssdp_addr = "239.255.255.250"
        ssdp_port = 1900
        queries = [
            'M-SEARCH * HTTP/1.1\r\n'
            'HOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\n'
            'MX: 2\r\n'
            'ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n',
            'M-SEARCH * HTTP/1.1\r\n'
            'HOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\n'
            'MX: 2\r\n'
            'ST: ssdp:all\r\n\r\n'
        ]

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        for q in queries:
            try:
                sock.sendto(q.encode("utf-8"), (ssdp_addr, ssdp_port))
            except Exception:
                pass

        discovered = []
        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                data, addr = sock.recvfrom(4096)
                text = data.decode("utf-8", errors="ignore")
                headers = {}
                for line in text.split("\r\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        headers[k.strip().upper()] = v.strip()

                loc = headers.get("LOCATION", "")
                st = headers.get("ST", "")
                server = headers.get("SERVER", "")
                ip = addr[0]

                if loc and not any(d["location"] == loc for d in discovered):
                    info = self.probe_description(loc, ip)
                    if info:
                        discovered.append(info)
            except socket.timeout:
                break
            except Exception:
                break

        sock.close()
        with self.lock:
            self.state["discovered_devices"] = discovered
        return discovered

    def probe_description(self, xml_url, ip):
        """Fetches and parses UPnP device XML description."""
        try:
            req = urllib.request.Request(xml_url, headers={"User-Agent": "BremenStudio/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                xml_content = resp.read()

            root = ET.fromstring(xml_content)
            # Remove XML namespace prefixes for easy querying
            for elem in root.iter():
                if "}" in elem.tag:
                    elem.tag = elem.tag.split("}", 1)[1]

            friendly_name = root.findtext(".//friendlyName", default="Network Audio Device")
            model_name = root.findtext(".//modelName", default="")
            manufacturer = root.findtext(".//manufacturer", default="")

            # Extract service control URLs
            parsed_base = urllib.parse.urlparse(xml_url)
            base_url = f"{parsed_base.scheme}://{parsed_base.netloc}"

            control_transport = ""
            control_rendering = ""

            for s in root.findall(".//service"):
                stype = s.findtext("serviceType", "")
                curl = s.findtext("controlURL", "")
                if not curl.startswith("http"):
                    curl = urllib.parse.urljoin(base_url, curl)
                if "AVTransport" in stype:
                    control_transport = curl
                elif "RenderingControl" in stype:
                    control_rendering = curl

            return {
                "ip": ip,
                "friendly_name": friendly_name,
                "model_name": model_name,
                "manufacturer": manufacturer,
                "location": xml_url,
                "control_transport": control_transport,
                "control_rendering": control_rendering
            }
        except Exception:
            return None

    def connect_to_device(self, ip, control_transport="", control_rendering="", friendly_name=""):
        """Connects to a specified device IP or control endpoint."""
        with self.lock:
            self.target_ip = ip
            self.control_url_transport = control_transport
            self.control_url_rendering = control_rendering
            self.device_name = friendly_name or f"Silent Angel Bremen ({ip})"
            self.is_connected = True
            self.state["connected"] = True
            self.state["device_ip"] = ip
            self.state["device_name"] = self.device_name

        self.save_config()
        self.refresh_state()
        return True

    def soap_request(self, control_url, service_type, action, args_dict):
        """Sends a UPnP SOAP control action."""
        if not control_url:
            return None

        args_xml = "".join([f"<{k}>{v}</{k}>" for k, v in args_dict.items()])
        body = (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">\r\n'
            '  <s:Body>\r\n'
            f'    <u:{action} xmlns:u="{service_type}">\r\n'
            f'      {args_xml}\r\n'
            f'    </u:{action}>\r\n'
            '  </s:Body>\r\n'
            '</s:Envelope>'
        )

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{service_type}#{action}"',
            "User-Agent": "BremenStudio/1.0"
        }

        try:
            req = urllib.request.Request(control_url, data=body.encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                xml_resp = resp.read()
                root = ET.fromstring(xml_resp)
                for elem in root.iter():
                    if "}" in elem.tag:
                        elem.tag = elem.tag.split("}", 1)[1]
                return root
        except Exception as e:
            # Device might be in standby or command rejected
            return None

    def play(self):
        """Triggers Play on Bremen SL1P."""
        if not self.control_url_transport:
            return False
        res = self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Play",
            {"InstanceID": "0", "Speed": "1"}
        )
        if res is not None:
            self.state["transport_state"] = "PLAYING"
            return True
        return False

    def pause(self):
        """Triggers Pause on Bremen SL1P."""
        if not self.control_url_transport:
            return False
        res = self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Pause",
            {"InstanceID": "0"}
        )
        if res is not None:
            self.state["transport_state"] = "PAUSED_PLAYBACK"
            return True
        return False

    def stop(self):
        """Triggers Stop on Bremen SL1P."""
        if not self.control_url_transport:
            return False
        res = self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Stop",
            {"InstanceID": "0"}
        )
        if res is not None:
            self.state["transport_state"] = "STOPPED"
            return True
        return False

    def next_track(self):
        """Skips to next track in queue."""
        if not self.control_url_transport:
            return False
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Next",
            {"InstanceID": "0"}
        ) is not None

    def prev_track(self):
        """Skips to previous track in queue."""
        if not self.control_url_transport:
            return False
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Previous",
            {"InstanceID": "0"}
        ) is not None

    def seek(self, target_time):
        """Seeks to target time string HH:MM:SS."""
        if not self.control_url_transport:
            return False
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Seek",
            {"InstanceID": "0", "Unit": "REL_TIME", "Target": target_time}
        ) is not None

    def set_volume(self, volume):
        """Sets output volume (0 - 100)."""
        vol = max(0, min(100, int(volume)))
        self.state["volume"] = vol
        if not self.control_url_rendering:
            return False
        return self.soap_request(
            self.control_url_rendering,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "SetVolume",
            {"InstanceID": "0", "Channel": "Master", "DesiredVolume": str(vol)}
        ) is not None

    def set_mute(self, mute):
        """Sets mute state."""
        val = "1" if mute else "0"
        self.state["mute"] = bool(mute)
        if not self.control_url_rendering:
            return False
        return self.soap_request(
            self.control_url_rendering,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "SetMute",
            {"InstanceID": "0", "Channel": "Master", "DesiredMute": val}
        ) is not None

    def refresh_state(self):
        """Polls current transport position and volume from the device."""
        if not self.target_ip:
            return

        # Poll Transport Info
        if self.control_url_transport:
            tinfo = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "GetTransportInfo",
                {"InstanceID": "0"}
            )
            if tinfo is not None:
                current_state = tinfo.findtext(".//CurrentTransportState", "STOPPED")
                self.state["transport_state"] = current_state
                self.state["connected"] = True

            pinfo = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "GetPositionInfo",
                {"InstanceID": "0"}
            )
            if pinfo is not None:
                rel_time = pinfo.findtext(".//RelTime", "00:00:00")
                duration = pinfo.findtext(".//TrackDuration", "00:00:00")
                meta = pinfo.findtext(".//TrackMetaData", "")

                self.state["rel_time"] = rel_time[:5] if len(rel_time) >= 5 else rel_time
                self.state["track_duration"] = duration[:5] if len(duration) >= 5 else duration

                # Parse DIDL-Lite metadata if present
                if meta and "<dc:title>" in meta:
                    m = re.search(r"<dc:title>(.*?)</dc:title>", meta)
                    if m:
                        self.state["track_title"] = m.group(1)
                    m = re.search(r"<dc:creator>(.*?)</dc:creator>", meta)
                    if m:
                        self.state["track_artist"] = m.group(1)
                    m = re.search(r"<upnp:album>(.*?)</upnp:album>", meta)
                    if m:
                        self.state["track_album"] = m.group(1)

        # Poll Volume
        if self.control_url_rendering:
            vinfo = self.soap_request(
                self.control_url_rendering,
                "urn:schemas-upnp-org:service:RenderingControl:1",
                "GetVolume",
                {"InstanceID": "0", "Channel": "Master"}
            )
            if vinfo is not None:
                cvol = vinfo.findtext(".//CurrentVolume", "")
                if cvol.isdigit():
                    self.state["volume"] = int(cvol)

    def start_background_poll(self):
        """Starts background loop to keep device state fresh."""
        def poll_loop():
            while True:
                try:
                    if self.target_ip and self.control_url_transport:
                        self.refresh_state()
                except Exception:
                    pass
                time.sleep(2.0)
        t = threading.Thread(target=poll_loop, daemon=True)
        t.start()


MANAGER = BremenDeviceManager()

class BremenHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Handles REST API and serves the embedded responsive audiophile web UI."""

    def log_message(self, format, *args):
        # Minimise terminal spam
        pass

    def send_json(self, data, status=200):
        out = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            with MANAGER.lock:
                self.send_json(MANAGER.state)
        elif path == "/api/discover":
            devices = MANAGER.discover_ssdp()
            self.send_json({"devices": devices})
        elif path == "/" or path == "/index.html":
            self.serve_ui()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/control":
            action = payload.get("action", "")
            val = payload.get("value")
            success = False

            if action == "play":
                success = MANAGER.play()
            elif action == "pause":
                success = MANAGER.pause()
            elif action == "stop":
                success = MANAGER.stop()
            elif action == "next":
                success = MANAGER.next_track()
            elif action == "prev":
                success = MANAGER.prev_track()
            elif action == "volume":
                success = MANAGER.set_volume(val)
            elif action == "mute":
                success = MANAGER.set_mute(val)
            elif action == "seek":
                success = MANAGER.seek(str(val))

            self.send_json({"status": "ok", "action": action, "success": success})

        elif path == "/api/connect":
            ip = payload.get("ip", "")
            curl_trans = payload.get("control_transport", "")
            curl_rend = payload.get("control_rendering", "")
            name = payload.get("friendly_name", "")

            # If user provided raw IP without endpoints, auto-build standard UPnP paths
            if ip and not curl_trans:
                # Common UPnP port locations
                curl_trans = f"http://{ip}:49152/upnp/control/avtransport"
                curl_rend = f"http://{ip}:49152/upnp/control/renderingcontrol"

            MANAGER.connect_to_device(ip, curl_trans, curl_rend, name)
            self.send_json({"status": "connected", "ip": ip})
        else:
            self.send_error(404, "Unknown action")

    def serve_ui(self):
        """Serves the complete responsive luxury audiophile web application."""
        html = """<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Bremen Studio — Silent Angel Bremen SL1P</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #0d0f12;
      --bg-surface: #15191f;
      --bg-elevated: #1e232b;
      --border-subtle: #272d38;
      --accent-gold: #c99d52;
      --accent-gold-hover: #dfb368;
      --text-main: #f3f5f8;
      --text-muted: #8b95a5;
      --telemetry-green: #2ecc71;
      --danger: #e74c3c;
      --font-stack: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
    }

    body {
      background: var(--bg-base);
      color: var(--text-main);
      font-family: var(--font-stack);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      overflow-x: hidden;
    }

    /* Layout structure */
    .app-container {
      display: flex;
      flex: 1;
      height: calc(100vh - 90px);
    }

    /* Sidebar (Desktop) */
    .sidebar {
      width: 280px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      padding: 24px;
      gap: 28px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand-logo {
      width: 36px;
      height: 36px;
      background: linear-gradient(135deg, var(--accent-gold), #8c6827);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 14px rgba(201, 157, 82, 0.25);
    }

    .brand-logo svg {
      width: 20px;
      height: 20px;
      fill: #fff;
    }

    .brand-text h1 {
      font-size: 17px;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: var(--text-main);
    }

    .brand-text span {
      font-size: 11px;
      color: var(--accent-gold);
      text-transform: uppercase;
      letter-spacing: 1.5px;
      font-weight: 600;
    }

    .nav-section h3 {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.2px;
      color: var(--text-muted);
      margin-bottom: 12px;
      font-weight: 600;
    }

    .nav-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      border-radius: 8px;
      color: var(--text-muted);
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .nav-item:hover, .nav-item.active {
      background: var(--bg-elevated);
      color: var(--text-main);
    }

    .nav-item.active {
      border-left: 3px solid var(--accent-gold);
      color: var(--accent-gold);
    }

    /* Device Connection Card */
    .device-card {
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      margin-top: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .device-status {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 600;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--danger);
    }

    .status-dot.connected {
      background: var(--telemetry-green);
      box-shadow: 0 0 10px rgba(46, 204, 113, 0.5);
    }

    .device-info h4 {
      font-size: 14px;
      font-weight: 600;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .device-info p {
      font-size: 12px;
      color: var(--text-muted);
      font-family: monospace;
    }

    .btn-connect {
      background: var(--border-subtle);
      border: none;
      color: var(--text-main);
      padding: 8px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .btn-connect:hover {
      background: var(--accent-gold);
      color: #000;
    }

    /* Main Content Area */
    .main-viewport {
      flex: 1;
      display: flex;
      flex-direction: column;
      background: radial-gradient(circle at top right, #181d26 0%, var(--bg-base) 60%);
      overflow-y: auto;
      padding: 32px 48px;
      gap: 32px;
    }

    /* Header Bar */
    .top-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .header-title h2 {
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.5px;
    }

    .header-title p {
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    .telemetry-pills {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .pill {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .pill-accent {
      border-color: var(--accent-gold);
      color: var(--accent-gold);
    }

    /* Hero Now Playing Stage */
    .stage-container {
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 40px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      padding: 36px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
    }

    .album-cover-box {
      width: 340px;
      height: 340px;
      border-radius: 16px;
      overflow: hidden;
      background: #1a1e27;
      position: relative;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
      border: 1px solid rgba(255, 255, 255, 0.05);
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .album-cover-box img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .stage-details {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
    }

    .meta-tags {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }

    .tag-hires {
      background: linear-gradient(135deg, var(--accent-gold), #8c6827);
      color: #000;
      font-size: 10px;
      font-weight: 800;
      padding: 3px 8px;
      border-radius: 4px;
      letter-spacing: 1px;
    }

    .tag-output {
      font-size: 12px;
      color: var(--text-muted);
      font-weight: 500;
    }

    .track-name {
      font-size: 32px;
      font-weight: 700;
      line-height: 1.2;
      margin-bottom: 8px;
    }

    .artist-name {
      font-size: 20px;
      color: var(--accent-gold);
      font-weight: 500;
      margin-bottom: 6px;
    }

    .album-name {
      font-size: 15px;
      color: var(--text-muted);
      font-weight: 400;
    }

    /* Progress scrub */
    .scrub-section {
      margin-top: 32px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .scrub-bar-wrapper {
      position: relative;
      height: 6px;
      background: var(--bg-elevated);
      border-radius: 3px;
      cursor: pointer;
    }

    .scrub-bar-progress {
      position: absolute;
      top: 0;
      left: 0;
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent-gold), var(--accent-gold-hover));
      border-radius: 3px;
      transition: width 0.2s linear;
    }

    .time-labels {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--text-muted);
      font-variant-numeric: tabular-nums;
    }

    /* Master Transport Bar */
    .master-player-bar {
      height: 90px;
      background: var(--bg-surface);
      border-top: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 32px;
      z-index: 100;
    }

    .transport-left {
      display: flex;
      align-items: center;
      gap: 16px;
      width: 280px;
    }

    .mini-art {
      width: 52px;
      height: 52px;
      border-radius: 8px;
      background: var(--bg-elevated);
      object-fit: cover;
    }

    .mini-meta h5 {
      font-size: 14px;
      font-weight: 600;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 200px;
    }

    .mini-meta p {
      font-size: 12px;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 200px;
    }

    .transport-centre {
      display: flex;
      align-items: center;
      gap: 20px;
    }

    .btn-circle {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .btn-circle:hover {
      border-color: var(--accent-gold);
      color: var(--accent-gold);
      transform: scale(1.05);
    }

    .btn-play-pause {
      width: 54px;
      height: 54px;
      background: var(--accent-gold);
      border: none;
      color: #000;
      box-shadow: 0 4px 16px rgba(201, 157, 82, 0.35);
    }

    .btn-play-pause:hover {
      background: var(--accent-gold-hover);
      color: #000;
      transform: scale(1.06);
    }

    .btn-circle svg {
      width: 20px;
      height: 20px;
      fill: currentColor;
    }

    .btn-play-pause svg {
      width: 24px;
      height: 24px;
    }

    .transport-right {
      display: flex;
      align-items: center;
      gap: 16px;
      width: 300px;
      justify-content: flex-end;
    }

    .volume-slider-box {
      display: flex;
      align-items: center;
      gap: 12px;
      width: 180px;
    }

    .volume-slider {
      -webkit-appearance: none;
      width: 100%;
      height: 5px;
      border-radius: 3px;
      background: var(--bg-elevated);
      outline: none;
    }

    .volume-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--accent-gold);
      cursor: pointer;
      box-shadow: 0 0 6px rgba(201, 157, 82, 0.6);
    }

    .vol-value {
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      color: var(--text-muted);
      width: 32px;
      text-align: right;
    }

    /* Modal for Discovery & IP input */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(8px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }

    .modal-box {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      width: 90%;
      max-width: 520px;
      padding: 32px;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .modal-header h3 {
      font-size: 18px;
      font-weight: 700;
    }

    .close-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 20px;
      cursor: pointer;
    }

    .ip-input-row {
      display: flex;
      gap: 10px;
    }

    .input-field {
      flex: 1;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 12px 16px;
      color: var(--text-main);
      font-size: 14px;
      outline: none;
      font-family: monospace;
    }

    .input-field:focus {
      border-color: var(--accent-gold);
    }

    .btn-action {
      background: var(--accent-gold);
      color: #000;
      border: none;
      padding: 12px 20px;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .btn-action:hover {
      background: var(--accent-gold-hover);
    }

    .scan-results {
      max-height: 200px;
      overflow-y: auto;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: var(--bg-base);
    }

    .device-item {
      padding: 10px 14px;
      border-radius: 6px;
      background: var(--bg-elevated);
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
      transition: all 0.2s ease;
    }

    .device-item:hover {
      border-left: 3px solid var(--accent-gold);
      background: #252b35;
    }

    /* Mobile Responsive Adaptation */
    @media (max-width: 900px) {
      .sidebar {
        display: none;
      }

      .app-container {
        height: auto;
      }

      .main-viewport {
        padding: 20px;
        gap: 20px;
      }

      .stage-container {
        grid-template-columns: 1fr;
        padding: 20px;
        gap: 24px;
      }

      .album-cover-box {
        width: 100%;
        height: 300px;
      }

      .master-player-bar {
        padding: 0 16px;
      }

      .transport-left {
        width: auto;
      }

      .transport-right {
        display: none;
      }
    }
  </style>
</head>
<body>

  <div class="app-container">
    <!-- Desktop Sidebar -->
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo">
          <svg viewBox="0 0 24 24"><path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/></svg>
        </div>
        <div class="brand-text">
          <h1>BREMEN</h1>
          <span>STUDIO PRO</span>
        </div>
      </div>

      <div class="nav-section">
        <h3>Sources</h3>
        <ul class="nav-list">
          <li class="nav-item active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
            Now Playing
          </li>
          <li class="nav-item" onclick="alert('NVMe SSD storage browser ready for VitOS mount')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            Internal NVMe (4TB)
          </li>
          <li class="nav-item" onclick="alert('Internet Radio directories ready')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>
            Internet Radio
          </li>
          <li class="nav-item" onclick="openModal()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            Device Discovery
          </li>
        </ul>
      </div>

      <!-- Device Connection Card -->
      <div class="device-card">
        <div class="device-status">
          <div class="status-dot" id="status-dot"></div>
          <span id="status-text">Disconnected</span>
        </div>
        <div class="device-info">
          <h4 id="card-dev-name">Bremen SL1P</h4>
          <p id="card-dev-ip">No IP set</p>
        </div>
        <button class="btn-connect" onclick="openModal()">Change Device</button>
      </div>
    </aside>

    <!-- Main Viewport -->
    <main class="main-viewport">
      <div class="top-header">
        <div class="header-title">
          <h2>Master Playback Stage</h2>
          <p>Lossless Bit-Perfect Streaming Output</p>
        </div>
        <div class="telemetry-pills">
          <div class="pill pill-accent">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>
            <span id="hud-format">FLAC 192kHz / 24-bit</span>
          </div>
          <div class="pill">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            <span id="hud-clock">Clock: Internal TCXO</span>
          </div>
          <div class="pill">
            <span id="hud-output">Output: Balanced XLR</span>
          </div>
        </div>
      </div>

      <!-- Hero Now Playing Stage -->
      <div class="stage-container">
        <div class="album-cover-box">
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="#3a4454" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="12" cy="12" r="5"/><polygon points="10 9 15 12 10 15 10 9"/></svg>
        </div>

        <div class="stage-details">
          <div>
            <div class="meta-tags">
              <span class="tag-hires">HI-RES AUDIO</span>
              <span class="tag-output" id="stage-codec">Studio Master Lossless</span>
            </div>
            <h1 class="track-name" id="stage-title">Waiting for Stream...</h1>
            <h2 class="artist-name" id="stage-artist">Silent Angel Bremen SL1P</h2>
            <h3 class="album-name" id="stage-album">VitOS High-Resolution Audio Engine</h3>
          </div>

          <div class="scrub-section">
            <div class="scrub-bar-wrapper" id="scrub-track" onclick="handleScrub(event)">
              <div class="scrub-bar-progress" id="scrub-progress"></div>
            </div>
            <div class="time-labels">
              <span id="time-elapsed">00:00</span>
              <span id="time-total">00:00</span>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>

  <!-- Master Transport Bar (Persistent at bottom) -->
  <footer class="master-player-bar">
    <div class="transport-left">
      <div class="mini-meta">
        <h5 id="mini-title">Waiting for Stream...</h5>
        <p id="mini-artist">Silent Angel Bremen SL1P</p>
      </div>
    </div>

    <div class="transport-centre">
      <button class="btn-circle" onclick="sendControl('prev')" title="Previous Track">
        <svg viewBox="0 0 24 24"><polygon points="11 19 2 12 11 5 11 19"/><polygon points="22 19 13 12 22 5 22 19"/></svg>
      </button>
      <button class="btn-circle btn-play-pause" id="btn-master-play" onclick="togglePlay()" title="Play / Pause (Spacebar)">
        <svg id="play-icon" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </button>
      <button class="btn-circle" onclick="sendControl('next')" title="Next Track">
        <svg viewBox="0 0 24 24"><polygon points="5 4 15 12 5 20 5 4"/><polygon points="13 4 23 12 13 20 13 4"/></svg>
      </button>
    </div>

    <div class="transport-right">
      <button class="btn-circle" id="btn-mute" onclick="toggleMute()" title="Mute Toggle">
        <svg viewBox="0 0 24 24"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
      </button>
      <div class="volume-slider-box">
        <input type="range" class="volume-slider" id="vol-range" min="0" max="100" value="35" oninput="handleVolume(this.value)">
        <span class="vol-value" id="vol-label">35%</span>
      </div>
    </div>
  </footer>

  <!-- Connection & Discovery Modal -->
  <div class="modal-overlay" id="modal-overlay">
    <div class="modal-box">
      <div class="modal-header">
        <h3>Connect to Silent Angel Bremen</h3>
        <button class="close-btn" onclick="closeModal()">&times;</button>
      </div>
      <p style="font-size: 13px; color: var(--text-muted);">
        Enter the IP address of your Bremen SL1P or click "Scan Network" to auto-discover UPnP endpoints.
      </p>

      <div class="ip-input-row">
        <input type="text" class="input-field" id="manual-ip-input" placeholder="e.g. 192.168.1.150">
        <button class="btn-action" onclick="connectManual()">Connect</button>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; margin-top: 10px;">
        <span style="font-size: 13px; font-weight:600;">Discovered Streamers</span>
        <button class="btn-connect" onclick="triggerScan()">Scan Network</button>
      </div>

      <div class="scan-results" id="scan-list">
        <div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px;">
          Click "Scan Network" or enter IP above
        </div>
      </div>
    </div>
  </div>

  <script>
    let isPlaying = false;
    let isMuted = false;

    // Polling state from backend
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Connection
        const dot = document.getElementById('status-dot');
        const stText = document.getElementById('status-text');
        const cardDevName = document.getElementById('card-dev-name');
        const cardDevIp = document.getElementById('card-dev-ip');

        if (data.connected && data.device_ip) {
          dot.className = "status-dot connected";
          stText.innerText = "Online";
          cardDevName.innerText = data.device_name;
          cardDevIp.innerText = data.device_ip;
        } else {
          dot.className = "status-dot";
          stText.innerText = data.device_ip ? "Connecting..." : "Disconnected";
          if (data.device_ip) cardDevIp.innerText = data.device_ip;
        }

        // Transport
        isPlaying = (data.transport_state === "PLAYING");
        const playIcon = document.getElementById('play-icon');
        if (isPlaying) {
          playIcon.innerHTML = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
        } else {
          playIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
        }

        // Track metadata
        document.getElementById('stage-title').innerText = data.track_title;
        document.getElementById('stage-artist').innerText = data.track_artist;
        document.getElementById('stage-album').innerText = data.track_album;
        document.getElementById('mini-title').innerText = data.track_title;
        document.getElementById('mini-artist').innerText = data.track_artist;

        // Times & Progress
        document.getElementById('time-elapsed').innerText = data.rel_time;
        document.getElementById('time-total').innerText = data.track_duration;
        const curSec = parseTimeToSec(data.rel_time);
        const totSec = parseTimeToSec(data.track_duration);
        if (totSec > 0) {
          const pct = Math.min(100, Math.max(0, (curSec / totSec) * 100));
          document.getElementById('scrub-progress').style.width = pct + '%';
        }

        // Volume
        if (!document.getElementById('vol-range').matches(':active')) {
          document.getElementById('vol-range').value = data.volume;
          document.getElementById('vol-label').innerText = data.volume + '%';
        }

      } catch (err) {
        console.error("Poll error:", err);
      }
    }

    function parseTimeToSec(tStr) {
      if (!tStr) return 0;
      const parts = tStr.split(':').map(Number);
      if (parts.length === 2) return parts[0] * 60 + parts[1];
      if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      return 0;
    }

    function secToTime(sec) {
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = Math.floor(sec % 60);
      return (h > 0 ? String(h).padStart(2, '0') + ':' : '') +
             String(m).padStart(2, '0') + ':' +
             String(s).padStart(2, '0');
    }

    function handleScrub(e) {
      const track = document.getElementById('scrub-track');
      const rect = track.getBoundingClientRect();
      const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const totText = document.getElementById('time-total').innerText;
      const totSec = parseTimeToSec(totText);
      if (totSec > 0) {
        const targetSec = frac * totSec;
        const targetStr = secToTime(targetSec);
        sendControl('seek', targetStr);
      }
    }

    setInterval(updateStatus, 1500);
    updateStatus();

    // Control actions
    async function sendControl(action, value = null) {
      await fetch('/api/control', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action, value})
      });
      setTimeout(updateStatus, 200);
    }

    function togglePlay() {
      sendControl(isPlaying ? 'pause' : 'play');
    }

    function toggleMute() {
      isMuted = !isMuted;
      sendControl('mute', isMuted);
    }

    function handleVolume(val) {
      document.getElementById('vol-label').innerText = val + '%';
      sendControl('volume', parseInt(val));
    }

    // Modal logic
    function openModal() {
      document.getElementById('modal-overlay').style.display = 'flex';
    }

    function closeModal() {
      document.getElementById('modal-overlay').style.display = 'none';
    }

    async function connectManual() {
      const ip = document.getElementById('manual-ip-input').value.trim();
      if (!ip) return;
      await fetch('/api/connect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ip: ip, friendly_name: 'Silent Angel Bremen SL1P'})
      });
      closeModal();
      updateStatus();
    }

    async function triggerScan() {
      const list = document.getElementById('scan-list');
      list.innerHTML = '<div style="font-size: 12px; color: var(--accent-gold); text-align: center; padding: 12px;">Scanning local network via SSDP...</div>';
      try {
        const res = await fetch('/api/discover');
        const data = await res.json();
        list.innerHTML = '';
        if (data.devices.length === 0) {
          list.innerHTML = '<div style="font-size: 12px; color: var(--text-muted); text-align: center; padding: 12px;">No UPnP renderers replied. Enter IP above directly.</div>';
          return;
        }
        data.devices.forEach(d => {
          const item = document.createElement('div');
          item.className = 'device-item';
          item.innerHTML = `<div><strong>${d.friendly_name}</strong><br><small style="color:var(--text-muted)">${d.ip}</small></div><button class="btn-connect">Select</button>`;
          item.onclick = async () => {
            await fetch('/api/connect', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({
                ip: d.ip,
                control_transport: d.control_transport,
                control_rendering: d.control_rendering,
                friendly_name: d.friendly_name
              })
            });
            closeModal();
            updateStatus();
          };
          list.appendChild(item);
        });
      } catch (err) {
        list.innerHTML = '<div style="font-size: 12px; color: var(--danger); text-align: center;">Scan failed. Check local firewall.</div>';
      }
    }

    // Desktop Keyboard shortcuts
    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT') return;
      if (e.code === 'Space') {
        e.preventDefault();
        togglePlay();
      } else if (e.code === 'ArrowRight' && (e.ctrlKey || e.metaKey)) {
        sendControl('next');
      } else if (e.code === 'ArrowLeft' && (e.ctrlKey || e.metaKey)) {
        sendControl('prev');
      } else if (e.code === 'KeyM') {
        toggleMute();
      } else if (e.code === 'ArrowUp') {
        const slider = document.getElementById('vol-range');
        slider.value = Math.min(100, parseInt(slider.value) + 2);
        handleVolume(slider.value);
      } else if (e.code === 'ArrowDown') {
        const slider = document.getElementById('vol-range');
        slider.value = Math.max(0, parseInt(slider.value) - 2);
        handleVolume(slider.value);
      }
    });
  </script>
</body>
</html>
"""
        out = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


def run_server(port=8080):
    """Starts the Bremen Studio local server."""
    server_address = ("", port)
    httpd = http.server.ThreadingHTTPServer(server_address, BremenHTTPHandler)
    print(f"===========================================================", flush=True)
    print(f" Silent Angel Bremen SL1P — Bremen Studio Web Controller   ", flush=True)
    print(f" Running at: http://localhost:{port}                        ", flush=True)
    print(f" Accessible from laptop browser and mobile phones on LAN    ", flush=True)
    print(f"===========================================================", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Bremen Studio server...", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    p = 8080
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        p = int(sys.argv[1])
    run_server(p)
