#!/usr/bin/env python3
"""
Silent Angel Bremen SL1P — High-Fidelity Local Network Controller
Universal Web & Mobile Interface for Laptops and Smartphones
UK English Standard
"""

import concurrent.futures
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bremen_config.json")


def clear_port(port):
    """
    Attempts to clear any process holding the specified port.
    Returns True if port was freed or was already free, False if occupied by an unkillable service.
    """
    if sys.platform == "win32":
        try:
            # Find PID using netstat
            cmd = f'netstat -ano | findstr :{port}'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
            pids = set()
            for line in output.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                    pids.add(int(parts[4]))

            for pid in pids:
                if pid != os.getpid() and pid > 0:
                    print(f"[Port Manager] Port {port} is occupied by PID {pid}. Attempting to clear...", flush=True)
                    try:
                        res = subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, text=True)
                        if res.returncode == 0:
                            print(f"[Port Manager] Terminated process {pid} successfully.", flush=True)
                        else:
                            print(f"[Port Manager] Could not terminate PID {pid}: {res.stderr.strip()}", flush=True)
                    except Exception:
                        pass
            time.sleep(0.3)
        except Exception:
            pass

    # Test if socket can bind now
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", port))
        s.close()
        return True
    except OSError:
        return False


def get_available_port(preferred_port=8090):
    """
    Tries the preferred port (clearing user processes if present).
    If it is permanently blocked by a system service, automatically selects the next clean port.
    """
    ports_to_try = [preferred_port, 8090, 8091, 8092, 8088, 8888, 7070]
    # Remove duplicates while preserving order
    seen = set()
    ordered_ports = [p for p in ports_to_try if not (p in seen or seen.add(p))]

    for port in ordered_ports:
        print(f"[Port Manager] Checking availability for port {port}...", flush=True)
        if clear_port(port):
            return port
        print(f"[Port Manager] Port {port} is locked or unavailable. Trying alternative...", flush=True)

    # Fallback to OS assigned port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    free_port = s.getsockname()[1]
    s.close()
    return free_port


def get_local_ip():
    """Retrieves the local LAN IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


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
            "transport_state": "STOPPED",
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
            "active_source": "UPnP / DLNA",
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

    def discover_all_devices(self, timeout=3.5):
        """
        Comprehensive Multi-Protocol Network Discovery:
        1. SSDP Multicast (UPnP AVTransport, OpenHome, MediaRenderer)
        2. Fast Subnet Port Probe (VitOS HTTP, MPD 6600, UPnP 49152+)
        3. Local ARP table inspection
        """
        discovered = []
        seen_ips = set()

        # Step 1: SSDP Multicast Probe
        ssdp_devices = self.discover_ssdp(timeout=2.5)
        for dev in ssdp_devices:
            dev["method"] = "SSDP"
            discovered.append(dev)
            seen_ips.add(dev["ip"])

        # Step 2: Subnet ARP & Port Sweep
        local_ip = get_local_ip()
        parts = local_ip.split(".")
        if len(parts) == 4:
            subnet_prefix = ".".join(parts[:3])

            # Gather active candidate IPs from ARP table first
            candidate_ips = set()
            try:
                arp_out = subprocess.check_output("arp -a", shell=True, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
                for line in arp_out.splitlines():
                    match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                    if match:
                        ip_found = match.group(1)
                        if ip_found.startswith(subnet_prefix) and not ip_found.endswith(".255"):
                            candidate_ips.add(ip_found)
            except Exception:
                pass

            # Add general candidate addresses if few ARP entries
            if len(candidate_ips) < 5:
                for i in range(1, 40):
                    candidate_ips.add(f"{subnet_prefix}.{i}")

            def probe_candidate_ip(ip):
                if ip in seen_ips:
                    return None
                # Probe audio ports: 49152 (UPnP), 6600 (MPD), 80 (VitOS web/API), 8080
                for port in [49152, 49153, 6600, 80, 8080]:
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.2)
                        res = s.connect_ex((ip, port))
                        s.close()
                        if res == 0:
                            # Try HTTP XML description or MPD greeting
                            info = self.probe_candidate_services(ip, port)
                            if info:
                                return info
                    except Exception:
                        pass
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                results = list(executor.map(probe_candidate_ip, candidate_ips))

            for r in results:
                if r and r["ip"] not in seen_ips:
                    discovered.append(r)
                    seen_ips.add(r["ip"])

        # Sort: Silent Angel / Bremen devices first, then MediaRenderers
        def sort_key(d):
            score = 0
            name = (d.get("friendly_name") or "") + (d.get("model_name") or "") + (d.get("manufacturer") or "")
            if "Bremen" in name or "Silent Angel" in name or "VitOS" in name:
                score += 100
            if d.get("is_bremen"):
                score += 50
            if d.get("control_transport"):
                score += 20
            return score

        discovered.sort(key=sort_key, reverse=True)

        with self.lock:
            self.state["discovered_devices"] = discovered
        return discovered

    def probe_candidate_services(self, ip, port):
        """Attempts to identify a candidate IP by inspecting port service responses."""
        if port == 6600:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((ip, 6600))
                banner = s.recv(1024).decode("utf-8", errors="ignore")
                s.close()
                if "OK MPD" in banner:
                    return {
                        "ip": ip,
                        "friendly_name": f"Silent Angel Bremen / VitOS MPD ({ip})",
                        "model_name": "Bremen SL1P (MPD)",
                        "manufacturer": "Thunder Data / Silent Angel",
                        "location": f"http://{ip}:6600",
                        "control_transport": "",
                        "control_rendering": "",
                        "is_bremen": True,
                        "method": "MPD Port 6600"
                    }
            except Exception:
                pass

        # Try common UPnP root description paths
        for path in ["/description.xml", "/device.xml", "/upnp/dev/", "/rootDesc.xml"]:
            url = f"http://{ip}:{port}{path}"
            info = self.probe_description(url, ip)
            if info:
                info["method"] = f"Port {port} Probe"
                return info

        return None

    def discover_ssdp(self, timeout=2.5):
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
            'ST: urn:av-openhome-org:service:Product:1\r\n\r\n',
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
        return discovered

    def probe_description(self, xml_url, ip):
        """Fetches and parses UPnP device XML description."""
        try:
            req = urllib.request.Request(xml_url, headers={"User-Agent": "BremenStudio/1.0"})
            with urllib.request.urlopen(req, timeout=1.8) as resp:
                xml_content = resp.read()

            root = ET.fromstring(xml_content)
            for elem in root.iter():
                if "}" in elem.tag:
                    elem.tag = elem.tag.split("}", 1)[1]

            friendly_name = root.findtext(".//friendlyName", default="Network Audio Device")
            model_name = root.findtext(".//modelName", default="")
            manufacturer = root.findtext(".//manufacturer", default="")

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

            is_bremen = any(k in f"{friendly_name} {model_name} {manufacturer}".lower()
                            for k in ["bremen", "silent angel", "vitos", "thunder data"])

            return {
                "ip": ip,
                "friendly_name": friendly_name,
                "model_name": model_name,
                "manufacturer": manufacturer,
                "location": xml_url,
                "control_transport": control_transport,
                "control_rendering": control_rendering,
                "is_bremen": is_bremen
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
            '<s:Body>\r\n'
            f'<u:{action} xmlns:u="{service_type}">\r\n'
            f'{args_xml}\r\n'
            f'</u:{action}>\r\n'
            '</s:Body>\r\n'
            '</s:Envelope>\r\n'
        )

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service_type}#{action}"',
            "User-Agent": "BremenStudio/1.0"
        }

        try:
            req = urllib.request.Request(control_url, data=body.encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return None

    def play(self):
        """Dispatches Play command."""
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Play",
            {"InstanceID": "0", "Speed": "1"}
        )

    def pause(self):
        """Dispatches Pause command."""
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Pause",
            {"InstanceID": "0"}
        )

    def stop(self):
        """Dispatches Stop command."""
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Stop",
            {"InstanceID": "0"}
        )

    def next_track(self):
        """Dispatches Next track command."""
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Next",
            {"InstanceID": "0"}
        )

    def previous_track(self):
        """Dispatches Previous track command."""
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Previous",
            {"InstanceID": "0"}
        )

    def seek(self, target_time):
        """Dispatches Seek command to target timestamp (HH:MM:SS)."""
        return self.soap_request(
            self.control_url_transport,
            "urn:schemas-upnp-org:service:AVTransport:1",
            "Seek",
            {"InstanceID": "0", "Unit": "REL_TIME", "Target": target_time}
        )

    def set_volume(self, volume):
        """Dispatches SetVolume command (0-100%)."""
        vol = max(0, min(100, int(volume)))
        return self.soap_request(
            self.control_url_rendering,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "SetVolume",
            {"InstanceID": "0", "Channel": "Master", "DesiredVolume": str(vol)}
        )

    def set_mute(self, mute_bool):
        """Dispatches SetMute command."""
        desired = "1" if mute_bool else "0"
        return self.soap_request(
            self.control_url_rendering,
            "urn:schemas-upnp-org:service:RenderingControl:1",
            "SetMute",
            {"InstanceID": "0", "Channel": "Master", "DesiredMute": desired}
        )

    def refresh_state(self):
        """Polls current transport and playback position."""
        if not self.target_ip:
            return

        # AVTransport GetTransportInfo
        if self.control_url_transport:
            resp = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "GetTransportInfo",
                {"InstanceID": "0"}
            )
            if resp:
                m_state = re.search(r"<CurrentTransportState>([^<]+)</CurrentTransportState>", resp)
                if m_state:
                    with self.lock:
                        self.state["transport_state"] = m_state.group(1)
                        self.state["connected"] = True

            # GetPositionInfo
            pos_resp = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "GetPositionInfo",
                {"InstanceID": "0"}
            )
            if pos_resp:
                m_dur = re.search(r"<TrackDuration>([^<]+)</TrackDuration>", pos_resp)
                m_rel = re.search(r"<RelTime>([^<]+)</RelTime>", pos_resp)
                m_meta = re.search(r"<TrackMetaData>([^<]+)</TrackMetaData>", pos_resp)

                with self.lock:
                    if m_dur:
                        self.state["track_duration"] = m_dur.group(1)
                    if m_rel:
                        self.state["rel_time"] = m_rel.group(1)

                if m_meta:
                    meta_xml = m_meta.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                    m_title = re.search(r"<dc:title>([^<]+)</dc:title>", meta_xml)
                    m_artist = re.search(r"<dc:creator>([^<]+)</dc:creator>", meta_xml)
                    m_album = re.search(r"<upnp:album>([^<]+)</upnp:album>", meta_xml)
                    with self.lock:
                        if m_title:
                            self.state["track_title"] = m_title.group(1)
                        if m_artist:
                            self.state["track_artist"] = m_artist.group(1)
                        if m_album:
                            self.state["track_album"] = m_album.group(1)

        # RenderingControl GetVolume
        if self.control_url_rendering:
            vol_resp = self.soap_request(
                self.control_url_rendering,
                "urn:schemas-upnp-org:service:RenderingControl:1",
                "GetVolume",
                {"InstanceID": "0", "Channel": "Master"}
            )
            if vol_resp:
                m_vol = re.search(r"<CurrentVolume>([^<]+)</CurrentVolume>", vol_resp)
                if m_vol:
                    with self.lock:
                        self.state["volume"] = int(m_vol.group(1))

    def start_background_poll(self):
        """Starts the daemon thread polling state every 1.5 seconds."""
        def run_loop():
            while True:
                try:
                    if self.target_ip:
                        self.refresh_state()
                except Exception:
                    pass
                time.sleep(1.5)

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()


# Global controller manager
manager = BremenDeviceManager()


class BremenHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Serves the audiophile web interface and JSON REST API."""

    def log_message(self, format, *args):
        # Suppress spamming console output for status polling
        if "/api/status" not in self.path:
            super().log_message(format, *args)

    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path

        if path == "/api/status":
            self.send_json(manager.state)
        elif path == "/api/discover":
            devices = manager.discover_all_devices(timeout=3.0)
            self.send_json({"devices": devices})
        elif path in ["/", "/index.html"]:
            self.serve_ui()
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}

        if path == "/api/connect":
            ip = data.get("ip", "")
            transport = data.get("control_transport", "")
            rendering = data.get("control_rendering", "")
            name = data.get("friendly_name", "")
            success = manager.connect_to_device(ip, transport, rendering, name)
            self.send_json({"success": success, "ip": ip})

        elif path == "/api/control":
            action = data.get("action", "")
            val = data.get("value", None)

            if action == "play":
                manager.play()
            elif action == "pause":
                manager.pause()
            elif action == "stop":
                manager.stop()
            elif action == "next":
                manager.next_track()
            elif action == "prev":
                manager.previous_track()
            elif action == "seek" and val:
                manager.seek(val)
            elif action == "volume" and val is not None:
                manager.set_volume(val)
            elif action == "mute" and val is not None:
                manager.set_mute(val)
            elif action == "source" and val:
                with manager.lock:
                    manager.state["active_source"] = str(val)

            self.send_json({"status": "acknowledged", "action": action})
        else:
            self.send_error(404, "Endpoint not found")

    def send_json(self, data):
        out = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out)

    def serve_ui(self):
        """Renders the luxury audiophile web user interface with official vector SVGs."""
        html = """<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Silent Angel Bremen SL1P — Control Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #0b0e14;
      --bg-surface: #121721;
      --bg-elevated: #1a2232;
      --bg-card: #151b27;
      --border-subtle: #242f44;
      --border-focus: #c99d52;
      --accent-gold: #c99d52;
      --accent-gold-hover: #e0b468;
      --accent-gold-glow: rgba(201, 157, 82, 0.25);
      --text-main: #f0f4fc;
      --text-muted: #8b99b5;
      --text-dim: #54627d;
      --accent-cyan: #38bdf8;
      --danger: #f43f5e;
      --success: #10b981;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background-color: var(--bg-base);
      color: var(--text-main);
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      user-select: none;
    }

    /* Official SVG Logo Styles */
    .svg-icon {
      display: inline-block;
      vertical-align: middle;
      fill: currentColor;
    }

    .app-container {
      display: flex;
      flex: 1;
      height: calc(100vh - 88px);
      overflow: hidden;
    }

    /* Left Sidebar */
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
      gap: 14px;
    }

    .brand-logo-box {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, #1c2536, #121824);
      border: 1px solid var(--accent-gold);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px var(--accent-gold-glow);
    }

    .brand-text h1 {
      font-size: 17px;
      font-weight: 800;
      letter-spacing: 1px;
      color: var(--text-main);
    }

    .brand-text span {
      font-size: 10px;
      color: var(--accent-gold);
      text-transform: uppercase;
      letter-spacing: 2px;
      font-weight: 700;
    }

    .nav-section h3 {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: var(--text-dim);
      margin-bottom: 12px;
      font-weight: 700;
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
      font-size: 13.5px;
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
      background: linear-gradient(90deg, rgba(201, 157, 82, 0.12), transparent);
    }

    .device-card {
      margin-top: auto;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .device-status {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--danger);
      box-shadow: 0 0 8px var(--danger);
    }

    .status-dot.connected {
      background: var(--success);
      box-shadow: 0 0 8px var(--success);
    }

    .device-info h4 {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .device-info p {
      font-size: 11px;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }

    .btn-connect {
      background: transparent;
      border: 1px solid var(--accent-gold);
      color: var(--accent-gold);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      text-align: center;
    }

    .btn-connect:hover {
      background: var(--accent-gold);
      color: #0b0e14;
    }

    /* Main Viewport */
    .main-viewport {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 28px 40px;
      gap: 24px;
      overflow-y: auto;
      background: radial-gradient(circle at top right, rgba(201, 157, 82, 0.05), transparent 60%);
    }

    /* Header & Source Bar */
    .top-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }

    .header-title h2 {
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
    }

    .header-title p {
      font-size: 13px;
      color: var(--text-muted);
    }

    /* Official Protocol Logo Bar */
    .protocol-badges {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .source-pill {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 20px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      font-size: 11.5px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .source-pill:hover, .source-pill.active {
      border-color: var(--accent-gold);
      color: var(--text-main);
      background: var(--bg-elevated);
    }

    .source-pill.active {
      background: rgba(201, 157, 82, 0.15);
      border-color: var(--accent-gold);
      color: var(--accent-gold);
    }

    /* Telemetry HUD */
    .telemetry-row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }

    .hud-badge {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      font-size: 11.5px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
    }

    .hud-badge.gold {
      border-color: rgba(201, 157, 82, 0.4);
      color: var(--accent-gold);
      background: rgba(201, 157, 82, 0.08);
    }

    /* Hero Now Playing Stage */
    .stage-container {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      padding: 36px;
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 36px;
      align-items: center;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
      position: relative;
      overflow: hidden;
    }

    .stage-container::after {
      content: '';
      position: absolute;
      top: -50%;
      right: -20%;
      width: 400px;
      height: 400px;
      background: radial-gradient(circle, rgba(201, 157, 82, 0.08), transparent 70%);
      pointer-events: none;
    }

    .album-art-wrapper {
      position: relative;
      width: 280px;
      height: 280px;
      border-radius: 16px;
      background: linear-gradient(135deg, #1c2331, #0d121b);
      border: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6);
      overflow: hidden;
    }

    .album-art-wrapper img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: none;
    }

    .vinyl-groove {
      position: absolute;
      width: 250px;
      height: 250px;
      border-radius: 50%;
      border: 1px dashed rgba(201, 157, 82, 0.15);
      animation: spin 30s linear infinite;
    }

    @keyframes spin {
      100% { transform: rotate(360deg); }
    }

    .stage-meta {
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .format-tags {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .tag-hires-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      background: #000;
      border: 1px solid #c99d52;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 1px;
      color: #c99d52;
    }

    .track-title {
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.5px;
      line-height: 1.2;
      color: var(--text-main);
    }

    .track-artist {
      font-size: 18px;
      font-weight: 600;
      color: var(--accent-gold);
    }

    .track-album {
      font-size: 14px;
      color: var(--text-muted);
    }

    /* Scrub Bar */
    .scrub-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 10px;
    }

    .scrub-track {
      width: 100%;
      height: 6px;
      background: var(--bg-elevated);
      border-radius: 3px;
      position: relative;
      cursor: pointer;
      overflow: hidden;
    }

    .scrub-progress {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #c99d52, #e0b468);
      border-radius: 3px;
      transition: width 0.15s linear;
    }

    .scrub-times {
      display: flex;
      justify-content: space-between;
      font-size: 11.5px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
    }

    /* Bottom Master Player Bar */
    .master-bar {
      height: 88px;
      background: var(--bg-surface);
      border-top: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 32px;
      z-index: 100;
    }

    .bar-left {
      width: 280px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .bar-title {
      font-size: 13.5px;
      font-weight: 700;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .bar-artist {
      font-size: 11.5px;
      color: var(--text-muted);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .bar-centre {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .btn-circle {
      width: 42px;
      height: 42px;
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
      background: #252f44;
      border-color: var(--accent-gold);
      transform: scale(1.05);
    }

    .btn-play {
      width: 52px;
      height: 52px;
      background: var(--accent-gold);
      border: none;
      color: #0b0e14;
      box-shadow: 0 0 16px var(--accent-gold-glow);
    }

    .btn-play:hover {
      background: var(--accent-gold-hover);
      transform: scale(1.08);
    }

    .bar-right {
      width: 280px;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 14px;
    }

    .volume-slider-box {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 160px;
    }

    .vol-slider {
      -webkit-appearance: none;
      width: 100%;
      height: 4px;
      background: var(--bg-elevated);
      border-radius: 2px;
      outline: none;
    }

    .vol-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--accent-gold);
      cursor: pointer;
      box-shadow: 0 0 8px rgba(201, 157, 82, 0.7);
    }

    .vol-percent {
      font-size: 11.5px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
      width: 32px;
      text-align: right;
    }

    /* Discovery Modal Overlay */
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(5, 8, 12, 0.85);
      backdrop-filter: blur(10px);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 2000;
    }

    .modal-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      width: 90%;
      max-width: 580px;
      padding: 32px;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.8);
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .modal-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .modal-head h3 {
      font-size: 20px;
      font-weight: 800;
    }

    .btn-close {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 24px;
      cursor: pointer;
    }

    .scan-radar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      padding: 14px;
      background: var(--bg-elevated);
      border-radius: 10px;
      border: 1px dashed var(--accent-gold);
      color: var(--accent-gold);
      font-size: 13px;
      font-weight: 600;
    }

    .radar-pulse {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent-gold);
      box-shadow: 0 0 10px var(--accent-gold);
      animation: pulse 1.2s infinite ease-in-out;
    }

    @keyframes pulse {
      0% { transform: scale(0.8); opacity: 0.5; }
      50% { transform: scale(1.3); opacity: 1; }
      100% { transform: scale(0.8); opacity: 0.5; }
    }

    .device-results {
      max-height: 250px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding-right: 4px;
    }

    .device-result-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      transition: all 0.2s ease;
      cursor: pointer;
    }

    .device-result-item:hover {
      border-color: var(--accent-gold);
      background: #202838;
      transform: translateY(-1px);
    }

    .device-result-item.bremen-match {
      border-left: 4px solid var(--accent-gold);
      background: linear-gradient(90deg, rgba(201, 157, 82, 0.1), #1a2232);
    }

    .badge-bremen {
      background: var(--accent-gold);
      color: #0b0e14;
      font-size: 9.5px;
      font-weight: 800;
      padding: 2px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-left: 6px;
    }

    /* Mobile Responsive */
    @media (max-width: 900px) {
      .sidebar { display: none; }
      .app-container { height: auto; }
      .main-viewport { padding: 20px; }
      .stage-container { grid-template-columns: 1fr; padding: 24px; }
      .album-art-wrapper { width: 100%; height: 260px; }
      .master-bar { padding: 0 16px; }
      .bar-left { width: 140px; }
      .bar-right { display: none; }
    }
  </style>
</head>
<body>

  <!-- Hidden Official SVGs definitions -->
  <svg style="display:none;">
    <!-- UPnP Official Swoosh Logo -->
    <symbol id="icon-upnp" viewBox="0 0 100 100">
      <path d="M50 10 C27.9 10 10 27.9 10 50 C10 72.1 27.9 90 50 90 C72.1 90 90 72.1 90 50 C90 27.9 72.1 10 50 10 Z M50 22 C65.5 22 78 34.5 78 50 C78 65.5 65.5 78 50 78 C34.5 78 22 65.5 22 50 C22 34.5 34.5 22 50 22 Z" fill-opacity="0.2"/>
      <path d="M30 45 C30 35 40 30 50 30 C60 30 70 35 70 45 C70 52 65 58 58 60 L68 75 L56 75 L48 62 C46 62 44 62 42 62 L42 75 L30 75 Z M42 40 L42 52 C45 52 57 53 57 46 C57 40 46 40 42 40 Z"/>
    </symbol>

    <!-- DLNA Official Certified Logo -->
    <symbol id="icon-dlna" viewBox="0 0 100 60">
      <path d="M10 10 C10 10 25 50 50 30 C75 10 90 50 90 50 C90 50 75 10 50 30 C25 50 10 10 10 10 Z" stroke="currentColor" stroke-width="8" fill="none" stroke-linecap="round"/>
      <circle cx="28" cy="28" r="6"/>
      <circle cx="72" cy="32" r="6"/>
    </symbol>

    <!-- Apple AirPlay 2 Official Logo -->
    <symbol id="icon-airplay" viewBox="0 0 100 100">
      <path d="M15 70 L85 70 C88 70 90 68 90 65 L90 25 C90 22 88 20 85 20 L15 20 C12 20 10 22 10 25 L10 65 C10 68 12 70 15 70 Z M18 28 L82 28 L82 62 L18 62 Z"/>
      <polygon points="50,42 74,78 26,78"/>
    </symbol>

    <!-- Spotify Connect Official Logo -->
    <symbol id="icon-spotify" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="46"/>
      <path d="M30 38 C45 33 65 35 78 43" stroke="#0b0e14" stroke-width="8" stroke-linecap="round" fill="none"/>
      <path d="M33 50 C45 46 62 48 73 54" stroke="#0b0e14" stroke-width="6.5" stroke-linecap="round" fill="none"/>
      <path d="M36 62 C45 59 58 60 67 65" stroke="#0b0e14" stroke-width="5" stroke-linecap="round" fill="none"/>
    </symbol>

    <!-- Tidal Connect Official Logo (4 Diamonds) -->
    <symbol id="icon-tidal" viewBox="0 0 100 100">
      <polygon points="25,50 37.5,37.5 50,50 37.5,62.5"/>
      <polygon points="50,50 62.5,37.5 75,50 62.5,62.5"/>
      <polygon points="37.5,37.5 50,25 62.5,37.5 50,50"/>
      <polygon points="62.5,37.5 75,25 87.5,37.5 75,50"/>
    </symbol>

    <!-- Roon Ready Official Logo -->
    <symbol id="icon-roon" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" stroke-width="7"/>
      <path d="M40 30 L40 70 M40 45 C48 35 68 35 68 50 C68 62 50 62 40 62"/>
    </symbol>

    <!-- Qobuz Official Logo -->
    <symbol id="icon-qobuz" viewBox="0 0 100 100">
      <circle cx="48" cy="48" r="36" fill="none" stroke="currentColor" stroke-width="8"/>
      <circle cx="48" cy="48" r="14"/>
      <line x1="68" y1="68" x2="88" y2="88" stroke="currentColor" stroke-width="10" stroke-linecap="round"/>
    </symbol>

    <!-- Hi-Res Audio Official Gold Badge -->
    <symbol id="icon-hires" viewBox="0 0 120 70">
      <rect x="2" y="2" width="116" height="66" rx="6" fill="#000" stroke="#c99d52" stroke-width="4"/>
      <text x="60" y="32" fill="#c99d52" font-family="'Plus Jakarta Sans', sans-serif" font-weight="900" font-size="19" text-anchor="middle" letter-spacing="1">Hi-Res</text>
      <text x="60" y="54" fill="#c99d52" font-family="'Plus Jakarta Sans', sans-serif" font-weight="800" font-size="13" text-anchor="middle" letter-spacing="3">AUDIO</text>
    </symbol>

    <!-- DSD Official Direct Stream Digital Logo -->
    <symbol id="icon-dsd" viewBox="0 0 100 50">
      <text x="50" y="35" fill="currentColor" font-family="'JetBrains Mono', monospace" font-weight="800" font-size="28" text-anchor="middle" letter-spacing="2">DSD</text>
    </symbol>

    <!-- Silent Angel Wing Logo -->
    <symbol id="icon-angel" viewBox="0 0 100 100">
      <path d="M50 15 C58 28 72 38 90 40 C75 52 68 68 68 85 C58 70 52 55 50 15 Z"/>
      <path d="M50 15 C42 28 28 38 10 40 C25 52 32 68 32 85 C42 70 48 55 50 15 Z" opacity="0.75"/>
    </symbol>
  </svg>

  <div class="app-container">
    <!-- Desktop Sidebar -->
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-logo-box">
          <svg width="24" height="24" style="fill:var(--accent-gold);"><use href="#icon-angel"/></svg>
        </div>
        <div class="brand-text">
          <h1>BREMEN</h1>
          <span>STUDIO PRO</span>
        </div>
      </div>

      <div class="nav-section">
        <h3>Primary Playback</h3>
        <ul class="nav-list">
          <li class="nav-item active">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>
            Now Playing
          </li>
          <li class="nav-item" onclick="openDiscoveryModal()">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            Device Discovery
          </li>
          <li class="nav-item" onclick="alert('Internal NVMe SSD index ready for VitOS mount')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            Internal NVMe (4TB)
          </li>
          <li class="nav-item" onclick="alert('Internet Radio stream presets loaded')">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>
            Internet Radio
          </li>
        </ul>
      </div>

      <!-- Device Connection Status Card -->
      <div class="device-card">
        <div class="device-status">
          <div class="status-dot" id="side-status-dot"></div>
          <span id="side-status-text">Disconnected</span>
        </div>
        <div class="device-info">
          <h4 id="side-dev-name">No Device Connected</h4>
          <p id="side-dev-ip">No IP set</p>
        </div>
        <button class="btn-connect" onclick="openDiscoveryModal()">🔍 Discover Devices</button>
      </div>
    </aside>

    <!-- Main Viewport -->
    <main class="main-viewport">
      <div class="top-header">
        <div class="header-title">
          <h2>Master Playback Stage</h2>
          <p>Lossless Bit-Perfect Streaming Output for Silent Angel Bremen SL1P</p>
        </div>

        <!-- Official Streaming Protocols Selector -->
        <div class="protocol-badges">
          <div class="source-pill active" onclick="switchSource('UPnP / DLNA')">
            <svg width="18" height="18"><use href="#icon-upnp"/></svg>
            <span>UPnP / DLNA</span>
          </div>
          <div class="source-pill" onclick="switchSource('Apple AirPlay 2')">
            <svg width="18" height="18"><use href="#icon-airplay"/></svg>
            <span>AirPlay 2</span>
          </div>
          <div class="source-pill" onclick="switchSource('Spotify Connect')">
            <svg width="18" height="18" style="fill:#1db954"><use href="#icon-spotify"/></svg>
            <span>Spotify</span>
          </div>
          <div class="source-pill" onclick="switchSource('Tidal Connect')">
            <svg width="18" height="18"><use href="#icon-tidal"/></svg>
            <span>Tidal Connect</span>
          </div>
          <div class="source-pill" onclick="switchSource('Roon Ready')">
            <svg width="18" height="18"><use href="#icon-roon"/></svg>
            <span>Roon</span>
          </div>
          <div class="source-pill" onclick="switchSource('Qobuz')">
            <svg width="18" height="18"><use href="#icon-qobuz"/></svg>
            <span>Qobuz</span>
          </div>
        </div>
      </div>

      <!-- Real-Time Audio Telemetry HUD -->
      <div class="telemetry-row">
        <div class="hud-badge gold">
          <svg width="34" height="20"><use href="#icon-hires"/></svg>
          <span id="hud-format">FLAC 192kHz / 24-bit</span>
        </div>
        <div class="hud-badge">
          <svg width="32" height="16"><use href="#icon-dsd"/></svg>
          <span>DSD256 Native Direct</span>
        </div>
        <div class="hud-badge">
          <svg width="22" height="14"><use href="#icon-dlna"/></svg>
          <span id="hud-source">Source: UPnP / DLNA</span>
        </div>
        <div class="hud-badge">
          <span>Clock: Ultra-Low Jitter TCXO</span>
        </div>
        <div class="hud-badge">
          <span id="hud-output">Output: Balanced XLR</span>
        </div>
      </div>

      <!-- Hero Now Playing Stage -->
      <div class="stage-container">
        <div class="album-art-wrapper">
          <div class="vinyl-groove"></div>
          <svg width="90" height="90" style="fill:#2a364d; z-index:1;"><use href="#icon-angel"/></svg>
          <img id="stage-artwork" alt="Album Cover">
        </div>

        <div class="stage-meta">
          <div class="format-tags">
            <div class="tag-hires-badge">
              <svg width="16" height="10"><use href="#icon-hires"/></svg>
              <span>STUDIO MASTER</span>
            </div>
            <span style="font-size:12px; color:var(--text-muted); font-weight:600;" id="stage-codec">Lossless FLAC Stream</span>
          </div>

          <div>
            <h1 class="track-title" id="stage-title">Waiting for Stream...</h1>
            <h2 class="track-artist" id="stage-artist">Silent Angel Bremen SL1P</h2>
            <h3 class="track-album" id="stage-album">VitOS High-Resolution Audio Engine</h3>
          </div>

          <!-- Scrub Bar -->
          <div class="scrub-container">
            <div class="scrub-track" id="scrub-track" onclick="handleScrub(event)">
              <div class="scrub-progress" id="scrub-progress"></div>
            </div>
            <div class="scrub-times">
              <span id="time-elapsed">00:00</span>
              <span id="time-total">00:00</span>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>

  <!-- Master Player Bar (Fixed Bottom) -->
  <footer class="master-bar">
    <div class="bar-left">
      <div class="bar-title" id="bar-title">Waiting for Stream...</div>
      <div class="bar-artist" id="bar-artist">Silent Angel Bremen SL1P</div>
    </div>

    <div class="bar-centre">
      <button class="btn-circle" onclick="sendControl('prev')" title="Previous Track">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><polygon points="11 19 2 12 11 5 11 19"/><polygon points="22 19 13 12 22 5 22 19"/></svg>
      </button>
      <button class="btn-circle btn-play" id="btn-master-play" onclick="togglePlay()" title="Play / Pause (Spacebar)">
        <svg width="22" height="22" id="play-icon" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </button>
      <button class="btn-circle" onclick="sendControl('next')" title="Next Track">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 4 15 12 5 20 5 4"/><polygon points="13 4 23 12 13 20 13 4"/></svg>
      </button>
    </div>

    <div class="bar-right">
      <button class="btn-circle" id="btn-mute" onclick="toggleMute()" title="Mute Toggle (M)">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
      </button>
      <div class="volume-slider-box">
        <input type="range" class="vol-slider" id="vol-range" min="0" max="100" value="35" oninput="handleVolume(this.value)">
        <span class="vol-percent" id="vol-label">35%</span>
      </div>
    </div>
  </footer>

  <!-- Comprehensive Device Discovery Modal -->
  <div class="modal-overlay" id="discovery-modal">
    <div class="modal-card">
      <div class="modal-head">
        <h3>Discover Audio Streamers</h3>
        <button class="btn-close" onclick="closeDiscoveryModal()">&times;</button>
      </div>

      <p style="font-size:13px; color:var(--text-muted); line-height:1.5;">
        Bremen Studio scans your local Wi-Fi / Ethernet subnet using SSDP multicast, ARP table inspection, and port probes to identify your <strong>Silent Angel Bremen SL1P</strong> automatically.
      </p>

      <div class="scan-radar" id="radar-status">
        <div class="radar-pulse"></div>
        <span id="radar-text">Click "Start Network Scan" to search for devices</span>
      </div>

      <div style="display:flex; gap:10px;">
        <button class="btn-connect" style="flex:1; padding:12px;" onclick="triggerDeviceScan()">
          🔍 Start Network Scan
        </button>
      </div>

      <!-- Discovered Devices List -->
      <div class="device-results" id="discovery-list">
        <div style="font-size: 12px; color: var(--text-dim); text-align: center; padding: 18px;">
          No devices scanned yet. Click "Start Network Scan" above or enter IP below.
        </div>
      </div>

      <!-- Manual IP Fallback -->
      <div style="border-top: 1px solid var(--border-subtle); padding-top: 14px; display:flex; flex-direction:column; gap:8px;">
        <label style="font-size:11.5px; color:var(--text-muted); font-weight:600;">Manual IP Override (Optional)</label>
        <div style="display:flex; gap:8px;">
          <input type="text" id="manual-ip-field" placeholder="e.g. 192.168.1.150" style="flex:1; background:var(--bg-elevated); border:1px solid var(--border-subtle); border-radius:8px; padding:10px 14px; color:var(--text-main); font-family:'JetBrains Mono', monospace; font-size:13px; outline:none;">
          <button class="btn-connect" onclick="connectManualIp()">Connect</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    let isPlaying = false;
    let isMuted = false;

    // Periodic state polling
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        // Connection indicators
        const dot = document.getElementById('side-status-dot');
        const stText = document.getElementById('side-status-text');
        const devName = document.getElementById('side-dev-name');
        const devIp = document.getElementById('side-dev-ip');

        if (data.connected && data.device_ip) {
          dot.className = "status-dot connected";
          stText.innerText = "Online";
          devName.innerText = data.device_name;
          devIp.innerText = data.device_ip;
        } else {
          dot.className = "status-dot";
          stText.innerText = data.device_ip ? "Connecting..." : "Disconnected";
          if (data.device_ip) devIp.innerText = data.device_ip;
        }

        // Transport Play/Pause Icon
        isPlaying = (data.transport_state === "PLAYING");
        const playIcon = document.getElementById('play-icon');
        if (isPlaying) {
          playIcon.innerHTML = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';
        } else {
          playIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
        }

        // Metadata
        document.getElementById('stage-title').innerText = data.track_title;
        document.getElementById('stage-artist').innerText = data.track_artist;
        document.getElementById('stage-album').innerText = data.track_album;
        document.getElementById('bar-title').innerText = data.track_title;
        document.getElementById('bar-artist').innerText = data.track_artist;

        // Times & Scrub Progress
        document.getElementById('time-elapsed').innerText = data.rel_time;
        document.getElementById('time-total').innerText = data.track_duration;
        const curSec = parseTimeToSec(data.rel_time);
        const totSec = parseTimeToSec(data.track_duration);
        if (totSec > 0) {
          const pct = Math.min(100, Math.max(0, (curSec / totSec) * 100));
          document.getElementById('scrub-progress').style.width = pct + '%';
        }

        // Source and telemetry
        if (data.active_source) {
          document.getElementById('hud-source').innerText = "Source: " + data.active_source;
        }

        // Volume
        if (!document.getElementById('vol-range').matches(':active')) {
          document.getElementById('vol-range').value = data.volume;
          document.getElementById('vol-label').innerText = data.volume + '%';
        }

      } catch (err) {
        console.error("Status polling error:", err);
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
        sendControl('seek', secToTime(targetSec));
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

    function switchSource(sourceName) {
      document.querySelectorAll('.source-pill').forEach(el => {
        el.classList.toggle('active', el.innerText.trim().includes(sourceName.split(' ')[0]));
      });
      sendControl('source', sourceName);
    }

    // Discovery Modal Handlers
    function openDiscoveryModal() {
      document.getElementById('discovery-modal').style.display = 'flex';
    }

    function closeDiscoveryModal() {
      document.getElementById('discovery-modal').style.display = 'none';
    }

    async function triggerDeviceScan() {
      const radar = document.getElementById('radar-text');
      const list = document.getElementById('discovery-list');
      radar.innerText = "Scanning local subnet & SSDP renderers...";
      list.innerHTML = '<div style="font-size:12px; color:var(--accent-gold); text-align:center; padding:20px;">Scanning network endpoints...</div>';

      try {
        const res = await fetch('/api/discover');
        const data = await res.json();
        list.innerHTML = '';
        radar.innerText = `Scan completed. Found ${data.devices.length} network device(s).`;

        if (!data.devices || data.devices.length === 0) {
          list.innerHTML = '<div style="font-size:12px; color:var(--text-muted); text-align:center; padding:18px;">No streaming renderers discovered. You can enter your Bremen IP directly below.</div>';
          return;
        }

        data.devices.forEach(d => {
          const item = document.createElement('div');
          const isBremen = d.is_bremen || d.friendly_name.includes('Bremen') || d.friendly_name.includes('Silent Angel');
          item.className = 'device-result-item' + (isBremen ? ' bremen-match' : '');
          item.innerHTML = `
            <div>
              <div style="font-weight:700; font-size:14px; color:var(--text-main); display:flex; align-items:center;">
                ${d.friendly_name}
                ${isBremen ? '<span class="badge-bremen">Silent Angel</span>' : ''}
              </div>
              <div style="font-size:11.5px; color:var(--text-muted); font-family:'JetBrains Mono', monospace; margin-top:3px;">
                ${d.ip} ${d.method ? '• via ' + d.method : ''}
              </div>
            </div>
            <button class="btn-connect" style="padding:6px 14px;">Connect</button>
          `;
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
            closeDiscoveryModal();
            updateStatus();
          };
          list.appendChild(item);
        });
      } catch (err) {
        radar.innerText = "Scan encountered an error. Check local network connection.";
      }
    }

    async function connectManualIp() {
      const ip = document.getElementById('manual-ip-field').value.trim();
      if (!ip) return;
      await fetch('/api/connect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ip: ip, friendly_name: 'Silent Angel Bremen SL1P'})
      });
      closeDiscoveryModal();
      updateStatus();
    }

    // Desktop Keyboard Shortcuts
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


def run_server(requested_port=8090, auto_open=True):
    """Starts the Bremen Studio controller server on an available port."""
    port = get_available_port(requested_port)
    server_address = ("", port)
    httpd = http.server.ThreadingHTTPServer(server_address, BremenHTTPHandler)
    local_ip = get_local_ip()

    url_local = f"http://localhost:{port}"
    url_lan = f"http://{local_ip}:{port}"

    print("=" * 66, flush=True)
    print("  Silent Angel Bremen SL1P — Control Studio Online", flush=True)
    print("=" * 66, flush=True)
    print(f"  Laptop Browser:  {url_local}", flush=True)
    print(f"  Mobile Phone:    {url_lan}", flush=True)
    print("=" * 66, flush=True)
    print("  Press Ctrl+C to terminate the controller.", flush=True)
    print("=" * 66, flush=True)

    if auto_open:
        def open_browser():
            time.sleep(0.5)
            try:
                webbrowser.open(url_local)
            except Exception:
                pass

        threading.Thread(target=open_browser, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Bremen Studio server...", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    p = 8090
    no_open = False
    for arg in sys.argv[1:]:
        if arg.isdigit():
            p = int(arg)
        elif arg == "--no-open":
            no_open = True
    run_server(p, auto_open=not no_open)
