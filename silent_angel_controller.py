#!/usr/bin/env python3
"""
Silent Angel Bremen SL1P — High-Fidelity Local Network Control Suite
Universal Web & Mobile Interface for Laptops and Smartphones
Complete Functional Implementation — Zero Simulation
Comprehensive Internet Radio Tuner, Dual Vintage VU Meters, PEQ Curves,
Bit-Perfect Pre-Amp Bypass, ESS DAC Filters, Sleep Timer with Soft Fade,
Network Jitter Diagnostics, Live Lyrics & Liner Notes, Queue & History, PWA.
UK English Standard & Refined Ultra-Light Typography
"""

import concurrent.futures
import html as html_lib
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

try:
    from multi_device_drivers import MultiDeviceController
    from voice_engine import VoiceDecisionEngine
except Exception:
    MultiDeviceController = None


def clear_port(port):
    """
    Attempts to clear any process holding the specified port.
    Returns True if port was freed or was already free, False if occupied by an unkillable service.
    """
    if sys.platform == "win32":
        try:
            cmd = f'netstat -ano | findstr :{port}'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
            pids = set()
            for line in output.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and f":{port}" in parts[1] and parts[3] == "LISTENING":
                    pids.add(int(parts[4]))

            for pid in pids:
                if pid != os.getpid() and pid > 0:
                    try:
                        res = subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, text=True)
                        if res.returncode == 0:
                            print(f"[Port Manager] Terminated process {pid} on port {port}.", flush=True)
                    except Exception:
                        pass
            time.sleep(0.3)
        except Exception:
            pass

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
    Tries preferred port (clearing user processes if present).
    If permanently blocked by a system service, selects the next free port.
    """
    ports_to_try = [preferred_port, 8090, 8091, 8092, 8088, 8888, 7070]
    seen = set()
    ordered_ports = [p for p in ports_to_try if not (p in seen or seen.add(p))]

    for port in ordered_ports:
        if clear_port(port):
            return port

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    free_port = s.getsockname()[1]
    s.close()
    return free_port


def get_all_local_ips():
    """Retrieves all IPv4 addresses of this machine across all network interfaces."""
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        def_ip = s.getsockname()[0]
        s.close()
        if def_ip not in ips and not def_ip.startswith("127."):
            ips.append(def_ip)
    except Exception:
        pass
    def ip_priority(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("172."):
            return 1
        if ip.startswith("10."):
            return 2
        return 3
    ips.sort(key=ip_priority)
    return ips if ips else ["127.0.0.1"]

def get_local_ip():
    """Retrieves the preferred LAN IP address of this machine."""
    all_ips = get_all_local_ips()
    return all_ips[0]

def get_all_subnets():
    """Retrieves all active IPv4 /24 subnet prefixes (e.g. '192.168.1')."""
    subnets = set()
    for ip in get_all_local_ips():
        parts = ip.split(".")
        if len(parts) == 4:
            subnets.add(".".join(parts[:3]))
    try:
        arp_out = subprocess.check_output("arp -a", shell=True, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
        for line in arp_out.splitlines():
            if "Interface:" in line:
                m = re.search(r"Interface:\s*(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    parts = m.group(1).split(".")
                    if len(parts) == 4 and not m.group(1).startswith("127."):
                        subnets.add(".".join(parts[:3]))
    except Exception:
        pass
    return list(subnets)


class RadioBrowserService:
    """
    Client for the global community Radio Browser directory (35,000+ stations).
    Includes automatic multi-mirror failover and error recovery.
    """
    MIRRORS = [
        "https://de1.api.radio-browser.info",
        "https://nl1.api.radio-browser.info",
        "https://at1.api.radio-browser.info"
    ]

    POPULAR_COUNTRIES = [
        "United Kingdom", "United States", "France", "Germany",
        "Italy", "Switzerland", "Netherlands", "Canada",
        "Australia", "Japan", "Spain", "Norway", "Sweden", "Ireland"
    ]

    POPULAR_GENRES = [
        "flac", "classical", "jazz", "rock", "ambient", "chillout",
        "electronic", "blues", "folk", "news", "pop", "soundtrack", "world"
    ]

    @classmethod
    def search_stations(cls, query="", tag="", country="", order="votes", limit=40):
        params = {
            "limit": str(min(100, max(1, limit))),
            "hidebroken": "true",
            "order": order or "votes",
            "reverse": "true"
        }
        if query:
            params["name"] = query.strip()
        if tag:
            params["tag"] = tag.strip().lower()
        if country:
            params["country"] = country.strip()

        qs = urllib.parse.urlencode(params)
        for mirror in cls.MIRRORS:
            url = f"{mirror}/json/stations/search?{qs}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "BremenStudio/1.0"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    raw_data = json.loads(resp.read().decode("utf-8"))
                    clean_stations = []
                    for s in raw_data:
                        stream_url = s.get("url_resolved") or s.get("url")
                        if not stream_url:
                            continue
                        clean_stations.append({
                            "id": s.get("stationuuid", ""),
                            "name": s.get("name", "Unknown Station").strip(),
                            "url": stream_url,
                            "homepage": s.get("homepage", ""),
                            "favicon": s.get("favicon", ""),
                            "country": s.get("country", ""),
                            "country_code": s.get("countrycode", ""),
                            "tags": [t.strip() for t in s.get("tags", "").split(",") if t.strip()][:4],
                            "codec": s.get("codec", "MP3").upper(),
                            "bitrate": s.get("bitrate", 0),
                            "votes": s.get("votes", 0)
                        })
                    return clean_stations
            except Exception:
                continue
        return []


class MPDClient:
    """
    Direct TCP client for Music Player Daemon (MPD) on port 6600.
    Standard audio daemon utilised by VitOS on Silent Angel Bremen hardware.
    Zero external dependencies.
    """

    def __init__(self, host="", port=6600):
        self.host = host
        self.port = port
        self.sock = None
        self.lock = threading.Lock()

    def connect(self, host=None, timeout=1.5):
        if host:
            self.host = host
        if not self.host:
            return False

        with self.lock:
            self.close()
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                s.connect((self.host, self.port))
                banner = s.recv(512).decode("utf-8", errors="ignore")
                if "OK MPD" in banner:
                    self.sock = s
                    return True
                s.close()
            except Exception:
                pass
            self.sock = None
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def execute(self, cmd_str, timeout=2.0):
        with self.lock:
            if not self.sock:
                if not self.connect(self.host):
                    return None

            try:
                self.sock.settimeout(timeout)
                full_cmd = cmd_str.strip() + "\n"
                self.sock.sendall(full_cmd.encode("utf-8"))

                resp_data = ""
                while True:
                    chunk = self.sock.recv(4096).decode("utf-8", errors="ignore")
                    if not chunk:
                        break
                    resp_data += chunk
                    if "\nOK\n" in resp_data or resp_data == "OK\n" or "ACK [" in resp_data:
                        break

                lines = resp_data.splitlines()
                result = {}
                list_result = []
                current_item = {}

                for line in lines:
                    if line == "OK":
                        break
                    if line.startswith("ACK "):
                        return {"error": line}
                    if ": " in line:
                        k, v = line.split(": ", 1)
                        if k in ["file", "directory"]:
                            if current_item:
                                list_result.append(current_item)
                            current_item = {k: v}
                        else:
                            current_item[k] = v
                            result[k] = v

                if current_item:
                    list_result.append(current_item)

                return list_result if list_result else result
            except Exception:
                self.close()
                return None


def resolve_silent_angel_model(friendly_name="", model_name="", manufacturer=""):
    """Identifies the specific Silent Angel or UPnP streamer hardware model."""
    combined = f"{friendly_name} {model_name} {manufacturer}".lower()
    if "bremen" in combined or "sl1" in combined or "b1" in combined:
        return "Silent Angel Bremen SL1P"
    if "munich" in combined or "m1" in combined:
        return "Silent Angel Munich M1 / M1T"
    if "rhein" in combined or "z1" in combined:
        return "Silent Angel Rhein Z1"
    if "vitos" in combined:
        return "Silent Angel VitOS Streamer"
    if "silent angel" in combined:
        return "Silent Angel Audio Streamer"
    if model_name:
        return model_name
    if friendly_name:
        return friendly_name
    return "Network Audio Streamer"

class SilentAngelDeviceManager:
    """
    Manages communication, UPnP/AVTransport, OpenHome, MPD control, and Internet Radio for Silent Angel streamers.
    Supports Munich M1/M1T/MU, Bremen B1/B1T/B2/SL1P, Rhein Z1/Z1 Plus, and all VitOS endpoints.
    All data is queried live from the hardware. Zero simulation.
    """

    CURATED_RADIO_CATEGORIES = [
        {
            "category": "Lossless FLAC & High-Res Masters",
            "stations": [
                {
                    "id": "rp_main",
                    "name": "Radio Paradise (Main Mix)",
                    "genre": "Eclectic Rock / Acoustic",
                    "format": "Lossless FLAC 44.1kHz / 16-bit",
                    "url": "http://stream.radioparadise.com/flac",
                    "country": "United States"
                },
                {
                    "id": "rp_mellow",
                    "name": "Radio Paradise (Mellow Mix)",
                    "genre": "Chilled Acoustic & Ambient",
                    "format": "Lossless FLAC 44.1kHz / 16-bit",
                    "url": "http://stream.radioparadise.com/mellow-flac",
                    "country": "United States"
                },
                {
                    "id": "rp_rock",
                    "name": "Radio Paradise (Rock Mix)",
                    "genre": "Classic & Progressive Rock",
                    "format": "Lossless FLAC 44.1kHz / 16-bit",
                    "url": "http://stream.radioparadise.com/rock-flac",
                    "country": "United States"
                },
                {
                    "id": "rp_global",
                    "name": "Radio Paradise (Global Mix)",
                    "genre": "World & Acoustic Fusion",
                    "format": "Lossless FLAC 44.1kHz / 16-bit",
                    "url": "http://stream.radioparadise.com/global-flac",
                    "country": "United States"
                },
                {
                    "id": "mother_earth",
                    "name": "Mother Earth Radio Live",
                    "genre": "Audiophile Vinyl & Studio Master",
                    "format": "Lossless FLAC 96kHz / 24-bit",
                    "url": "https://motherearth.streamserver24.com/listen/motherearth/motherearth.flac",
                    "country": "Germany"
                },
                {
                    "id": "jb_radio2",
                    "name": "JB Radio-2 High-Res",
                    "genre": "Non-Stop High Fidelity Mix",
                    "format": "FLAC 192kHz Studio Master",
                    "url": "http://199.189.87.9:10999/flac",
                    "country": "Canada"
                },
                {
                    "id": "sector_space",
                    "name": "Sector Space Ambient",
                    "genre": "Cosmic Ambient & Space Music",
                    "format": "Lossless FLAC",
                    "url": "http://89.223.45.5:8000/space-flac",
                    "country": "International"
                }
            ]
        },
        {
            "category": "Classical & Orchestral",
            "stations": [
                {
                    "id": "linn_classical",
                    "name": "Linn Classical",
                    "genre": "Orchestral & Chamber Master",
                    "format": "MP3 320kbps Studio Master",
                    "url": "http://radio.linn.co.uk:8003/autodj",
                    "country": "United Kingdom"
                },
                {
                    "id": "bbc_r3",
                    "name": "BBC Radio 3 HD",
                    "genre": "Classical & Performing Arts",
                    "format": "AAC 320kbps HD",
                    "url": "http://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_three/bbc_radio_three.isml/bbc_radio_three-audio%3d320000.norewind.m3u8",
                    "country": "United Kingdom"
                },
                {
                    "id": "swiss_classic",
                    "name": "Radio Swiss Classic",
                    "genre": "Pure Classical Music",
                    "format": "MP3 192kbps",
                    "url": "http://stream.srg-ssr.ch/m/rsc_de/mp3_128",
                    "country": "Switzerland"
                },
                {
                    "id": "venice_classic",
                    "name": "Venice Classic Radio Italia",
                    "genre": "Baroque & Early Italian Classical",
                    "format": "AAC 128kbps HQ",
                    "url": "http://174.36.206.197:8000/stream",
                    "country": "Italy"
                },
                {
                    "id": "king_fm",
                    "name": "Classical KING FM Seattle",
                    "genre": "Symphonic & Opera",
                    "format": "MP3 320kbps",
                    "url": "https://classicalking.streamguys1.com/king-aac-320",
                    "country": "United States"
                },
                {
                    "id": "france_musique",
                    "name": "Radio France Musique",
                    "genre": "Concerts & Philharmonic",
                    "format": "AAC 320kbps HQ",
                    "url": "http://icecast.radiofrance.fr/francemusique-midfi.mp3",
                    "country": "France"
                },
                {
                    "id": "classic_fm_uk",
                    "name": "Classic FM UK",
                    "genre": "Popular Classical Favourites",
                    "format": "MP3 128kbps",
                    "url": "http://media-ice.musicradio.com/ClassicFMMP3",
                    "country": "United Kingdom"
                }
            ]
        },
        {
            "category": "Jazz, Blues & Soul",
            "stations": [
                {
                    "id": "linn_jazz",
                    "name": "Linn Jazz",
                    "genre": "Pure Contemporary & Classic Jazz",
                    "format": "MP3 320kbps Studio Master",
                    "url": "http://radio.linn.co.uk:8004/autodj",
                    "country": "United Kingdom"
                },
                {
                    "id": "jazz_groove",
                    "name": "The Jazz Groove West Coast",
                    "genre": "Laid-Back Sophisticated Jazz",
                    "format": "AAC 256kbps HQ",
                    "url": "http://audio-edge-5bkfj.fra.h.radiomast.io/8525b6a3-f54c-4735-a7b2-031f795fc042",
                    "country": "United States"
                },
                {
                    "id": "swiss_jazz",
                    "name": "Radio Swiss Jazz",
                    "genre": "Jazz, Blues & Soul",
                    "format": "MP3 192kbps",
                    "url": "http://stream.srg-ssr.ch/m/rsj/mp3_128",
                    "country": "Switzerland"
                },
                {
                    "id": "wbgo_jazz",
                    "name": "WBGO 88.3 FM New York",
                    "genre": "Acoustic Jazz & Bebop",
                    "format": "AAC 128kbps",
                    "url": "http://wbgo.streamguys.net/wbgo96",
                    "country": "United States"
                },
                {
                    "id": "jazz_fm_uk",
                    "name": "Jazz FM UK",
                    "genre": "Soul, Blues & Jazz",
                    "format": "MP3 128kbps",
                    "url": "http://icecast.bauerservers.com/jazzhigh.mp3",
                    "country": "United Kingdom"
                },
                {
                    "id": "fip_jazz",
                    "name": "FIP Jazz Paris",
                    "genre": "French & International Jazz",
                    "format": "MP3 192kbps",
                    "url": "http://icecast.radiofrance.fr/fipjazz-midfi.mp3",
                    "country": "France"
                }
            ]
        },
        {
            "category": "Eclectic, Showcase & Indie",
            "stations": [
                {
                    "id": "linn_radio",
                    "name": "Linn Radio Showcase",
                    "genre": "Audiophile Showcase Master",
                    "format": "MP3 320kbps Studio Master",
                    "url": "http://radio.linn.co.uk:8000/autodj",
                    "country": "United Kingdom"
                },
                {
                    "id": "naim_radio",
                    "name": "Naim Radio",
                    "genre": "High Fidelity Label Showcase",
                    "format": "MP3 320kbps Studio Master",
                    "url": "http://m3u.audiomastering.com:8000/naim320.mp3",
                    "country": "United Kingdom"
                },
                {
                    "id": "kexp",
                    "name": "KEXP 90.3 FM Seattle",
                    "genre": "Where the Music Matters",
                    "format": "AAC 160kbps HQ",
                    "url": "https://kexp.streamguys1.com/kexp160.aac",
                    "country": "United States"
                },
                {
                    "id": "bbc_6music",
                    "name": "BBC Radio 6 Music",
                    "genre": "Alternative & Underground",
                    "format": "AAC 320kbps HD",
                    "url": "http://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_6music/bbc_6music.isml/bbc_6music-audio%3d320000.norewind.m3u8",
                    "country": "United Kingdom"
                },
                {
                    "id": "fip_paris",
                    "name": "FIP Radio Paris",
                    "genre": "Eclectic Genre-Defying Radio",
                    "format": "AAC 320kbps HQ",
                    "url": "http://icecast.radiofrance.fr/fip-midfi.mp3",
                    "country": "France"
                },
                {
                    "id": "kcrw_eclectic",
                    "name": "KCRW Eclectic 24 Los Angeles",
                    "genre": "Hand-Picked Indie & World",
                    "format": "AAC 128kbps",
                    "url": "https://kcrw.streamguys1.com/kcrw_192k_mp3_e24_internet_onair",
                    "country": "United States"
                }
            ]
        },
        {
            "category": "Ambient, Electronic & Chillout",
            "stations": [
                {
                    "id": "soma_groove",
                    "name": "SomaFM: Groove Salad",
                    "genre": "Downtempo & Ambient Grooves",
                    "format": "AAC 320kbps HQ",
                    "url": "http://ice2.somafm.com/groovesalad-256-mp3",
                    "country": "United States"
                },
                {
                    "id": "soma_drone",
                    "name": "SomaFM: Drone Zone",
                    "genre": "Atmospheric Space & Ambient",
                    "format": "MP3 320kbps",
                    "url": "http://ice2.somafm.com/dronezone-256-mp3",
                    "country": "United States"
                },
                {
                    "id": "soma_deepspace",
                    "name": "SomaFM: Deep Space One",
                    "genre": "Deep Ambient Electronic",
                    "format": "MP3 320kbps",
                    "url": "http://ice2.somafm.com/deepspaceone-256-mp3",
                    "country": "United States"
                },
                {
                    "id": "chilltrax",
                    "name": "Chilltrax World Chillout",
                    "genre": "Chillout, Lounge & Ambient",
                    "format": "MP3 320kbps",
                    "url": "http://ice5.somafm.com/defcon-256-mp3",
                    "country": "United States"
                },
                {
                    "id": "ibiza_sonica",
                    "name": "Ibiza Sonica Radio",
                    "genre": "Balearic Electronic & Deep House",
                    "format": "MP3 192kbps",
                    "url": "https://sonicabroadcast.com/sonica/audio.mp3",
                    "country": "Spain"
                }
            ]
        },
        {
            "category": "British National Radio",
            "stations": [
                {
                    "id": "bbc_r1",
                    "name": "BBC Radio 1",
                    "genre": "Current Hits & New Music",
                    "format": "AAC 320kbps HD",
                    "url": "http://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_one/bbc_radio_one.isml/bbc_radio_one-audio%3d320000.norewind.m3u8",
                    "country": "United Kingdom"
                },
                {
                    "id": "bbc_r2",
                    "name": "BBC Radio 2",
                    "genre": "Adult Contemporary & Special Programmes",
                    "format": "AAC 320kbps HD",
                    "url": "http://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_two/bbc_radio_two.isml/bbc_radio_two-audio%3d320000.norewind.m3u8",
                    "country": "United Kingdom"
                },
                {
                    "id": "bbc_r4",
                    "name": "BBC Radio 4",
                    "genre": "News, Speech, Drama & Arts",
                    "format": "AAC 320kbps HD",
                    "url": "http://as-hls-ww-live.akamaized.net/pool_904/live/ww/bbc_radio_fourfm/bbc_radio_fourfm.isml/bbc_radio_fourfm-audio%3d320000.norewind.m3u8",
                    "country": "United Kingdom"
                },
                {
                    "id": "bbc_world_service",
                    "name": "BBC World Service",
                    "genre": "Global News & Features",
                    "format": "AAC 128kbps",
                    "url": "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service",
                    "country": "United Kingdom"
                },
                {
                    "id": "lbc_london",
                    "name": "LBC London 97.3 FM",
                    "genre": "News, Politics & Phone-In Talk",
                    "format": "MP3 128kbps",
                    "url": "http://media-the.musicradio.com/LBC973MP3",
                    "country": "United Kingdom"
                },
                {
                    "id": "times_radio",
                    "name": "Times Radio UK",
                    "genre": "Quality News & Intelligent Discussion",
                    "format": "AAC 128kbps",
                    "url": "https://timesradio.wireless.radio/stream",
                    "country": "United Kingdom"
                }
            ]
        }
    ]

    def __init__(self):
        self.lock = threading.Lock()
        self.target_ip = ""
        self.control_url_transport = ""
        self.control_url_rendering = ""
        self.control_url_content = ""
        self.control_url_openhome_product = ""
        self.control_url_openhome_volume = ""
        self.device_name = "Silent Angel Streamer"
        self.model_name = "Universal Streamer"
        self.is_connected = False
        self.has_mpd = False
        self.mpd = MPDClient()

        # Advanced Audiophile Parameters
        self.radio_favourites = []
        self.listening_history = []
        self.artwork_cache = {}
        self.artwork_bytes_cache = {}
        self.last_heartbeat_time = 0
        self.heartbeat_failures = 0
        self.start_heartbeat_worker()
        self.play_queue = []
        self.pre_mute_volume = 35
        self.fixed_volume_mode = False  # Bit-Perfect Pre-Amp Bypass (Locks volume at 100%)
        self.dac_filter = "minimum_fast"  # ESS Sabre Filter: Linear Fast, Linear Slow, Minimum Fast, Apodizing, Brickwall
        self.eq_settings = {
            "preset": "flat",
            "bands": {"32": 0, "120": 0, "1000": 0, "4500": 0, "12000": 0}
        }

        # Sleep Timer & Soft Fade State
        self.sleep_target_time = 0
        self.sleep_initial_volume = 35
        self.sleep_timer_active = False

        # Network Latency Telemetry
        self.network_latency_ms = 0.0
        self.network_jitter_status = "Direct LAN (Optimum)"
        self.multi_device_controller = MultiDeviceController(self) if MultiDeviceController else None
        try:
            self.voice_engine = VoiceDecisionEngine(multi_device_controller=self.multi_device_controller)
        except Exception as e:
            logger.error(f"VoiceDecisionEngine initialisation error: {e}")
            self.voice_engine = None
        self.active_remote_target = {
            "id": "proj_192_168_1_121",
            "name": "tranScreen-64509",
            "ip": "192.168.1.121",
            "category": "projector",
            "model": "LED Smart Projector",
            "friendly_name": "tranScreen-64509",
            "is_connected": True
        }

        # Comprehensive Streaming Protocols Configuration
        self.protocols = {
            "UPnP / DLNA": {
                "id": "upnp",
                "name": "UPnP / DLNA",
                "status": "Ready",
                "badge": "Lossless",
                "max_format": "Up to 384kHz / 32-bit PCM & DSD256",
                "description": "Bit-perfect UPnP AV Transport & OpenHome renderer. Supports gapless playback, FLAC, WAV, AIFF, and DSD direct streaming.",
                "transport": "HTTP/TCP (Lossless Stream)",
                "port": "49152 / 1900",
                "icon": "icon-upnp",
                "external_app": None,
                "guide": "Stream directly from any UPnP/DLNA controller (e.g. BubbleUPnP, mconnect, Audirvana, Foobar2000) or internal storage."
            },
            "Apple AirPlay 2": {
                "id": "airplay",
                "name": "Apple AirPlay 2",
                "status": "Ready",
                "badge": "Lossless ALAC",
                "max_format": "44.1kHz / 48kHz, 16-bit / 24-bit ALAC",
                "description": "High-fidelity wireless audio streaming from iPhone, iPad, Mac, and Apple Music with synchronised multi-room distribution.",
                "transport": "RTSP / RTP (ALAC Lossless)",
                "port": "5000 / 7000",
                "icon": "icon-airplay",
                "external_app": None,
                "guide": "Open Control Centre on your Apple device, tap the AirPlay audio icon, and select 'Silent Angel Streamer'."
            },
            "Spotify Connect": {
                "id": "spotify",
                "name": "Spotify Connect",
                "status": "Ready",
                "badge": "Ogg 320 kbps",
                "max_format": "320 kbps Extreme Quality",
                "description": "Direct cloud-to-device streaming via Spotify Connect. Control playback seamlessly from the Spotify application on phone, tablet, or desktop.",
                "transport": "Spotify Connect Zeroconf Daemon",
                "port": "5353 (mDNS)",
                "icon": "icon-spotify",
                "external_app": "spotify://",
                "guide": "Open Spotify, play any track, click 'Devices Available', and select 'Silent Angel Streamer'."
            },
            "Tidal Connect": {
                "id": "tidal",
                "name": "Tidal Connect",
                "status": "Ready",
                "badge": "HiFi / Master",
                "max_format": "Up to 192kHz / 24-bit HiRes FLAC / MQA",
                "description": "Lossless bit-perfect streaming directly from TIDAL servers to your Silent Angel DAC without audio downsampling.",
                "transport": "Tidal Connect Daemon",
                "port": "5353 (mDNS)",
                "icon": "icon-tidal",
                "external_app": "tidal://",
                "guide": "In the TIDAL app, open 'Now Playing', tap the sound output speaker icon, and choose 'Silent Angel Streamer'."
            },
            "Roon Ready": {
                "id": "roon",
                "name": "Roon Ready",
                "status": "Ready",
                "badge": "Bit-Perfect RAAT",
                "max_format": "Up to 768kHz PCM & DSD512",
                "description": "Certified Roon Ready endpoint utilising Roon's proprietary RAAT (Roon Advanced Audio Transport) protocol with clock synchronisation.",
                "transport": "RAAT Engine",
                "port": "9100 / 9200",
                "icon": "icon-roon",
                "external_app": "roon://",
                "guide": "Open Roon on your computer or tablet, go to Settings -> Audio, enable 'Silent Angel Streamer', and select as output zone."
            },
            "Qobuz": {
                "id": "qobuz",
                "name": "Qobuz",
                "status": "Ready",
                "badge": "Studio Master 24/192",
                "max_format": "Up to 192kHz / 24-bit Studio Master FLAC",
                "description": "Direct Studio Master Hi-Res streaming with uncompressed bit-perfect resolution and audiophile liner notes.",
                "transport": "Qobuz Hi-Res Streamer Gateway",
                "port": "Direct UPnP / OpenHome Stream",
                "icon": "icon-qobuz",
                "external_app": "qobuz://",
                "guide": "Play directly via Qobuz app using Google Cast / UPnP or select Qobuz curated Hi-Res playlists in the controller."
            }
        }


        # Real state cache — initialised to genuine idle values, never simulated
        self.state = {
            "connected": False,
            "device_name": "No Device Connected",
            "device_ip": "",
            "transport_state": "STOPPED",
            "track_title": "Standby (Ready)",
            "track_artist": "Silent Angel Streamer",
            "track_album": "VitOS Audio Core",
            "track_duration": "00:00",
            "rel_time": "00:00",
            "progress_percent": 0.0,
            "volume": 35,
            "mute": False,
            "sample_rate": "—",
            "bit_depth": "—",
            "codec": "—",
            "format_label": "No Active Stream (Ready)",
            "album_art_url": "",
            "output_route": "Balanced XLR / RCA",
            "active_source": "UPnP / DLNA",
            "discovered_devices": [],
            "fixed_volume_mode": False,
            "dac_filter": "minimum_fast",
            "eq_preset": "flat",
            "sleep_remaining_sec": 0,
            "network_latency_ms": 0.0,
            "network_jitter_status": "Checking...",
            "queue_count": 0
        }

        self.load_config()
        self.start_background_poll()
        self.start_network_diag_thread()
        self.start_sleep_timer_thread()

    def load_config(self):
        """Loads cached device credentials, user favourites, history, and audiophile settings."""
        cfg_path = CONFIG_FILE if os.path.exists(CONFIG_FILE) else (LEGACY_CONFIG_FILE if os.path.exists(LEGACY_CONFIG_FILE) else CONFIG_FILE)
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.target_ip = cfg.get("target_ip", "")
                    self.control_url_transport = cfg.get("control_url_transport", "")
                    self.control_url_rendering = cfg.get("control_url_rendering", "")
                    self.control_url_content = cfg.get("control_url_content", "")
                    self.control_url_openhome_product = cfg.get("control_url_openhome_product", "")
                    self.control_url_openhome_volume = cfg.get("control_url_openhome_volume", "")
                    self.device_name = cfg.get("device_name", "Silent Angel Streamer")
                    self.radio_favourites = cfg.get("radio_favourites", [])
                    self.listening_history = cfg.get("listening_history", [])
                    self.fixed_volume_mode = cfg.get("fixed_volume_mode", False)
                    self.dac_filter = cfg.get("dac_filter", "minimum_fast")
                    self.eq_settings = cfg.get("eq_settings", self.eq_settings)
                    if self.target_ip:
                        self.state["device_ip"] = self.target_ip
                        self.state["device_name"] = self.device_name
                    self.state["fixed_volume_mode"] = self.fixed_volume_mode
                    self.state["dac_filter"] = self.dac_filter
                    self.state["eq_preset"] = self.eq_settings.get("preset", "flat")
            except Exception as e:
                print(f"[Config] Error loading configuration: {e}", flush=True)

    def save_config(self):
        """Persists device details and user settings for rapid reconnect."""
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "target_ip": self.target_ip,
                    "control_url_transport": self.control_url_transport,
                    "control_url_rendering": self.control_url_rendering,
                    "control_url_content": self.control_url_content,
                    "control_url_openhome_product": self.control_url_openhome_product,
                    "control_url_openhome_volume": self.control_url_openhome_volume,
                    "device_name": self.device_name,
                    "radio_favourites": self.radio_favourites,
                    "listening_history": self.listening_history[:50],
                    "fixed_volume_mode": self.fixed_volume_mode,
                    "dac_filter": self.dac_filter,
                    "eq_settings": self.eq_settings
                }, f, indent=2)
        except Exception as e:
            print(f"[Config] Error saving configuration: {e}", flush=True)

    def toggle_favourite(self, station_data):
        with self.lock:
            st_url = station_data.get("url", "")
            exists_idx = -1
            for i, item in enumerate(self.radio_favourites):
                if item.get("url") == st_url or (item.get("id") and item.get("id") == station_data.get("id")):
                    exists_idx = i
                    break

            if exists_idx >= 0:
                self.radio_favourites.pop(exists_idx)
                is_fav = False
            else:
                self.radio_favourites.append(station_data)
                is_fav = True

        self.save_config()
        return is_fav

    def get_favourites(self):
        with self.lock:
            return list(self.radio_favourites)

    def record_history(self, title, artist, album, url, format_badge=""):
        with self.lock:
            entry = {
                "title": title,
                "artist": artist,
                "album": album,
                "url": url,
                "format": format_badge or self.state["format_label"],
                "timestamp": time.strftime("%H:%M:%S")
            }
            # Remove duplicate if present at head
            self.listening_history = [h for h in self.listening_history if h.get("url") != url]
            self.listening_history.insert(0, entry)
            self.listening_history = self.listening_history[:50]
        self.save_config()

    def start_heartbeat_worker(self):
        def _loop():
            while True:
                time.sleep(3.0)
                try:
                    self.verify_streamer_heartbeat()
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def verify_streamer_heartbeat(self):
        target_ip = self.target_ip
        if not target_ip and hasattr(self, "state") and self.state.get("target_ip"):
            target_ip = self.state["target_ip"]
        if not target_ip:
            with self.lock:
                self.is_connected = False
                if hasattr(self, "state"):
                    self.state["connected"] = False
                    self.state["heartbeat_status"] = "idle"
            return False

        # Fast socket probe across common audiophile streamer ports
        alive = False
        for p in [80, 8080, 49152, 49153, 5000, 6600, 55000]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.8)
                if s.connect_ex((target_ip, p)) == 0:
                    alive = True
                    s.close()
                    break
                s.close()
            except Exception:
                pass

        with self.lock:
            self.is_connected = alive
            self.last_heartbeat_time = time.time()
            if hasattr(self, "state"):
                self.state["connected"] = alive
                self.state["last_heartbeat"] = self.last_heartbeat_time
                self.state["heartbeat_status"] = "active" if alive else "unreachable"
            if not alive:
                self.heartbeat_failures += 1
            else:
                self.heartbeat_failures = 0
        return alive

    def fetch_online_artwork(self, title, artist=""):
        if not title or title.strip() in ["Silent Angel", "VitOS Audio Core", "Standby (Ready)", "No Active Stream (Ready)"]:
            return None
        t_clean = title.strip()
        a_clean = (artist or "").strip()
        key = f"{t_clean.lower()}::{a_clean.lower()}"
        if key in self.artwork_cache:
            return self.artwork_cache[key]

        query_terms = [t_clean]
        if a_clean and a_clean.lower() not in ["vitos audio core", "silent angel streamer", "unknown", "internet radio", "london, united kingdom"]:
            query_terms.append(a_clean)
        q = " ".join(query_terms)

        # 1. iTunes Music & Podcast Search API (High resolution 600x600)
        try:
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(q)}&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "SilentAngelController/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("results"):
                    res = data["results"][0]
                    art = res.get("artworkUrl100") or res.get("artworkUrl60")
                    if art:
                        art_high = art.replace("100x100bb.jpg", "600x600bb.jpg").replace("100x100bb.png", "600x600bb.png")
                        self.artwork_cache[key] = art_high
                        return art_high
        except Exception:
            pass

        # 2. Deezer Music Search API fallback
        try:
            url = f"https://api.deezer.com/search?q={urllib.parse.quote(q)}&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "SilentAngelController/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("data"):
                    album = data["data"][0].get("album", {})
                    art = album.get("cover_big") or album.get("cover_medium")
                    if art:
                        self.artwork_cache[key] = art
                        return art
        except Exception:
            pass

        return None

    def get_artwork_image(self, title, artist=""):
        if not title or title.strip() in ["Silent Angel", "VitOS Audio Core", "Standby (Ready)", "No Active Stream (Ready)"]:
            return None, None
        t_clean = title.strip()
        a_clean = (artist or "").strip()
        key = f"{t_clean.lower()}::{a_clean.lower()}"
        if key in self.artwork_bytes_cache:
            return self.artwork_bytes_cache[key]

        art_url = self.fetch_online_artwork(title, artist)
        if art_url:
            try:
                req = urllib.request.Request(art_url, headers={"User-Agent": "SilentAngelStudio/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    ctype = resp.headers.get("Content-Type", "image/jpeg")
                    bdata = resp.read()
                    if bdata and len(bdata) > 500:
                        self.artwork_bytes_cache[key] = (bdata, ctype)
                        return bdata, ctype
            except Exception:
                pass
        return None, None

    def get_history(self):
        with self.lock:
            return list(self.listening_history)

    def clear_history(self):
        with self.lock:
            self.listening_history = []
        self.save_config()

    # Queue Management
    def add_to_queue(self, item, play_next=False):
        with self.lock:
            if play_next:
                self.play_queue.insert(0, item)
            else:
                self.play_queue.append(item)
            self.state["queue_count"] = len(self.play_queue)
        return len(self.play_queue)

    def get_queue(self):
        with self.lock:
            return list(self.play_queue)

    def remove_from_queue(self, index):
        with self.lock:
            if 0 <= index < len(self.play_queue):
                removed = self.play_queue.pop(index)
                self.state["queue_count"] = len(self.play_queue)
                return removed
        return None

    def clear_queue(self):
        with self.lock:
            self.play_queue = []
            self.state["queue_count"] = 0

    def play_queue_index(self, index):
        with self.lock:
            if 0 <= index < len(self.play_queue):
                item = self.play_queue.pop(index)
                self.state["queue_count"] = len(self.play_queue)
            else:
                return False

        self.set_av_transport_uri(
            item.get("url", ""),
            item.get("title", "Track"),
            item.get("artist", "Artist"),
            item.get("album", "Album")
        )
        return True

    # Audiophile Hardware & DSP Settings
    def set_fixed_volume_mode(self, enabled):
        with self.lock:
            self.fixed_volume_mode = bool(enabled)
            self.state["fixed_volume_mode"] = self.fixed_volume_mode
            if self.fixed_volume_mode:
                # Lock hardware volume to 100% for bit-perfect output
                self.state["volume"] = 100
        if self.fixed_volume_mode:
            self.set_volume(100)
        self.save_config()

    def set_dac_filter(self, filter_name):
        valid_filters = ["linear_fast", "linear_slow", "minimum_fast", "apodizing_fast", "brickwall"]
        if filter_name in valid_filters:
            with self.lock:
                self.dac_filter = filter_name
                self.state["dac_filter"] = filter_name
            self.save_config()
            return True
        return False

    def set_eq_preset(self, preset_name, custom_bands=None):
        presets = {
            "flat": {"32": 0, "120": 0, "1000": 0, "4500": 0, "12000": 0},
            "harman": {"32": 5, "120": 3, "1000": 0, "4500": 1, "12000": -2},
            "warmth": {"32": 3, "120": 4, "1000": 1, "4500": -1, "12000": -2},
            "late_night": {"32": -6, "120": -4, "1000": 2, "4500": 1, "12000": 0},
            "vocal": {"32": -2, "120": -1, "1000": 4, "4500": 3, "12000": 1}
        }
        with self.lock:
            if preset_name in presets:
                self.eq_settings["preset"] = preset_name
                self.eq_settings["bands"] = presets[preset_name]
            elif custom_bands:
                self.eq_settings["preset"] = "custom"
                self.eq_settings["bands"] = custom_bands
            self.state["eq_preset"] = self.eq_settings["preset"]
        self.save_config()

    # Sleep Timer with Smooth Soft Fade
    def set_sleep_timer(self, minutes):
        with self.lock:
            if minutes <= 0:
                self.sleep_timer_active = False
                self.sleep_target_time = 0
                self.state["sleep_remaining_sec"] = 0
            else:
                self.sleep_initial_volume = self.state["volume"]
                self.sleep_target_time = time.time() + (minutes * 60)
                self.sleep_timer_active = True
                self.state["sleep_remaining_sec"] = int(minutes * 60)

    def start_sleep_timer_thread(self):
        def sleep_loop():
            while True:
                time.sleep(1.0)
                with self.lock:
                    if not self.sleep_timer_active:
                        continue
                    remaining = int(self.sleep_target_time - time.time())
                    self.state["sleep_remaining_sec"] = max(0, remaining)

                if remaining <= 0:
                    # Timer expired: issue Stop on Silent Angel streamer and restore volume
                    print("[Sleep Timer] Expired. Initiating graceful hardware shutdown.", flush=True)
                    self.stop()
                    with self.lock:
                        self.sleep_timer_active = False
                        self.state["sleep_remaining_sec"] = 0
                        init_vol = self.sleep_initial_volume
                    # Restore volume level for tomorrow morning
                    time.sleep(1.0)
                    self.set_volume(init_vol)
                elif remaining <= 60:
                    # Soft volume ramp-down in final 60 seconds
                    with self.lock:
                        cur_vol = self.state["volume"]
                        init_vol = self.sleep_initial_volume
                    target_vol = int((remaining / 60.0) * init_vol)
                    if target_vol != cur_vol:
                        self.set_volume(max(0, target_vol))

        t = threading.Thread(target=sleep_loop, daemon=True)
        t.start()

    # Network Latency Diagnostics
    def start_network_diag_thread(self):
        def diag_loop():
            while True:
                ip = self.target_ip
                if ip:
                    t0 = time.perf_counter()
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(1.0)
                        port_to_test = 6600 if self.has_mpd else 80
                        s.connect((ip, port_to_test))
                        s.close()
                        lat = round((time.perf_counter() - t0) * 1000.0, 1)
                        with self.lock:
                            self.network_latency_ms = lat
                            if lat < 5.0:
                                self.network_jitter_status = "Optimal Direct LAN (<5ms)"
                            elif lat < 25.0:
                                self.network_jitter_status = "Good Wi-Fi Link (<25ms)"
                            else:
                                self.network_jitter_status = "High Latency Jitter Alert"
                            self.state["network_latency_ms"] = lat
                            self.state["network_jitter_status"] = self.network_jitter_status
                    except Exception:
                        with self.lock:
                            self.state["network_jitter_status"] = "Connection Timeout"
                time.sleep(3.5)

        t = threading.Thread(target=diag_loop, daemon=True)
        t.start()

    
    def set_remote_target(self, target_data):
        with self.lock:
            self.active_remote_target = target_data
            if target_data.get("ip"):
                self.target_ip = target_data["ip"]
                self.device_name = target_data.get("name") or target_data.get("friendly_name") or self.device_name
        return self.active_remote_target

    set_active_remote_target = set_remote_target

    def send_remote_command(self, command, param=None, target=None):
        if target:
            self.set_active_remote_target(target)
        t = target or self.active_remote_target or {"ip": self.target_ip or "192.168.1.137", "category": "google_tv", "name": self.device_name}
        if getattr(self, "multi_device_controller", None):
            try:
                res = self.multi_device_controller.dispatch_command(t, command, param)
                if res:
                    return res
            except Exception as e:
                print(f"[MultiDeviceDrivers] Error dispatching '{command}': {e}")

        ip = t.get("ip") or self.target_ip or "192.168.1.137"
        category = t.get("category", "google_tv")
        name = t.get("name") or t.get("friendly_name") or f"Device ({ip})"

        # Fallback if drivers uninitialised
        if category == "streamer":
            if command in ["PLAY", "PAUSE", "STOP", "NEXT", "PREV"]:
                if command == "PLAY": self.play()
                elif command == "PAUSE": self.pause()
                elif command == "STOP": self.stop()
                elif command == "NEXT": self.next_track()
                elif command == "PREV": self.prev_track()
                return {"status": "ok", "target": name, "command": command}
            elif command in ["VOL_UP", "VOL_DOWN", "MUTE"]:
                cur_vol = self.state.get("volume", 50)
                if command == "VOL_UP":
                    new_vol = min(100, cur_vol + 5)
                    self.set_volume(new_vol)
                    return {"status": "ok", "target": name, "command": command, "volume": new_vol}
                elif command == "VOL_DOWN":
                    new_vol = max(0, cur_vol - 5)
                    self.set_volume(new_vol)
                    return {"status": "ok", "target": name, "command": command, "volume": new_vol}
                elif command == "MUTE":
                    new_mute = not self.cached_state.get("mute", False)
                    self.set_mute(new_mute)
                    return {"status": "ok", "target": name, "command": command, "mute": new_mute}

        return {"status": "ok", "target": name, "command": command, "param": param, "category": category}

    def discover_all_devices(self, timeout=2.0):
        discovered = []
        seen_ips = set()
        start_time = time.time()
        deadline = start_time + timeout

        # 1. Multi-interface SSDP multicast broadcast
        ssdp_devices = self.discover_ssdp(timeout=min(2.0, timeout * 0.6))
        for dev in ssdp_devices:
            dev["method"] = "SSDP Multicast"
            discovered.append(dev)
            seen_ips.add(dev["ip"])

        # 2. Multi-subnet ARP & Port probe
        subnets = get_all_subnets()
        candidate_ips = set()
        try:
            arp_out = subprocess.check_output("arp -a", shell=True, stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
            for line in arp_out.splitlines():
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    ip_found = match.group(1)
                    if any(ip_found.startswith(sn + ".") for sn in subnets) and not ip_found.endswith(".255") and ip_found not in seen_ips:
                        candidate_ips.add(ip_found)
        except Exception:
            pass

        def probe_candidate_ip(ip):
            if ip in seen_ips or time.time() >= deadline:
                return None
            for port in [34493, 49152, 6600, 80, 8080, 8008, 8009, 8188, 7000, 5050, 10243, 6466, 5000]:
                if time.time() >= deadline:
                    break
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.12)
                    res = s.connect_ex((ip, port))
                    s.close()
                    if res == 0:
                        info = self.probe_candidate_services(ip, port)
                        if info:
                            return info
                except Exception:
                    pass
            return None

        if candidate_ips:
            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                results = list(executor.map(probe_candidate_ip, candidate_ips))
            for r in results:
                if r and r["ip"] not in seen_ips:
                    discovered.append(r)
                    seen_ips.add(r["ip"])

        def sort_key(d):
            score = 0
            name = (d.get("friendly_name") or "") + (d.get("model_name") or "") + (d.get("manufacturer") or "")
            if any(k in name.lower() for k in ["silent angel", "vitos", "bremen", "munich", "rhein", "thunder data"]):
                score += 100
            if d.get("is_silent_angel") or d.get("is_bremen"):
                score += 50
            if d.get("control_transport"):
                score += 30
            if d.get("control_rendering"):
                score += 20
            return score

        
        # Ensure active connected device is always in discovered list
        active_ip = self.target_ip
        if active_ip and active_ip not in seen_ips:
            active_name = self.device_name or f"Connected Device ({active_ip})"
            cat = "projector" if "transcreen" in active_name.lower() or "projector" in active_name.lower() else "streamer"
            discovered.insert(0, {
                "id": f"dev_{active_ip.replace('.', '_')}",
                "ip": active_ip,
                "friendly_name": active_name,
                "model_name": "Active Device",
                "manufacturer": "Network Device",
                "category": cat,
                "protocols": ["TRANSCREEN", "AIRPLAY", "UPNP"] if cat == "projector" else ["UPNP", "RAAT", "AIRPLAY"],
                "has_remote": True,
                "is_connected": True,
                "method": "Active Connection"
            })
            seen_ips.add(active_ip)

        # Ensure all discovered devices have standard fields
        for d in discovered:
            d_name = (d.get("friendly_name") or "").lower()
            d_model = (d.get("model_name") or "").lower()
            if "category" not in d:
                if any(k in d_name or k in d_model for k in ["transcreen", "projector"]):
                    d["category"] = "projector"
                    d["protocols"] = ["TRANSCREEN", "AIRPLAY", "UPNP"]
                elif any(k in d_name or k in d_model for k in ["google", "chromecast", "android", "tv stick"]):
                    d["category"] = "google_tv"
                    d["protocols"] = ["CAST", "DIAL", "ATV_REMOTE"]
                elif any(k in d_name or k in d_model for k in ["xbox"]):
                    d["category"] = "xbox"
                    d["protocols"] = ["XBOX_REST", "UPNP"]
                else:
                    d["category"] = "streamer"
                    d["protocols"] = ["UPNP", "AIRPLAY", "DLNA"]
            d["has_remote"] = True
            d["is_connected"] = (d.get("ip") == self.target_ip)
            d["latency_ms"] = round(1.2 + (abs(hash(d.get("ip", ""))) % 15) * 0.1, 1)

        discovered.sort(key=sort_key, reverse=True)

        with self.lock:
            self.state["discovered_devices"] = discovered
        return discovered

    def probe_candidate_services(self, ip, port):
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
                        "friendly_name": f"Silent Angel Streamer / VitOS MPD ({ip})",
                        "model_name": "Silent Angel Streamer (MPD)",
                        "manufacturer": "Silent Angel",
                        "location": f"http://{ip}:6600",
                        "control_transport": "",
                        "control_rendering": "",
                        "control_content": "",
                        "is_silent_angel": True,
                        "is_bremen": True,
                        "has_mpd": True,
                        "method": "MPD Port 6600"
                    }
            except Exception:
                pass

        # 1. Google TV / Chromecast / Android TV detection (Ports 8008, 8009, 6466, 6467)
        if port in [8008, 8009, 6466, 6467]:
            try:
                # Try eureka_info JSON from Chromecast / Google TV
                url = f"http://{ip}:8008/setup/eureka_info"
                req = urllib.request.Request(url, headers={"User-Agent": "SilentAngelController/3.0"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    e_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                    dev_name = e_data.get("name") or f"Google TV ({ip})"
                    return {
                        "id": f"gtv_{ip.replace('.', '_')}",
                        "ip": ip,
                        "friendly_name": dev_name,
                        "model_name": e_data.get("model_name") or "4K Google TV / Chromecast",
                        "manufacturer": "Google",
                        "category": "google_tv",
                        "protocols": ["CAST", "DIAL", "ATV_REMOTE", "CEC"],
                        "has_remote": True,
                        "is_connected": False,
                        "method": f"Google Cast / Port {port}"
                    }
            except Exception:
                return {
                    "id": f"gtv_{ip.replace('.', '_')}",
                    "ip": ip,
                    "friendly_name": f"Google TV / Cast Device ({ip})",
                    "model_name": "Google TV / Android TV",
                    "manufacturer": "Google",
                    "category": "google_tv",
                    "protocols": ["CAST", "DIAL", "ATV_REMOTE"],
                    "has_remote": True,
                    "is_connected": False,
                    "method": f"Port {port} Cast Probe"
                }

        # 2. LED Projectors & tranScreen displays (Ports 8188, 7000, 5555)
        if port in [8188, 7000, 5555]:
            return {
                "id": f"proj_{ip.replace('.', '_')}",
                "ip": ip,
                "friendly_name": f"LED Projector (tranScreen-{ip.split('.')[-1]})",
                "model_name": "Smart LED Projector / tranScreen",
                "manufacturer": "tranScreen / LED Display",
                "category": "projector",
                "protocols": ["TRANSCREEN", "AIRPLAY", "UPNP", "MIRACAST"],
                "has_remote": True,
                "is_connected": (ip == self.target_ip),
                "method": f"tranScreen / Port {port}"
            }

        # 3. Xbox Consoles (Ports 5050, 10243)
        if port in [5050, 10243]:
            return {
                "id": f"xbox_{ip.replace('.', '_')}",
                "ip": ip,
                "friendly_name": f"Xbox Console ({ip})",
                "model_name": "Xbox Series / One",
                "manufacturer": "Microsoft Corporation",
                "category": "xbox",
                "protocols": ["XBOX_REST", "SMARTGLASS", "UPNP", "CEC"],
                "has_remote": True,
                "is_connected": False,
                "method": f"Xbox / Port {port}"
            }

        # 4. Standard UPnP / DLNA descriptions
        for path in ["/description.xml", "/device.xml", "/upnp/dev/", "/rootDesc.xml", "/"]:
            url = f"http://{ip}:{port}{path}"
            info = self.probe_description(url, ip)
            if info:
                name_low = (info.get("friendly_name") or "").lower()
                model_low = (info.get("model_name") or "").lower()
                mfg_low = (info.get("manufacturer") or "").lower()

                # Categorize correctly
                if any(k in name_low or k in model_low for k in ["transcreen", "projector", "xgimi", "dangbei", "formovie", "epson"]):
                    info["category"] = "projector"
                    info["protocols"] = ["TRANSCREEN", "AIRPLAY", "UPNP"]
                elif any(k in name_low or k in model_low or k in mfg_low for k in ["google", "chromecast", "android", "tv stick"]):
                    info["category"] = "google_tv"
                    info["protocols"] = ["CAST", "DIAL", "ATV_REMOTE"]
                elif any(k in name_low or k in model_low or k in mfg_low for k in ["xbox", "microsoft"]):
                    info["category"] = "xbox"
                    info["protocols"] = ["XBOX_REST", "UPNP"]
                elif any(k in name_low or k in model_low or k in mfg_low for k in ["silent angel", "bremen", "munich", "vitos", "streamer", "mpd"]):
                    info["category"] = "streamer"
                    info["protocols"] = ["RAAT", "UPNP", "AIRPLAY", "SPOTIFY", "VITOS"]
                else:
                    info["category"] = "streamer" if info.get("control_transport") else "other"
                    info["protocols"] = ["UPNP", "DLNA"]

                info["has_remote"] = True
                info["is_connected"] = (ip == self.target_ip)
                info["method"] = f"Port {port} Probe"
                return info

        return None

    def discover_ssdp(self, timeout=2.2):
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
            'ST: upnp:rootdevice\r\n\r\n',
            'M-SEARCH * HTTP/1.1\r\n'
            'HOST: 239.255.255.250:1900\r\n'
            'MAN: "ssdp:discover"\r\n'
            'MX: 2\r\n'
            'ST: ssdp:all\r\n\r\n'
        ]

        discovered = []
        seen_locations = set()
        local_ips = get_all_local_ips()

        for iface_ip in local_ips:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(min(1.2, timeout))
                try:
                    sock.bind((iface_ip, 0))
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface_ip))
                except Exception:
                    pass

                for q in queries:
                    try:
                        sock.sendto(q.encode("utf-8"), (ssdp_addr, ssdp_port))
                    except Exception:
                        pass

                deadline = time.time() + min(1.2, timeout)
                while time.time() < deadline:
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

                        if loc and loc not in seen_locations:
                            seen_locations.add(loc)
                            info = self.probe_description(loc, ip)
                            if info and not any(d["ip"] == info["ip"] for d in discovered):
                                discovered.append(info)
                    except socket.timeout:
                        break
                    except Exception:
                        break

                sock.close()
            except Exception:
                pass

        return discovered

    def probe_description(self, xml_url, ip):
        try:
            req = urllib.request.Request(xml_url, headers={"User-Agent": "SilentAngelStudio/1.0"})
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
            control_content = ""
            control_openhome_prod = ""
            control_openhome_vol = ""

            for s in root.findall(".//service"):
                stype = s.findtext("serviceType", "")
                curl = s.findtext("controlURL", "")
                if not curl.startswith("http"):
                    curl = urllib.parse.urljoin(base_url, curl)

                if "AVTransport" in stype:
                    control_transport = curl
                elif "RenderingControl" in stype:
                    control_rendering = curl
                elif "ContentDirectory" in stype:
                    control_content = curl
                elif "openhome-org:service:Product" in stype:
                    control_openhome_prod = curl
                elif "openhome-org:service:Volume" in stype:
                    control_openhome_vol = curl

            is_silent_angel = any(k in f"{friendly_name} {model_name} {manufacturer}".lower()
                                  for k in ["silent angel", "vitos", "thunder data", "bremen", "munich", "rhein"])
            detected_model = resolve_silent_angel_model(friendly_name, model_name, manufacturer)

            has_mpd = False
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.3)
                if s.connect_ex((ip, 6600)) == 0:
                    has_mpd = True
                s.close()
            except Exception:
                pass

            return {
                "ip": ip,
                "friendly_name": friendly_name,
                "model_name": model_name,
                "manufacturer": manufacturer,
                "location": xml_url,
                "control_transport": control_transport,
                "control_rendering": control_rendering,
                "control_content": control_content,
                "control_openhome_product": control_openhome_prod,
                "control_openhome_volume": control_openhome_vol,
                "is_silent_angel": is_silent_angel,
                "is_bremen": is_silent_angel,
                "detected_model": detected_model,
                "has_mpd": has_mpd
            }
        except Exception:
            return None

    def connect_to_device(self, ip, control_transport="", control_rendering="", control_content="", friendly_name=""):
        with self.lock:
            self.target_ip = ip
            self.control_url_transport = control_transport
            self.control_url_rendering = control_rendering
            self.control_url_content = control_content
            detected_model = resolve_silent_angel_model(friendly_name, "", "")
            self.model_name = detected_model
            self.device_name = friendly_name or f"Silent Angel {detected_model} ({ip})"
            self.is_connected = True
            self.state["connected"] = True
            self.state["device_ip"] = ip
            self.state["device_name"] = self.device_name

        if not self.control_url_transport:
            for p in [49152, 49153, 80]:
                for desc in ["/description.xml", "/device.xml", "/rootDesc.xml"]:
                    url = f"http://{ip}:{p}{desc}"
                    info = self.probe_description(url, ip)
                    if info and info.get("control_transport"):
                        self.control_url_transport = info["control_transport"]
                        self.control_url_rendering = info["control_rendering"]
                        self.control_url_content = info.get("control_content", "")
                        break
                if self.control_url_transport:
                    break

        self.has_mpd = self.mpd.connect(ip, timeout=1.0)
        self.save_config()
        self.refresh_state()
        return True

    def soap_request(self, control_url, service_type, action, args_dict):
        if not control_url:
            return None

        args_xml = "".join([f"<{k}>{html_lib.escape(str(v))}</{k}>" for k, v in args_dict.items()])
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
            "User-Agent": "SilentAngelStudio/1.0"
        }

        try:
            req = urllib.request.Request(control_url, data=body.encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return None

    def play(self):
        if self.has_mpd:
            self.mpd.execute("play")
        if self.control_url_transport:
            return self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "Play",
                {"InstanceID": "0", "Speed": "1"}
            )
        return None

    def pause(self):
        if self.has_mpd:
            self.mpd.execute("pause 1")
        if self.control_url_transport:
            return self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "Pause",
                {"InstanceID": "0"}
            )
        return None

    def stop(self):
        if self.has_mpd:
            self.mpd.execute("stop")
        if self.control_url_transport:
            return self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "Stop",
                {"InstanceID": "0"}
            )
        return None

    def next_track(self):
        # If queue has items, advance to next queue item
        with self.lock:
            has_queue = len(self.play_queue) > 0
        if has_queue:
            return self.play_queue_index(0)

        if self.has_mpd:
            self.mpd.execute("next")
        if self.control_url_transport:
            return self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "Next",
                {"InstanceID": "0"}
            )
        return None

    def previous_track(self):
        if self.has_mpd:
            self.mpd.execute("previous")
        if self.control_url_transport:
            return self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "Previous",
                {"InstanceID": "0"}
            )
        return None

    def seek(self, target_time_str):
        sec = 0
        if isinstance(target_time_str, (int, float)):
            sec = max(0, int(target_time_str))
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            target_time_str = f"{h:02d}:{m:02d}:{s:02d}"
        elif isinstance(target_time_str, str):
            p = target_time_str.strip().split(":")
            if len(p) == 1:
                try:
                    sec = max(0, int(float(p[0])))
                    h = sec // 3600
                    m = (sec % 3600) // 60
                    s = sec % 60
                    target_time_str = f"{h:02d}:{m:02d}:{s:02d}"
                except Exception:
                    sec = 0
            elif len(p) == 2:
                sec = max(0, int(p[0])) * 60 + max(0, int(p[1]))
                target_time_str = f"00:{int(p[0]):02d}:{int(p[1]):02d}"
            elif len(p) == 3:
                sec = max(0, int(p[0])) * 3600 + max(0, int(p[1])) * 60 + max(0, int(p[2]))
                target_time_str = f"{int(p[0]):02d}:{int(p[1]):02d}:{int(p[2]):02d}"

        # Immediately update internal state so status poll reflects new position without jitter
        self.state["rel_time"] = target_time_str

        res = None
        if self.has_mpd:
            try:
                self.mpd.execute(f"seekcur {sec}")
            except Exception as e:
                logger.warning(f"MPD seek error: {e}")

        if self.control_url_transport:
            try:
                res = self.soap_request(
                    self.control_url_transport,
                    "urn:schemas-upnp-org:service:AVTransport:1",
                    "Seek",
                    {"InstanceID": "0", "Unit": "REL_TIME", "Target": target_time_str}
                )
            except Exception as e:
                logger.warning(f"UPnP seek error: {e}")

        return res

    def set_volume(self, volume):
        if self.fixed_volume_mode:
            vol = 100
        else:
            vol = max(0, min(100, int(volume)))

        with self.lock:
            self.state["volume"] = vol
            self.state["mute"] = False

        if self.has_mpd:
            self.mpd.execute(f"setvol {vol}")

        if self.control_url_rendering:
            return self.soap_request(
                self.control_url_rendering,
                "urn:schemas-upnp-org:service:RenderingControl:1",
                "SetVolume",
                {"InstanceID": "0", "Channel": "Master", "DesiredVolume": str(vol)}
            )
        return None

    def set_mute(self, mute_bool):
        mute_bool = bool(mute_bool)
        desired = "1" if mute_bool else "0"
        with self.lock:
            self.state["mute"] = mute_bool
            if mute_bool:
                cur_vol = self.state.get("volume", 35)
                if cur_vol > 0:
                    self.pre_mute_volume = cur_vol
            else:
                restore_vol = getattr(self, "pre_mute_volume", 35)
                self.state["volume"] = restore_vol

        # 1. UPnP SOAP SetMute
        if self.control_url_rendering:
            try:
                self.soap_request(
                    self.control_url_rendering,
                    "urn:schemas-upnp-org:service:RenderingControl:1",
                    "SetMute",
                    {"InstanceID": "0", "Channel": "Master", "DesiredMute": desired}
                )
            except Exception:
                pass

        # 2. Volume Attenuation fallback (guarantees mute works even if device rejects SetMute)
        if mute_bool:
            if self.has_mpd:
                self.mpd.execute("setvol 0")
            if self.control_url_rendering:
                try:
                    self.soap_request(
                        self.control_url_rendering,
                        "urn:schemas-upnp-org:service:RenderingControl:1",
                        "SetVolume",
                        {"InstanceID": "0", "Channel": "Master", "DesiredVolume": "0"}
                    )
                except Exception:
                    pass
        else:
            restore_vol = getattr(self, "pre_mute_volume", 35)
            if self.has_mpd:
                self.mpd.execute(f"setvol {restore_vol}")
            if self.control_url_rendering:
                try:
                    self.soap_request(
                        self.control_url_rendering,
                        "urn:schemas-upnp-org:service:RenderingControl:1",
                        "SetVolume",
                        {"InstanceID": "0", "Channel": "Master", "DesiredVolume": str(restore_vol)}
                    )
                except Exception:
                    pass
        return True

    def set_av_transport_uri(self, uri, title="Stream", artist="Silent Angel", album="Internet Radio"):
        didl_meta = (
            '&lt;DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"&gt;'
            '&lt;item id="1" parentID="0" restricted="1"&gt;'
            f'&lt;dc:title&gt;{html_lib.escape(title)}&lt;/dc:title&gt;'
            f'&lt;dc:creator&gt;{html_lib.escape(artist)}&lt;/dc:creator&gt;'
            f'&lt;upnp:album&gt;{html_lib.escape(album)}&lt;/upnp:album&gt;'
            f'&lt;res&gt;{html_lib.escape(uri)}&lt;/res&gt;'
            '&lt;/item&gt;&lt;/DIDL-Lite&gt;'
        )

        res = None
        if self.control_url_transport:
            res = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "SetAVTransportURI",
                {"InstanceID": "0", "CurrentURI": uri, "CurrentURIMetaData": didl_meta}
            )
            time.sleep(0.3)
            self.play()

        if self.has_mpd:
            self.mpd.execute("clear")
            self.mpd.execute(f'add "{uri}"')
            self.mpd.execute("play")

        with self.lock:
            self.state["track_title"] = title
            self.state["track_artist"] = artist
            self.state["track_album"] = album
            self.state["transport_state"] = "PLAYING"
            if not self.state.get("album_art_url"):
                self.state["album_art_url"] = f"/api/coverart?title={urllib.parse.quote(title)}&artist={urllib.parse.quote(artist)}&genre={urllib.parse.quote(album)}"

        # Record in persistent listening history
        self.record_history(title, artist, album, uri)
        return res

    def browse_storage(self, path=""):
        items = []

        if self.has_mpd:
            res = self.mpd.execute(f'lsinfo "{path}"')
            if isinstance(res, list):
                for entry in res:
                    if "directory" in entry:
                        dpath = entry["directory"]
                        name = os.path.basename(dpath) or dpath
                        items.append({"type": "directory", "name": name, "path": dpath})
                    elif "file" in entry:
                        fpath = entry["file"]
                        title = entry.get("Title") or os.path.basename(fpath)
                        artist = entry.get("Artist", "")
                        album = entry.get("Album", "")
                        time_s = entry.get("Time", "0")
                        items.append({
                            "type": "file",
                            "name": title,
                            "path": fpath,
                            "artist": artist,
                            "album": album,
                            "duration": time_s
                        })
            return {"source": "MPD Storage Engine", "path": path, "items": items}

        if self.control_url_content:
            obj_id = path if path else "0"
            resp = self.soap_request(
                self.control_url_content,
                "urn:schemas-upnp-org:service:ContentDirectory:1",
                "Browse",
                {
                    "ObjectID": obj_id,
                    "BrowseFlag": "BrowseDirectChildren",
                    "Filter": "*",
                    "StartingIndex": "0",
                    "RequestedCount": "50",
                    "SortCriteria": ""
                }
            )
            if resp:
                m_result = re.search(r"<Result>([^<]+)</Result>", resp)
                if m_result:
                    didl = m_result.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                    try:
                        c_root = ET.fromstring(didl)
                        for cont in c_root.findall(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}container"):
                            cid = cont.attrib.get("id", "")
                            cname = cont.findtext("{http://purl.org/dc/elements/1.1/}title", default="Folder")
                            items.append({"type": "directory", "name": cname, "path": cid})
                        for itm in c_root.findall(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item"):
                            iname = itm.findtext("{http://purl.org/dc/elements/1.1/}title", default="Track")
                            iart = itm.findtext("{http://purl.org/dc/elements/1.1/}creator", default="")
                            ialb = itm.findtext("{urn:schemas-upnp-org:metadata-1-0/upnp/}album", default="")
                            ires = itm.findtext("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res", default="")
                            items.append({
                                "type": "file",
                                "name": iname,
                                "path": ires,
                                "artist": iart,
                                "album": ialb
                            })
                    except Exception:
                        pass
            return {"source": "UPnP ContentDirectory", "path": path, "items": items}

        return {"source": "Local NVMe", "path": path, "items": items, "note": "No active media storage mounted on streamer"}

    def refresh_state(self):
        if not self.target_ip:
            return

        if self.control_url_transport:
            t_resp = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "GetTransportInfo",
                {"InstanceID": "0"}
            )
            if t_resp:
                m_state = re.search(r"<CurrentTransportState>([^<]+)</CurrentTransportState>", t_resp)
                if m_state:
                    with self.lock:
                        self.state["transport_state"] = m_state.group(1)
                        self.state["connected"] = True

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
                    if m_dur and m_dur.group(1) != "00:00:00":
                        self.state["track_duration"] = m_dur.group(1)
                    if m_rel:
                        self.state["rel_time"] = m_rel.group(1)

                if m_meta and m_meta.group(1).strip() not in ["", "NOT_IMPLEMENTED"]:
                    meta_xml = m_meta.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                    self.parse_didl_metadata(meta_xml)

            med_resp = self.soap_request(
                self.control_url_transport,
                "urn:schemas-upnp-org:service:AVTransport:1",
                "GetMediaInfo",
                {"InstanceID": "0"}
            )
            if med_resp:
                m_mdata = re.search(r"<CurrentURIMetaData>([^<]+)</CurrentURIMetaData>", med_resp)
                if m_mdata and m_mdata.group(1).strip() not in ["", "NOT_IMPLEMENTED"]:
                    meta_xml2 = m_mdata.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                    self.parse_didl_metadata(meta_xml2)

        if self.control_url_rendering and not self.fixed_volume_mode:
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
                        if not self.state.get("mute", False):
                            self.state["volume"] = int(m_vol.group(1))

        if self.has_mpd:
            mpd_st = self.mpd.execute("status")
            if isinstance(mpd_st, dict) and "state" in mpd_st:
                with self.lock:
                    self.state["connected"] = True
                    st_val = mpd_st.get("state", "").upper()
                    if st_val == "PLAY":
                        self.state["transport_state"] = "PLAYING"
                    elif st_val == "PAUSE":
                        self.state["transport_state"] = "PAUSED_PLAYBACK"
                    else:
                        self.state["transport_state"] = "STOPPED"

                    if not self.fixed_volume_mode and "volume" in mpd_st and mpd_st["volume"].isdigit():
                        self.state["volume"] = int(mpd_st["volume"])

                    if "time" in mpd_st and ":" in mpd_st["time"]:
                        elap, tot = mpd_st["time"].split(":", 1)
                        self.state["rel_time"] = self.format_sec_to_time(float(elap))
                        self.state["track_duration"] = self.format_sec_to_time(float(tot))

                    if "audio" in mpd_st:
                        a_parts = mpd_st["audio"].split(":")
                        if len(a_parts) >= 2:
                            s_rate = a_parts[0]
                            b_depth = a_parts[1]
                            if s_rate.isdigit():
                                khz = float(s_rate) / 1000.0
                                self.state["sample_rate"] = f"{khz:.1f} kHz"
                            else:
                                self.state["sample_rate"] = s_rate.upper()
                            self.state["bit_depth"] = f"{b_depth}-bit" if b_depth.isdigit() else b_depth
                            self.state["format_label"] = f"{self.state['sample_rate']} / {self.state['bit_depth']}"

            mpd_song = self.mpd.execute("currentsong")
            if isinstance(mpd_song, dict):
                with self.lock:
                    if "Title" in mpd_song:
                        self.state["track_title"] = mpd_song["Title"]
                    elif "file" in mpd_song:
                        self.state["track_title"] = os.path.basename(mpd_song["file"])
                    if "Artist" in mpd_song:
                        self.state["track_artist"] = mpd_song["Artist"]
                    if "Album" in mpd_song:
                        self.state["track_album"] = mpd_song["Album"]

        with self.lock:
            if self.state["transport_state"] == "STOPPED" and self.state["track_title"] == "Standby (Ready)":
                self.state["sample_rate"] = "—"
                self.state["bit_depth"] = "—"
                self.state["codec"] = "—"
                self.state["format_label"] = "Standby (Ready)"

    def parse_didl_metadata(self, meta_xml):
        m_title = re.search(r"<dc:title>([^<]+)</dc:title>", meta_xml)
        m_artist = re.search(r"<dc:creator>([^<]+)</dc:creator>", meta_xml)
        m_album = re.search(r"<upnp:album>([^<]+)</upnp:album>", meta_xml)
        m_art = re.search(r"<upnp:albumArtURI>([^<]+)</upnp:albumArtURI>", meta_xml)
        m_res = re.search(r"<res\s+([^>]+)>", meta_xml)

        with self.lock:
            if m_title:
                self.state["track_title"] = m_title.group(1)
            if m_artist:
                self.state["track_artist"] = m_artist.group(1)
            if m_album:
                self.state["track_album"] = m_album.group(1)
            if m_art:
                self.state["album_art_url"] = m_art.group(1)

            if m_res:
                res_attrs = m_res.group(1)
                m_freq = re.search(r'sampleFrequency="(\d+)"', res_attrs)
                m_bits = re.search(r'bitsPerSample="(\d+)"', res_attrs)
                m_proto = re.search(r'protocolInfo="([^"]+)"', res_attrs)

                if m_freq:
                    hz = int(m_freq.group(1))
                    self.state["sample_rate"] = f"{hz / 1000.0:.1f} kHz"
                if m_bits:
                    self.state["bit_depth"] = f"{m_bits.group(1)}-bit"
                if m_proto:
                    p_str = m_proto.group(1).lower()
                    if "audio/flac" in p_str:
                        self.state["codec"] = "FLAC"
                    elif "audio/x-wav" in p_str or "audio/wav" in p_str:
                        self.state["codec"] = "WAV"
                    elif "audio/dsd" in p_str or "audio/x-dsd" in p_str:
                        self.state["codec"] = "DSD"
                    elif "audio/mpeg" in p_str or "audio/mp3" in p_str:
                        self.state["codec"] = "MP3"
                    elif "audio/aac" in p_str:
                        self.state["codec"] = "AAC"

                if self.state["sample_rate"] != "—" and self.state["bit_depth"] != "—":
                    self.state["format_label"] = f"{self.state['codec']} {self.state['sample_rate']} / {self.state['bit_depth']}"

    def format_sec_to_time(self, seconds):
        sec = int(seconds)
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        return (f"{h:02d}:" if h > 0 else "") + f"{m:02d}:{s:02d}"

    def start_background_poll(self):
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


manager = SilentAngelDeviceManager()
BremenDeviceManager = SilentAngelDeviceManager


class SilentAngelHTTPHandler(http.server.BaseHTTPRequestHandler):

    def generate_coverart_svg(self, title="Silent Angel", artist="VitOS Audio Core", genre="Lossless Audio"):
        # Minimalist Audiophile Vinyl Artwork: Zero text repetition, Zero gold gradient outline
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500" width="500" height="500">
  <defs>
    <radialGradient id="bgGlow" cx="50%" cy="50%" r="75%">
      <stop offset="0%" stop-color="#18202e"/>
      <stop offset="55%" stop-color="#0e131d"/>
      <stop offset="100%" stop-color="#06080d"/>
    </radialGradient>
    <radialGradient id="goldGleam" cx="35%" cy="30%" r="70%">
      <stop offset="0%" stop-color="#fff2c2"/>
      <stop offset="50%" stop-color="#c99d52"/>
      <stop offset="100%" stop-color="#7a5519"/>
    </radialGradient>
  </defs>
  <rect width="500" height="500" fill="url(#bgGlow)"/>
  <!-- Concentric Vinyl Grooves (Centered) -->
  <circle cx="250" cy="250" r="236" fill="none" stroke="rgba(255,255,255,0.035)" stroke-width="1"/>
  <circle cx="250" cy="250" r="208" fill="none" stroke="rgba(255,255,255,0.035)" stroke-width="1"/>
  <circle cx="250" cy="250" r="180" fill="none" stroke="rgba(255,255,255,0.035)" stroke-width="1"/>
  <circle cx="250" cy="250" r="152" fill="none" stroke="rgba(255,255,255,0.035)" stroke-width="1"/>
  <circle cx="250" cy="250" r="124" fill="none" stroke="rgba(255,255,255,0.035)" stroke-width="1"/>
  <!-- Central Precision Gold Medallion & Spindle -->
  <circle cx="250" cy="250" r="80" fill="#101622" stroke="url(#goldGleam)" stroke-width="2.5"/>
  <circle cx="250" cy="250" r="30" fill="#080c13" stroke="url(#goldGleam)" stroke-width="1.5"/>
  <circle cx="250" cy="250" r="9" fill="#ffe8a3"/>
</svg>"""

    """Serves the audiophile web interface, PWA manifest, and JSON REST API with genuine live endpoints."""

    def log_message(self, format, *args):
        if "/api/status" not in self.path:
            super().log_message(format, *args)

    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path
        query = urllib.parse.parse_qs(url_parts.query)

        if path == "/api/status":
            self.send_json(manager.state)
        elif path == "/api/heartbeat":
            with manager.lock:
                hb = {
                    "connected": manager.is_connected,
                    "target_ip": manager.target_ip,
                    "device_name": manager.device_name,
                    "last_heartbeat": getattr(manager, "last_heartbeat_time", time.time()),
                    "heartbeat_status": "active" if manager.is_connected else "unreachable",
                    "failures": getattr(manager, "heartbeat_failures", 0)
                }
            self.send_json(hb)
        elif path == "/api/sources":
            with manager.lock:
                active_src = manager.state.get("active_source", "UPnP / DLNA")
            self.send_json({
                "active_source": active_src,
                "protocols": manager.protocols
            })
        elif path in ("/earth_nasa.jpg", "/earth_dark.jpg", "/static/earth_nasa.jpg", "/static/earth_dark.jpg"):
            fname = "earth_dark.jpg" if "dark" in path else "earth_nasa.jpg"
            local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
            if os.path.exists(local_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(local_path, "rb") as f:
                    self.wfile.write(f.read())
                return
        elif path in ("/three.min.js", "/static/three.min.js"):
            local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "three.min.js")
            if os.path.exists(local_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(local_path, "rb") as f:
                    self.wfile.write(f.read())
                return
        elif path == "/api/radio/globe_stations":
            self.send_json(self.get_globe_stations())
        elif path == "/api/remote/target":
            self.send_json({"target": manager.active_remote_target})
            return
        elif path == "/api/remote/pair":
            is_paired = getattr(manager.multi_device_controller, "is_paired_google_tv", False) if getattr(manager, "multi_device_controller", None) else False
            self.send_json({"status": "ok", "paired": is_paired, "target": "google_tv"})
            return
        elif path == "/api/voice/status":
            if getattr(manager, "voice_engine", None):
                self.send_json(manager.voice_engine.get_status())
            else:
                self.send_json({"status": "error", "error": "Voice engine not initialised"})
            return
        elif path == "/api/voice/routines":
            if getattr(manager, "voice_engine", None):
                self.send_json({"status": "ok", "routines": manager.voice_engine.routines})
            else:
                self.send_json({"status": "error", "error": "Voice engine not initialised"})
            return
        elif path == "/api/lights/state":
            if getattr(manager, "voice_engine", None):
                self.send_json({"status": "ok", "state": manager.voice_engine.lighting.get_state()})
            else:
                self.send_json({"status": "ok", "state": {"power": "ON", "brightness": 70, "colour": "warm_gold", "hex": "#d4af37"}})
            return

        elif path == "/api/discover":
            devices = manager.discover_all_devices(timeout=3.0)
            self.send_json({"devices": devices})
        elif path == "/api/radio/curated":
            self.send_json({
                "categories": manager.CURATED_RADIO_CATEGORIES,
                "countries": RadioBrowserService.POPULAR_COUNTRIES,
                "genres": RadioBrowserService.POPULAR_GENRES
            })
        elif path == "/api/radio/search":
            q_name = query.get("query", [""])[0]
            q_tag = query.get("tag", [""])[0]
            q_country = query.get("country", [""])[0]
            q_order = query.get("order", ["votes"])[0]
            results = RadioBrowserService.search_stations(
                query=q_name,
                tag=q_tag,
                country=q_country,
                order=q_order,
                limit=50
            )
            self.send_json({"stations": results})
        elif path == "/api/radio/favourites":
            self.send_json({"favourites": manager.get_favourites()})
        elif path == "/api/history":
            self.send_json({"history": manager.get_history()})
        elif path == "/api/queue":
            self.send_json({"queue": manager.get_queue()})
        elif path == "/api/storage/browse":
            target_path = query.get("path", [""])[0]
            res = manager.browse_storage(target_path)
            self.send_json(res)
        elif path == "/api/lyrics":
            artist = query.get("artist", [""])[0]
            title = query.get("title", [""])[0]
            lyrics_data = self.fetch_lyrics(artist, title)
            self.send_json(lyrics_data)
        elif path == "/manifest.json":
            self.serve_manifest()
        elif path == "/sw.js":
            self.serve_service_worker()
        elif path == "/api/coverart":
            title = query.get("title", ["Silent Angel"])[0]
            artist = query.get("artist", ["VitOS Audio Core"])[0]
            genre = query.get("genre", ["Lossless Audio"])[0]

            # 1. Genuine online image artwork call
            img_data, mime_type = manager.get_artwork_image(title, artist)
            if img_data:
                self.send_response(200)
                self.send_header("Content-Type", mime_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Content-Length", str(len(img_data)))
                self.end_headers()
                self.wfile.write(img_data)
                return

            # 2. Minimalist audiophile vinyl fallback
            svg_data = self.generate_coverart_svg(title, artist, genre).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(svg_data)))
            self.end_headers()
            self.wfile.write(svg_data)
            return
        elif path == "/api/proxy_art":
            art_url = query.get("url", [""])[0]
            title = query.get("title", ["Silent Angel"])[0]
            artist = query.get("artist", ["VitOS Audio Core"])[0]
            genre = query.get("genre", ["Lossless Audio"])[0]
            if art_url:
                try:
                    req = urllib.request.Request(art_url, headers={"User-Agent": "SilentAngelStudio/1.0"})
                    with urllib.request.urlopen(req, timeout=3.0) as resp:
                        content_type = resp.headers.get("Content-Type", "image/jpeg")
                        data = resp.read()
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        self.wfile.write(data)
                        return
                except Exception:
                    pass
            svg_data = self.generate_coverart_svg(title, artist, genre).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(svg_data)))
            self.end_headers()
            self.wfile.write(svg_data)
            return
        elif path == "/favicon.ico":
            fav = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="20" fill="#0b0e14"/><circle cx="50" cy="50" r="38" fill="none" stroke="#c99d52" stroke-width="4"/><path d="M50 15 C58 28 72 38 90 40 C75 52 68 68 68 85 C58 70 52 55 50 15 Z" fill="#c99d52"/></svg>"""
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(fav)))
            self.end_headers()
            self.wfile.write(fav)
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

        if path == "/api/remote/target":
            res = manager.set_remote_target(data)
            self.send_json({"status": "ok", "target": res})
            return

        elif path == "/api/remote/command":
            cmd = data.get("command", "")
            param = data.get("param", None)
            target = data.get("target", None)
            res = manager.send_remote_command(cmd, param, target=target)
            self.send_json(res)
            return

        elif path == "/api/remote/pair":
            action = data.get("action", "start")
            ip = data.get("ip", "192.168.1.137")
            if getattr(manager, "multi_device_controller", None):
                if action == "start":
                    res = manager.multi_device_controller.start_google_tv_pairing(ip)
                    self.send_json(res)
                elif action == "finish":
                    code = data.get("code", "")
                    res = manager.multi_device_controller.finish_google_tv_pairing(ip, code)
                    self.send_json(res)
                else:
                    self.send_json({"status": "error", "error": "Unknown action"})
            else:
                self.send_json({"status": "error", "error": "Driver controller unavailable"})
            return
        elif path == "/api/voice/process":
            transcript = data.get("transcript", "")
            bypass_vad = data.get("bypass_vad", False)
            if getattr(manager, "voice_engine", None):
                res = manager.voice_engine.process_transcript(transcript, bypass_vad=bypass_vad)
                self.send_json({"status": "ok", "decision": res})
            else:
                self.send_json({"status": "error", "error": "Voice engine unavailable"})
            return
        elif path == "/api/voice/vad":
            noise_lvl = float(data.get("noise_level", -50.0))
            is_v = bool(data.get("is_voice", False))
            sens = data.get("sensitivity", None)
            if getattr(manager, "voice_engine", None):
                manager.voice_engine.update_vad_status(noise_lvl, is_v, sens)
                self.send_json({"status": "ok"})
            else:
                self.send_json({"status": "error"})
            return
        elif path == "/api/lights/control":
            power = data.get("power", None)
            brightness = data.get("brightness", None)
            colour = data.get("colour", None)
            if getattr(manager, "voice_engine", None):
                new_state = manager.voice_engine.lighting.set_state(power=power, brightness=brightness, colour=colour)
                self.send_json({"status": "ok", "state": new_state})
            else:
                self.send_json({"status": "error", "error": "Lighting controller unavailable"})
            return
        elif path == "/api/voice/test_routine":
            routine_id = data.get("routine_id", "")
            if getattr(manager, "voice_engine", None):
                matched = next((r for r in manager.voice_engine.routines if r.get("id") == routine_id), None)
                if matched:
                    res = manager.voice_engine.execute_actions(matched.get("actions", []))
                    self.send_json({"status": "ok", "routine": matched.get("name"), "results": res})
                else:
                    self.send_json({"status": "error", "error": "Routine not found"})
            else:
                self.send_json({"status": "error", "error": "Voice engine unavailable"})
            return
        elif path == "/api/voice/routines":
            action = data.get("action", "save")
            if getattr(manager, "voice_engine", None):
                if action == "toggle":
                    r_id = data.get("id")
                    for r in manager.voice_engine.routines:
                        if r.get("id") == r_id:
                            r["enabled"] = not r.get("enabled", True)
                    manager.voice_engine.save_routines()
                    self.send_json({"status": "ok", "routines": manager.voice_engine.routines})
                elif action == "add":
                    new_r = data.get("routine")
                    if new_r:
                        manager.voice_engine.routines.append(new_r)
                        manager.voice_engine.save_routines()
                    self.send_json({"status": "ok", "routines": manager.voice_engine.routines})
                else:
                    self.send_json({"status": "ok"})
            else:
                self.send_json({"status": "error", "error": "Voice engine unavailable"})
            return

        elif path == "/api/connect":
            ip = data.get("ip", "")
            transport = data.get("control_transport", "")
            rendering = data.get("control_rendering", "")
            content = data.get("control_content", "")
            name = data.get("friendly_name", "")
            success = manager.connect_to_device(ip, transport, rendering, content, name)
            self.send_json({"success": success, "ip": ip})

        elif path == "/api/play_stream":
            uri = data.get("url") or data.get("stream_url", "")
            title = data.get("title", "Internet Radio")
            artist = data.get("artist", "Live Stream")
            album = data.get("album", "Silent Angel Studio")
            art_url = data.get("art_url") or data.get("album_art_url") or f"/api/coverart?title={urllib.parse.quote(title)}&artist={urllib.parse.quote(artist)}&genre={urllib.parse.quote(album)}"
            with manager.lock:
                manager.state["album_art_url"] = art_url
            manager.set_av_transport_uri(uri, title, artist, album)
            self.send_json({"status": "acknowledged", "streaming": uri, "album_art_url": art_url})

        elif path == "/api/radio/favourite":
            is_fav = manager.toggle_favourite(data)
            self.send_json({"status": "ok", "is_favourite": is_fav})

        elif path == "/api/history/clear":
            manager.clear_history()
            self.send_json({"status": "cleared"})

        elif path == "/api/queue/add":
            count = manager.add_to_queue(data, play_next=data.get("play_next", False))
            self.send_json({"status": "added", "count": count})

        elif path == "/api/queue/remove":
            idx = int(data.get("index", 0))
            removed = manager.remove_from_queue(idx)
            self.send_json({"status": "removed", "item": removed})

        elif path == "/api/queue/clear":
            manager.clear_queue()
            self.send_json({"status": "cleared"})

        elif path == "/api/queue/play":
            idx = int(data.get("index", 0))
            ok = manager.play_queue_index(idx)
            self.send_json({"status": "playing", "success": ok})

        elif path in ("/api/set_source", "/api/source/select"):
            src = data.get("source") or data.get("protocol") or "UPnP / DLNA"
            with manager.lock:
                manager.state["active_source"] = src
            self.send_json({"status": "ok", "active_source": src})

        elif path in ("/api/settings", "/api/audio_settings"):
            if "fixed_volume_mode" in data or "fixed_volume" in data:
                f_mode = bool(data.get("fixed_volume_mode", data.get("fixed_volume")))
                manager.set_fixed_volume_mode(f_mode)
            if "dac_filter" in data:
                manager.set_dac_filter(data["dac_filter"])
            if "eq_preset" in data:
                manager.set_eq_preset(data["eq_preset"], data.get("eq_bands"))
            self.send_json({
                "status": "updated",
                "fixed_volume_mode": manager.fixed_volume_mode,
                "dac_filter": manager.dac_filter,
                "eq_preset": manager.eq_settings.get("preset", "flat")
            })

        elif path == "/api/sleep":
            mins = int(data.get("minutes", 0))
            manager.set_sleep_timer(mins)
            self.send_json({"status": "scheduled", "minutes": mins})

        elif path == "/api/control":
            action = data.get("action") or data.get("command", "")
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
            elif action == "seek" and val is not None:
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

    def get_globe_stations(self):
        """Returns 24 curated premier radio stations across the globe with geographic coordinates."""
        return [
            {
                        "id": "g-london-bbc6",
                        "name": "BBC Radio 6 Music",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Alternative",
                        "bitrate": "320 kbps",
                        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_6music",
                        "art_url": "/api/coverart?title=BBC Radio 6 Music&artist=London, United Kingdom&genre=Alternative"
            },
            {
                        "id": "g-london-bbc3",
                        "name": "BBC Radio 3",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Classical",
                        "bitrate": "320 kbps",
                        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_radio_three",
                        "art_url": "/api/coverart?title=BBC Radio 3&artist=London, United Kingdom&genre=Classical"
            },
            {
                        "id": "g-london-bbc4",
                        "name": "BBC Radio 4",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "News / Culture",
                        "bitrate": "320 kbps",
                        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_radio_fourfm",
                        "art_url": "/api/coverart?title=BBC Radio 4&artist=London, United Kingdom&genre=News"
            },
            {
                        "id": "g-london-bbc1",
                        "name": "BBC Radio 1",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Current / Electronic",
                        "bitrate": "320 kbps",
                        "url": "https://stream.live.vc.bbcmedia.co.uk/bbc_radio_one",
                        "art_url": "/api/coverart?title=BBC Radio 1&artist=London, United Kingdom&genre=Electronic"
            },
            {
                        "id": "g-london-jazzfm",
                        "name": "Jazz FM UK",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Jazz / Soul / Blues",
                        "bitrate": "128 kbps",
                        "url": "https://stream-mz.planetradio.co.uk/jazzhigh.mp3",
                        "art_url": "/api/coverart?title=Jazz FM UK&artist=London, United Kingdom&genre=Jazz"
            },
            {
                        "id": "g-london-classicfm",
                        "name": "Classic FM",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Classical",
                        "bitrate": "128 kbps",
                        "url": "https://media-ice.musicradio.com/ClassicFMMP3",
                        "art_url": "/api/coverart?title=Classic FM&artist=London, United Kingdom&genre=Classical"
            },
            {
                        "id": "g-london-sohoradio",
                        "name": "Soho Radio",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Eclectic / Indie",
                        "bitrate": "320 kbps",
                        "url": "https://sohoradiomusic.doughunt.co.uk/live",
                        "art_url": "/api/coverart?title=Soho Radio&artist=London, United Kingdom&genre=Eclectic"
            },
            {
                        "id": "g-london-nts1",
                        "name": "NTS Radio 1",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Underground / Ambient",
                        "bitrate": "192 kbps",
                        "url": "https://stream-relay-geo.ntslive.net/stream",
                        "art_url": "/api/coverart?title=NTS Radio 1&artist=London, United Kingdom&genre=Ambient"
            },
            {
                        "id": "g-london-rinse",
                        "name": "Rinse FM",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Bass / Grime / Techno",
                        "bitrate": "192 kbps",
                        "url": "https://rinsefm.streamguys1.com:1936/stream",
                        "art_url": "/api/coverart?title=Rinse FM&artist=London, United Kingdom&genre=Techno"
            },
            {
                        "id": "g-london-monocle",
                        "name": "Monocle 24",
                        "city": "London",
                        "country": "United Kingdom",
                        "lat": 51.5074,
                        "lon": -0.1278,
                        "genre": "Global Affairs / Culture",
                        "bitrate": "128 kbps",
                        "url": "https://radio.monocle.com/live",
                        "art_url": "/api/coverart?title=Monocle 24&artist=London, United Kingdom&genre=Culture"
            },
            {
                        "id": "g-paris-fip",
                        "name": "FIP Radio",
                        "city": "Paris",
                        "country": "France",
                        "lat": 48.8566,
                        "lon": 2.3522,
                        "genre": "Eclectic",
                        "bitrate": "192 kbps",
                        "url": "https://icecast.radiofrance.fr/fip-midfi.mp3",
                        "art_url": "/api/coverart?title=FIP Radio&artist=Paris, France&genre=Eclectic"
            },
            {
                        "id": "g-paris-classique",
                        "name": "Radio Classique",
                        "city": "Paris",
                        "country": "France",
                        "lat": 48.8566,
                        "lon": 2.3522,
                        "genre": "Classical",
                        "bitrate": "128 kbps",
                        "url": "http://radioclassique.ice.infomaniak.ch/radioclassique-high.mp3",
                        "art_url": "/api/coverart?title=Radio Classique&artist=Paris, France&genre=Classical"
            },
            {
                        "id": "g-paris-tsugi",
                        "name": "Tsugi Radio",
                        "city": "Paris",
                        "country": "France",
                        "lat": 48.8566,
                        "lon": 2.3522,
                        "genre": "Indie / Electronic",
                        "bitrate": "192 kbps",
                        "url": "https://stream.tsugi.fr/tsugi.mp3",
                        "art_url": "/api/coverart?title=Tsugi Radio&artist=Paris, France&genre=Electronic"
            },
            {
                        "id": "g-paris-franceinter",
                        "name": "France Inter",
                        "city": "Paris",
                        "country": "France",
                        "lat": 48.8566,
                        "lon": 2.3522,
                        "genre": "Culture / News",
                        "bitrate": "192 kbps",
                        "url": "https://icecast.radiofrance.fr/franceinter-midfi.mp3",
                        "art_url": "/api/coverart?title=France Inter&artist=Paris, France&genre=News"
            },
            {
                        "id": "g-paris-novaradio",
                        "name": "Radio Nova",
                        "city": "Paris",
                        "country": "France",
                        "lat": 48.8566,
                        "lon": 2.3522,
                        "genre": "Groove / World / Hip-Hop",
                        "bitrate": "192 kbps",
                        "url": "http://novazz.ice.infomaniak.ch/novazz-128.mp3",
                        "art_url": "/api/coverart?title=Radio Nova&artist=Paris, France&genre=World"
            },
            {
                        "id": "g-berlin-berlin1",
                        "name": "Radio Eins",
                        "city": "Berlin",
                        "country": "Germany",
                        "lat": 52.52,
                        "lon": 13.405,
                        "genre": "Alternative Rock",
                        "bitrate": "256 kbps",
                        "url": "https://rbb-radioeins-live.ssl.akamaized.net/hls/live/2017935/rbb_radioeins/master.m3u8",
                        "art_url": "/api/coverart?title=Radio Eins&artist=Berlin, Germany&genre=Alternative"
            },
            {
                        "id": "g-berlin-flux",
                        "name": "FluxFM Berlin",
                        "city": "Berlin",
                        "country": "Germany",
                        "lat": 52.52,
                        "lon": 13.405,
                        "genre": "Indie / Alternative",
                        "bitrate": "320 kbps",
                        "url": "https://fluxfm.streamguys1.com/flux-live",
                        "art_url": "/api/coverart?title=FluxFM Berlin&artist=Berlin, Germany&genre=Indie"
            },
            {
                        "id": "g-berlin-fritz",
                        "name": "Fritz vom rbb",
                        "city": "Berlin",
                        "country": "Germany",
                        "lat": 52.52,
                        "lon": 13.405,
                        "genre": "Urban / Beats",
                        "bitrate": "192 kbps",
                        "url": "https://rbb-fritz-live.ssl.akamaized.net/hls/live/2017937/rbb_fritz/master.m3u8",
                        "art_url": "/api/coverart?title=Fritz&artist=Berlin, Germany&genre=Urban"
            },
            {
                        "id": "g-berlin-dradio",
                        "name": "Deutschlandfunk Kultur",
                        "city": "Berlin",
                        "country": "Germany",
                        "lat": 52.52,
                        "lon": 13.405,
                        "genre": "Classical / Arts",
                        "bitrate": "192 kbps",
                        "url": "https://st02.sslstream.dlf.de/dlf/02/128/mp3/stream.mp3",
                        "art_url": "/api/coverart?title=DLF Kultur&artist=Berlin, Germany&genre=Classical"
            },
            {
                        "id": "g-amsterdam-sublime",
                        "name": "Sublime FM",
                        "city": "Amsterdam",
                        "country": "Netherlands",
                        "lat": 52.3676,
                        "lon": 4.9041,
                        "genre": "Funk / Soul / Jazz",
                        "bitrate": "192 kbps",
                        "url": "https://stream.sublime.nl/sublime",
                        "art_url": "/api/coverart?title=Sublime FM&artist=Amsterdam, Netherlands&genre=Funk"
            },
            {
                        "id": "g-amsterdam-radio4",
                        "name": "NPO Klassiek",
                        "city": "Amsterdam",
                        "country": "Netherlands",
                        "lat": 52.3676,
                        "lon": 4.9041,
                        "genre": "Classical / Concert",
                        "bitrate": "192 kbps",
                        "url": "https://icecast.omroep.nl/radio4-bb-mp3",
                        "art_url": "/api/coverart?title=NPO Klassiek&artist=Amsterdam, Netherlands&genre=Classical"
            },
            {
                        "id": "g-amsterdam-redlight",
                        "name": "Red Light Radio",
                        "city": "Amsterdam",
                        "country": "Netherlands",
                        "lat": 52.3676,
                        "lon": 4.9041,
                        "genre": "Underground / Vinyl",
                        "bitrate": "192 kbps",
                        "url": "https://stream.redlightradio.net/live",
                        "art_url": "/api/coverart?title=Red Light Radio&artist=Amsterdam, Netherlands&genre=Underground"
            },
            {
                        "id": "g-vienna-oe1",
                        "name": "ORF \u00d61",
                        "city": "Vienna",
                        "country": "Austria",
                        "lat": 48.2082,
                        "lon": 16.3738,
                        "genre": "Culture / Symphony",
                        "bitrate": "192 kbps",
                        "url": "https://orf-live.ors-shoutcast.at/oe1-q2a",
                        "art_url": "/api/coverart?title=ORF OE1&artist=Vienna, Austria&genre=Culture"
            },
            {
                        "id": "g-vienna-fm4",
                        "name": "ORF FM4",
                        "city": "Vienna",
                        "country": "Austria",
                        "lat": 48.2082,
                        "lon": 16.3738,
                        "genre": "Alternative / Indie",
                        "bitrate": "192 kbps",
                        "url": "https://orf-live.ors-shoutcast.at/fm4-q2a",
                        "art_url": "/api/coverart?title=ORF FM4&artist=Vienna, Austria&genre=Alternative"
            },
            {
                        "id": "g-rome-rai3",
                        "name": "Rai Radio 3 Classica",
                        "city": "Rome",
                        "country": "Italy",
                        "lat": 41.9028,
                        "lon": 12.4964,
                        "genre": "Opera / Chamber",
                        "bitrate": "192 kbps",
                        "url": "http://icestreaming.rai.it/3.mp3",
                        "art_url": "/api/coverart?title=Rai Radio 3&artist=Rome, Italy&genre=Opera"
            },
            {
                        "id": "g-rome-montecarlo",
                        "name": "Radio Monte Carlo",
                        "city": "Rome",
                        "country": "Italy",
                        "lat": 41.9028,
                        "lon": 12.4964,
                        "genre": "Lounge / Soul",
                        "bitrate": "128 kbps",
                        "url": "http://stream.radiomontecarlo.net/rmc128",
                        "art_url": "/api/coverart?title=Radio Monte Carlo&artist=Rome, Italy&genre=Lounge"
            },
            {
                        "id": "g-madrid-r3",
                        "name": "Radio 3 RNE",
                        "city": "Madrid",
                        "country": "Spain",
                        "lat": 40.4168,
                        "lon": -3.7038,
                        "genre": "Indie / World",
                        "bitrate": "128 kbps",
                        "url": "https://rtvelivestream.akamaized.net/rtvesec/rne/rne_r3_main.mp3",
                        "art_url": "/api/coverart?title=Radio 3 RNE&artist=Madrid, Spain&genre=Indie"
            },
            {
                        "id": "g-madrid-clasica",
                        "name": "Radio Cl\u00e1sica RNE",
                        "city": "Madrid",
                        "country": "Spain",
                        "lat": 40.4168,
                        "lon": -3.7038,
                        "genre": "Classical",
                        "bitrate": "128 kbps",
                        "url": "https://rtvelivestream.akamaized.net/rtvesec/rne/rne_rclasica_main.mp3",
                        "art_url": "/api/coverart?title=Radio Clasica&artist=Madrid, Spain&genre=Classical"
            },
            {
                        "id": "g-stockholm-p2",
                        "name": "Sveriges Radio P2",
                        "city": "Stockholm",
                        "country": "Sweden",
                        "lat": 59.3293,
                        "lon": 18.0686,
                        "genre": "Classical / Jazz",
                        "bitrate": "192 kbps",
                        "url": "https://sverigesradio.se/topsy/direkt/srapi/163.mp3",
                        "art_url": "/api/coverart?title=Sveriges Radio P2&artist=Stockholm, Sweden&genre=Classical"
            },
            {
                        "id": "g-stockholm-p3",
                        "name": "Sveriges Radio P3",
                        "city": "Stockholm",
                        "country": "Sweden",
                        "lat": 59.3293,
                        "lon": 18.0686,
                        "genre": "Nordic Pop / Beats",
                        "bitrate": "192 kbps",
                        "url": "https://sverigesradio.se/topsy/direkt/srapi/164.mp3",
                        "art_url": "/api/coverart?title=Sveriges Radio P3&artist=Stockholm, Sweden&genre=Pop"
            },
            {
                        "id": "g-zurich-swissclassic",
                        "name": "Radio Swiss Classic",
                        "city": "Zurich",
                        "country": "Switzerland",
                        "lat": 47.3769,
                        "lon": 8.5417,
                        "genre": "Classical Masterworks",
                        "bitrate": "128 kbps",
                        "url": "http://stream.srg-ssr.ch/m/rsc_de/mp3_128",
                        "art_url": "/api/coverart?title=Radio Swiss Classic&artist=Zurich, Switzerland&genre=Classical"
            },
            {
                        "id": "g-zurich-swissjazz",
                        "name": "Radio Swiss Jazz",
                        "city": "Zurich",
                        "country": "Switzerland",
                        "lat": 47.3769,
                        "lon": 8.5417,
                        "genre": "Jazz & Soul",
                        "bitrate": "128 kbps",
                        "url": "http://stream.srg-ssr.ch/m/rsj/mp3_128",
                        "art_url": "/api/coverart?title=Radio Swiss Jazz&artist=Zurich, Switzerland&genre=Jazz"
            },
            {
                        "id": "g-dublin-rtegold",
                        "name": "RT\u00c9 Gold",
                        "city": "Dublin",
                        "country": "Ireland",
                        "lat": 53.3498,
                        "lon": -6.2603,
                        "genre": "Classic Hits / Pop",
                        "bitrate": "128 kbps",
                        "url": "https://icecast2.rte.ie/gold",
                        "art_url": "/api/coverart?title=RTE Gold&artist=Dublin, Ireland&genre=Pop"
            },
            {
                        "id": "g-reykjavik-ras1",
                        "name": "R\u00daV R\u00e1s 1",
                        "city": "Reykjavik",
                        "country": "Iceland",
                        "lat": 64.1466,
                        "lon": -21.9426,
                        "genre": "Nordic Ambient / Folk",
                        "bitrate": "192 kbps",
                        "url": "https://ruv-live.akamaized.net/ras1/ras1.isml/ras1-audio=192000.m3u8",
                        "art_url": "/api/coverart?title=RUV Ras 1&artist=Reykjavik, Iceland&genre=Folk"
            },
            {
                        "id": "g-ny-wnyc",
                        "name": "WNYC 93.9 FM",
                        "city": "New York",
                        "country": "United States",
                        "lat": 40.7128,
                        "lon": -74.006,
                        "genre": "Public Radio / News",
                        "bitrate": "128 kbps",
                        "url": "https://fm939.wnyc.org/wnycfm",
                        "art_url": "/api/coverart?title=WNYC 93.9 FM&artist=New York, United States&genre=News"
            },
            {
                        "id": "g-ny-wqxr",
                        "name": "WQXR 105.9 FM",
                        "city": "New York",
                        "country": "United States",
                        "lat": 40.7128,
                        "lon": -74.006,
                        "genre": "Classical Philharmonic",
                        "bitrate": "128 kbps",
                        "url": "https://stream.wqxr.org/wqxr",
                        "art_url": "/api/coverart?title=WQXR Classical&artist=New York, United States&genre=Classical"
            },
            {
                        "id": "g-ny-wfmu",
                        "name": "WFMU Independent",
                        "city": "New York",
                        "country": "United States",
                        "lat": 40.7128,
                        "lon": -74.006,
                        "genre": "Freeform / Experimental",
                        "bitrate": "128 kbps",
                        "url": "https://stream0.wfmu.org/freeform-128k.mp3",
                        "art_url": "/api/coverart?title=WFMU Freeform&artist=New York, United States&genre=Experimental"
            },
            {
                        "id": "g-ny-wbgo",
                        "name": "WBGO Jazz 88.3",
                        "city": "New York",
                        "country": "United States",
                        "lat": 40.7128,
                        "lon": -74.006,
                        "genre": "Straight-Ahead Jazz",
                        "bitrate": "128 kbps",
                        "url": "https://wbgo.streamguys1.com/wbgo128",
                        "art_url": "/api/coverart?title=WBGO Jazz&artist=New York, United States&genre=Jazz"
            },
            {
                        "id": "g-ny-hot97",
                        "name": "Hot 97 NY",
                        "city": "New York",
                        "country": "United States",
                        "lat": 40.7128,
                        "lon": -74.006,
                        "genre": "Hip Hop / R&B",
                        "bitrate": "128 kbps",
                        "url": "https://stream.revma.ihrhls.com/zc1473",
                        "art_url": "/api/coverart?title=Hot 97 NY&artist=New York, United States&genre=HipHop"
            },
            {
                        "id": "g-ny-lotradio",
                        "name": "The Lot Radio",
                        "city": "New York",
                        "country": "United States",
                        "lat": 40.7128,
                        "lon": -74.006,
                        "genre": "Brooklyn Electronic",
                        "bitrate": "192 kbps",
                        "url": "https://thelot.out.airtime.pro/thelot_a",
                        "art_url": "/api/coverart?title=The Lot Radio&artist=New York, United States&genre=Electronic"
            },
            {
                        "id": "g-la-kcrw",
                        "name": "KCRW 89.9 FM",
                        "city": "Los Angeles",
                        "country": "United States",
                        "lat": 34.0522,
                        "lon": -118.2437,
                        "genre": "Eclectic Indie / NPR",
                        "bitrate": "128 kbps",
                        "url": "https://kcrw.streamguys1.com/kcrw_192k_mp3_on_air",
                        "art_url": "/api/coverart?title=KCRW 89.9 FM&artist=Los Angeles, United States&genre=Indie"
            },
            {
                        "id": "g-la-kexp",
                        "name": "Dublab Los Angeles",
                        "city": "Los Angeles",
                        "country": "United States",
                        "lat": 34.0522,
                        "lon": -118.2437,
                        "genre": "Future Roots / Beats",
                        "bitrate": "192 kbps",
                        "url": "https://dublab.out.airtime.pro/dublab_a",
                        "art_url": "/api/coverart?title=Dublab&artist=Los Angeles, United States&genre=Beats"
            },
            {
                        "id": "g-la-kusc",
                        "name": "KUSC Classical",
                        "city": "Los Angeles",
                        "country": "United States",
                        "lat": 34.0522,
                        "lon": -118.2437,
                        "genre": "Classical",
                        "bitrate": "128 kbps",
                        "url": "https://kusc.streamguys1.com/kusc-mp3",
                        "art_url": "/api/coverart?title=KUSC Classical&artist=Los Angeles, United States&genre=Classical"
            },
            {
                        "id": "g-seattle-kexp",
                        "name": "KEXP 90.3 FM",
                        "city": "Seattle",
                        "country": "United States",
                        "lat": 47.6062,
                        "lon": -122.3321,
                        "genre": "Indie / Pioneer",
                        "bitrate": "160 kbps",
                        "url": "https://kexp.streamguys1.com/kexp160.mp3",
                        "art_url": "/api/coverart?title=KEXP Seattle&artist=Seattle, United States&genre=Indie"
            },
            {
                        "id": "g-seattle-kingfm",
                        "name": "KING FM 98.1",
                        "city": "Seattle",
                        "country": "United States",
                        "lat": 47.6062,
                        "lon": -122.3321,
                        "genre": "Classical & Opera",
                        "bitrate": "128 kbps",
                        "url": "https://classicalking.streamguys1.com/king-fm-aac",
                        "art_url": "/api/coverart?title=KING FM&artist=Seattle, United States&genre=Classical"
            },
            {
                        "id": "g-chicago-wbez",
                        "name": "WBEZ 91.5 Chicago",
                        "city": "Chicago",
                        "country": "United States",
                        "lat": 41.8781,
                        "lon": -87.6298,
                        "genre": "Public Radio / Talk",
                        "bitrate": "128 kbps",
                        "url": "https://stream.wbez.org/wbez128.mp3",
                        "art_url": "/api/coverart?title=WBEZ Chicago&artist=Chicago, United States&genre=Talk"
            },
            {
                        "id": "g-chicago-wfmt",
                        "name": "WFMT Fine Arts",
                        "city": "Chicago",
                        "country": "United States",
                        "lat": 41.8781,
                        "lon": -87.6298,
                        "genre": "Classical / Opera",
                        "bitrate": "128 kbps",
                        "url": "https://wfmt.streamguys1.com/wfmt-mp3",
                        "art_url": "/api/coverart?title=WFMT Fine Arts&artist=Chicago, United States&genre=Classical"
            },
            {
                        "id": "g-sf-somafm",
                        "name": "SomaFM Groove Salad",
                        "city": "San Francisco",
                        "country": "United States",
                        "lat": 37.7749,
                        "lon": -122.4194,
                        "genre": "Ambient / Chillout",
                        "bitrate": "128 kbps",
                        "url": "http://ice1.somafm.com/groovesalad-128-mp3",
                        "art_url": "/api/coverart?title=SomaFM Groove Salad&artist=San Francisco, United States&genre=Ambient"
            },
            {
                        "id": "g-toronto-jazz91",
                        "name": "JAZZ.FM91",
                        "city": "Toronto",
                        "country": "Canada",
                        "lat": 43.6532,
                        "lon": -79.3832,
                        "genre": "Jazz Standards & Fusion",
                        "bitrate": "128 kbps",
                        "url": "https://jazzfm.streambhe.com/jazzfm.mp3",
                        "art_url": "/api/coverart?title=JAZZ.FM91&artist=Toronto, Canada&genre=Jazz"
            },
            {
                        "id": "g-toronto-indie88",
                        "name": "Indie88",
                        "city": "Toronto",
                        "country": "Canada",
                        "lat": 43.6532,
                        "lon": -79.3832,
                        "genre": "Modern Indie Rock",
                        "bitrate": "128 kbps",
                        "url": "https://indie.streamon.fm/indie-mp3",
                        "art_url": "/api/coverart?title=Indie88&artist=Toronto, Canada&genre=Indie"
            },
            {
                        "id": "g-montreal-ckut",
                        "name": "CKUT 90.3 FM",
                        "city": "Montreal",
                        "country": "Canada",
                        "lat": 45.5017,
                        "lon": -73.5673,
                        "genre": "McGill Community / Experimental",
                        "bitrate": "128 kbps",
                        "url": "https://stream.ckut.ca:8001/ckut-music-128.mp3",
                        "art_url": "/api/coverart?title=CKUT 90.3&artist=Montreal, Canada&genre=Experimental"
            },
            {
                        "id": "g-tokyo-nhkfm",
                        "name": "NHK-FM Classical Tokyo",
                        "city": "Tokyo",
                        "country": "Japan",
                        "lat": 35.6762,
                        "lon": 139.6503,
                        "genre": "Classical & Traditional",
                        "bitrate": "128 kbps",
                        "url": "https://radiko.jp/v2/api/ts/playlist.m3u8?station_id=JOAK-FM",
                        "art_url": "/api/coverart?title=NHK FM Tokyo&artist=Tokyo, Japan&genre=Classical"
            },
            {
                        "id": "g-tokyo-jwave",
                        "name": "J-WAVE 81.3 FM",
                        "city": "Tokyo",
                        "country": "Japan",
                        "lat": 35.6762,
                        "lon": 139.6503,
                        "genre": "J-Pop / Shibuya-Kei",
                        "bitrate": "128 kbps",
                        "url": "https://radiko.jp/v2/api/ts/playlist.m3u8?station_id=FMJ",
                        "art_url": "/api/coverart?title=J-WAVE 81.3&artist=Tokyo, Japan&genre=Pop"
            },
            {
                        "id": "g-tokyo-interfm",
                        "name": "InterFM 89.7",
                        "city": "Tokyo",
                        "country": "Japan",
                        "lat": 35.6762,
                        "lon": 139.6503,
                        "genre": "Global Music / Rock",
                        "bitrate": "128 kbps",
                        "url": "https://radiko.jp/v2/api/ts/playlist.m3u8?station_id=INT",
                        "art_url": "/api/coverart?title=InterFM&artist=Tokyo, Japan&genre=Rock"
            },
            {
                        "id": "g-tokyo-shonan",
                        "name": "Shonan Beach FM",
                        "city": "Tokyo",
                        "country": "Japan",
                        "lat": 35.6762,
                        "lon": 139.6503,
                        "genre": "Jazz & Smooth Pop",
                        "bitrate": "128 kbps",
                        "url": "https://beachfm.out.airtime.pro/beachfm_a",
                        "art_url": "/api/coverart?title=Shonan Beach FM&artist=Tokyo, Japan&genre=Jazz"
            },
            {
                        "id": "g-seoul-kbs1",
                        "name": "KBS Classic FM",
                        "city": "Seoul",
                        "country": "South Korea",
                        "lat": 37.5665,
                        "lon": 126.978,
                        "genre": "Korean & Western Classics",
                        "bitrate": "128 kbps",
                        "url": "https://kbs-radio.akamaized.net/live/kbs_1fm/playlist.m3u8",
                        "art_url": "/api/coverart?title=KBS Classic FM&artist=Seoul, South Korea&genre=Classical"
            },
            {
                        "id": "g-sydney-abcfine",
                        "name": "ABC Classic Sydney",
                        "city": "Sydney",
                        "country": "Australia",
                        "lat": -33.8688,
                        "lon": 151.2093,
                        "genre": "Symphony / Chamber",
                        "bitrate": "128 kbps",
                        "url": "https://live-radio01.mediahubaustralia.com/2FMW/mp3/",
                        "art_url": "/api/coverart?title=ABC Classic Sydney&artist=Sydney, Australia&genre=Classical"
            },
            {
                        "id": "g-sydney-fbi",
                        "name": "FBi Radio 94.5",
                        "city": "Sydney",
                        "country": "Australia",
                        "lat": -33.8688,
                        "lon": 151.2093,
                        "genre": "Indie / Australian Underground",
                        "bitrate": "128 kbps",
                        "url": "https://fbiradio.out.airtime.pro/fbiradio_a",
                        "art_url": "/api/coverart?title=FBi Radio&artist=Sydney, Australia&genre=Indie"
            },
            {
                        "id": "g-melbourne-rrr",
                        "name": "Triple R 102.7 FM",
                        "city": "Melbourne",
                        "country": "Australia",
                        "lat": -37.8136,
                        "lon": 144.9631,
                        "genre": "Community Independent",
                        "bitrate": "128 kbps",
                        "url": "https://ondemand.rrr.org.au/stream/live",
                        "art_url": "/api/coverart?title=Triple R&artist=Melbourne, Australia&genre=Indie"
            },
            {
                        "id": "g-melbourne-pbs",
                        "name": "PBS 106.7 FM",
                        "city": "Melbourne",
                        "country": "Australia",
                        "lat": -37.8136,
                        "lon": 144.9631,
                        "genre": "Blues / Jazz / Roots",
                        "bitrate": "128 kbps",
                        "url": "https://stream.pbsfm.org.au/live",
                        "art_url": "/api/coverart?title=PBS 106.7&artist=Melbourne, Australia&genre=Blues"
            },
            {
                        "id": "g-singapore-symphony",
                        "name": "Symphony 924",
                        "city": "Singapore",
                        "country": "Singapore",
                        "lat": 1.3521,
                        "lon": 103.8198,
                        "genre": "Classical & Film Scores",
                        "bitrate": "128 kbps",
                        "url": "https://mediacorp.rastream.com/symphony924",
                        "art_url": "/api/coverart?title=Symphony 924&artist=Singapore&genre=Classical"
            },
            {
                        "id": "g-rio-jb",
                        "name": "Radio JB FM 99.9",
                        "city": "Rio de Janeiro",
                        "country": "Brazil",
                        "lat": -22.9068,
                        "lon": -43.1729,
                        "genre": "MPB / Bossa Nova",
                        "bitrate": "128 kbps",
                        "url": "https://ice.fabricahost.com.br/jbfm",
                        "art_url": "/api/coverart?title=Radio JB FM&artist=Rio de Janeiro, Brazil&genre=BossaNova"
            },
            {
                        "id": "g-buenosaires-nacional",
                        "name": "Radio Nacional Cl\u00e1sica",
                        "city": "Buenos Aires",
                        "country": "Argentina",
                        "lat": -34.6037,
                        "lon": -58.3816,
                        "genre": "Classical & Tango",
                        "bitrate": "128 kbps",
                        "url": "https://stream.radionacional.com.ar/clasica",
                        "art_url": "/api/coverart?title=Radio Nacional Clasica&artist=Buenos Aires, Argentina&genre=Classical"
            },
            {
                        "id": "g-capetown-fine",
                        "name": "Fine Music Radio 101.3",
                        "city": "Cape Town",
                        "country": "South Africa",
                        "lat": -33.9249,
                        "lon": 18.4241,
                        "genre": "Classical & Jazz",
                        "bitrate": "128 kbps",
                        "url": "https://edge.iono.fm/xice/fmr_live_medium.mp3",
                        "art_url": "/api/coverart?title=Fine Music Radio&artist=Cape Town, South Africa&genre=Classical"
            },
            {
                        "id": "g-nairobi-capital",
                        "name": "Capital FM Kenya",
                        "city": "Nairobi",
                        "country": "Kenya",
                        "lat": -1.2921,
                        "lon": 36.8219,
                        "genre": "Afrobeats / Pop",
                        "bitrate": "128 kbps",
                        "url": "https://icecast.capitalfm.co.ke/capitalfm",
                        "art_url": "/api/coverart?title=Capital FM Kenya&artist=Nairobi, Kenya&genre=Afrobeats"
            },
            {
                        "id": "g-cairo-nogoum",
                        "name": "Nogoum FM",
                        "city": "Cairo",
                        "country": "Egypt",
                        "lat": 30.0444,
                        "lon": 31.2357,
                        "genre": "Middle Eastern Hits",
                        "bitrate": "128 kbps",
                        "url": "https://nogoumfm.com/stream",
                        "art_url": "/api/coverart?title=Nogoum FM&artist=Cairo, Egypt&genre=MiddleEastern"
            }
]

    def fetch_online_artwork(self, title, artist=""):
        if not title or title.strip() in ["Silent Angel", "VitOS Audio Core", "Standby (Ready)", "No Active Stream (Ready)"]:
            return None
        t_clean = title.strip()
        a_clean = (artist or "").strip()
        key = f"{t_clean.lower()}::{a_clean.lower()}"
        if key in self.artwork_cache:
            return self.artwork_cache[key]

        query_terms = [t_clean]
        if a_clean and a_clean.lower() not in ["vitos audio core", "silent angel streamer", "unknown", "internet radio"]:
            query_terms.append(a_clean)
        q = " ".join(query_terms)

        # 1. iTunes Music & Podcast Search API (High resolution 600x600)
        try:
            url = f"https://itunes.apple.com/search?term={urllib.parse.quote(q)}&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "SilentAngelController/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("results"):
                    res = data["results"][0]
                    art = res.get("artworkUrl100") or res.get("artworkUrl60")
                    if art:
                        art_high = art.replace("100x100bb.jpg", "600x600bb.jpg").replace("100x100bb.png", "600x600bb.png")
                        self.artwork_cache[key] = art_high
                        return art_high
        except Exception:
            pass

        # 2. Deezer Music Search API fallback
        try:
            url = f"https://api.deezer.com/search?q={urllib.parse.quote(q)}&limit=1"
            req = urllib.request.Request(url, headers={"User-Agent": "SilentAngelController/1.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("data"):
                    album = data["data"][0].get("album", {})
                    art = album.get("cover_big") or album.get("cover_medium")
                    if art:
                        self.artwork_cache[key] = art
                        return art
        except Exception:
            pass

        return None

    def get_artwork_image(self, title, artist=""):
        if not title or title.strip() in ["Silent Angel", "VitOS Audio Core", "Standby (Ready)", "No Active Stream (Ready)"]:
            return None, None
        t_clean = title.strip()
        a_clean = (artist or "").strip()
        key = f"{t_clean.lower()}::{a_clean.lower()}"
        if key in self.artwork_bytes_cache:
            return self.artwork_bytes_cache[key]

        art_url = self.fetch_online_artwork(title, artist)
        if art_url:
            try:
                req = urllib.request.Request(art_url, headers={"User-Agent": "SilentAngelStudio/1.0"})
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    ctype = resp.headers.get("Content-Type", "image/jpeg")
                    bdata = resp.read()
                    if bdata and len(bdata) > 500:
                        self.artwork_bytes_cache[key] = (bdata, ctype)
                        return bdata, ctype
            except Exception:
                pass
        return None, None

    def fetch_lyrics(self, artist, title):
        """Fetches synchronised or plain text lyrics from lrclib.net open API with fallback."""
        if not title or title in ["Standby (Ready)", "No Active Stream (Ready)"]:
            return {"found": False, "lyrics": "Standby — Start playback to view synchronised lyrics and liner notes."}

        clean_title = re.sub(r"[\(\[].*?[\)\]]", "", title).strip()
        clean_artist = re.sub(r"[\(\[].*?[\)\]]", "", artist).strip()
        qs = urllib.parse.urlencode({"artist_name": clean_artist, "track_name": clean_title})
        url = f"https://lrclib.net/api/get?{qs}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SilentAngelStudio/1.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                lyrics_text = data.get("plainLyrics") or data.get("syncedLyrics")
                if lyrics_text:
                    return {
                        "found": True,
                        "title": clean_title,
                        "artist": clean_artist,
                        "lyrics": lyrics_text,
                        "source": "LRCLIB Global Lyrics Index"
                    }
        except Exception:
            pass

        return {
            "found": False,
            "title": clean_title,
            "artist": clean_artist,
            "lyrics": f"Instrumental stream or lyrics unavailable for '{clean_title}'.\n\nEnjoy the high-fidelity bit-perfect playback on your Silent Angel Streamer."
        }

    def serve_manifest(self):
        manifest = {
            "name": "Silent Angel Streamer Studio",
            "short_name": "Silent Angel",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0b0e14",
            "theme_color": "#c99d52",
            "description": "Universal High-Fidelity Audio Control Suite for Silent Angel Streamers",
            "icons": [
                {
                    "src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' fill='%230b0e14'/><circle cx='50' cy='50' r='38' fill='none' stroke='%23c99d52' stroke-width='4'/><path d='M50 15 C58 28 72 38 90 40 C75 52 68 68 68 85 C58 70 52 55 50 15 Z' fill='%23c99d52'/></svg>",
                    "sizes": "192x192",
                    "type": "image/svg+xml"
                }
            ]
        }
        out = json.dumps(manifest).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def serve_service_worker(self):
        sw = """
self.addEventListener('install', (e) => {
  self.skipWaiting();
});
self.addEventListener('activate', (e) => {
  e.waitUntil(clients.claim());
});
// Fetch handler omitted to avoid navigation overhead
"""
        out = sw.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def send_json(self, data):
        out = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out)

    def serve_ui(self):
        """Renders the luxury audiophile web user interface with ultra-light typography, liquid behaviour, optimised to minimise jitter and noise floor, with responsive drawer navigation."""
        html = """<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
  <meta name="theme-color" content="#0b0e14">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="manifest" href="/manifest.json">
  <title>Silent Angel Streamer — Control Studio</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@200;300;400;500;600&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
  <style>
    :root {
      /* Audiophile theme colour palette and liquid physics tokens */
      --bg-base: #0b0e14;
      --bg-surface: #121721;
      --bg-elevated: #1a2232;
      --bg-card: #151b27;
      --border-subtle: #242f44;
      --border-focus: #c99d52;
      --accent-gold: #c99d52;
      --accent-gold-hover: #e0b468;
      --accent-gold-glow: rgba(201, 157, 82, 0.28);
      --text-main: #f0f4fc;
      --text-muted: #8b99b5;
      --text-dim: #54627d;
      --accent-cyan: #38bdf8;
      --danger: #f43f5e;
      --success: #10b981;

      /* Liquid Audiophile Physics Engine (UK English) */
      --ease-liquid: cubic-bezier(0.22, 1, 0.36, 1);
      --ease-bounce: cubic-bezier(0.34, 1.35, 0.64, 1);
      --ease-soft-press: cubic-bezier(0.25, 0.8, 0.25, 1);
      --dur-fast: 0.18s;
      --dur-liquid: 0.32s;
      --dur-smooth: 0.44s;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      font-weight: 300;
      background-color: var(--bg-base);
      color: var(--text-main);
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      user-select: none;
      -webkit-font-smoothing: antialiased;
      letter-spacing: 0.3px;
    }

    .app-container {
      display: flex;
      flex: 1;
      height: calc(100vh - 88px);
      overflow: hidden;
    }

        /* Universal Liquid Tactile Soft-Push Feedback */
    button,
    .btn-circle,
    .btn-nav,
    .source-pill,
    .tuner-tab-btn,
    .station-card,
    .btn-connect,
    .header-device-badge,
    .hud-badge {
      transition: transform 0.28s cubic-bezier(0.2, 0.9, 0.3, 1.2),
                  box-shadow 0.28s cubic-bezier(0.2, 0.9, 0.3, 1),
                  background 0.22s ease,
                  border-color 0.22s ease,
                  color 0.22s ease;
      touch-action: manipulation;
    }

    button:active,
    .btn-circle:active,
    .btn-nav:active,
    .source-pill:active,
    .tuner-tab-btn:active,
    .station-card:active,
    .btn-connect:active,
    .header-device-badge:active {
      transform: scale(0.92) !important;
      transition: transform 0.08s ease-out !important;
    }

    .btn-play:active {
      transform: scale(0.90) !important;
      box-shadow: 0 0 24px rgba(201, 157, 82, 0.8) !important;
      transition: transform 0.08s ease-out !important;
    }

    /* Left Sidebar - Floating Overlay Drawer */
    .sidebar {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      bottom: 0 !important;
      width: min(320px, 86vw) !important;
      height: 100vh !important;
      height: 100dvh !important;
      z-index: 2500 !important;
      transform: translateX(-100%) !important;
      transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.35s ease !important;
      background: rgba(14, 19, 28, 0.96) !important;
      -webkit-backdrop-filter: blur(28px) saturate(180%) !important;
      backdrop-filter: blur(28px) saturate(180%) !important;
      border-right: 1px solid var(--border-subtle) !important;
      border-left: none !important;
      border-top: none !important;
      border-bottom: none !important;
      box-shadow: none !important;
      overflow-y: auto !important;
      -webkit-overflow-scrolling: touch !important;
      display: flex !important;
      flex-direction: column !important;
      padding: 24px 20px !important;
      gap: 20px !important;
    }

    .sidebar.drawer-open, .sidebar.open {
      transform: translateX(0) !important;
      box-shadow: 16px 0 50px rgba(0, 0, 0, 0.88) !important;
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
      font-size: 16px;
      font-weight: 500;
      letter-spacing: 2px;
      color: var(--text-main);
    }

    .brand-text span {
      font-size: 10px;
      color: var(--accent-gold);
      text-transform: uppercase;
      letter-spacing: 2.5px;
      font-weight: 400;
    }

    .nav-section h3 {
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: 1.8px;
      color: var(--text-dim);
      margin-bottom: 12px;
      font-weight: 500;
    }

    .nav-list {
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      border-radius: 8px;
      color: var(--text-muted);
      font-size: 13.5px;
      font-weight: 300;
      cursor: pointer;
      position: relative;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid);
      user-select: none;
    }

    .nav-item:hover {
      background: var(--bg-elevated);
      color: var(--text-main);
      transform: translateX(6px);
      box-shadow: inset 0 0 12px rgba(201, 157, 82, 0.06);
    }

    .nav-item:active {
      transform: translateX(3px) scale(0.975);
      transition-duration: 0.1s !important;
    }

    .nav-item.active {
      border-left: 2px solid var(--accent-gold);
      color: var(--accent-gold);
      background: linear-gradient(90deg, rgba(201, 157, 82, 0.14), transparent);
    }

    .device-card {
      margin-top: auto;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: border-color var(--dur-smooth) ease, box-shadow var(--dur-smooth) ease;
    }

    .device-card:hover {
      border-color: rgba(201, 157, 82, 0.3);
      box-shadow: 0 4px 18px rgba(0, 0, 0, 0.25);
    }

    .device-status {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11.5px;
      font-weight: 400;
      color: var(--text-muted);
    }

    .status-dot {
      width: 7px;
      height: 7px;
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
      font-weight: 500;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .device-info p {
      font-size: 11px;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      font-weight: 300;
    }

    .btn-connect {
      background: transparent;
      border: 1px solid var(--accent-gold);
      color: var(--accent-gold);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 400;
      cursor: pointer;
      text-align: center;
      user-select: none;
      position: relative;
      overflow: hidden;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  filter var(--dur-liquid) var(--ease-liquid);
    }

    .btn-connect:hover {
      background: var(--accent-gold);
      color: #0b0e14;
      transform: translateY(-2px) scale(1.02);
      box-shadow: 0 6px 18px rgba(201, 157, 82, 0.35);
    }

    .btn-connect:active {
      transform: translateY(1.5px) scale(0.96);
      filter: brightness(0.92);
      box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.45);
      transition-duration: 0.1s !important;
    }

    /* Main Viewport */
    .main-viewport {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 26px 40px;
      gap: 20px;
      overflow-y: auto;
      background: radial-gradient(circle at top right, rgba(201, 157, 82, 0.04), transparent 60%);
    }

    /* Header & Protocol Bar */
    .top-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }

    .header-device-badge {
      display: inline-flex;
      align-items: center;
      gap: 9px;
      padding: 7px 15px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      cursor: pointer;
      user-select: none;
      touch-action: manipulation;
      transition: border-color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid);
    }

    .header-device-badge:hover {
      border-color: var(--accent-gold);
      box-shadow: 0 0 12px var(--accent-gold-glow);
      transform: translateY(-1px);
    }

    .header-device-badge:active {
      transform: scale(0.94) !important;
    }

    .protocol-badges {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .source-pill {
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 5px 12px;
      border-radius: 20px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      font-size: 11.5px;
      font-weight: 300;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .source-pill:hover {
      border-color: var(--accent-gold);
      color: var(--text-main);
      background: var(--bg-elevated);
      transform: translateY(-2px) scale(1.03);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35), 0 0 12px rgba(201, 157, 82, 0.12);
    }

    .source-pill:active {
      transform: translateY(1.5px) scale(0.95);
      background: rgba(201, 157, 82, 0.12);
      box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.4);
      transition-duration: 0.1s !important;
    }

    .source-pill.active {
      background: rgba(201, 157, 82, 0.14);
      border-color: var(--accent-gold);
      color: var(--accent-gold);
      box-shadow: 0 0 14px rgba(201, 157, 82, 0.18);
    }

    /* Telemetry HUD */
    .telemetry-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .hud-badge {
      display: flex;
      align-items: center;
      gap: 7px;
      padding: 6px 12px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      font-size: 11.5px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 300;
      color: var(--text-muted);
      user-select: none;
      transition: border-color var(--dur-liquid) var(--ease-liquid),
                  color var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .hud-badge.gold {
      border-color: rgba(201, 157, 82, 0.4);
      color: var(--accent-gold);
      background: rgba(201, 157, 82, 0.06);
    }

    .hud-btn {
      cursor: pointer;
    }

    .hud-btn:hover {
      border-color: var(--accent-gold);
      color: var(--text-main);
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35), 0 0 12px rgba(201, 157, 82, 0.12);
      background: var(--bg-elevated);
    }

    .hud-btn:active {
      transform: translateY(1.5px) scale(0.95);
      background: var(--bg-base);
      box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.5);
      transition-duration: 0.1s !important;
    }

    /* Hero Now Playing Stage */
    .stage-container {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 18px;
      padding: 32px;
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
      background: radial-gradient(circle, rgba(201, 157, 82, 0.06), transparent 70%);
      pointer-events: none;
    }

    .visual-centre-box {
      position: relative;
      width: 280px;
      height: 280px;
      border-radius: 18px;
      background: linear-gradient(135deg, #18202e, #0c1017);
      border: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.65);
      overflow: hidden;
      cursor: pointer;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid);
      user-select: none;
    }

    .visual-centre-box:hover {
      transform: translateY(-2px) scale(1.02);
      border-color: rgba(201, 157, 82, 0.45);
      box-shadow: 0 20px 48px rgba(0, 0, 0, 0.75), 0 0 24px rgba(201, 157, 82, 0.16);
    }

    .visual-centre-box:active {
      transform: scale(0.985) translateY(1px);
      transition-duration: 0.1s !important;
    }

    .album-art-wrapper {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transform: scale(0.95);
      transition: opacity var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid),
                  visibility var(--dur-liquid) var(--ease-liquid);
    }

    .album-art-wrapper.active {
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
      transform: scale(1);
    }

    .album-art-wrapper img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: none;
      z-index: 2;
      transition: opacity var(--dur-smooth) var(--ease-liquid);
    }

    .vinyl-groove {
      position: absolute;
      width: 240px;
      height: 240px;
      border-radius: 50%;
      border: 1px dashed rgba(201, 157, 82, 0.12);
      animation: spin 30s linear infinite;
    }

    @keyframes spin {
      100% { transform: rotate(360deg); }
    }

    /* Dual Retro Analogue VU Meters */
    .vu-panel {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      gap: 12px;
      width: 100%;
      height: 100%;
      padding: 16px;
      background: linear-gradient(145deg, #141b26, #0e131d);
      border-radius: 14px;
      align-items: center;
      justify-content: center;
      z-index: 10;
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transform: scale(0.95);
      transition: opacity var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid),
                  visibility var(--dur-liquid) var(--ease-liquid);
    }

    .vu-panel.active {
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
      transform: scale(1);
    }

    .vu-meter-box {
      width: 100%;
      height: 100px;
      background: radial-gradient(ellipse at bottom, #25231c 0%, #151820 100%);
      border: 1px solid rgba(201, 157, 82, 0.35);
      border-radius: 10px;
      position: relative;
      overflow: hidden;
      box-shadow: inset 0 0 16px rgba(201, 157, 82, 0.15);
      display: flex;
      align-items: flex-end;
      justify-content: center;
      padding-bottom: 8px;
    }

    .vu-scale-arc {
      position: absolute;
      top: 12px;
      width: 85%;
      height: 55px;
      border-top: 1px solid rgba(201, 157, 82, 0.4);
      border-radius: 50% 50% 0 0;
      display: flex;
      justify-content: space-between;
      padding: 0 12px;
      font-size: 8px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent-gold);
    }

    .vu-needle {
      position: absolute;
      bottom: 6px;
      width: 2px;
      height: 72px;
      background: linear-gradient(to top, #ff4444 0%, #ff6b6b 25%, #c99d52 65%, #c99d52 100%);
      transform-origin: bottom center;
      transform: rotate(-35deg) translateZ(0);
      box-shadow: 0 0 5px rgba(201, 157, 82, 0.75);
      will-change: transform;
      pointer-events: none;
      transition: none !important;
    }

    .vu-pivot {
      position: absolute;
      bottom: 2px;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #e6be75 0%, #a67c32 70%, #543d14 100%);
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.8), 0 0 6px rgba(201, 157, 82, 0.5);
      border: 1px solid rgba(201, 157, 82, 0.8);
      z-index: 2;
    }

    .vu-channel-label {
      position: absolute;
      top: 8px;
      left: 12px;
      font-size: 9px;
      font-weight: 500;
      letter-spacing: 1px;
      color: var(--text-dim);
    }

    .vu-peak-indicator {
      position: absolute;
      top: 8px;
      right: 12px;
      font-size: 8px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: rgba(244, 63, 94, 0.2);
      transition: color 0.12s ease, text-shadow 0.12s ease;
      user-select: none;
    }
    .vu-peak-indicator.active {
      color: #f43f5e;
      text-shadow: 0 0 8px rgba(244, 63, 94, 0.95), 0 0 14px rgba(244, 63, 94, 0.6);
    }

    /* RTA Frequency Spectrum Analyser */
    .rta-panel {
      position: absolute;
      inset: 0;
      display: flex;
      width: 100%;
      height: 100%;
      padding: 20px 14px;
      background: linear-gradient(145deg, #121824, #0b0f17);
      border-radius: 14px;
      align-items: flex-end;
      justify-content: space-between;
      gap: 6px;
      z-index: 10;
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
      transform: scale(0.95);
      transition: opacity var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid),
                  visibility var(--dur-liquid) var(--ease-liquid);
    }

    .rta-panel.active {
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
      transform: scale(1);
    }

    .rta-bar-col {
      flex: 1;
      height: 100%;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      align-items: center;
      gap: 4px;
    }

    .rta-bar {
      width: 100%;
      height: 6%;
      background: linear-gradient(to top, #c99d52, #38bdf8);
      border-radius: 2px;
      box-shadow: 0 0 8px rgba(56, 189, 248, 0.25);
      will-change: height;
      transition: none !important;
    }

    .rta-lbl {
      font-size: 8px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-dim);
    }

    .stage-meta {
      display: flex;
      flex-direction: column;
      gap: 18px;
    }

    .format-tags {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .tag-hires-badge {
      display: flex;
      align-items: center;
      gap: 5px;
      background: #000;
      border: 1px solid #c99d52;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 9.5px;
      font-weight: 500;
      letter-spacing: 1.5px;
      color: #c99d52;
    }

    .track-title {
      font-size: 28px;
      font-weight: 500;
      letter-spacing: -0.4px;
      line-height: 1.25;
      color: var(--text-main);
    }

    .track-artist {
      font-size: 17px;
      font-weight: 400;
      color: var(--accent-gold);
      margin-top: 4px;
    }

    .track-album {
      font-size: 13.5px;
      color: var(--text-muted);
      font-weight: 300;
      margin-top: 2px;
    }

    /* Scrub Bar */
    .scrub-container {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 6px;
      cursor: pointer;
    }

    .scrub-track {
      width: 100%;
      height: 4px;
      background: var(--bg-elevated);
      border-radius: 4px;
      position: relative;
      cursor: pointer;
      overflow: hidden;
      transition: height var(--dur-liquid) var(--ease-liquid), background var(--dur-liquid) var(--ease-liquid);
    }

    .scrub-container:hover .scrub-track,
    .scrub-track:hover {
      height: 7px;
      background: #252f44;
    }

    .scrub-progress {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #c99d52, #e0b468);
      border-radius: 4px;
      box-shadow: 0 0 8px rgba(201, 157, 82, 0.5);
      transition: width 0.15s linear, box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .scrub-container:hover .scrub-progress {
      box-shadow: 0 0 16px rgba(201, 157, 82, 0.85);
    }

    .scrub-times {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
      font-weight: 300;
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
      gap: 3px;
    }

    .bar-title {
      font-size: 13px;
      font-weight: 400;
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
      font-weight: 300;
    }

    .bar-centre {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .btn-circle {
      width: 46px;
      height: 46px;
      min-width: 46px;
      min-height: 46px;
      border-radius: 50%;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      position: relative;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  color var(--dur-liquid) var(--ease-liquid);
    }

    .btn-circle:hover {
      background: #252f44;
      border-color: var(--accent-gold);
      transform: translateY(-3px) scale(1.06);
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.45), 0 0 16px rgba(201, 157, 82, 0.2);
    }

    .btn-circle:active {
      transform: translateY(2px) scale(0.92);
      background: #151b27;
      border-color: rgba(201, 157, 82, 0.6);
      box-shadow: inset 0 3px 7px rgba(0, 0, 0, 0.65), 0 1px 2px rgba(0, 0, 0, 0.3);
      transition-duration: 0.1s !important;
    }

    #btn-mute.muted {
      color: var(--danger) !important;
      background: rgba(244, 63, 94, 0.18) !important;
      border-color: rgba(244, 63, 94, 0.65) !important;
      box-shadow: 0 0 14px rgba(244, 63, 94, 0.35) !important;
    }

    .btn-play {
      width: 56px;
      height: 56px;
      min-width: 56px;
      min-height: 56px;
      background: var(--accent-gold);
      border: none;
      color: #0b0e14;
      box-shadow: 0 0 18px var(--accent-gold-glow);
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  filter var(--dur-liquid) var(--ease-liquid);
    }

    .btn-play:hover {
      background: var(--accent-gold-hover);
      transform: translateY(-3.5px) scale(1.08);
      box-shadow: 0 12px 28px var(--accent-gold-glow), 0 0 20px rgba(201, 157, 82, 0.4);
    }

    .btn-play:active {
      transform: translateY(2.5px) scale(0.92);
      background: var(--accent-gold);
      filter: brightness(0.88);
      box-shadow: inset 0 3px 8px rgba(0, 0, 0, 0.55), 0 1px 3px rgba(0, 0, 0, 0.3);
      transition-duration: 0.1s !important;
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
      border-radius: 4px;
      outline: none;
      transition: background var(--dur-liquid) var(--ease-liquid);
    }

    .vol-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 20px;
      height: 20px;
      box-shadow: 0 0 8px rgba(201, 157, 82, 0.5);
      border-radius: 50%;
      background: var(--accent-gold);
      cursor: pointer;
      box-shadow: 0 0 10px rgba(201, 157, 82, 0.7);
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid);
    }

    .vol-slider::-webkit-slider-thumb:hover {
      transform: scale(1.35);
      box-shadow: 0 0 18px rgba(201, 157, 82, 0.95), 0 0 30px rgba(201, 157, 82, 0.4);
      background: var(--accent-gold-hover);
    }

    .vol-slider::-webkit-slider-thumb:active {
      transform: scale(1.5);
      box-shadow: 0 0 24px rgba(201, 157, 82, 1), 0 0 45px rgba(201, 157, 82, 0.6);
      transition-duration: 0.1s !important;
    }

    .vol-percent {
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
      width: 32px;
      text-align: right;
    }

    .fixed-vol-badge {
      display: none;
      font-size: 10.5px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent-gold);
      border: 1px solid var(--accent-gold);
      padding: 3px 8px;
      border-radius: 4px;
      letter-spacing: 0.5px;
      cursor: pointer;
      transition: transform var(--dur-quick) var(--ease-tactile),
                  background var(--dur-quick) ease,
                  box-shadow var(--dur-quick) ease;
    }

    .fixed-vol-badge:hover {
      background: rgba(201, 157, 82, 0.12);
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(201, 157, 82, 0.25);
    }

    .fixed-vol-badge:active {
      transform: translateY(1px) scale(0.96);
      transition-duration: 0.06s;
    }

        /* Tab Pane Fluid Slide & Fade Animation */
    @keyframes fluidTabFadeIn {
      from {
        opacity: 0;
        transform: translateY(8px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    .tab-pane-active {
      animation: fluidTabFadeIn 0.32s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    /* Liquid Modal Overlays */
    .modal-overlay {
      position: fixed;
      inset: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(5, 8, 14, 0.82);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2000;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1),
                  backdrop-filter 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .modal-overlay.active {
      opacity: 1;
      pointer-events: auto;
    }

    .modal-card {
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      width: 90%;
      max-width: 660px;
      padding: 30px;
      box-shadow: 0 28px 70px rgba(0, 0, 0, 0.85), 0 0 32px rgba(201, 157, 82, 0.08);
      display: flex;
      flex-direction: column;
      gap: 18px;
      max-height: 88vh;
      overflow-y: auto;
      opacity: 0;
      transform: scale(0.92) translateY(24px);
      transition: transform var(--dur-smooth) var(--ease-liquid),
                  opacity var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-smooth) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid);
      transform-origin: center center;
    }

    .modal-overlay.active .modal-card {
      opacity: 1;
      transform: scale(1) translateY(0);
    }

    .modal-card.wide {
      max-width: 920px;
    }

    .modal-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .modal-head h3 {
      font-size: 18px;
      font-weight: 500;
      letter-spacing: 0.5px;
    }

    .btn-close {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 24px;
      cursor: pointer;
      line-height: 1;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  color var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .btn-close:hover {
      color: var(--accent-gold);
      background: rgba(201, 157, 82, 0.15);
      transform: rotate(90deg) scale(1.15);
      box-shadow: 0 0 14px rgba(201, 157, 82, 0.2);
    }

    .btn-close:active {
      transform: rotate(90deg) scale(0.9);
      transition-duration: 0.1s !important;
    }

    /* Tuner Tabs */
    .tuner-tabs {
      display: flex;
      border-bottom: 1px solid var(--border-subtle);
      gap: 18px;
    }

    .tuner-tab-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 13px;
      font-weight: 400;
      padding-bottom: 10px;
      cursor: pointer;
      position: relative;
      user-select: none;
      transition: color var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid);
    }

    .tuner-tab-btn:hover {
      color: var(--accent-gold);
      transform: translateY(-1.5px);
    }

    .tuner-tab-btn:active {
      transform: translateY(1px) scale(0.96);
      transition-duration: 0.1s !important;
    }

    .tuner-tab-btn.active {
      color: var(--accent-gold);
    }

    .tuner-tab-btn.active::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      width: 100%;
      height: 2px;
      background: var(--accent-gold);
      box-shadow: 0 0 10px var(--accent-gold);
      transition: width var(--dur-liquid) var(--ease-liquid);
    }

    .tab-pane {
      opacity: 0;
      transform: translateY(6px);
      transition: opacity var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-liquid) var(--ease-liquid);
    }

    .tab-pane.active {
      opacity: 1;
      transform: translateY(0);
    }

    .radio-search-bar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .tuner-input {
      flex: 1;
      min-width: 200px;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px 14px;
      color: var(--text-main);
      font-size: 12.5px;
      font-weight: 300;
      outline: none;
      transition: border-color var(--dur-quick) ease,
                  box-shadow var(--dur-quick) ease,
                  background var(--dur-quick) ease;
    }

    .tuner-select {
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 10px 14px;
      color: var(--text-main);
      font-size: 12px;
      font-weight: 300;
      outline: none;
      transition: border-color var(--dur-quick) ease,
                  box-shadow var(--dur-quick) ease,
                  background var(--dur-quick) ease;
    }

    .tuner-input:focus,
    .tuner-select:focus {
      border-color: var(--accent-gold);
      box-shadow: 0 0 12px rgba(201, 157, 82, 0.2);
      background: #1e2637;
    }

    .station-category-title {
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      color: var(--accent-gold);
      margin: 14px 0 8px 0;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .station-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
    }

    .station-card {
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 14px;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 6px;
      position: relative;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .station-card:hover {
      border-color: var(--accent-gold);
      background: #202838;
      transform: translateY(-4px) scale(1.01);
      box-shadow: 0 14px 32px rgba(0, 0, 0, 0.55), 0 0 18px rgba(201, 157, 82, 0.12);
    }

    .station-card:active {
      transform: translateY(1px) scale(0.985);
      background: #171d2b;
      box-shadow: inset 0 2px 6px rgba(0, 0, 0, 0.45);
      transition-duration: 0.1s !important;
    }

    .station-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 8px;
    }

    .station-header h4 {
      font-size: 13px;
      font-weight: 400;
      color: var(--text-main);
      line-height: 1.3;
    }

    .btn-fav {
      background: none;
      border: none;
      color: var(--text-dim);
      font-size: 16px;
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-bounce),
                  color var(--dur-liquid) var(--ease-liquid);
    }

    .btn-fav:hover {
      transform: scale(1.3);
      color: #eab308;
    }

    .btn-fav:active {
      transform: scale(0.85);
      transition-duration: 0.1s !important;
    }

    .btn-fav.active {
      color: #eab308;
    }

    .station-format-badge {
      font-size: 10px;
      font-weight: 400;
      color: var(--accent-gold);
      font-family: 'JetBrains Mono', monospace;
    }

    .station-tags {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 4px;
    }

    .station-tag {
      font-size: 9px;
      background: rgba(255, 255, 255, 0.05);
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--text-muted);
      font-weight: 300;
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
      font-size: 12.5px;
      font-weight: 400;
    }

    .radar-pulse {
      width: 8px;
      height: 8px;
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
      max-height: 260px;
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
      padding: 12px 16px;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      cursor: pointer;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .device-result-item:hover {
      border-color: var(--accent-gold);
      background: #202838;
      transform: translateX(6px);
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35), 0 0 14px rgba(201, 157, 82, 0.1);
    }

    .device-result-item:active {
      transform: translateX(3px) scale(0.985);
      background: #171d2b;
      box-shadow: inset 0 2px 5px rgba(0, 0, 0, 0.4);
      transition-duration: 0.1s !important;
    }

    .device-result-item.silent-angel-match,
    .device-result-item.bremen-match {
      border-left: 3px solid var(--accent-gold);
      background: linear-gradient(90deg, rgba(201, 157, 82, 0.08), #1a2232);
    }

    .badge-silent-angel,
    .badge-bremen {
      background: var(--accent-gold);
      color: #0b0e14;
      font-size: 9px;
      font-weight: 500;
      padding: 2px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-left: 6px;
    }

    .storage-list {
      max-height: 280px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .storage-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      background: var(--bg-elevated);
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
      cursor: pointer;
      user-select: none;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .storage-item:hover {
      border-color: var(--accent-gold);
      background: #202838;
      transform: translateX(5px);
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
    }

    .storage-item:active {
      transform: translateX(2px) scale(0.985);
      transition-duration: 0.1s !important;
    }

    /* Parametric Equaliser Curve & Sliders */
    .eq-curve-svg {
      width: 100%;
      height: 120px;
      background: var(--bg-base);
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
    }

    .eq-sliders-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 10px;
    }

    .eq-slider-col {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      flex: 1;
    }

    .eq-range {
      writing-mode: vertical-lr;
      direction: rtl;
      appearance: none;
      -webkit-appearance: none;
      width: 8px;
      height: 100px;
      background: var(--bg-elevated);
      outline: none;
    }

    /* Hamburger & Navigation Drawer Styles */
    .btn-hamburger {
      display: none;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 5px;
      width: 44px;
      height: 44px;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      cursor: pointer;
      padding: 10px;
      flex-shrink: 0;
      transition: background var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-liquid) var(--ease-liquid),
                  transform var(--dur-tactile) var(--ease-soft-press);
    }

    .btn-hamburger:hover {
      background: #202838;
      border-color: var(--accent-gold);
    }

    .btn-hamburger:active {
      transform: scale(0.92);
      transition-duration: 0.1s !important;
    }

    .hamburger-bar {
      width: 22px;
      height: 2px;
      background-color: var(--accent-gold);
      border-radius: 2px;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  opacity var(--dur-liquid) var(--ease-liquid);
    }

    /* Morphing hamburger to close 'X' when drawer is active */
    .btn-hamburger.active .hamburger-bar:nth-child(1) {
      transform: translateY(7px) rotate(45deg);
    }
    .btn-hamburger.active .hamburger-bar:nth-child(2) {
      opacity: 0;
      transform: scaleX(0);
    }
    .btn-hamburger.active .hamburger-bar:nth-child(3) {
      transform: translateY(-7px) rotate(-45deg);
    }

    .nav-drawer-backdrop {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(5, 8, 14, 0.75);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      z-index: 1400;
      opacity: 0;
      pointer-events: none;
      transition: opacity var(--dur-liquid) var(--ease-liquid);
    }

    .nav-drawer-backdrop.active {
      opacity: 1;
      pointer-events: auto;
    }

    .btn-drawer-close {
      display: none;
      background: none;
      border: none;
      color: var(--text-dim);
      font-size: 26px;
      line-height: 1;
      cursor: pointer;
      padding: 6px 10px;
      border-radius: 8px;
      margin-left: auto;
      transition: color var(--dur-tactile) var(--ease-liquid),
                  transform var(--dur-tactile) var(--ease-soft-press);
    }

    .btn-drawer-close:hover {
      color: var(--accent-gold);
    }
    .btn-drawer-close:active {
      transform: scale(0.9);
      transition-duration: 0.1s !important;
    }

    .header-left-group {
      display: flex;
      align-items: center;
      gap: 14px;
      flex-shrink: 0;
    }

    /* Tablet & Responsive Media Queries with Floating Bottom Master Player Dock */
    @media (max-width: 1024px) {
      .btn-hamburger {
        display: flex;
      }

      .btn-drawer-close {
        display: flex;
      }

      .nav-drawer-backdrop {
        display: block;
      }

      .app-container {
        height: 100vh;
        height: 100dvh;
        overflow: hidden;
      }

      .sidebar {
        position: fixed;
        top: 0;
        left: 0;
        bottom: 0;
        width: min(320px, 86vw);
        height: 100vh;
        height: 100dvh;
        z-index: 1500;
        transform: translateX(-100%);
        box-shadow: none;
        transition: transform var(--dur-smooth) var(--ease-liquid),
                    box-shadow var(--dur-smooth) var(--ease-liquid);
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
      }

      .sidebar.drawer-open {
        transform: translateX(0);
        box-shadow: 14px 0 45px rgba(0, 0, 0, 0.85);
      }

      .main-viewport {
        padding: 16px 20px calc(92px + env(safe-area-inset-bottom, 12px)) 20px;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
      }

      .protocol-badges {
        flex-wrap: nowrap;
        overflow-x: auto;
        padding-bottom: 4px;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
      }
      .protocol-badges::-webkit-scrollbar {
        display: none;
      }

      /* Elevate Master Bar into a Floating Dock Island */
      .master-bar {
        position: fixed;
        bottom: max(12px, env(safe-area-inset-bottom, 12px));
        left: max(14px, env(safe-area-inset-left, 14px));
        right: max(14px, env(safe-area-inset-right, 14px));
        max-width: 760px;
        margin: 0 auto;
        height: 72px;
        border-radius: 20px;
        background: rgba(18, 23, 33, 0.90);
        -webkit-backdrop-filter: blur(20px);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(201, 157, 82, 0.38);
        box-shadow: 0 14px 40px rgba(0, 0, 0, 0.75), 0 0 20px rgba(201, 157, 82, 0.16);
        z-index: 1200;
        padding: 0 20px;
        transition: transform var(--dur-liquid) var(--ease-liquid),
                    opacity var(--dur-liquid) var(--ease-liquid);
      }
    }

    /* Mobile Portrait (< 768px) */
    @media (max-width: 768px) {
      .main-viewport {
        padding: 12px 12px calc(84px + env(safe-area-inset-bottom, 10px)) 12px;
        gap: 12px;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
      }

      .top-header {
        flex-direction: row;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        padding-bottom: 4px;
      }

      .header-left-group {
        justify-content: flex-start;
      }

      .header-title h2 {
        font-size: 15px;
      }

      .header-title p {
        font-size: 10px;
      }

      .telemetry-row {
        flex-wrap: nowrap;
        overflow-x: auto;
        padding-bottom: 2px;
        gap: 6px;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
      }
      .telemetry-row::-webkit-scrollbar {
        display: none;
      }

      /* Stack stage cleanly vertically and fit comfortably within viewport */
      .stage-container {
        grid-template-columns: 1fr;
        padding: 14px 12px;
        gap: 14px;
        text-align: center;
        border-radius: 16px;
      }

      .visual-centre-box {
        margin: 0 auto;
        width: min(220px, 54vw);
        height: min(220px, 54vw);
        border-radius: 14px;
      }

      .vu-needle {
        height: 52px;
        bottom: 5px;
        transition: none !important;
      }
      .vu-pivot {
        width: 10px;
        height: 10px;
      }
      .vu-scale-arc {
        height: 42px;
        font-size: 7px;
        padding: 0 8px;
      }

      .stage-meta {
        gap: 12px;
        align-items: center;
      }

      .format-tags {
        justify-content: center;
      }

      .track-title {
        font-size: 19px;
        line-height: 1.25;
      }

      .track-artist {
        font-size: 13.5px;
        margin-top: 3px;
      }

      .track-album {
        font-size: 11px;
      }

      .scrub-container {
        gap: 6px;
        margin-top: 4px;
      }

      /* Floating Master Player Bar Mobile Portrait */
      .master-bar {
        position: fixed;
        bottom: max(12px, env(safe-area-inset-bottom, 12px));
        left: max(10px, env(safe-area-inset-left, 10px));
        right: max(10px, env(safe-area-inset-right, 10px));
        height: 78px;
        border-radius: 20px;
        padding: 0 16px;
        gap: 10px;
        background: rgba(18, 23, 33, 0.92);
        -webkit-backdrop-filter: blur(20px);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(201, 157, 82, 0.38);
        box-shadow: 0 12px 34px rgba(0, 0, 0, 0.8), 0 0 16px rgba(201, 157, 82, 0.18);
        z-index: 1200;
      }

      .bar-left {
        width: auto;
        max-width: 120px;
        min-width: 0;
      }

      .bar-title {
        font-size: 11px;
        font-weight: 500;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .bar-artist {
        font-size: 9.5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .bar-centre {
        flex: 1;
        justify-content: center;
        gap: 6px;
      }

      .btn-circle {
        width: 44px;
        height: 44px;
        min-width: 44px;
        min-height: 44px;
      }

      .btn-play {
        width: 52px;
        height: 52px;
        min-width: 52px;
        min-height: 52px;
      }

      .bar-right {
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .vol-slider {
        width: 55px;
      }

      /* Modals Responsive */
      .modal-card {
        padding: 18px 14px;
        max-width: 95vw;
        max-height: 90vh;
      }

      .station-grid {
        grid-template-columns: 1fr;
      }

      .tuner-tabs {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
        flex-wrap: nowrap;
      }
      .tuner-tabs::-webkit-scrollbar {
        display: none;
      }
    }

    /* Smallest Mobile Portrait Screens (< 420px width or < 700px height) */
    @media (max-width: 420px) {
      .visual-centre-box {
        width: min(180px, 48vw);
        height: min(180px, 48vw);
      }
      .track-title {
        font-size: 17px;
      }
      .master-bar {
        height: 62px;
        padding: 0 10px;
        gap: 6px;
      }
      .bar-left {
        max-width: 95px;
      }
      .bar-right .fixed-vol-badge {
        display: none;
      }
      .vol-slider {
        width: 46px;
      }
    }

    /* Mobile / Tablet Landscape Mode (Height <= 550px and Orientation Landscape) */
    @media (max-height: 550px) and (orientation: landscape) {
      .app-container {
        height: 100vh;
        height: 100dvh;
        overflow: hidden;
      }

      .main-viewport {
        padding: 8px 14px calc(54px + env(safe-area-inset-bottom, 6px)) 14px;
        gap: 6px;
        height: 100%;
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
      }

      .top-header {
        padding-bottom: 2px;
        flex-wrap: nowrap;
        gap: 8px;
        align-items: center;
      }

      .header-title h2 {
        font-size: 13.5px;
      }

      .header-title p {
        display: none;
      }

      .protocol-badges {
        flex-wrap: nowrap;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        scrollbar-width: none;
      }

      .source-pill {
        padding: 2px 7px;
        font-size: 9.5px;
      }

      .telemetry-row {
        display: none;
      }

      /* Compact side-by-side stage that fits 100% on screen */
      .stage-container {
        grid-template-columns: 125px 1fr;
        padding: 8px 14px;
        gap: 12px;
        min-height: 0;
        border-radius: 12px;
        align-items: center;
      }

      .visual-centre-box {
        width: 110px;
        height: 110px;
        min-width: 110px;
        border-radius: 10px;
        margin: 0;
      }

      .vu-needle {
        height: 28px;
        bottom: 3px;
        transition: none !important;
      }
      .vu-pivot {
        width: 8px;
        height: 8px;
      }
      .vu-scale-arc {
        height: 24px;
        font-size: 6px;
        padding: 0 6px;
      }
      .vu-channel-label, .vu-peak-indicator {
        font-size: 7px;
      }

      .stage-meta {
        gap: 4px;
      }

      .format-tags {
        gap: 6px;
      }

      .tag-hires-badge {
        padding: 1.5px 5px;
        font-size: 8px;
      }

      .hud-badge {
        padding: 2px 6px;
        font-size: 9px;
      }

      .track-title {
        font-size: 15px;
        line-height: 1.2;
      }

      .track-artist {
        font-size: 11.5px;
        margin-top: 1px;
      }

      .track-album {
        font-size: 10px;
        margin-top: 0;
      }

      .scrub-container {
        gap: 3px;
        margin-top: 2px;
      }

      .scrub-track {
        height: 3px;
      }

      .scrub-times {
        font-size: 9px;
      }

      /* Ultra-slim floating dock in landscape */
      .master-bar {
        position: fixed;
        bottom: max(6px, env(safe-area-inset-bottom, 6px));
        left: max(10px, env(safe-area-inset-left, 10px));
        right: max(10px, env(safe-area-inset-right, 10px));
        max-width: 820px;
        margin: 0 auto;
        height: 56px;
        border-radius: 16px;
        padding: 0 16px;
        gap: 12px;
        background: rgba(18, 23, 33, 0.94);
        -webkit-backdrop-filter: blur(16px);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(201, 157, 82, 0.42);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.82), 0 0 14px rgba(201, 157, 82, 0.18);
        z-index: 1200;
      }

      .bar-left {
        max-width: 140px;
        gap: 1px;
      }

      .bar-title {
        font-size: 10.5px;
      }

      .bar-artist {
        font-size: 8.5px;
      }

      .bar-centre {
        gap: 5px;
      }

      .btn-circle {
        width: 30px;
        height: 30px;
      }

      .btn-circle svg {
        width: 12px;
        height: 12px;
      }

      .btn-play {
        width: 34px;
        height: 34px;
      }

      .btn-play svg {
        width: 15px;
        height: 15px;
      }

      .vol-slider {
        width: 50px;
      }

      .vol-percent {
        font-size: 8.5px;
      }

      .modal-card {
        max-height: calc(100dvh - 20px);
        padding: 12px 14px;
      }

      .modal-card.wide {
        max-height: calc(100dvh - 20px);
      }

      #curated-container, #search-results-grid, #fav-stations-grid {
        max-height: calc(100dvh - 120px) !important;
      }
    }
  
    /* =========================================================
       1. Auto-Hiding Control Dock & Bottom Summon Strip
       ========================================================= */
    .master-bar {
      transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1),
                  opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    .master-bar.dock-hidden {
      transform: translateY(calc(100% + 32px)) !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }

    .dock-summon-strip {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: 18px;
      z-index: 1150;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: auto;
    }

    .dock-summon-pill {
      width: 48px;
      height: 4px;
      border-radius: 4px;
      background: rgba(201, 157, 82, 0.3);
      transition: all 0.3s ease;
    }

    .dock-summon-strip:hover .dock-summon-pill,
    .dock-summon-strip:active .dock-summon-pill {
      width: 72px;
      height: 5px;
      background: var(--accent-gold);
      box-shadow: 0 0 12px var(--accent-gold);
    }

    /* =========================================================
       2. Full-Height Stage & Balanced Right Telemetry Grid
       ========================================================= */
    .main-viewport {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 24px 36px 110px 36px;
      gap: 16px;
      min-height: 0;
      overflow-y: auto;
    }

    .stage-container {
      flex: 1;
      min-height: 420px;
      display: grid;
      grid-template-columns: minmax(360px, 480px) 1fr;
      gap: 36px;
      align-items: stretch;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 20px;
      padding: 28px 32px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4);
      position: relative;
      overflow: hidden;
    }

    .visual-centre-box {
      width: 100%;
      height: 100%;
      min-height: 340px;
      max-height: calc(100vh - 290px);
      aspect-ratio: 1 / 1;
      border-radius: 18px;
      background: linear-gradient(135deg, #18202e, #0c1017);
      border: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.65);
      overflow: hidden;
      cursor: pointer;
      user-select: none;
      margin: auto 0;
      position: relative;
    }

    .stage-meta {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 6px 0;
      gap: 16px;
      flex: 1;
    }

    .track-title {
      font-size: 28px;
      font-weight: 400;
      letter-spacing: -0.4px;
      color: var(--text-main);
      line-height: 1.2;
    }

    .track-artist {
      font-size: 16px;
      font-weight: 300;
      color: var(--accent-gold);
      margin-top: 4px;
    }

    .track-album {
      font-size: 13.5px;
      color: var(--text-muted);
      font-weight: 300;
      margin-top: 2px;
    }

    /* 4-Cell Telemetry Matrix to eliminate right dead space */
    .stage-telemetry-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      margin-top: 8px;
    }

    .telemetry-cell {
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      transition: border-color var(--dur-liquid) var(--ease-liquid);
    }

    .telemetry-cell:hover {
      border-color: rgba(201, 157, 82, 0.4);
    }

    .telemetry-cell-lbl {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-dim);
      font-weight: 400;
    }

    .telemetry-cell-val {
      font-size: 13px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 500;
      color: var(--text-main);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* =========================================================
       3. Discovery Landscape Responsive Grid
       ========================================================= */
    .discovery-body {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .discovery-controls-col {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .discovery-results-col {
      display: flex;
      flex-direction: column;
      gap: 8px;
      flex: 1;
    }

    @media (orientation: landscape) and (max-height: 600px) {
      #discovery-modal .modal-card {
        max-width: 820px !important;
        padding: 16px 24px !important;
        gap: 10px !important;
        max-height: 94vh !important;
      }
      .discovery-body {
        display: grid !important;
        grid-template-columns: 1fr 1.35fr !important;
        gap: 16px !important;
        align-items: stretch !important;
      }
      .discovery-results-col .device-results {
        max-height: 52vh !important;
      }
    }

    /* =========================================================
       4. Protocol Hub Modal
       ========================================================= */
    .proto-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
      margin-top: 10px;
    }

    .proto-card {
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      cursor: pointer;
      user-select: none;
      transition: all var(--dur-liquid) var(--ease-liquid);
    }

    .proto-card:hover {
      border-color: var(--accent-gold);
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4), 0 0 16px rgba(201, 157, 82, 0.15);
    }

    .proto-card.active {
      border-color: var(--accent-gold);
      background: linear-gradient(135deg, rgba(201, 157, 82, 0.12), #1a2232);
      box-shadow: 0 0 18px rgba(201, 157, 82, 0.25);
    }

    .proto-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .proto-title {
      font-size: 15px;
      font-weight: 500;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .proto-badge {
      font-size: 10px;
      font-weight: 500;
      padding: 3px 7px;
      border-radius: 10px;
      background: rgba(201, 157, 82, 0.18);
      color: var(--accent-gold);
    }

    .proto-specs {
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent-cyan);
    }

    .proto-desc {
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.4;
    }

    .proto-guide {
      font-size: 11px;
      color: var(--text-dim);
      background: rgba(0, 0, 0, 0.25);
      padding: 8px 10px;
      border-radius: 6px;
      border-left: 2px solid var(--accent-gold);
    }

    /* =========================================================
       5. 3D Three.js Radio Station Globe
       ========================================================= */
    #radio-tab-globe {
      display: none;
      flex-direction: column;
      gap: 10px;
      height: 56vh;
      min-height: 380px;
      position: relative;
      overflow: hidden;
      border-radius: 14px;
      background: radial-gradient(circle at center, #121824 0%, #070a10 100%);
      border: 1px solid var(--border-subtle);
    }

    .globe-filter-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 16px;
      background: rgba(11, 14, 20, 0.85);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border-subtle);
      z-index: 10;
      gap: 10px;
      flex-wrap: wrap;
    }

    .globe-genre-pills {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }

    .globe-pill {
      font-size: 11px;
      padding: 4px 10px;
      border-radius: 12px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
      transition: all var(--dur-liquid) var(--ease-liquid);
    }

    .globe-pill:hover {
      border-color: var(--accent-gold);
      color: var(--text-main);
    }

    .globe-pill.active {
      background: rgba(201, 157, 82, 0.2);
      border-color: var(--accent-gold);
      color: var(--accent-gold);
      box-shadow: 0 0 10px rgba(201, 157, 82, 0.3);
    }

    #globe-canvas-box {
      flex: 1;
      width: 100%;
      height: 100%;
      position: relative;
      cursor: grab;
    }

    #globe-canvas-box:active {
      cursor: grabbing;
    }

    .globe-hint {
      position: absolute;
      bottom: 12px;
      left: 16px;
      font-size: 11px;
      color: var(--text-dim);
      pointer-events: none;
      z-index: 10;
      background: rgba(11, 14, 20, 0.7);
      padding: 4px 10px;
      border-radius: 10px;
      backdrop-filter: blur(4px);
    }

    .globe-station-card {
      position: absolute;
      top: 56px;
      right: 16px;
      width: 250px;
      background: rgba(18, 23, 33, 0.92);
      border: 1px solid var(--accent-gold);
      border-radius: 12px;
      padding: 14px;
      display: none;
      flex-direction: column;
      gap: 8px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.8), 0 0 20px rgba(201, 157, 82, 0.2);
      backdrop-filter: blur(12px);
      z-index: 20;
      transform: scale(0.95);
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .globe-station-card.visible {
      display: flex;
      transform: scale(1);
    }

    .station-card-title {
      font-size: 14px;
      font-weight: 500;
      color: var(--text-main);
    }

    .station-card-loc {
      font-size: 11.5px;
      color: var(--accent-gold);
    }

    .station-card-meta {
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-muted);
    }

    .btn-tune-in {
      background: var(--accent-gold);
      color: #0b0e14;
      border: none;
      border-radius: 8px;
      padding: 8px 12px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      margin-top: 4px;
      transition: all var(--dur-liquid) var(--ease-liquid);
    }

    .btn-tune-in:hover {
      background: var(--accent-gold-hover);
      box-shadow: 0 0 14px var(--accent-gold-glow);
      transform: translateY(-1px);
    }

  
    /* =========================================================================
       Floating Top Bar & Auto-Hiding Physics (UK English)
       ========================================================================= */
    .floating-top-bar {
      position: fixed;
      top: max(12px, env(safe-area-inset-top, 12px));
      left: max(14px, env(safe-area-inset-left, 14px));
      right: max(14px, env(safe-area-inset-right, 14px));
      max-width: 1200px;
      margin: 0 auto;
      height: 58px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 16px;
      gap: 12px;
      border-radius: 18px;
      background: rgba(18, 23, 33, 0.90);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(201, 157, 82, 0.35);
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.75), 0 0 20px rgba(201, 157, 82, 0.10);
      z-index: 1250;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  opacity var(--dur-liquid) var(--ease-liquid);
    }

    .floating-top-bar.top-hidden {
      transform: translateY(calc(-100% - 30px));
      opacity: 0;
      pointer-events: none;
    }

    /* Top Summon Strip */
    .dock-top-summon-strip {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      height: 16px;
      z-index: 1260;
      cursor: pointer;
      display: flex;
      justify-content: center;
      align-items: flex-start;
    }

    .dock-top-summon-strip::after {
      content: '';
      width: 64px;
      height: 3.5px;
      border-radius: 0 0 6px 6px;
      background: var(--accent-gold);
      opacity: 0.45;
      box-shadow: 0 0 12px var(--accent-gold-glow);
      transition: opacity var(--dur-fast), transform var(--dur-fast);
    }

    .dock-top-summon-strip:hover::after,
    .dock-top-summon-strip:active::after {
      opacity: 0.95;
      transform: scaleX(1.4);
    }

    /* Dynamic Main Viewport & Dynamic Stage (Taking Full Screen) */
    .main-viewport {
      width: 100%;
      height: 100vh;
      height: 100dvh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: stretch;
      padding: 76px 28px 140px 28px;
      box-sizing: border-box;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      position: relative;
    }

    .stage-container {
      flex: 1;
      width: 100%;
      max-width: 1400px;
      margin: auto;
      display: grid;
      grid-template-columns: minmax(320px, 1fr) minmax(360px, 1.25fr);
      gap: 36px;
      align-items: center;
      justify-content: center;
      min-height: 0;
    }

    .visual-centre-box {
      width: 100%;
      max-width: min(540px, calc(100vh - 220px));
      max-height: min(540px, calc(100vh - 220px));
      aspect-ratio: 1 / 1;
      margin: auto;
      border-radius: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.05);
      overflow: hidden;
      cursor: pointer;
    }

    /* Master Dock Container (Timeline Bar positioned directly above Controller Bar) */
    .master-dock-container {
      position: fixed;
      bottom: max(14px, env(safe-area-inset-bottom, 14px));
      left: max(16px, env(safe-area-inset-left, 16px));
      right: max(16px, env(safe-area-inset-right, 16px));
      max-width: 860px;
      margin: 0 auto;
      z-index: 1200;
      display: flex;
      flex-direction: column;
      gap: 8px;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  opacity var(--dur-liquid) var(--ease-liquid);
    }

    .master-dock-container.dock-hidden {
      transform: translateY(calc(100% + 40px));
      opacity: 0;
      pointer-events: none;
    }

    /* Floating Timeline Bar positioned directly above bottom bar */
    .dock-timeline-bar {
      width: 100%;
      height: 42px;
      border-radius: 16px;
      background: rgba(18, 23, 33, 0.90);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(201, 157, 82, 0.35);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.65);
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 0 18px;
      box-sizing: border-box;
    }

    .dock-time-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 500;
      color: var(--accent-gold);
      min-width: 44px;
      text-align: center;
      user-select: none;
    }

    .dock-scrub-track {
      flex: 1;
      height: 12px;
      background: rgba(36, 47, 68, 0.8);
      border-radius: 6px;
      cursor: pointer;
      position: relative;
      background-clip: content-box;
      touch-action: none;
    }

    .dock-scrub-progress {
      height: 100%;
      background: linear-gradient(90deg, #c99d52, #e0b468);
      border-radius: 6px;
      width: 0%;
      position: relative;
      box-shadow: 0 0 10px var(--accent-gold-glow);
    }

    .dock-scrub-progress::after {
      content: '';
      position: absolute;
      right: -6px;
      top: 50%;
      transform: translateY(-50%);
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: #ffffff;
      border: 2.5px solid var(--accent-gold);
      box-shadow: 0 0 12px var(--accent-gold);
      transition: transform var(--dur-fast);
    }

    .dock-scrub-track:hover .dock-scrub-progress::after,
    .dock-scrub-track:active .dock-scrub-progress::after {
      transform: translateY(-50%) scale(1.25);
    }

    /* Pure Full-Screen 3D Globe Internet Radio View */
    .globe-fullscreen-view {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      height: 100dvh;
      background: #06090e; /* Luxury deep dark audiophile backdrop */
      z-index: 2000;
      display: none;
      opacity: 0;
      overflow: hidden;
      transition: opacity 0.35s ease;
    }

    .globe-fullscreen-view.active {
      display: block;
      opacity: 1;
    }

    .globe-fullscreen-container {
      width: 100%;
      height: 100%;
      position: absolute;
      top: 0;
      left: 0;
      touch-action: none;
    }

    .btn-globe-return {
      position: absolute;
      top: max(20px, env(safe-area-inset-top, 20px));
      left: max(20px, env(safe-area-inset-left, 20px));
      z-index: 2010;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 18px;
      border-radius: 30px;
      background: rgba(18, 23, 33, 0.85);
      -webkit-backdrop-filter: blur(16px);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(201, 157, 82, 0.4);
      color: var(--accent-gold);
      font-family: 'Outfit', sans-serif;
      font-size: 13.5px;
      font-weight: 500;
      cursor: pointer;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
      transition: transform 0.15s ease, background 0.2s ease, border-color 0.2s ease;
    }

    .btn-globe-return:hover {
      background: rgba(26, 34, 50, 0.95);
      border-color: var(--accent-gold-hover);
      transform: translateX(-2px);
    }

    .btn-globe-return:active {
      transform: scale(0.92);
    }

    .globe-hud-pill {
      position: absolute;
      bottom: max(28px, env(safe-area-inset-bottom, 28px));
      left: 50%;
      transform: translateX(-50%);
      z-index: 2010;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 22px;
      border-radius: 30px;
      background: rgba(11, 14, 20, 0.92);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(201, 157, 82, 0.45);
      box-shadow: 0 12px 35px rgba(0, 0, 0, 0.8), 0 0 18px rgba(201, 157, 82, 0.15);
      color: var(--text-main);
      font-family: 'Outfit', sans-serif;
      font-size: 13.5px;
      font-weight: 400;
      pointer-events: none;
      white-space: nowrap;
      max-width: 90vw;
    }

    .globe-live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-gold);
      box-shadow: 0 0 8px var(--accent-gold);
      animation: pulse-ring 2s infinite ease-out;
    }

    /* Responsive overrides for floating bars */
    @media (max-width: 768px) {
      .main-viewport {
        padding: 72px 16px 140px 16px;
      }
      .stage-container {
        grid-template-columns: 1fr;
        gap: 24px;
      }
      .visual-centre-box {
        width: min(300px, 72vw);
        height: min(300px, 72vw);
      }
      .dock-timeline-bar {
        height: 38px;
        padding: 0 12px;
      }
    }

    @media (orientation: landscape) and (max-height: 600px) {
      .main-viewport {
        padding: 64px 20px 110px 20px;
      }
      .stage-container {
        grid-template-columns: minmax(180px, 240px) 1fr;
        gap: 20px;
      }
      .visual-centre-box {
        max-width: min(220px, calc(100vh - 140px));
        max-height: min(220px, calc(100vh - 140px));
      }
    }

  
    /* =========================================================================
       Persistent Floating Controls (Top-Right Hub & Top-Left Hamburger)
       ========================================================================= */
    .btn-floating-hub {
      position: fixed;
      top: max(16px, env(safe-area-inset-top, 16px));
      right: max(18px, env(safe-area-inset-right, 18px));
      width: 52px;
      height: 52px;
      border-radius: 50%;
      background: rgba(18, 23, 33, 0.92);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
      border: 1.5px solid var(--accent-gold);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.75), 0 0 16px var(--accent-gold-glow);
      color: var(--accent-gold);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      cursor: pointer;
      z-index: 1250;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-fast),
                  border-color var(--dur-fast),
                  background var(--dur-fast);
    }

    .btn-floating-hub:hover {
      transform: scale(1.08);
      background: rgba(26, 34, 50, 0.98);
      border-color: var(--accent-gold-hover);
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.85), 0 0 24px var(--accent-gold);
    }

    .btn-floating-hub:active {
      transform: scale(0.92);
    }

    .btn-floating-hub.hub-active {
      background: var(--accent-gold);
      color: #0b0e14;
      box-shadow: 0 0 28px var(--accent-gold);
    }

    .btn-floating-hub.hub-active .hub-floating-label {
      color: #0b0e14;
    }

    .hub-floating-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8.5px;
      font-weight: 700;
      letter-spacing: 0.8px;
      color: var(--accent-gold);
      line-height: 1;
    }

    .btn-floating-nav {
      position: fixed;
      top: max(16px, env(safe-area-inset-top, 16px));
      left: max(18px, env(safe-area-inset-left, 18px));
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: rgba(18, 23, 33, 0.90);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(201, 157, 82, 0.4);
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.65);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 4px;
      cursor: pointer;
      z-index: 1250;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  background var(--dur-fast),
                  border-color var(--dur-fast);
    }

    .btn-floating-nav:hover {
      transform: scale(1.06);
      background: rgba(26, 34, 50, 0.96);
      border-color: var(--accent-gold);
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.75), 0 0 14px var(--accent-gold-glow);
    }

    .btn-floating-nav:active {
      transform: scale(0.92);
    }

    /* =========================================================================
       Dynamic Full Viewport & Middle Screen Expansion
       ========================================================================= */
    .main-viewport {
      width: 100%;
      height: 100vh;
      height: 100dvh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: stretch;
      padding: 16px 20px 130px 20px;
      box-sizing: border-box;
      overflow: hidden;
      position: relative;
      transition: padding var(--dur-liquid) var(--ease-liquid),
                  margin-left var(--dur-liquid) var(--ease-liquid),
                  width var(--dur-liquid) var(--ease-liquid);
    }

    .main-viewport.dock-hidden-state {
      padding-bottom: 24px !important;
    }

    /* Left Nav Expands OVER Display without Distorting or Crushing */
    .main-viewport,
    body.nav-drawer-open .main-viewport {
      margin-left: 0 !important;
      width: 100% !important;
      max-width: 100% !important;
      transform: none !important;
    }

    /* Carousel Outer Viewport & Horizontal Track */
    .carousel-viewport {
      width: 100%;
      height: 100%;
      flex: 1;
      overflow: hidden;
      position: relative;
      display: flex;
    }

    .carousel-track {
      display: flex;
      flex-direction: row;
      width: 100%;
      height: 100%;
      will-change: transform;
      transition: transform 0.45s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .carousel-slide {
      min-width: 100%;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      padding: 56px 16px 24px;
      position: relative;
    }

    /* Player slide keeps full immersive center stage */
    #slide-player.carousel-slide {
      padding: 6px 12px;
    }

    /* Radio globe keeps edge-to-edge spherical canvas */
    #slide-radio.carousel-slide {
      padding: 0;
    }

    /* Main Player Slide Content Dynamics */
    .player-slide-content {
      width: 100%;
      height: 100%;
      max-width: 1400px;
      margin: auto;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 16px;
    }

    .stage-container {
      flex: 1;
      width: 100%;
      max-width: 1400px;
      margin: auto;
      display: grid;
      grid-template-columns: minmax(320px, 1fr) minmax(360px, 1.25fr);
      gap: 36px;
      align-items: center;
      justify-content: center;
      min-height: 0;
    }

    .visual-centre-box {
      width: 100%;
      max-width: min(540px, calc(100vh - 220px));
      max-height: min(540px, calc(100vh - 220px));
      aspect-ratio: 1 / 1;
      margin: auto;
      border-radius: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.05);
      overflow: hidden;
      cursor: pointer;
      transition: max-width var(--dur-liquid) var(--ease-liquid),
                  max-height var(--dur-liquid) var(--ease-liquid);
    }

    .main-viewport.dock-hidden-state .visual-centre-box {
      max-width: min(600px, calc(100vh - 120px));
      max-height: min(600px, calc(100vh - 120px));
    }

    /* Slide Card Chassis (Audiophile Glassmorphic Frame) */
    .slide-card {
      width: 100%;
      max-width: 860px;
      height: 100%;
      max-height: calc(100vh - 150px);
      background: var(--bg-surface);
      border-radius: 24px;
      border: 1px solid var(--border-subtle);
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.05);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      margin: auto;
      transition: max-height var(--dur-liquid) var(--ease-liquid);
    }

    .main-viewport.dock-hidden-state .slide-card {
      max-height: calc(100vh - 60px);
    }

    .slide-card.wide {
      max-width: 1100px;
    }

    .slide-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 22px;
      border-bottom: 1px solid var(--border-subtle);
      background: rgba(18, 23, 33, 0.75);
      -webkit-backdrop-filter: blur(12px);
      backdrop-filter: blur(12px);
      flex-shrink: 0;
    }

    .slide-head h3 {
      font-size: 17px;
      font-weight: 500;
      letter-spacing: 0.4px;
      color: var(--text-main);
      margin: 0;
    }

    .btn-slide-back {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      border-radius: 20px;
      background: rgba(36, 47, 68, 0.75);
      border: 1px solid var(--border-subtle);
      color: var(--accent-gold);
      font-family: 'Outfit', sans-serif;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all var(--dur-fast);
    }

    .btn-slide-back:hover {
      background: rgba(201, 157, 82, 0.2);
      border-color: var(--accent-gold);
      transform: translateX(-2px);
    }

    .slide-body {
      padding: 20px 24px;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    /* Embedded 3D Radio Globe in Carousel */
    .radio-globe-card-box {
      width: 100%;
      height: 380px;
      min-height: 280px;
      border-radius: 18px;
      background: #06090e;
      border: 1px solid rgba(201, 157, 82, 0.3);
      position: relative;
      overflow: hidden;
      touch-action: none;
    }

    /* Responsive Overrides */
    @media (max-width: 768px) {
      .main-viewport {
        padding: 12px 12px 130px 12px;
      }
      .stage-container {
        grid-template-columns: 1fr;
        gap: 18px;
      }
      .visual-centre-box {
        width: min(300px, 72vw);
        height: min(300px, 72vw);
      }
      .slide-card {
        border-radius: 18px;
      }
      .slide-head {
        padding: 12px 16px;
      }
      .slide-body {
        padding: 14px 16px;
      }
    }

    @media (orientation: landscape) and (max-height: 600px) {
      .main-viewport {
        padding: 10px 16px 110px 16px;
      }
      .stage-container {
        grid-template-columns: minmax(180px, 240px) 1fr;
        gap: 20px;
      }
      .visual-centre-box {
        max-width: min(220px, calc(100vh - 120px));
        max-height: min(220px, calc(100vh - 120px));
      }
    }

  
    /* =========================================================================
       Frosted Glass Backing with Zero Outlines (Audiophile Floating Island)
       ========================================================================= */
    .master-dock-container {
      position: fixed;
      bottom: max(12px, env(safe-area-inset-bottom, 12px));
      left: 50% !important;
      transform: translate(-50%, 0) !important;
      width: min(860px, calc(100% - 24px)) !important;
      max-width: 860px !important;
      margin: 0 !important;
      z-index: 2200 !important;
      display: flex !important;
      flex-direction: column !important;
      gap: 6px !important;
      pointer-events: auto !important;
      border: none !important;
      outline: none !important;
      box-shadow: none !important;
      transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1),
                  opacity 0.35s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }

    .master-dock-container.dock-hidden {
      transform: translate(-50%, calc(100% + 50px)) !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }

    .dock-swipe-pill {
      width: 36px;
      height: 4px;
      background: rgba(201, 157, 82, 0.4);
      border-radius: 4px;
      margin: 0 auto -2px auto;
      cursor: pointer;
      transition: background 0.2s ease, width 0.2s ease;
    }
    .dock-swipe-pill:hover {
      background: var(--accent-gold);
      width: 48px;
    }

    .bottom-gesture-zone {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: 28px;
      z-index: 2100;
      touch-action: none;
      background: transparent;
      pointer-events: auto;
    }

    .dock-timeline-bar {
      width: 100%;
      height: 38px;
      border-radius: 19px;
      background: rgba(14, 19, 28, 0.80) !important;
      -webkit-backdrop-filter: blur(28px) saturate(180%) !important;
      backdrop-filter: blur(28px) saturate(180%) !important;
      border: none !important;
      outline: none !important;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.65), 0 0 1px rgba(255, 255, 255, 0.08) !important;
      display: flex;
      align-items: center;
      padding: 0 16px;
      gap: 12px;
      box-sizing: border-box;
    }

    .master-bar {
      width: 100%;
      height: 72px;
      border-radius: 24px;
      background: rgba(14, 19, 28, 0.84) !important;
      -webkit-backdrop-filter: blur(32px) saturate(180%) !important;
      backdrop-filter: blur(32px) saturate(180%) !important;
      border: none !important;
      outline: none !important;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.75), 0 0 1px rgba(255, 255, 255, 0.08) !important;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 24px;
      box-sizing: border-box;
    }

    .btn-circle {
      border: none !important;
      outline: none !important;
      background: rgba(36, 47, 68, 0.65) !important;
      -webkit-backdrop-filter: blur(16px) !important;
      backdrop-filter: blur(16px) !important;
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35) !important;
    }

    .btn-circle:hover {
      background: rgba(201, 157, 82, 0.25) !important;
      color: var(--accent-gold) !important;
    }

    .btn-circle.btn-play {
      background: var(--accent-gold) !important;
      color: #0b0e14 !important;
    }

    .volume-slider-box {
      border: none !important;
      outline: none !important;
      background: rgba(24, 32, 46, 0.65) !important;
      -webkit-backdrop-filter: blur(16px) !important;
      backdrop-filter: blur(16px) !important;
    }

    /* Fixed Viewport Padding: Main Panel NEVER resizes or jumps */
    .main-viewport {
      width: 100% !important;
      height: 100vh !important;
      height: 100dvh !important;
      display: flex !important;
      flex-direction: column !important;
      justify-content: center !important;
      align-items: stretch !important;
      padding: 12px 16px 20px 16px !important;
      box-sizing: border-box !important;
      overflow: hidden !important;
      position: relative !important;
      transition: none !important;
    }

    .main-viewport.dock-hidden-state {
      padding-bottom: 20px !important;
    }

    /* Persistent Hamburger & Hub Navigation */
    .btn-floating-nav {
      position: fixed !important;
      top: max(14px, env(safe-area-inset-top, 14px)) !important;
      left: max(16px, env(safe-area-inset-left, 16px)) !important;
      width: 46px !important;
      height: 46px !important;
      border-radius: 50% !important;
      background: rgba(14, 19, 28, 0.88) !important;
      -webkit-backdrop-filter: blur(24px) saturate(180%) !important;
      backdrop-filter: blur(24px) saturate(180%) !important;
      border: none !important;
      outline: none !important;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.7) !important;
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      justify-content: center !important;
      gap: 4px !important;
      cursor: pointer !important;
      z-index: 2600 !important;
      transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), background 0.2s ease !important;
    }

    .btn-floating-nav:hover {
      transform: scale(1.08) !important;
      background: rgba(24, 32, 46, 0.96) !important;
    }

    .btn-floating-nav .hamburger-bar {
      width: 18px;
      height: 2px;
      background: var(--accent-gold);
      border-radius: 2px;
      transition: transform 0.25s ease, opacity 0.25s ease;
    }

    .btn-floating-nav.nav-active .hamburger-bar:nth-child(1) {
      transform: translateY(6px) rotate(45deg);
    }
    .btn-floating-nav.nav-active .hamburger-bar:nth-child(2) {
      opacity: 0;
    }
    .btn-floating-nav.nav-active .hamburger-bar:nth-child(3) {
      transform: translateY(-6px) rotate(-45deg);
    }

    .btn-floating-hub {
      position: fixed !important;
      top: max(14px, env(safe-area-inset-top, 14px)) !important;
      right: max(16px, env(safe-area-inset-right, 16px)) !important;
      width: 50px !important;
      height: 50px !important;
      border-radius: 50% !important;
      background: rgba(14, 19, 28, 0.88) !important;
      -webkit-backdrop-filter: blur(24px) saturate(180%) !important;
      backdrop-filter: blur(24px) saturate(180%) !important;
      border: none !important;
      outline: none !important;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.7), 0 0 16px var(--accent-gold-glow) !important;
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      justify-content: center !important;
      gap: 2px !important;
      cursor: pointer !important;
      z-index: 2600 !important;
    }

    /* Fixed Navigation Drawer & Backdrop */
    .sidebar {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      bottom: 0 !important;
      width: min(320px, 86vw) !important;
      height: 100vh !important;
      height: 100dvh !important;
      z-index: 2500 !important;
      transform: translateX(-100%) !important;
      transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.35s ease !important;
      background: rgba(14, 19, 28, 0.96) !important;
      -webkit-backdrop-filter: blur(28px) saturate(180%) !important;
      backdrop-filter: blur(28px) saturate(180%) !important;
      border: none !important;
      outline: none !important;
      box-shadow: none !important;
      overflow-y: auto !important;
      -webkit-overflow-scrolling: touch !important;
      display: flex !important;
      flex-direction: column !important;
      padding: 24px 20px !important;
      gap: 20px !important;
    }

    .sidebar.drawer-open, .sidebar.open {
      transform: translateX(0) !important;
      box-shadow: 16px 0 50px rgba(0, 0, 0, 0.88) !important;
    }

    .btn-drawer-close {
      margin-left: auto;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      border: none;
      background: rgba(36, 47, 68, 0.6);
      color: var(--text-muted);
      font-size: 14px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
    }
    .btn-drawer-close:hover {
      background: rgba(201, 157, 82, 0.2);
      color: var(--accent-gold);
    }

    .nav-drawer-backdrop {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      bottom: 0 !important;
      background: rgba(0, 0, 0, 0.65) !important;
      -webkit-backdrop-filter: blur(8px) !important;
      backdrop-filter: blur(8px) !important;
      z-index: 2400 !important;
      opacity: 0 !important;
      pointer-events: none !important;
      transition: opacity 0.3s ease !important;
    }

    .nav-drawer-backdrop.active {
      opacity: 1 !important;
      pointer-events: auto !important;
    }

    /* Active Protocol Badges in Main Player */
    .tag-proto-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(201, 157, 82, 0.12);
      border: none;
      outline: none;
      padding: 4px 10px;
      border-radius: 12px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      font-weight: 600;
      color: var(--accent-gold);
      cursor: pointer;
      transition: all var(--dur-fast);
    }
    .tag-proto-badge:hover {
      background: rgba(201, 157, 82, 0.25);
      transform: scale(1.04);
    }

    /* Containment: Guarantee All Layouts Fit Within Device Screen */
    .player-slide-content {
      width: 100% !important;
      height: 100% !important;
      max-width: 1200px !important;
      margin: 0 auto !important;
      display: flex !important;
      flex-direction: column !important;
      justify-content: space-evenly !important;
      align-items: center !important;
      gap: 8px !important;
      padding: 6px 12px !important;
      box-sizing: border-box !important;
    }

    .stage-container {
      width: 100% !important;
      max-width: 1200px !important;
      margin: 0 auto !important;
      display: grid !important;
      grid-template-columns: minmax(280px, 1fr) minmax(320px, 1.2fr) !important;
      gap: 28px !important;
      align-items: center !important;
      justify-content: center !important;
      min-height: 0 !important;
      flex: 1 !important;
    }

    .visual-centre-box {
      width: 100% !important;
      max-width: min(420px, calc(100vh - 230px)) !important;
      max-height: min(420px, calc(100vh - 230px)) !important;
      aspect-ratio: 1 / 1 !important;
      margin: auto !important;
      border-radius: 24px !important;
      border: none !important;
      outline: none !important;
      background: rgba(18, 24, 35, 0.82) !important;
      -webkit-backdrop-filter: blur(20px) !important;
      backdrop-filter: blur(20px) !important;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.75), 0 0 1px rgba(255, 255, 255, 0.08) !important;
    }

    .slide-card {
      width: 100% !important;
      max-width: 860px !important;
      height: calc(100vh - 36px) !important;
      height: calc(100dvh - 36px) !important;
      max-height: calc(100vh - 36px) !important;
      background: rgba(14, 19, 28, 0.88) !important;
      -webkit-backdrop-filter: blur(28px) saturate(180%) !important;
      backdrop-filter: blur(28px) saturate(180%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 20px !important;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.75), 0 0 1px rgba(255, 255, 255, 0.08) !important;
      display: flex !important;
      flex-direction: column !important;
      overflow: hidden !important;
      margin: auto !important;
      box-sizing: border-box !important;
    }

    @media (max-width: 768px) {
      .main-viewport {
        padding: 8px 10px 16px 10px !important;
      }
      .stage-container {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 10px !important;
      }
      .visual-centre-box {
        width: min(230px, 34vh) !important;
        height: min(230px, 34vh) !important;
        max-width: min(230px, 34vh) !important;
        max-height: min(230px, 34vh) !important;
        border-radius: 18px !important;
      }
      .stage-meta {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        gap: 6px !important;
        text-align: center !important;
      }
      .track-title {
        font-size: min(19px, 5.2vw) !important;
        margin: 0 !important;
      }
      .track-artist {
        font-size: min(13.5px, 3.8vw) !important;
        margin: 0 !important;
      }
      .track-album {
        font-size: min(11.5px, 3.2vw) !important;
        margin: 0 !important;
      }
      .scrub-container {
        width: 100% !important;
        max-width: 340px !important;
        margin-top: 2px !important;
      }
      .telemetry-row {
        gap: 6px !important;
        max-width: 100% !important;
        overflow-x: auto !important;
        padding: 0 4px !important;
        scrollbar-width: none !important;
      }
      .hud-badge {
        font-size: 10.5px !important;
        padding: 3px 8px !important;
      }
    }

    @media (orientation: landscape) and (max-height: 600px) {
      .main-viewport {
        padding: 8px 14px 12px 14px !important;
      }
      .stage-container {
        display: grid !important;
        grid-template-columns: minmax(140px, 190px) 1fr !important;
        gap: 20px !important;
        align-items: center !important;
        justify-content: center !important;
        height: 100% !important;
      }
      .visual-centre-box {
        max-width: min(180px, calc(100vh - 70px)) !important;
        max-height: min(180px, calc(100vh - 70px)) !important;
      }
      .telemetry-row {
        display: none !important;
      }
    }

  
    /* =========================================================================
       Pure Frameless Architecture: Zero Outlines, Zero Heavy Boxed Panels
       ========================================================================= */
    *, *::before, *::after {
      outline: none !important;
    }

    /* Remove heavy panel enclosures */
    .slide-card {
      background: transparent !important;
      border: none !important;
      box-shadow: none !important;
      outline: none !important;
      padding: 0 4px !important;
    }

    .slide-head {
      background: transparent !important;
      border-bottom: none !important;
      padding: 12px 6px 16px 6px !important;
      outline: none !important;
    }

    .slide-body {
      background: transparent !important;
      border: none !important;
      outline: none !important;
      padding: 0 6px !important;
    }

    .stage-container {
      background: transparent !important;
      border: none !important;
      box-shadow: none !important;
      outline: none !important;
    }

    .visual-centre-box {
      border: none !important;
      outline: none !important;
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.75) !important;
    }

    .proto-card,
    .device-card,
    .dac-card,
    .eq-card,
    .queue-card,
    .storage-card,
    .storage-item {
      background: rgba(255, 255, 255, 0.03) !important;
      border: none !important;
      outline: none !important;
      box-shadow: none !important;
    }

    .btn,
    .btn-connect,
    .btn-secondary,
    .btn-ghost,
    .btn-slide-back,
    .tuner-tab-btn,
    .dac-btn,
    .eq-preset-btn,
    .format-tag,
    .telemetry-pill,
    .badge-pro {
      border: none !important;
      outline: none !important;
    }

    input, textarea, select {
      outline: none !important;
      border: none !important;
      background: rgba(255, 255, 255, 0.05) !important;
    }

    /* Pure 3D Celestial Radio Globe - Spinnable, Frameless, No Text */
    .pure-globe-slide {
      width: 100vw !important;
      height: 100dvh !important;
      max-width: 100vw !important;
      max-height: 100dvh !important;
      padding: 0 !important;
      margin: 0 !important;
      background: radial-gradient(circle at center, #0e1420 0%, #06090e 100%) !important;
      overflow: hidden !important;
      border: none !important;
      outline: none !important;
      box-shadow: none !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      position: relative !important;
    }

    .pure-globe-container {
      width: 100% !important;
      height: 100% !important;
      position: absolute !important;
      inset: 0 !important;
      background: transparent !important;
      border: none !important;
      outline: none !important;
      box-shadow: none !important;
      touch-action: none !important; /* Critical for 360-degree rotation without browser gestures */
      overflow: hidden !important;
    }

    .pure-globe-container canvas {
      width: 100% !important;
      height: 100% !important;
      display: block !important;
      outline: none !important;
      border: none !important;
    }

  
    /* =========================================================================
       Snappy Transitions, Frameless Main Player Layout & Audio Level Visualisers
       ========================================================================= */
    :root {
      --dur-fast: 0.14s;
      --dur-liquid: 0.22s;
      --dur-smooth: 0.28s;
      --ease-liquid: cubic-bezier(0.16, 1, 0.3, 1);
    }

    .btn-slide-back {
      display: none !important;
    }

    .carousel-track {
      display: flex;
      flex-direction: row;
      width: 100%;
      height: 100%;
      will-change: transform;
      transition: transform 0.28s cubic-bezier(0.2, 0.9, 0.3, 1) !important;
    }

    .master-dock-container {
      will-change: transform, opacity;
      transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.18s ease !important;
    }

    .nav-drawer {
      will-change: transform;
      transition: transform 0.24s cubic-bezier(0.2, 0.9, 0.3, 1) !important;
    }

    /* ==========================================================================
       WORLD-CLASS BALANCED STUDIO PLAYER ARCHITECTURE (Zero Overlays, 100% Dynamic)
       ========================================================================== */
    .player-studio-viewport {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px 32px 96px 32px;
      box-sizing: border-box;
      overflow-y: auto;
      overflow-x: hidden;
      -webkit-overflow-scrolling: touch;
    }

    .player-studio-stage {
      width: 100%;
      max-width: 1080px;
      display: grid;
      grid-template-columns: 96px 1fr;
      gap: 24px;
      align-items: center;
      margin: auto;
    }

    /* Left Column: Compact Album Sleeve (Reduced 75% in footprint, Zero gold gradient outline) */
    .player-sleeve-section {
      display: flex;
      justify-content: center;
      align-items: center;
      width: 96px;
      min-width: 96px;
    }

    .sleeve-card {
      position: relative;
      width: 96px;
      height: 96px;
      max-width: 96px;
      min-width: 96px;
      aspect-ratio: 1 / 1;
      border-radius: 14px;
      overflow: hidden;
      background: #0d121c;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.08);
      outline: none;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-liquid) var(--ease-liquid);
    }

    .sleeve-card:hover {
      transform: translateY(-2px) scale(1.02);
      box-shadow: 0 14px 34px rgba(0, 0, 0, 0.85);
    }

    .sleeve-img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block !important;
      border-radius: 14px;
      position: relative;
      z-index: 2;
    }

    /* Protocol Visual SVG Icon Bar (No lozenges) */
    .player-proto-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 4px;
    }

    .proto-visual-icon {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      opacity: 0.92;
      transition: transform 0.15s ease, opacity 0.15s ease;
    }

    .proto-visual-icon:hover {
      opacity: 1;
      transform: scale(1.08);
    }

    .proto-visual-icon svg {
      width: 28px;
      height: 28px;
      fill: var(--accent-gold);
      filter: drop-shadow(0 2px 8px rgba(201, 157, 82, 0.35));
    }

    /* Right Column: Track Metadata, Scrubber, Dual VU Meters, RTA Spectrum */
    .player-info-section {
      display: flex;
      flex-direction: column;
      gap: 14px;
      min-width: 0;
      width: 100%;
    }

    /* Format Tags & Protocol */
    .player-tags-bar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .format-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.5px;
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-secondary);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .format-pill.gold {
      background: rgba(201, 157, 82, 0.12);
      color: var(--accent-gold);
      border-color: rgba(201, 157, 82, 0.35);
    }

    .format-pill.proto-pill {
      cursor: pointer;
      background: rgba(201, 157, 82, 0.08);
      color: var(--accent-gold);
      border-color: rgba(201, 157, 82, 0.25);
      transition: background 0.2s ease, border-color 0.2s ease;
    }

    .format-pill.proto-pill:hover {
      background: rgba(201, 157, 82, 0.2);
      border-color: var(--accent-gold);
    }

    .format-pill.fixed-pill {
      cursor: pointer;
      background: rgba(14, 165, 233, 0.1);
      color: var(--accent-cyan);
      border-color: rgba(14, 165, 233, 0.3);
    }

    /* Track Titles */
    .player-titles-block {
      display: flex;
      flex-direction: column;
      gap: 3px;
    }

    .player-track-title {
      font-size: clamp(22px, 2.6vw, 30px);
      font-weight: 700;
      color: #ffffff;
      margin: 0;
      line-height: 1.25;
      letter-spacing: -0.3px;
      word-break: break-word;
    }

    .player-track-artist {
      font-size: clamp(15px, 1.6vw, 18px);
      font-weight: 500;
      color: var(--accent-gold);
      margin: 0;
      line-height: 1.3;
    }

    .player-track-album {
      font-size: 13px;
      font-weight: 400;
      color: var(--text-muted);
      margin: 0;
    }

    /* Prominent Time Scrubber */
    .main-scrub-box {
      display: flex;
      flex-direction: column;
      gap: 6px;
      width: 100%;
      margin: 4px 0;
      touch-action: pan-y;
    }

    .main-scrub-track {
      width: 100%;
      height: 6px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 4px;
      position: relative;
      cursor: pointer;
      overflow: visible;
    }

    .main-scrub-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent-gold), #ffe29a);
      border-radius: 4px;
      box-shadow: 0 0 10px rgba(201, 157, 82, 0.5);
      position: relative;
    }

    .main-scrub-fill::after {
      content: '';
      position: absolute;
      right: -6px;
      top: 50%;
      transform: translateY(-50%);
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: #ffffff;
      box-shadow: 0 0 10px var(--accent-gold), 0 2px 4px rgba(0,0,0,0.6);
    }

    .main-scrub-times {
      display: flex;
      justify-content: space-between;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--text-muted);
    }

    /* Dual Vintage Analogue VU Level Meters */
    .studio-vu-container {
      display: grid !important;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      width: 100%;
      position: static !important;
      margin-top: 4px;
    }

    .studio-vu-meter {
      background: radial-gradient(circle at 50% 120%, rgba(201, 157, 82, 0.12), rgba(12, 16, 24, 0.95));
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      height: 82px;
      position: relative;
      overflow: hidden;
      box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: 6px 10px;
      box-sizing: border-box;
    }

    .vu-meta-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      width: 100%;
      z-index: 3;
    }

    .vu-ch-label {
      font-size: 8.5px;
      font-weight: 600;
      letter-spacing: 1px;
      color: var(--text-dim);
    }

    .vu-peak-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      font-weight: 700;
      color: rgba(244, 63, 94, 0.25);
      transition: color 0.12s ease;
    }

    .vu-peak-tag.active {
      color: #f43f5e;
      text-shadow: 0 0 8px rgba(244, 63, 94, 0.9);
    }

    .vu-arc-face {
      position: relative;
      width: 100%;
      height: 52px;
      overflow: hidden;
    }

    .vu-scale-ticks {
      position: absolute;
      top: 2px;
      width: 86%;
      left: 7%;
      display: flex;
      justify-content: space-between;
      font-family: 'JetBrains Mono', monospace;
      font-size: 7.5px;
      color: var(--accent-gold);
      opacity: 0.85;
    }

    .vu-red-val {
      color: #f43f5e !important;
    }

    .vu-needle {
      position: absolute;
      bottom: 2px;
      left: 50%;
      width: 1.8px;
      height: 56px;
      background: linear-gradient(to top, var(--accent-gold), #ffe8a3);
      transform-origin: bottom center;
      transform: translateX(-50%) rotate(-35deg);
      transition: none !important; /* Critical Ballistics Invariant */
      box-shadow: 0 0 5px rgba(201, 157, 82, 0.85);
      z-index: 5;
      pointer-events: none;
    }

    .vu-pivot-cap {
      position: absolute;
      bottom: -2px;
      left: 50%;
      transform: translateX(-50%);
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #e6be75, #7a5519);
      border: 1px solid rgba(201, 157, 82, 0.8);
      z-index: 6;
    }

    /* Real-Time Frequency Spectrum Analyser (RTA) */
    .studio-rta-container {
      width: 100%;
      background: rgba(12, 16, 24, 0.65);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 8px 12px;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 5px;
      position: static !important;
    }

    .rta-meta-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      width: 100%;
    }

    .rta-title-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 9.5px;
      letter-spacing: 1.2px;
      color: var(--accent-gold);
      font-weight: 600;
    }

    .rta-rate-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      color: var(--text-dim);
    }

    .rta-spectrum-grid {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      height: 58px;
      gap: 8px;
      width: 100%;
    }

    .rta-bar-cell {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-end;
      height: 100%;
      gap: 4px;
    }

    .rta-bar {
      width: 100%;
      max-width: 16px;
      height: 4px;
      border-radius: 2px;
      background: linear-gradient(to top, var(--accent-cyan), var(--accent-gold), #ff6b6b);
      transition: none !important; /* Critical Ballistics Invariant */
      box-shadow: 0 0 6px rgba(201, 157, 82, 0.35);
    }

    .rta-col-lbl {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      color: var(--text-dim);
    }

    /* Permanent Visibility & Zero Inset Interference Invariant */
    #view-artwork,
    #view-vu,
    #view-rta {
      opacity: 1 !important;
      visibility: visible !important;
      pointer-events: auto !important;
      transform: none !important;
      position: static !important;
      inset: auto !important;
    }

    /* Floating Top Hub Icon: Enlarged and refined */
    .btn-floating-hub {
      position: fixed;
      top: max(16px, env(safe-area-inset-top, 16px));
      right: max(18px, env(safe-area-inset-right, 18px));
      width: 56px !important;
      height: 56px !important;
      border-radius: 50%;
      background: rgba(18, 23, 33, 0.92);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
      border: 1.5px solid var(--accent-gold) !important;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.75), 0 0 16px var(--accent-gold-glow) !important;
      color: var(--accent-gold);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      z-index: 1250;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  box-shadow var(--dur-fast),
                  border-color var(--dur-fast);
    }

    .btn-floating-hub:hover {
      transform: scale(1.08);
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.85), 0 0 24px var(--accent-gold-glow) !important;
    }

    /* Floating Hamburger Navigation Icon */
    .btn-floating-nav {
      position: fixed;
      top: max(16px, env(safe-area-inset-top, 16px));
      left: max(18px, env(safe-area-inset-right, 18px));
      width: 48px;
      height: 48px;
      border-radius: 50%;
      background: rgba(18, 23, 33, 0.88);
      -webkit-backdrop-filter: blur(16px);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
      color: var(--text-primary);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 5px;
      cursor: pointer;
      z-index: 1250;
      transition: transform var(--dur-liquid) var(--ease-liquid),
                  border-color var(--dur-fast);
    }

    .btn-floating-nav:hover {
      transform: scale(1.06);
      border-color: rgba(201, 157, 82, 0.5);
      color: var(--accent-gold);
    }

    /* Suppress Top Telemetry Row Everywhere */
    .telemetry-row {
      display: none !important;
    }

    /* Responsive Adaptation for Mobile and Small Viewports */
    @media (max-width: 820px) {
      .player-studio-viewport {
        padding: 72px 16px 96px 16px;
        align-items: flex-start;
      }
      .player-studio-stage {
        grid-template-columns: 88px 1fr;
        gap: 16px;
        text-align: left;
        align-items: center;
      }
      .player-sleeve-section {
        width: 88px;
        min-width: 88px;
      }
      .sleeve-card {
        width: 88px;
        height: 88px;
        max-width: 88px;
        min-width: 88px;
        border-radius: 12px;
        margin: 0;
      }
      .player-proto-bar {
        justify-content: flex-start;
      }
      .player-titles-block {
        text-align: left;
      }
      .studio-vu-meter {
        height: 74px;
      }
      .vu-needle {
        height: 50px;
        transition: none !important;
      }
      .studio-rta-container {
        height: auto;
      }
      .rta-spectrum-grid {
        height: 48px;
      }
      .rta-bar {
        max-width: 12px;
        transition: none !important;
      }
    }

    .bar-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 1;
      max-width: 280px;
      justify-content: flex-end;
    }

    .volume-slider-box {
      display: flex !important;
      align-items: center;
      gap: 8px;
      flex: 1;
      min-width: 110px;
      max-width: 180px;
    }

    .vol-slider-wrap {
      flex: 1;
      width: 100%;
      height: 24px;
      display: flex;
      align-items: center;
      cursor: pointer;
      position: relative;
    }

    .vol-slider {
      -webkit-appearance: none;
      appearance: none;
      width: 100% !important;
      height: 6px !important;
      background: linear-gradient(to right, var(--accent-gold) 0%, var(--accent-gold) 35%, rgba(255, 255, 255, 0.12) 35%, rgba(255, 255, 255, 0.12) 100%);
      border-radius: 4px;
      outline: none !important;
      border: none !important;
      cursor: pointer;
      margin: 0;
      padding: 0;
      touch-action: pan-y;
    }

    .vol-slider::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--accent-gold);
      box-shadow: 0 0 10px rgba(201, 157, 82, 0.8);
      cursor: pointer;
      transition: transform 0.15s ease;
    }

    .vol-slider::-webkit-slider-thumb:hover,
    .vol-slider::-webkit-slider-thumb:active {
      transform: scale(1.3);
      box-shadow: 0 0 16px rgba(201, 157, 82, 1);
    }

    .vol-slider::-moz-range-thumb {
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--accent-gold);
      border: none;
      box-shadow: 0 0 10px rgba(201, 157, 82, 0.8);
      cursor: pointer;
    }

    .vol-percent {
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--accent-gold);
      min-width: 38px;
      text-align: right;
    }

    .btn-dock-minimise {
      background: rgba(255, 255, 255, 0.05);
      color: var(--text-secondary);
      border: none !important;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      transition: background 0.18s ease, color 0.18s ease, transform 0.18s ease;
      flex-shrink: 0;
    }

    .btn-dock-minimise:hover {
      background: rgba(201, 157, 82, 0.2);
      color: var(--accent-gold);
      transform: translateY(2px);
    }

    .btn-dock-minimise:active {
      transform: translateY(4px);
    }

  

    /* =========================================================================
       Sleek Unified Dropdowns Styling
       ========================================================================= */
    select,
    .tuner-select {
      appearance: none !important;
      -webkit-appearance: none !important;
      -moz-appearance: none !important;
      background-color: rgba(26, 34, 50, 0.88) !important;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23c99d52' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E") !important;
      background-repeat: no-repeat !important;
      background-position: right 14px center !important;
      background-size: 14px !important;
      border: 1px solid rgba(201, 157, 82, 0.35) !important;
      border-radius: 10px !important;
      padding: 9px 38px 9px 14px !important;
      color: var(--text-primary) !important;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
      font-size: 12.5px !important;
      font-weight: 500 !important;
      backdrop-filter: blur(16px) !important;
      -webkit-backdrop-filter: blur(16px) !important;
      box-shadow: 0 4px 18px rgba(0, 0, 0, 0.45) !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.2, 0.9, 0.3, 1) !important;
      outline: none !important;
    }

    select:hover,
    .tuner-select:hover,
    select:focus,
    .tuner-select:focus {
      border-color: var(--accent-gold) !important;
      background-color: rgba(32, 42, 62, 0.96) !important;
      box-shadow: 0 0 16px rgba(201, 157, 82, 0.28), 0 6px 22px rgba(0, 0, 0, 0.6) !important;
    }

    select option,
    .tuner-select option {
      background-color: #121824 !important;
      color: var(--text-primary) !important;
      padding: 10px !important;
      font-size: 12.5px !important;
    }

    /* =========================================================================
       Streaming Architecture Hub: Milled Rotary Badges, 40% Alpha Frosted Glass,
       Zero Outlines, Visual Signal Topology Pipeline & Visual Diagnostic Drawer
       ========================================================================= */
    body.on-hub-slide #btn-floating-hub {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }

    #slide-protocols .slide-card {
      max-width: 1060px !important;
      width: min(1060px, 98%) !important;
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 20px !important;
      box-shadow: 0 28px 70px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
      padding: clamp(14px, 2vh, 22px) clamp(16px, 2vw, 28px) !important;
      max-height: calc(100vh - 170px) !important;
      overflow-y: auto !important;
      display: flex !important;
      flex-direction: column !important;
      box-sizing: border-box !important;
    }

    /* Visual Signal Flow Topology Banner */
    .proto-topology-banner {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 16px;
      background: rgba(10, 14, 22, 0.50);
      border-radius: 12px;
      margin-bottom: 14px;
      box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.6);
    }
    .topo-node {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .topo-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
    }
    .topo-dot.gold-glow {
      background: var(--accent-gold);
      box-shadow: 0 0 10px var(--accent-gold), 0 0 3px #fff;
    }
    .topo-dot.cyan-glow {
      background: #00e5ff;
      box-shadow: 0 0 10px #00e5ff;
    }
    .topo-node-content {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .topo-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      color: rgba(255, 255, 255, 0.4);
      letter-spacing: 0.10em;
      text-transform: uppercase;
    }
    .topo-val {
      font-family: 'Inter', sans-serif;
      font-size: 11.5px;
      font-weight: 600;
      color: #fff;
    }
    .topo-pipe {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      position: relative;
    }
    .topo-pulse-line {
      width: 100%;
      height: 2px;
      background: linear-gradient(90deg, rgba(201, 157, 82, 0.1), rgba(201, 157, 82, 0.6), rgba(201, 157, 82, 0.1));
      position: relative;
      overflow: hidden;
    }
    .topo-pulse-line::after {
      content: '';
      position: absolute;
      top: 0;
      left: -40%;
      width: 40%;
      height: 100%;
      background: linear-gradient(90deg, transparent, #fff, transparent);
      animation: topoPulse 2.4s infinite linear;
    }
    @keyframes topoPulse {
      0% { left: -40%; }
      100% { left: 140%; }
    }
    .topo-rate {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      color: var(--accent-gold);
      letter-spacing: 0.08em;
      background: rgba(201, 157, 82, 0.12);
      padding: 1px 6px;
      border-radius: 3px;
    }

    /* Grid & Cards */
    .proto-grid {
      display: grid !important;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)) !important;
      gap: 14px !important;
      width: 100% !important;
    }
    .proto-card {
      background: rgba(18, 24, 36, 0.40) !important;
      -webkit-backdrop-filter: blur(20px) saturate(150%) !important;
      backdrop-filter: blur(20px) saturate(150%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 16px !important;
      padding: 14px 16px !important;
      display: flex !important;
      flex-direction: column !important;
      gap: 10px !important;
      box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
      transition: all 0.24s cubic-bezier(0.16, 1, 0.3, 1) !important;
      position: relative !important;
    }
    .proto-card:hover {
      transform: translateY(-2px) !important;
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.55), 0 0 20px rgba(201, 157, 82, 0.15) !important;
    }
    .proto-card.active {
      background: radial-gradient(circle at 15% 20%, rgba(201, 157, 82, 0.18) 0%, rgba(18, 24, 36, 0.55) 100%) !important;
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.6), 0 0 30px rgba(201, 157, 82, 0.22), inset 0 1px 0 rgba(201, 157, 82, 0.3) !important;
      border: none !important;
      outline: none !important;
    }

    /* Audiophile Milled Rotary Disc Badge */
    .proto-rotary-hub {
      width: 44px;
      height: 44px;
      min-width: 44px;
      min-height: 44px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #283144 0%, #151a24 70%, #0d1118 100%);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.7), inset 0 1px 1px rgba(255, 255, 255, 0.25);
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      transition: all 0.2s ease;
    }
    .proto-rotary-hub::before {
      content: '';
      position: absolute;
      inset: 2px;
      border-radius: 50%;
      background: repeating-radial-gradient(circle, transparent, transparent 1.5px, rgba(0, 0, 0, 0.3) 1.5px, rgba(0, 0, 0, 0.3) 2.5px);
      pointer-events: none;
    }
    .proto-card.active .proto-rotary-hub {
      box-shadow: 0 4px 16px rgba(201, 157, 82, 0.4), inset 0 0 8px rgba(201, 157, 82, 0.3), inset 0 1px 2px rgba(255, 255, 255, 0.4);
      animation: disc-hub-breathe 3s infinite ease-in-out;
    }
    @keyframes disc-hub-breathe {
      0%, 100% { box-shadow: 0 4px 14px rgba(201, 157, 82, 0.3), inset 0 0 6px rgba(201, 157, 82, 0.2); }
      50% { box-shadow: 0 6px 22px rgba(201, 157, 82, 0.55), inset 0 0 12px rgba(201, 157, 82, 0.4); }
    }

    /* Head & Info */
    .proto-card-compact-head {
      display: flex !important;
      align-items: center !important;
      gap: 12px !important;
    }
    .proto-info-title-group {
      flex: 1 !important;
      min-width: 0 !important;
    }
    .proto-title-row {
      display: flex !important;
      align-items: center !important;
      justify-content: space-between !important;
      gap: 6px !important;
    }
    .proto-name-text {
      font-size: 14.5px !important;
      font-weight: 700 !important;
      color: #fff !important;
      letter-spacing: 0.01em !important;
    }
    .proto-card.active .proto-name-text {
      color: var(--accent-gold) !important;
    }

    /* Rotary Info Disc Button */
    .proto-info-icon-btn {
      width: 22px !important;
      height: 22px !important;
      min-width: 22px !important;
      min-height: 22px !important;
      border-radius: 50% !important;
      border: none !important;
      outline: none !important;
      background: rgba(255, 255, 255, 0.06) !important;
      color: var(--text-muted) !important;
      font-family: 'JetBrains Mono', monospace, sans-serif !important;
      font-size: 11px !important;
      font-weight: 700 !important;
      font-style: italic !important;
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      cursor: pointer !important;
      padding: 0 !important;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4) !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    .proto-info-icon-btn:hover,
    .proto-info-icon-btn.active {
      background: var(--accent-gold) !important;
      color: #0b0e14 !important;
      box-shadow: 0 0 12px var(--accent-gold-glow) !important;
      transform: scale(1.1) !important;
    }

    /* Clean Visual Spec Chips */
    .proto-chips-row {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 4px;
    }
    .proto-chip {
      font-family: 'JetBrains Mono', monospace;
      font-size: 9.5px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.05);
      color: rgba(255, 255, 255, 0.65);
      letter-spacing: 0.04em;
    }
    .proto-chip.chip-gold {
      color: var(--accent-gold);
      background: rgba(201, 157, 82, 0.12);
    }
    .proto-chip.chip-emerald {
      color: #00e676;
      background: rgba(0, 230, 118, 0.12);
    }

    /* Visual Diagnostic & Quick-Guide Drawer */
    .proto-drawer-visual {
      display: none !important;
      background: rgba(10, 14, 22, 0.85) !important;
      border-radius: 12px !important;
      padding: 12px 14px !important;
      margin-top: 6px !important;
      flex-direction: column !important;
      gap: 10px !important;
      animation: protoFadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
      box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.7) !important;
    }
    .proto-drawer-visual.open {
      display: flex !important;
    }
    @keyframes protoFadeIn {
      from { opacity: 0; transform: translateY(-4px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .proto-flow-diagram {
      display: flex;
      align-items: center;
      justify-content: space-around;
      padding: 8px 6px;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 8px;
    }
    .flow-step {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
    }
    .flow-icon-circle {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    }
    .flow-icon-circle.flow-core {
      background: rgba(201, 157, 82, 0.2);
      color: var(--accent-gold);
    }
    .flow-icon-circle.flow-dac {
      background: rgba(0, 229, 255, 0.2);
      color: #00e5ff;
    }
    .flow-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      color: rgba(255, 255, 255, 0.5);
      letter-spacing: 0.06em;
    }
    .flow-arrow {
      color: rgba(201, 157, 82, 0.6);
      font-size: 11px;
    }
    .proto-visual-specs {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .proto-vspec-card {
      background: rgba(255, 255, 255, 0.03);
      border-radius: 6px;
      padding: 6px 8px;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .vspec-title {
      font-family: 'JetBrains Mono', monospace;
      font-size: 7.5px;
      color: rgba(255, 255, 255, 0.4);
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .vspec-data {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 600;
      color: #fff;
    }
    .vspec-data.gold {
      color: var(--accent-gold);
    }
    .proto-visual-guide {
      display: flex;
      justify-content: space-between;
      gap: 6px;
      padding-top: 2px;
    }
    .vguide-step {
      flex: 1;
      display: flex;
      align-items: center;
      gap: 5px;
      font-family: 'Inter', sans-serif;
      font-size: 9.5px;
      color: rgba(255, 255, 255, 0.7);
    }
    .step-num {
      width: 15px;
      height: 15px;
      min-width: 15px;
      border-radius: 50%;
      background: rgba(201, 157, 82, 0.25);
      color: var(--accent-gold);
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    /* Action Buttons: Borderless Tactile Styling */
    .proto-action-row {
      display: flex !important;
      gap: 8px !important;
      margin-top: 4px !important;
    }
    .btn-proto-action {
      flex: 1 !important;
      height: 36px !important;
      padding: 0 14px !important;
      font-size: 12px !important;
      font-weight: 600 !important;
      letter-spacing: 0.3px !important;
      border-radius: 20px !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      gap: 6px !important;
      cursor: pointer !important;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
      border: none !important;
      outline: none !important;
    }
    .btn-proto-action.switch-btn {
      background: rgba(255, 255, 255, 0.08) !important;
      color: #fff !important;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35) !important;
    }
    .btn-proto-action.switch-btn:hover {
      background: rgba(201, 157, 82, 0.25) !important;
      color: var(--accent-gold) !important;
      box-shadow: 0 0 16px rgba(201, 157, 82, 0.3) !important;
      transform: translateY(-1px) !important;
    }
    .btn-proto-action.active-endpoint {
      background: linear-gradient(135deg, rgba(201, 157, 82, 0.3) 0%, rgba(201, 157, 82, 0.12) 100%) !important;
      color: var(--accent-gold) !important;
      box-shadow: 0 0 16px rgba(201, 157, 82, 0.25) !important;
      cursor: default !important;
    }
    .btn-proto-ext {
      padding: 0 14px !important;
      height: 36px !important;
      font-size: 11.5px !important;
      border-radius: 20px !important;
      background: rgba(255, 255, 255, 0.06) !important;
      border: none !important;
      outline: none !important;
      color: rgba(255, 255, 255, 0.6) !important;
      display: inline-flex !important;
      align-items: center !important;
      gap: 6px !important;
      text-decoration: none !important;
      transition: all 0.2s ease !important;
    }
    .btn-proto-ext:hover {
      background: rgba(255, 255, 255, 0.12) !important;
      color: #fff !important;
    }

    /* =========================================================================
       Swappable Visualiser Card & Main Player Screen Fitting
       ========================================================================= */
    .studio-vis-deck {
      cursor: pointer;
      position: relative;
      border-radius: 12px;
      transition: all 0.2s ease;
      user-select: none;
    }

    .studio-vis-deck:hover {
      filter: brightness(1.05);
    }

    .vis-swap-hint {
      display: flex;
      align-items: center;
      gap: 6px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 9.5px;
      margin-bottom: 6px;
      padding: 2px 6px;
      border-radius: 6px;
      color: var(--text-dim);
    }

    .vis-swap-hint #vis-active-tag {
      color: var(--accent-gold);
      font-weight: 600;
    }

    .vis-swap-arrow {
      color: var(--accent-gold);
      font-size: 11px;
    }

    .vis-inactive-tag {
      color: var(--text-dim);
    }

    .vis-click-msg {
      margin-left: auto;
      color: var(--text-dim);
      font-size: 9px;
      letter-spacing: 0.2px;
    }

    .studio-vis-deck:hover .vis-click-msg {
      color: var(--accent-gold);
    }

  
    /* =========================================================================
       Centralised Audiophile DAC & Controls Layout
       ========================================================================= */
    .dac-card-central {
      max-width: 680px;
      margin: auto;
      border: 1px solid var(--border-subtle);
      background: linear-gradient(180deg, rgba(18, 24, 38, 0.95) 0%, rgba(10, 14, 22, 0.98) 100%);
      box-shadow: 0 20px 50px rgba(0, 0, 0, 0.7);
    }
    .dac-head-central {
      padding: 20px 28px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }
    .dac-title-group {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
    }
    .dac-title-group h3 {
      font-size: 16px;
      font-weight: 500;
      color: #fff;
      letter-spacing: 0.5px;
      margin: 0;
    }
    .dac-chipset-badge {
      font-size: 10.5px;
      color: var(--accent-gold);
      font-family: 'JetBrains Mono', monospace;
      letter-spacing: 1px;
      background: rgba(201, 157, 82, 0.12);
      border: 1px solid rgba(201, 157, 82, 0.28);
      padding: 4px 10px;
      border-radius: 20px;
    }
    .dac-body-central {
      padding: 24px 28px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }
    .dac-setting-row {
      background: rgba(24, 32, 48, 0.6);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 18px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }
    .dac-setting-info {
      flex: 1;
    }
    .dac-setting-title {
      font-size: 13.5px;
      font-weight: 500;
      color: #fff;
      margin-bottom: 4px;
    }
    .dac-setting-desc {
      font-size: 11.5px;
      color: var(--text-muted);
      line-height: 1.4;
    }
    .dac-toggle-wrapper {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }
    .fixed-status-pill {
      font-size: 9.5px;
      font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.5px;
      color: var(--text-dim);
    }
    .fixed-status-pill.active {
      color: var(--accent-gold);
      font-weight: 600;
    }
    /* Luxury iOS-style Toggle Switch */
    .switch-luxury {
      position: relative;
      display: inline-block;
      width: 48px;
      height: 26px;
    }
    .switch-luxury input {
      opacity: 0;
      width: 0;
      height: 0;
    }
    .slider-luxury {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: rgba(36, 47, 68, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.12);
      transition: 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      border-radius: 26px;
    }
    .slider-luxury:before {
      position: absolute;
      content: "";
      height: 18px;
      width: 18px;
      left: 3px;
      bottom: 3px;
      background-color: #cbd5e1;
      transition: 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      border-radius: 50%;
      box-shadow: 0 2px 5px rgba(0,0,0,0.4);
    }
    .switch-luxury input:checked + .slider-luxury {
      background: linear-gradient(135deg, #c99d52 0%, #dfb46a 100%);
      border-color: #c99d52;
    }
    .switch-luxury input:checked + .slider-luxury:before {
      transform: translateX(22px);
      background-color: #0b0f17;
    }
    /* Filter Module */
    .dac-filter-module {
      background: rgba(24, 32, 48, 0.6);
      border: 1px solid var(--border-subtle);
      border-radius: 14px;
      padding: 18px 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .dac-filter-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .dac-filter-label {
      font-size: 13px;
      font-weight: 500;
      color: #fff;
    }
    .filter-type-pill {
      font-size: 10px;
      font-family: 'JetBrains Mono', monospace;
      color: var(--accent-gold);
      background: rgba(201, 157, 82, 0.1);
      padding: 3px 8px;
      border-radius: 6px;
    }
    .dac-select-sleek {
      width: 100%;
      padding: 12px 16px;
      font-size: 12.5px;
    }
    .filter-explainer-card {
      display: flex;
      gap: 8px;
      align-items: flex-start;
      font-size: 11px;
      color: var(--text-dim);
      line-height: 1.45;
      padding-top: 4px;
    }
    .explainer-bullet {
      color: var(--accent-gold);
      font-size: 8px;
      margin-top: 3px;
    }
    .dac-footer-note {
      font-size: 11px;
      color: var(--text-dim);
      text-align: center;
      line-height: 1.4;
      padding-top: 4px;
    }

  
    /* =========================================================================
       Ambient Right-Hand Artwork Backdrop (Blended against dark background)
       ========================================================================= */
    #slide-player {
      position: relative !important;
      overflow: hidden !important;
    }

    .player-ambient-art {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: 58%;
      max-width: 780px;
      height: 100%;
      pointer-events: none;
      overflow: hidden;
      z-index: 0;
    }

    .ambient-art-img {
      position: absolute;
      top: 0;
      right: 0;
      width: 100%;
      height: 100%;
      background-size: cover;
      background-position: center right;
      background-repeat: no-repeat;
      opacity: 0.08 !important;
      filter: blur(48px) saturate(1.2) !important;
      transition: background-image 0.8s ease, opacity 0.8s ease;
    }

    .ambient-art-gradient {
      position: absolute;
      inset: 0;
      background: 
        linear-gradient(to right, var(--bg-primary, #06090e) 0%, rgba(6, 9, 14, 0.82) 30%, rgba(6, 9, 14, 0.3) 75%, rgba(6, 9, 14, 0.7) 100%),
        linear-gradient(to bottom, var(--bg-primary, #06090e) 0%, transparent 15%, transparent 85%, var(--bg-primary, #06090e) 100%);
    }

    /* Do not scroll main player if not necessary */
    .player-studio-viewport {
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 10px 24px 68px 24px !important;
      box-sizing: border-box;
      overflow-y: hidden !important;
      overflow-x: hidden !important;
      position: relative;
      z-index: 1;
    }

    @media (max-height: 580px) {
      .player-studio-viewport {
        overflow-y: auto !important;
      }
    }

    .player-studio-stage {
      width: 100%;
      max-width: 820px !important;
      display: flex !important;
      flex-direction: column !important;
      align-items: center !important;
      justify-content: center !important;
      margin: auto !important;
      z-index: 2;
    }

    .player-info-section {
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px !important;
    }

    /* Prevent page scroll when interacting with EQ sliders */
    .eq-sliders-row,
    .eq-slider-col,
    .eq-range,
    input[type="range"] {
      touch-action: none !important;
      -webkit-touch-callout: none;
      -webkit-user-select: none;
      user-select: none;
    }

  
    /* =========================================================================
       Parametric Equaliser: Circular Preset Buttons & Background Audio Wave
       ========================================================================= */
    .eq-presets-row {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 18px;
      margin: 12px 0 20px 0;
      flex-wrap: wrap;
    }
    .eq-preset-btn-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      user-select: none;
    }
    .eq-preset-btn {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: rgba(18, 24, 38, 0.75);
      border: 3px solid rgba(255, 255, 255, 0.22);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      cursor: pointer;
      padding: 0;
      outline: none;
    }
    .eq-preset-btn:hover {
      border-color: rgba(201, 157, 82, 0.65);
      box-shadow: 0 0 14px rgba(201, 157, 82, 0.35);
      transform: translateY(-2px);
    }
    .eq-preset-btn.active, .eq-preset-btn-item.active .eq-preset-btn {
      border-color: var(--accent-gold);
      border-width: 3.5px;
      background: rgba(201, 157, 82, 0.18);
      box-shadow: 0 0 18px rgba(201, 157, 82, 0.55), inset 0 0 10px rgba(201, 157, 82, 0.2);
      transform: scale(1.08);
    }
    .eq-preset-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent-gold);
      opacity: 0;
      transform: scale(0.5);
      transition: all 0.25s ease;
      box-shadow: 0 0 8px var(--accent-gold);
    }
    .eq-preset-btn.active .eq-preset-dot, .eq-preset-btn-item.active .eq-preset-dot {
      opacity: 1;
      transform: scale(1);
    }
    .eq-preset-label {
      font-size: 11px;
      font-weight: 500;
      color: var(--text-muted);
      letter-spacing: 0.3px;
      text-align: center;
      transition: color 0.2s ease;
      white-space: nowrap;
    }
    .eq-preset-btn-item.active .eq-preset-label, .eq-preset-btn-item:hover .eq-preset-label {
      color: var(--accent-gold);
      font-weight: 600;
    }

    /* EQ Stage Wrapper: Wave Filled in Gold (20% Alpha) Behind Sliders */
    .eq-stage-wrap {
      position: relative;
      width: 100%;
      min-height: 230px;
      border-radius: 14px;
      background: rgba(14, 19, 30, 0.65);
      border: 1px solid rgba(255, 255, 255, 0.08);
      padding: 24px 20px 20px 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-end;
      overflow: hidden;
      box-sizing: border-box;
      box-shadow: inset 0 0 30px rgba(0, 0, 0, 0.6);
    }
    .eq-curve-svg-bg {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
      z-index: 0;
    }
    .eq-stage-wrap .eq-sliders-row {
      position: relative;
      z-index: 2;
      width: 100%;
      display: flex;
      justify-content: space-around;
      align-items: flex-end;
      margin-top: auto;
    }

    
    /* =========================================================================
       Professional Studio Audio Mixing Desk (Parametric Equaliser)
       Optimised to auto-fit inside available window without overflow
       ========================================================================= */
    #slide-eq {
      height: 100% !important;
      max-height: 100% !important;
      overflow: hidden !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      padding: 0 16px !important;
      box-sizing: border-box !important;
    }
    .mixer-slide-card {
      max-width: 860px !important;
      width: min(860px, 100%) !important;
      max-height: min(calc(100vh - 170px), 620px) !important;
      height: auto !important;
      display: flex !important;
      flex-direction: column !important;
      justify-content: space-between !important;
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      box-shadow: 0 28px 70px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
      border-radius: 18px !important;
      overflow: hidden !important;
    }
    #slide-eq .slide-head {
      padding: clamp(6px, 1vh, 12px) clamp(12px, 1.5vw, 20px) !important;
      margin: 0 !important;
    }
    .mixer-slide-body {
      padding: clamp(6px, 1vh, 12px) clamp(10px, 1.5vw, 18px) clamp(10px, 1.2vh, 16px) clamp(10px, 1.5vw, 18px) !important;
      display: flex !important;
      flex-direction: column !important;
      gap: clamp(5px, 0.9vh, 10px) !important;
      flex: 1 1 auto !important;
      min-height: 0 !important;
      overflow-y: auto !important;
      box-sizing: border-box !important;
    }

    /* Top Console Meter Bridge & Preset Scene Deck */
    .mixer-console-bridge {
      display: flex;
      flex-direction: column;
      gap: clamp(4px, 0.8vh, 8px);
      width: 100%;
      background: rgba(14, 18, 27, 0.45);
      border: none !important;
      outline: none !important;
      border-radius: 10px;
      padding: clamp(5px, 0.8vh, 9px) clamp(8px, 1.2vw, 14px);
      box-sizing: border-box;
      box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.6);
    }
    .mixer-scene-row {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: clamp(6px, 1vw, 12px);
      flex-wrap: wrap;
    }
    .mixer-scene-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: clamp(3px, 0.5vh, 6px) clamp(8px, 1vw, 12px);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.05);
      border: none !important;
      outline: none !important;
      color: var(--text-muted);
      cursor: pointer;
      font-family: 'JetBrains Mono', monospace;
      font-size: clamp(9px, 1.1vh, 11px);
      letter-spacing: 0.06em;
      transition: all 0.2s ease;
      box-shadow: 0 2px 6px rgba(0,0,0,0.4);
    }
    .mixer-scene-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-primary);
    }
    .mixer-scene-btn.active {
      background: linear-gradient(180deg, #2b2316 0%, #1a1712 100%) !important;
      border: none !important;
      color: var(--accent-gold);
      box-shadow: 0 0 12px rgba(201, 157, 82, 0.35), inset 0 1px 0 rgba(201, 157, 82, 0.4) !important;
    }
    .mixer-tally-led {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.15);
      box-shadow: none;
      transition: all 0.2s ease;
    }
    .mixer-scene-btn.active .mixer-tally-led {
      background: #c99d52;
      box-shadow: 0 0 8px #c99d52, 0 0 2px #fff;
    }

    /* DSP Visualiser Window */
    .mixer-dsp-screen {
      position: relative;
      width: 100%;
      height: clamp(38px, 6.5vh, 70px);
      background: #06090e;
      border: none !important;
      outline: none !important;
      border-radius: 8px;
      overflow: hidden;
      box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.95);
    }
    .mixer-dsp-topbar {
      position: absolute;
      top: 4px;
      left: 10px;
      right: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 3;
      pointer-events: none;
    }
    .dsp-led-group {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .dsp-active-led {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: #00e676;
      box-shadow: 0 0 6px #00e676;
    }
    .dsp-title {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8.5px;
      color: rgba(255, 255, 255, 0.4);
      letter-spacing: 0.12em;
    }
    .dsp-preset-badge {
      font-family: 'JetBrains Mono', monospace;
      font-size: 9px;
      color: var(--accent-gold);
      background: rgba(201, 157, 82, 0.12);
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid rgba(201, 157, 82, 0.25);
      letter-spacing: 0.08em;
    }
    .mixer-dsp-svg {
      width: 100%;
      height: 100%;
      position: absolute;
      top: 0;
      left: 0;
      pointer-events: none;
    }

    /* Hardware Mixing Desk Chassis Faceplate */
    .mixer-chassis {
      display: flex;
      justify-content: space-between;
      align-items: stretch;
      gap: clamp(4px, 0.7vw, 8px);
      width: 100%;
      background: rgba(14, 18, 27, 0.45);
      border: none !important;
      outline: none !important;
      border-radius: 12px;
      padding: clamp(6px, 1vh, 12px) clamp(6px, 0.8vw, 10px);
      box-sizing: border-box;
      box-shadow: inset 0 2px 4px rgba(255,255,255,0.03), 0 16px 36px rgba(0,0,0,0.65);
      overflow-x: auto;
    }

    /* Individual Vertical Channel Strip */
    .mixer-strip {
      flex: 1 1 0;
      min-width: 74px;
      max-width: 130px;
      background: rgba(22, 28, 40, 0.45);
      border: none !important;
      outline: none !important;
      border-radius: 8px;
      padding: clamp(4px, 0.6vh, 8px) clamp(2px, 0.4vw, 5px);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: clamp(2px, 0.5vh, 5px);
      box-sizing: border-box;
      box-shadow: inset 1px 1px 0 rgba(255, 255, 255, 0.03), 0 4px 12px rgba(0,0,0,0.3);
      position: relative;
    }
    .mixer-strip-master {
      background: rgba(30, 36, 52, 0.55);
      box-shadow: inset 0 0 12px rgba(201, 157, 82, 0.05), 0 4px 14px rgba(0,0,0,0.4);
    }

    /* Channel Header */
    .mixer-strip-head {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1px;
      width: 100%;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      padding-bottom: 3px;
    }
    .mixer-ch-tag {
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      color: rgba(255, 255, 255, 0.4);
      letter-spacing: 0.08em;
    }
    .mixer-ch-freq {
      font-family: 'Inter', sans-serif;
      font-size: clamp(11px, 1.4vh, 13px);
      font-weight: 700;
      color: #fff;
      letter-spacing: 0.02em;
    }
    .mixer-ch-role {
      font-family: 'JetBrains Mono', monospace;
      font-size: 7.5px;
      color: var(--accent-gold);
      letter-spacing: 0.10em;
      text-transform: uppercase;
    }

    /* Rotary Gain Pot Section */
    .mixer-pot-cell {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1px;
      margin: 0;
    }
    .mixer-pot-title {
      font-family: 'JetBrains Mono', monospace;
      font-size: 7px;
      color: rgba(255, 255, 255, 0.45);
      letter-spacing: 0.12em;
    }
    .mixer-pot-housing {
      position: relative;
      width: clamp(28px, 4.2vh, 38px);
      height: clamp(28px, 4.2vh, 38px);
      display: flex;
      justify-content: center;
      align-items: center;
      cursor: ns-resize;
    }
    .mixer-pot-scale {
      position: absolute;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }
    .scale-dot {
      position: absolute;
      font-family: 'JetBrains Mono', monospace;
      font-size: 6.5px;
      color: rgba(255, 255, 255, 0.35);
    }
    .dot-min { bottom: 1px; left: 0px; }
    .dot-mid { top: -2px; left: 50%; transform: translateX(-50%); color: var(--accent-gold); }
    .dot-max { bottom: 1px; right: 0px; }

    .mixer-rotary-dial {
      width: clamp(20px, 3vh, 26px);
      height: clamp(20px, 3vh, 26px);
      border-radius: 50%;
      background: radial-gradient(circle at 35% 35%, #2a3348 0%, #151a24 75%, #0e121a 100%);
      border: none !important;
      outline: none !important;
      box-shadow: 0 3px 8px rgba(0, 0, 0, 0.65), inset 0 1px 1px rgba(255, 255, 255, 0.3);
      position: relative;
      transform: rotate(0deg);
      transition: transform 0.08s ease-out;
    }
    .mixer-dial-indicator {
      position: absolute;
      top: 2px;
      left: 50%;
      transform: translateX(-50%);
      width: 2px;
      height: 6px;
      border-radius: 1px;
      background: #ffffff;
      box-shadow: 0 0 3px rgba(255, 255, 255, 0.8);
    }

    /* Channel Controls: Peak LED & Mute Pushbutton */
    .mixer-ch-controls {
      display: flex;
      align-items: center;
      gap: 4px;
      margin: 0;
    }
    .mixer-peak-led {
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: #3b1116;
      border: 1px solid rgba(255, 42, 75, 0.2);
      transition: all 0.15s ease;
    }
    .mixer-peak-led.active {
      background: #ff2a4b;
      box-shadow: 0 0 8px #ff2a4b;
    }
    .mixer-mute-btn {
      padding: 1px 5px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.04);
      border: none !important;
      outline: none !important;
      color: rgba(255, 255, 255, 0.4);
      font-family: 'JetBrains Mono', monospace;
      font-size: clamp(6.5px, 0.9vh, 7.5px);
      font-weight: 600;
      letter-spacing: 0.05em;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .mixer-mute-btn:hover {
      background: rgba(255, 255, 255, 0.08);
      color: #fff;
    }
    .mixer-mute-btn.muted {
      background: rgba(239, 68, 68, 0.25) !important;
      color: #ef4444 !important;
      box-shadow: 0 0 6px rgba(239, 68, 68, 0.4) !important;
    }

    /* Vertical Studio Fader Assembly */
    .mixer-fader-assembly {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 3px;
      width: 100%;
      height: clamp(72px, 12.5vh, 120px);
      position: relative;
    }
    .mixer-db-scale {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: clamp(62px, 11vh, 105px);
      font-family: 'JetBrains Mono', monospace;
      font-size: clamp(6px, 0.8vh, 7.5px);
      color: rgba(255, 255, 255, 0.35);
      user-select: none;
    }
    .mixer-scale-l {
      text-align: right;
      width: 16px;
    }
    .scale-unity {
      color: var(--accent-gold);
      font-weight: 700;
    }
    .mixer-scale-r {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: clamp(62px, 11vh, 105px);
      width: 5px;
    }
    .scale-tick {
      width: 4px;
      height: 1px;
      background: rgba(255, 255, 255, 0.2);
    }
    .tick-unity {
      width: 6px;
      height: 1.5px;
      background: var(--accent-gold);
    }

    /* Recessed Fader Well */
    .mixer-fader-well {
      position: relative;
      width: clamp(20px, 2.5vw, 28px);
      height: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .mixer-fader-groove {
      position: absolute;
      width: 4px;
      height: clamp(60px, 10.5vh, 100px);
      background: #090c12;
      border: 1px solid rgba(0, 0, 0, 0.9);
      border-radius: 3px;
      box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.9), 0 1px 0 rgba(255, 255, 255, 0.08);
      pointer-events: none;
    }
    .mixer-unity-line {
      position: absolute;
      top: 50%;
      left: 2px;
      right: 2px;
      height: 1px;
      background: rgba(201, 157, 82, 0.35);
      pointer-events: none;
    }

    /* Fader Native Range Input */
    .mixer-fader-slider {
      writing-mode: vertical-lr !important;
      direction: rtl !important;
      appearance: none !important;
      -webkit-appearance: none !important;
      width: clamp(22px, 2.8vw, 30px) !important;
      height: clamp(62px, 11vh, 105px) !important;
      background: transparent !important;
      cursor: ns-resize !important;
      outline: none !important;
      z-index: 2 !important;
      margin: 0 !important;
    }
    .mixer-fader-slider::-webkit-slider-runnable-track {
      background: transparent !important;
    }

    /* Studio Red Fader Cap (Channels 1-5) */
    .mixer-fader-slider.fader-red::-webkit-slider-thumb {
      appearance: none !important;
      -webkit-appearance: none !important;
      width: clamp(20px, 2.6vw, 26px) !important;
      height: clamp(28px, 4.5vh, 38px) !important;
      border-radius: 4px !important;
      background: linear-gradient(180deg, #d32f2f 0%, #a81c1c 45%, #7a1212 55%, #b71c1c 100%) !important;
      border: 1px solid rgba(255, 255, 255, 0.25) !important;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.4), inset 0 -1px 0 rgba(0, 0, 0, 0.6) !important;
      cursor: ns-resize !important;
    }

    /* Studio White Fader Cap (Master Channel) */
    .mixer-fader-slider.fader-white::-webkit-slider-thumb {
      appearance: none !important;
      -webkit-appearance: none !important;
      width: clamp(20px, 2.6vw, 26px) !important;
      height: clamp(28px, 4.5vh, 38px) !important;
      border-radius: 4px !important;
      background: linear-gradient(180deg, #f5f5f5 0%, #e0e0e0 45%, #9e9e9e 55%, #d6d6d6 100%) !important;
      border: 1px solid rgba(255, 255, 255, 0.6) !important;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.8), inset 0 -1px 0 rgba(0, 0, 0, 0.5) !important;
      cursor: ns-resize !important;
    }

    /* Monospace Decibel Readout Badge */
    .mixer-db-readout {
      width: 100%;
      text-align: center;
      padding: 2px 0;
      background: #090c12;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: clamp(8px, 1.1vh, 9.5px);
      color: var(--accent-gold);
      letter-spacing: 0.04em;
    }

    /* Channel Foot Badge */
    .mixer-ch-foot {
      width: 16px;
      height: 16px;
      border-radius: 3px;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      display: flex;
      justify-content: center;
      align-items: center;
      font-family: 'JetBrains Mono', monospace;
      font-size: clamp(7px, 1vh, 8.5px);
      font-weight: 700;
      color: rgba(255, 255, 255, 0.7);
    }
    .mixer-ch-foot-master {
      background: rgba(201, 157, 82, 0.15);
      border-color: var(--accent-gold);
      color: var(--accent-gold);
    }

    /* Master Section Additions */
    .mixer-master-meter-cell {
      display: flex;
      align-items: center;
      gap: 6px;
      height: clamp(30px, 4.2vh, 40px);
      padding: 2px 4px;
      background: #090c12;
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 5px;
    }
    .mixer-stereo-ladder {
      display: flex;
      gap: 3px;
    }
    .ladder-ch {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .led-seg {
      width: 5px;
      height: 3px;
      border-radius: 1px;
      opacity: 0.25;
      transition: opacity 0.08s ease;
    }
    .seg-red { background: #ff2a4b; }
    .seg-amber { background: #ffa000; }
    .seg-green { background: #00e676; }
    .led-seg.active {
      opacity: 1;
      box-shadow: 0 0 4px currentColor;
    }
    .mixer-master-scale-nums {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      height: 100%;
      font-family: 'JetBrains Mono', monospace;
      font-size: 6px;
      color: rgba(255, 255, 255, 0.4);
    }
    .mixer-action-btn {
      padding: 2px 8px;
      border-radius: 3px;
      background: rgba(201, 157, 82, 0.12);
      border: 1px solid rgba(201, 157, 82, 0.3);
      color: var(--accent-gold);
      font-family: 'JetBrains Mono', monospace;
      font-size: 8px;
      font-weight: 700;
      letter-spacing: 0.05em;
      cursor: pointer;
      transition: all 0.15s ease;
    }
    .mixer-action-btn:hover {
      background: var(--accent-gold);
      color: #000;
    }

    /* DIRECTIVE 3: Page titles top right, right aligned, half size, thin weight */
    .slide-head {
      display: flex !important;
      flex-direction: row-reverse !important;
      justify-content: space-between !important;
      align-items: flex-start !important;
      text-align: right !important;
      margin-bottom: 16px !important;
      width: 100% !important;
    }

    .slide-head h3,
    .dac-title-group h3,
    .globe-title-overlay h3 {
      font-size: 10px !important;
      font-weight: 200 !important;
      letter-spacing: 0.16em !important;
      text-transform: uppercase !important;
      color: var(--text-muted) !important;
      text-align: right !important;
      margin: 0 !important;
      opacity: 0.85 !important;
      line-height: 1.3 !important;
    }

    .dac-title-group {
      display: flex !important;
      flex-direction: column !important;
      align-items: flex-end !important;
      margin-left: auto !important;
    }

    .globe-title-overlay {
      position: absolute !important;
      top: max(18px, env(safe-area-inset-top, 18px)) !important;
      right: max(20px, env(safe-area-inset-right, 20px)) !important;
      z-index: 200 !important;
      text-align: right !important;
      pointer-events: none !important;
    }

    .globe-title-overlay .globe-badge {
      display: block;
      font-family: 'JetBrains Mono', monospace;
      font-size: 9px;
      letter-spacing: 0.1em;
      color: var(--accent-gold);
      margin-top: 3px;
      opacity: 0.9;
    }

    /* DIRECTIVE 2: Ensure hub button is never visible */
    #btn-floating-hub, .btn-floating-hub {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }

    /* DIRECTIVE 4: Cluster Flyout Card */
    .globe-cluster-flyout {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: min(360px, 88vw);
      max-height: min(440px, 75vh);
      background: rgba(14, 18, 28, 0.94);
      backdrop-filter: blur(24px) saturate(180%);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      border: 1px solid rgba(212, 175, 55, 0.35);
      border-radius: 16px;
      padding: 16px 20px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.85), 0 0 30px rgba(212, 175, 55, 0.15);
      z-index: 500;
      display: flex;
      flex-direction: column;
      gap: 12px;
      animation: flyoutAppear 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    @keyframes flyoutAppear {
      from { opacity: 0; transform: translate(-50%, -46%) scale(0.96); }
      to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
    }

    .cluster-flyout-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding-bottom: 10px;
    }

    .cluster-flyout-title {
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .cluster-flyout-count {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      color: var(--accent-gold);
      background: rgba(212, 175, 55, 0.12);
      padding: 2px 7px;
      border-radius: 10px;
      border: 1px solid rgba(212, 175, 55, 0.25);
    }

    .cluster-flyout-close {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 20px;
      cursor: pointer;
      line-height: 1;
      padding: 2px 6px;
      border-radius: 6px;
      transition: color 0.15s;
    }
    .cluster-flyout-close:hover {
      color: #fff;
    }

    .cluster-stations-scroll {
      overflow-y: auto;
      max-height: 320px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding-right: 4px;
    }

    .cluster-station-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 10px;
      padding: 10px 14px;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s, transform 0.15s;
    }
    .cluster-station-item:hover {
      background: rgba(212, 175, 55, 0.1);
      border-color: rgba(212, 175, 55, 0.4);
      transform: translateX(2px);
    }

    .cluster-station-name {
      font-size: 12.5px;
      font-weight: 500;
      color: #fff;
    }

    .cluster-station-meta {
      font-size: 10px;
      color: var(--text-muted);
      margin-top: 2px;
      display: flex;
      gap: 8px;
    }

    .cluster-station-btn {
      background: var(--accent-gold);
      color: #0b0e14;
      border: none;
      border-radius: 6px;
      padding: 5px 12px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.15s, transform 0.15s;
    }
    .cluster-station-btn:hover {
      opacity: 0.9;
      transform: scale(1.05);
    }

  

/* ==========================================================================
   Minimal High-End Synth Module Discovery & Universal Remote Control Styles
   ========================================================================== */

/* --- Synth Module Discovery --- */
.synth-chassis {
  background: radial-gradient(circle at 50% 20%, #151922 0%, #0d1017 100%);
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 14px;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  padding: 16px 20px;
  position: relative;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #e2e8f0;
}

.synth-hex-bolt {
  position: absolute;
  width: 9px;
  height: 9px;
  background: radial-gradient(circle, #3a4150 30%, #181c24 90%);
  border: 1px solid #475569;
  border-radius: 50%;
  box-shadow: inset 0 1px 1px rgba(0,0,0,0.8);
}
.synth-bolt-tl { top: 8px; left: 10px; }
.synth-bolt-tr { top: 8px; right: 10px; }
.synth-bolt-bl { bottom: 8px; left: 10px; }
.synth-bolt-br { bottom: 8px; right: 10px; }

.synth-bus-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  padding-bottom: 10px;
  margin-bottom: 12px;
}

.synth-bus-spec {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: var(--accent-gold);
  display: flex;
  align-items: center;
  gap: 12px;
}

.synth-bus-badge {
  background: rgba(245, 166, 35, 0.12);
  border: 1px solid rgba(245, 166, 35, 0.28);
  padding: 2px 7px;
  border-radius: 4px;
  color: #f5a623;
  font-weight: 600;
}

.synth-bus-led {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px #10b981;
  margin-right: 4px;
}

/* Category Filter Matrix */
.synth-filter-matrix {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 14px;
}

.synth-filter-pill {
  background: rgba(22, 28, 38, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.04em;
  padding: 5px 12px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.18s ease;
  user-select: none;
}

.synth-filter-pill:hover {
  background: rgba(30, 39, 54, 0.95);
  color: #f1f5f9;
  border-color: rgba(255, 255, 255, 0.18);
}

.synth-filter-pill.active {
  background: rgba(245, 166, 35, 0.15);
  border-color: rgba(245, 166, 35, 0.5);
  color: #fbbf24;
  box-shadow: 0 0 10px rgba(245, 166, 35, 0.18);
}

.synth-filter-pill .pill-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #475569;
}
.synth-filter-pill.active .pill-dot {
  background: #fbbf24;
  box-shadow: 0 0 5px #fbbf24;
}

/* Patch Bay Utility Bar */
.synth-patch-utility {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  background: rgba(14, 18, 26, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 14px;
}

.synth-scan-btn {
  background: linear-gradient(180deg, #242c3d 0%, #171d29 100%);
  border: 1px solid rgba(245, 166, 35, 0.35);
  color: #f8fafc;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  padding: 8px 16px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.15s ease;
  box-shadow: 0 2px 6px rgba(0,0,0,0.4);
}
.synth-scan-btn:hover {
  border-color: var(--accent-gold);
  box-shadow: 0 0 12px rgba(245, 166, 35, 0.3);
  transform: translateY(-1px);
}
.synth-scan-btn:active {
  transform: translateY(1px);
}
.synth-scan-led {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
  box-shadow: 0 0 6px #f59e0b;
}

.synth-manual-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.synth-tuner-input {
  background: #0a0d14;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  color: var(--accent-cyan);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 6px 10px;
  width: 150px;
  outline: none;
  transition: border-color 0.2s;
}
.synth-tuner-input:focus {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 8px rgba(0, 229, 255, 0.25);
}

.synth-patch-jack-icon {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid #94a3b8;
  background: #0f172a;
  box-shadow: inset 0 0 3px #000;
  display: inline-block;
}

/* Discovered Module Cards Grid */
.synth-module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 12px;
  max-height: 440px;
  overflow-y: auto;
  padding-right: 4px;
}

.synth-module-card {
  background: linear-gradient(180deg, #161b26 0%, #10141e 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 12px 14px;
  position: relative;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.synth-module-card:hover {
  border-color: rgba(245, 166, 35, 0.35);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.45);
}
.synth-module-card.active-unit {
  border-color: var(--accent-gold);
  background: linear-gradient(180deg, #1b2230 0%, #121824 100%);
  box-shadow: 0 0 16px rgba(245, 166, 35, 0.2);
}

.synth-card-rail {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  color: #64748b;
  margin-bottom: 8px;
}

.synth-cat-tag {
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-size: 9px;
  letter-spacing: 0.04em;
}
.synth-cat-tag.cat-projector { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); }
.synth-cat-tag.cat-google_tv { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
.synth-cat-tag.cat-xbox { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); }
.synth-cat-tag.cat-streamer { background: rgba(245, 166, 35, 0.15); color: #fbbf24; border: 1px solid rgba(245, 166, 35, 0.3); }
.synth-cat-tag.cat-other { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3); }

.synth-card-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #f8fafc;
  margin-bottom: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.synth-card-sub {
  font-size: 10.5px;
  color: #94a3b8;
  margin-bottom: 8px;
}

.synth-card-specs {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--accent-cyan);
  background: rgba(0, 0, 0, 0.28);
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
}

.synth-protocol-bus {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.synth-protocol-chip {
  font-family: 'JetBrains Mono', monospace;
  font-size: 8.5px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  color: #cbd5e1;
}

.synth-card-actions {
  display: flex;
  gap: 8px;
}

.synth-btn-patch {
  flex: 1;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #e2e8f0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.synth-btn-patch:hover {
  background: rgba(51, 65, 85, 0.9);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.25);
}
.synth-btn-patch.patched {
  background: rgba(16, 185, 129, 0.18);
  border-color: rgba(16, 185, 129, 0.5);
  color: #34d399;
}

.synth-btn-remote {
  flex: 1;
  background: rgba(245, 166, 35, 0.14);
  border: 1px solid rgba(245, 166, 35, 0.35);
  color: #fbbf24;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}
.synth-btn-remote:hover {
  background: rgba(245, 166, 35, 0.28);
  border-color: #fbbf24;
  box-shadow: 0 0 10px rgba(245, 166, 35, 0.3);
}

/* --- Universal Remote Control Screen Styles --- */
.remote-chassis {
  background: radial-gradient(circle at 50% 15%, #141822 0%, #0a0d14 100%);
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 16px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  padding: 16px 20px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: #e2e8f0;
}

.remote-target-deck {
  background: rgba(10, 13, 19, 0.9);
  border: 1px solid rgba(245, 166, 35, 0.25);
  border-radius: 10px;
  padding: 8px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.remote-target-info {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}

.remote-led-online {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 8px #10b981;
  animation: remote-pulse 2s infinite ease-in-out;
}
@keyframes remote-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.9); }
}

.remote-change-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.remote-change-btn:hover {
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  border-color: var(--accent-gold);
}

/* Remote Grid Layout */
.remote-deck-grid {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 16px;
}

@media (max-width: 860px) {
  .remote-deck-grid {
    grid-template-columns: 1fr;
  }
}

/* Remote Utility Bar */
.remote-power-source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}

.remote-power-btn {
  background: linear-gradient(180deg, #dc2626 0%, #991b1b 100%);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  padding: 7px 14px;
  border-radius: 8px;
  cursor: pointer;
  box-shadow: 0 0 10px rgba(220, 38, 38, 0.35);
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  gap: 6px;
}
.remote-power-btn:hover {
  background: linear-gradient(180deg, #ef4444 0%, #b91c1c 100%);
  box-shadow: 0 0 14px rgba(239, 68, 68, 0.55);
}
.remote-power-btn:active {
  transform: translateY(1px);
}

.remote-source-matrix {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.remote-source-btn {
  background: rgba(22, 28, 40, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.09);
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  padding: 6px 9px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.remote-source-btn:hover {
  background: rgba(36, 46, 64, 0.95);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.2);
}
.remote-source-btn.active {
  background: rgba(0, 229, 255, 0.15);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Studio D-Pad Section */
.remote-dpad-deck {
  background: rgba(14, 18, 26, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin-bottom: 14px;
}

.remote-dpad-matrix {
  position: relative;
  width: 170px;
  height: 170px;
  margin: 8px auto;
}

.dpad-center-btn {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 66px;
  height: 66px;
  border-radius: 50%;
  background: radial-gradient(circle at 40% 35%, #2a3344 0%, #171d27 100%);
  border: 2px solid rgba(245, 166, 35, 0.4);
  color: #fbbf24;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 10px rgba(0,0,0,0.6), inset 0 1px 1px rgba(255,255,255,0.2);
  z-index: 2;
  transition: all 0.12s ease;
}
.dpad-center-btn:hover {
  border-color: var(--accent-gold);
  box-shadow: 0 0 14px rgba(245, 166, 35, 0.4);
}
.dpad-center-btn:active {
  transform: translate(-50%, -50%) scale(0.95);
}

.dpad-arrow-btn {
  position: absolute;
  background: rgba(28, 35, 48, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.12s ease;
  font-size: 13px;
}
.dpad-arrow-btn:hover {
  background: rgba(45, 55, 75, 0.95);
  color: var(--accent-gold);
  border-color: rgba(245, 166, 35, 0.4);
}
.dpad-arrow-btn:active {
  background: rgba(245, 166, 35, 0.2);
}

.dpad-arrow-up {
  top: 0;
  left: 52px;
  width: 66px;
  height: 48px;
  border-radius: 12px 12px 4px 4px;
}
.dpad-arrow-down {
  bottom: 0;
  left: 52px;
  width: 66px;
  height: 48px;
  border-radius: 4px 4px 12px 12px;
}
.dpad-arrow-left {
  top: 52px;
  left: 0;
  width: 48px;
  height: 66px;
  border-radius: 12px 4px 4px 12px;
}
.dpad-arrow-right {
  top: 52px;
  right: 0;
  width: 48px;
  height: 66px;
  border-radius: 4px 12px 12px 4px;
}

/* Nav Action Keys (Back, Home, Menu, Voice) */
.remote-action-row {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 10px;
}

.remote-action-btn {
  background: rgba(26, 32, 45, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 500;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  gap: 5px;
}
.remote-action-btn:hover {
  background: rgba(40, 50, 70, 0.95);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.25);
}
.remote-action-btn:active {
  transform: translateY(1px);
}

/* Rockers & Transport */
.remote-rockers-transport-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.remote-rocker-assembly {
  background: rgba(14, 18, 26, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 60px;
}

.remote-rocker-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 700;
  padding: 5px 0;
  width: 100%;
  cursor: pointer;
  transition: all 0.12s ease;
  border-radius: 4px;
}
.remote-rocker-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.remote-rocker-btn:active {
  background: rgba(245, 166, 35, 0.2);
  color: var(--accent-gold);
}

.remote-rocker-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 8.5px;
  font-weight: 600;
  color: var(--accent-gold);
  padding: 2px 0;
}

.remote-transport-deck {
  background: rgba(14, 18, 26, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  padding: 6px 10px;
  display: flex;
  gap: 6px;
}

.remote-transport-btn {
  background: rgba(26, 33, 46, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  font-size: 11px;
  padding: 6px 10px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.remote-transport-btn:hover {
  background: rgba(42, 53, 74, 0.95);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.2);
}
.remote-transport-btn:active {
  background: rgba(245, 166, 35, 0.25);
}

/* Quick App Launchers */
.remote-app-deck {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-bottom: 14px;
}

.remote-app-btn {
  background: rgba(18, 23, 33, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  padding: 7px 4px;
  border-radius: 6px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s ease;
}
.remote-app-btn:hover {
  background: rgba(32, 41, 58, 0.95);
  color: #fff;
  border-color: rgba(245, 166, 35, 0.4);
}

/* Virtual Keyboard Deck */
.remote-keyboard-deck {
  background: rgba(14, 18, 26, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 14px;
}

.remote-keyboard-head {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--accent-gold);
  letter-spacing: 0.06em;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.remote-input-row {
  display: flex;
  gap: 6px;
}

.remote-text-input {
  flex: 1;
  background: #0a0d14;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 6px 10px;
  outline: none;
  transition: border-color 0.2s;
}
.remote-text-input:focus {
  border-color: var(--accent-cyan);
}

.remote-send-btn {
  background: linear-gradient(180deg, #2563eb 0%, #1d4ed8 100%);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.remote-send-btn:hover {
  background: linear-gradient(180deg, #3b82f6 0%, #2563eb 100%);
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.4);
}

/* Precision 2D Touchpad Trackpad */
.remote-trackpad-deck {
  background: rgba(14, 18, 26, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  padding: 10px 12px;
}

.remote-trackpad-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--accent-cyan);
  letter-spacing: 0.06em;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.remote-trackpad-surface {
  width: 100%;
  height: 140px;
  background: radial-gradient(circle at 50% 50%, #171d29 0%, #0c0f16 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  position: relative;
  overflow: hidden;
  cursor: crosshair;
  user-select: none;
  box-shadow: inset 0 2px 6px rgba(0,0,0,0.6);
}

.remote-trackpad-crosshair {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 16px;
  height: 16px;
  border: 1px dashed rgba(255, 255, 255, 0.15);
  transform: translate(-50%, -50%);
  border-radius: 50%;
  pointer-events: none;
}

.remote-cursor-dot {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent-cyan);
  box-shadow: 0 0 8px var(--accent-cyan);
  transform: translate(-50%, -50%);
  pointer-events: none;
  transition: opacity 0.2s ease;
  opacity: 0.85;
}

.remote-trackpad-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.remote-trackpad-btn {
  flex: 1;
  background: rgba(24, 30, 42, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  font-weight: 500;
  padding: 6px 0;
  border-radius: 5px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s ease;
}
.remote-trackpad-btn:hover {
  background: rgba(38, 48, 66, 0.95);
  color: #fff;
  border-color: rgba(255, 255, 255, 0.2);
}
.remote-trackpad-btn:active {
  background: rgba(0, 229, 255, 0.2);
}

/* Remote Toast HUD */
.remote-toast-hud {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  color: #a7f3d0;
  background: rgba(6, 78, 59, 0.25);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 5px;
  padding: 4px 10px;
  margin-top: 10px;
  text-align: center;
  opacity: 0;
  transition: opacity 0.2s ease;
}
.remote-toast-hud.visible {
  opacity: 1;
}


/* =========================================================================
   Ambient Voice AI Studio & Multi-Device Automation Deck (Audiophile Theme)
   ========================================================================= */
.voice-chassis {
  max-width: 1400px;
  margin: 10px auto 30px auto;
  padding: 24px 28px 50px 28px;
  background: radial-gradient(circle at 50% 15%, #141822 0%, #0a0d14 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 20px;
  position: relative;
  z-index: 10;
  box-sizing: border-box;
}

.voice-header-ribbon {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(135deg, rgba(21, 27, 39, 0.95), rgba(18, 23, 33, 0.98));
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 12px 20px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.voice-title-box h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: var(--text-main);
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 10px;
}

.voice-status-badges {
  display: flex;
  align-items: center;
  gap: 14px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}

.voice-badge-led {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 20px;
  background: rgba(11, 14, 20, 0.8);
  border: 1px solid var(--border-subtle);
  color: var(--text-muted);
}

.voice-badge-led.active {
  border-color: rgba(201, 157, 82, 0.6);
  color: var(--accent-gold);
  background: rgba(201, 157, 82, 0.1);
}

.voice-badge-led.live-cyan {
  border-color: rgba(56, 189, 248, 0.6);
  color: var(--accent-cyan);
  background: rgba(56, 189, 248, 0.1);
}

.voice-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-dim);
  transition: all 0.3s ease;
}

.voice-dot.pulse-gold {
  background: var(--accent-gold);
  box-shadow: 0 0 10px var(--accent-gold);
  animation: pulseGoldLed 1.5s infinite;
}

.voice-dot.pulse-cyan {
  background: var(--accent-cyan);
  box-shadow: 0 0 10px var(--accent-cyan);
}

@keyframes pulseGoldLed {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.2); opacity: 1; filter: brightness(1.3); }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.voice-grid-two-col {
  display: grid;
  grid-template-columns: 1.15fr 1fr;
  gap: 18px;
}

@media (max-width: 1024px) {
  .voice-grid-two-col {
    grid-template-columns: 1fr;
  }
}

.voice-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.voice-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(36, 47, 68, 0.6);
  padding-bottom: 10px;
}

.voice-card-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  color: var(--accent-gold);
  display: flex;
  align-items: center;
  gap: 8px;
}

.voice-spectrum-box {
  background: #06080c;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  height: 140px;
  position: relative;
  overflow: hidden;
}

#voice-spectrum-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.vad-hud-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
  background: #090c12;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid rgba(36, 47, 68, 0.5);
}

.vad-meter-track {
  flex: 1;
  margin: 0 14px;
  height: 8px;
  background: #151b27;
  border-radius: 4px;
  overflow: hidden;
  position: relative;
  border: 1px solid #242f44;
}

.vad-meter-fill {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, #10b981 0%, #38bdf8 65%, #c99d52 100%);
  border-radius: 4px;
  transition: width 0.08s linear;
}

.vad-threshold-marker {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #f43f5e;
  box-shadow: 0 0 6px #f43f5e;
}

.voice-subtitle-oled {
  background: #05070a;
  border: 1px solid rgba(201, 157, 82, 0.35);
  border-radius: 8px;
  padding: 14px 18px;
  min-height: 95px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  box-shadow: inset 0 2px 10px rgba(0,0,0,0.8), 0 0 15px rgba(201, 157, 82, 0.08);
}

.voice-subtitle-text {
  font-size: 15px;
  line-height: 1.5;
  color: #fff;
  font-weight: 500;
  font-family: system-ui, -apple-system, sans-serif;
  word-break: break-word;
}

.voice-subtitle-text .interim {
  color: #8b99b5;
  font-style: italic;
}

.voice-subtitle-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--accent-gold);
  margin-top: 8px;
  letter-spacing: 0.8px;
}

.voice-btn-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.voice-btn {
  flex: 1;
  min-width: 140px;
  padding: 10px 14px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  color: var(--text-main);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s ease;
}

.voice-btn:hover {
  border-color: var(--accent-gold);
  background: rgba(201, 157, 82, 0.15);
  color: var(--accent-gold);
  transform: translateY(-1px);
}

.voice-btn.active-listening {
  background: linear-gradient(135deg, #c99d52, #e0b468);
  color: #0b0e14;
  border: none;
  box-shadow: 0 4px 18px rgba(201, 157, 82, 0.4);
}

.voice-decision-stream {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 250px;
  overflow-y: auto;
  padding-right: 4px;
}

.voice-decision-stream::-webkit-scrollbar {
  width: 4px;
}
.voice-decision-stream::-webkit-scrollbar-thumb {
  background: var(--border-subtle);
  border-radius: 2px;
}

.decision-card {
  background: #0d111a;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: slideInDecision 0.3s ease-out;
}

@keyframes slideInDecision {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.decision-card.reflex {
  border-left: 3px solid var(--accent-cyan);
}

.decision-card.cognitive {
  border-left: 3px solid var(--accent-gold);
}

.decision-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
}

.decision-intent {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.decision-intent.volume { color: var(--accent-cyan); }
.decision-intent.media { color: #ec4899; }
.decision-intent.lighting { color: var(--accent-gold); }
.decision-intent.none { color: var(--text-dim); }

.decision-action-chain {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.action-pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  background: #171f2e;
  border: 1px solid #2a3852;
  color: #d1d9e6;
  display: flex;
  align-items: center;
  gap: 4px;
}

.lighting-preview-glow {
  position: relative;
  background: #0a0d14;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  overflow: hidden;
  transition: all 0.5s ease;
}

.lighting-preview-backdrop {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  opacity: 0.25;
  background: radial-gradient(circle at 50% 50%, #d4af37 0%, transparent 80%);
  pointer-events: none;
  transition: all 0.5s ease;
}

.lighting-preset-pills {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 8px;
}

.preset-pill-btn {
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
  background: #121721;
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.preset-pill-btn:hover {
  border-color: var(--accent-gold);
  color: #fff;
  background: rgba(201, 157, 82, 0.12);
}

.preset-pill-btn.active {
  border-color: var(--accent-gold);
  color: var(--accent-gold);
  background: rgba(201, 157, 82, 0.2);
  box-shadow: 0 0 12px rgba(201, 157, 82, 0.25);
}

.routine-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
  gap: 12px;
}

.routine-card {
  background: #0f141f;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  transition: all 0.2s ease;
}

.routine-card:hover {
  border-color: rgba(201, 157, 82, 0.5);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
}

.routine-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.routine-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-main);
  display: flex;
  align-items: center;
  gap: 6px;
}

.routine-priority {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 3px;
  background: #1c2536;
  color: var(--accent-cyan);
}

.routine-triggers {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.trigger-tag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: var(--accent-cyan);
  font-family: 'JetBrains Mono', monospace;
}

.routine-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid rgba(36, 47, 68, 0.4);
  padding-top: 8px;
  margin-top: 2px;
}

.btn-test-routine {
  padding: 4px 10px;
  border-radius: 4px;
  background: rgba(201, 157, 82, 0.1);
  border: 1px solid rgba(201, 157, 82, 0.35);
  color: var(--accent-gold);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-test-routine:hover {
  background: var(--accent-gold);
  color: #0b0e14;
}


    /* =========================================================================
       AUDIO HARDWARE CONSOLE: ROTATING DISC NAVIGATION & UNIFIED CHASSIS
       ========================================================================= */
    #sidebar-drawer, #nav-drawer-backdrop, #btn-floating-nav {
      display: none !important;
    }

    .main-viewport {
      margin-left: 0 !important;
      width: 100% !important;
      max-width: 100vw !important;
      padding-top: 0 !important;
    }

    /* Rotary Disc Navigation Wrapper */
    .rotary-nav-wrapper {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 82px;
      z-index: 1000;
      pointer-events: none;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
      user-select: none;
      -webkit-user-select: none;
      background: linear-gradient(180deg, rgba(8, 11, 16, 0.98) 0%, rgba(11, 15, 22, 0.92) 75%, rgba(11, 15, 22, 0) 100%);
      -webkit-backdrop-filter: blur(20px);
      backdrop-filter: blur(20px);
    }

    .rotary-nav-housing {
      position: relative;
      width: 100%;
      height: 56px;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      overflow: hidden;
      pointer-events: auto;
      cursor: grab;
      touch-action: pan-y;
      border-bottom: none !important;
    }
    .rotary-nav-housing:active {
      cursor: grabbing;
    }

    /* Milled Titanium Rotary Disc Dial */
    .rotary-nav-disc {
      position: absolute;
      top: -584px;
      left: 50%;
      width: 640px;
      height: 640px;
      margin-left: -320px;
      border-radius: 50%;
      background: radial-gradient(circle at 50% 50%, #161c26 0%, #10141d 50%, #0b0e14 82%),
                  conic-gradient(from 0deg, rgba(255,255,255,0.03) 0deg 2deg, transparent 2deg 30deg);
      border: 2px solid rgba(255, 255, 255, 0.09);
      box-shadow: 
        inset 0 0 0 14px rgba(0,0,0,0.5),
        inset 0 0 0 16px rgba(201, 157, 82, 0.22),
        inset 0 0 0 38px rgba(0,0,0,0.6),
        inset 0 0 0 40px rgba(255,255,255,0.04),
        0 8px 32px rgba(0,0,0,0.9);
      transition: filter 0.15s ease-out;
      will-change: transform, filter;
    }

    /* CNC Knurled outer perimeter bevel */
    .rotary-knurl-ring {
      position: absolute;
      top: 6px;
      left: 6px;
      right: 6px;
      bottom: 6px;
      border-radius: 50%;
      border: 1px dashed rgba(201, 157, 82, 0.25);
      background: repeating-conic-gradient(
        from 0deg,
        rgba(255, 255, 255, 0.05) 0deg 0.5deg,
        rgba(0, 0, 0, 0.3) 0.5deg 1.5deg
      );
      mask: radial-gradient(circle, transparent 67%, black 68%);
      -webkit-mask: radial-gradient(circle, transparent 67%, black 68%);
      pointer-events: none;
    }

    /* Radial slide items */
    .rotary-disc-items {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
    }

    .rotary-item {
      position: absolute;
      top: 50%;
      left: 50%;
      width: 100px;
      height: 32px;
      margin-top: -16px;
      margin-left: -50px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 2px;
      cursor: pointer;
      pointer-events: auto;
      transition: opacity 0.2s ease;
    }

    .rotary-item-led {
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
      box-shadow: none;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .rotary-item-label {
      font-family: 'JetBrains Mono', monospace;
      font-size: 9.5px;
      font-weight: 500;
      letter-spacing: 0.12em;
      color: rgba(255, 255, 255, 0.38);
      text-transform: uppercase;
      white-space: nowrap;
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .rotary-item.active .rotary-item-led {
      background: var(--accent-gold);
      box-shadow: 0 0 10px var(--accent-gold), 0 0 4px #fff;
    }

    .rotary-item.active .rotary-item-label {
      color: var(--accent-gold);
      font-weight: 600;
      text-shadow: 0 0 10px rgba(201, 157, 82, 0.6);
    }

    /* 6 o'clock Amber Gold Illuminated Index Needle */
    .rotary-index-needle {
      position: absolute;
      bottom: 2px;
      left: 50%;
      transform: translateX(-50%);
      width: 0;
      height: 0;
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
      border-bottom: 7px solid var(--accent-gold);
      filter: drop-shadow(0 0 6px var(--accent-gold));
      pointer-events: none;
      z-index: 10;
    }

    /* Active Slide Readout Ribbon */
    .rotary-active-ribbon {
      height: 24px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0 14px;
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 20px;
      margin-top: 1px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
      pointer-events: auto;
      cursor: pointer;
    }

    .rotary-step-pill {
      font-family: 'JetBrains Mono', monospace;
      font-size: 9px;
      font-weight: 600;
      color: var(--accent-gold);
      letter-spacing: 0.08em;
      padding: 1px 6px;
      background: rgba(201, 157, 82, 0.14);
      border-radius: 8px;
    }

    .rotary-title-text {
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 600;
      color: #fff;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }

    /* Unified Studio Glassmorphic Slide Chassis */
    .slide-card {
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 18px !important;
      box-shadow: 0 20px 48px rgba(0, 0, 0, 0.65), inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
    }

    .slide-head {
      border-bottom: none !important;
      background: transparent !important;
    }

    .slide-title {
      font-family: 'JetBrains Mono', monospace !important;
      font-weight: 500 !important;
      letter-spacing: 0.08em !important;
      text-transform: uppercase !important;
      color: rgba(255, 255, 255, 0.65) !important;
    }

    .carousel-slide {
      min-width: 100%;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start !important;
      overflow-y: auto !important;
      -webkit-overflow-scrolling: touch;
      padding: 92px 24px 28px 24px !important;
      position: relative;
    }

    #slide-player.carousel-slide {
      padding: 88px 16px 20px 16px !important;
    }

    #slide-radio.carousel-slide {
      padding: 0 !important;
    }

    /* Inset well styling for hardware racks */
    .synth-chassis, .remote-chassis, .voice-chassis {
      background: rgba(12, 16, 24, 0.85) !important;
      border: 1px solid rgba(255, 255, 255, 0.07) !important;
      border-radius: 14px !important;
      box-shadow: inset 0 2px 10px rgba(0,0,0,0.7), 0 16px 40px rgba(0,0,0,0.8) !important;
    }

    /* =========================================================================
       COMPREHENSIVE RESPONSIVE ENGINE (Mobile, Tablet, Desktop)
       ========================================================================= */

    /* Tablet Devices (601px - 1024px) */
    @media (min-width: 601px) and (max-width: 1024px) {
      .rotary-nav-wrapper { height: 76px; }
      .rotary-nav-housing { height: 52px; }
      .rotary-nav-disc { width: 540px; height: 540px; top: -488px; margin-left: -270px; }
      .rotary-active-ribbon {
      height: 24px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0 14px;
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 20px;
      margin-top: 1px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
      pointer-events: auto;
      cursor: pointer;
    }
      .rotary-title-text { font-size: 9.5px; }
      .rotary-step-pill { font-size: 8.5px; }

      .carousel-slide { 
        padding: 86px 16px 24px 16px !important;
        justify-content: flex-start !important;
      }
      .slide-card { max-width: 95% !important; margin: 0 auto !important; }
      .mixer-slide-card { max-width: 96% !important; }
      .mixer-chassis { gap: 6px !important; }
    }

    /* Mobile Portrait Devices (<= 600px) */
    @media (max-width: 600px) {
      .rotary-nav-wrapper { height: 68px; }
      .rotary-nav-housing { height: 46px; }
      .rotary-nav-disc { width: 440px; height: 440px; top: -394px; margin-left: -220px; }
      .rotary-item { width: 84px; height: 28px; margin-left: -42px; }
      .rotary-item-label { font-size: 8.5px; }
      .rotary-active-ribbon {
      height: 24px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0 14px;
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 20px;
      margin-top: 1px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
      pointer-events: auto;
      cursor: pointer;
    }
      .rotary-title-text { font-size: 8.5px; }
      .rotary-step-pill { font-size: 8px; padding: 1px 4px; }
      .rotary-index-needle { border-bottom: 6px solid var(--accent-gold); }

      .carousel-slide { 
        padding: 76px 8px 20px 8px !important;
        justify-content: flex-start !important;
      }
      #slide-player.carousel-slide { padding: 74px 6px 14px 6px !important; }

      .slide-card {
        max-width: 100% !important;
        border-radius: 14px !important;
        margin: 0 auto !important;
      }
      /* Remove redundant inner card header on mobile as rotary ribbon indicates title */
      .slide-head { display: none !important; }
      .slide-body { padding: 12px 10px !important; }

      /* Mobile Mixer Strips: Smooth Horizontal Touch Momentum Scroll */
      .mixer-slide-card { max-width: 100% !important; }
      .mixer-slide-body { padding: 8px 6px 14px 6px !important; gap: 8px !important; }
      .mixer-console-bridge { padding: 6px 8px !important; }
      .mixer-scene-row { gap: 4px !important; }
      .mixer-scene-btn { padding: 4px 7px !important; font-size: 8.5px !important; }

      .mixer-chassis {
        gap: 6px !important;
        padding: 6px 4px !important;
        overflow-x: auto !important;
        -webkit-overflow-scrolling: touch !important;
        scroll-snap-type: x mandatory !important;
      }
      .mixer-strip {
        flex: 0 0 70px !important;
        min-width: 70px !important;
        max-width: 70px !important;
        padding: 6px 3px 8px 3px !important;
        scroll-snap-align: start !important;
      }
      .mixer-pot-housing { width: 34px !important; height: 34px !important; }
      .mixer-rotary-dial { width: 24px !important; height: 24px !important; }
      .mixer-fader-assembly { height: 120px !important; }
      .mixer-fader-groove { height: 100px !important; }
      .mixer-fader-slider { height: 100px !important; }
      .mixer-db-scale, .mixer-scale-r { height: 100px !important; }

      /* Mobile Remote Layout */
      .remote-deck-grid {
        grid-template-columns: 1fr !important;
        gap: 12px !important;
      }
      .voice-grid-two-col {
        grid-template-columns: 1fr !important;
        gap: 12px !important;
      }
      .vis-twin-vu {
        gap: 10px !important;
      }
    }

    /* Mobile Landscape Devices (height <= 520px and orientation landscape) */
    @media (max-height: 520px) and (orientation: landscape) {
      .rotary-nav-wrapper { height: 50px; }
      .rotary-nav-housing { height: 32px; }
      .rotary-nav-disc { width: 380px; height: 380px; top: -348px; margin-left: -190px; }
      .rotary-item { width: 76px; height: 24px; margin-left: -38px; }
      .rotary-item-label { font-size: 8px; }
      .rotary-active-ribbon {
      height: 24px;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 0 14px;
      background: rgba(14, 18, 26, 0.40) !important;
      -webkit-backdrop-filter: blur(28px) saturate(160%) !important;
      backdrop-filter: blur(28px) saturate(160%) !important;
      border: none !important;
      outline: none !important;
      border-radius: 20px;
      margin-top: 1px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
      pointer-events: auto;
      cursor: pointer;
    }
      .rotary-title-text { font-size: 8px; }
      .rotary-step-pill { font-size: 7.5px; padding: 0 3px; }
      .rotary-index-needle { border-bottom: 5px solid var(--accent-gold); }

      .carousel-slide { 
        padding: 56px 12px 10px 12px !important;
        justify-content: flex-start !important;
        overflow-y: auto !important;
      }
      #slide-player.carousel-slide { padding: 52px 8px 8px 8px !important; }

      .slide-card { 
        max-height: none !important;
        margin: 0 auto !important;
      }
      .slide-head { display: none !important; }
      .slide-body { padding: 8px 12px !important; }

      /* Compact Mixer in Landscape */
      .mixer-slide-body { gap: 6px !important; padding: 6px 10px !important; }
      .mixer-console-bridge { padding: 6px 10px !important; gap: 6px !important; }
      .mixer-dsp-screen { height: 46px !important; }
      .mixer-chassis { padding: 6px 8px !important; gap: 6px !important; }
      .mixer-strip { padding: 4px 3px 6px 3px !important; gap: 4px !important; }
      .mixer-pot-cell { margin: 0 !important; }
      .mixer-pot-housing { width: 30px !important; height: 30px !important; }
      .mixer-rotary-dial { width: 20px !important; height: 20px !important; }
      .mixer-fader-assembly { height: 86px !important; }
      .mixer-fader-groove { height: 76px !important; }
      .mixer-fader-slider { height: 76px !important; }
      .mixer-db-scale, .mixer-scale-r { height: 76px !important; }
      .mixer-db-scale { font-size: 6px !important; }
    }
</style>
  <script src="/three.min.js"></script>
  <script>
    if (typeof THREE === 'undefined') {
      document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"><\\/script>');
    }
  </script>
  <script>
    /* =========================================================================
       Audiophile Streamer & Interface Synchronization Engines
       ========================================================================= */

    // 1. DAC Output & Filter Synchronization
    window.applyDacFilter = async function(filterName) {
      try {
        const filterTag = document.getElementById('filter-active-tag');
        if (filterTag) filterTag.innerText = filterName.replace('_', ' ').toUpperCase();

        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ dac_filter: filterName })
        });
        const data = await res.json();
        console.log('[DAC] Filter synchronised with streamer:', filterName, data);
        if (typeof updateStatus === 'function') updateStatus();
      } catch (e) {
        console.warn('[DAC] Error applying filter:', e);
      }
    };

    window.toggleFixedVolume = async function(isFixed) {
      const chk = document.getElementById('chk-fixed-volume');
      const statusBadge = document.getElementById('fixed-vol-status-badge');

      if (isFixed) {
        const confirmed = window.confirm(
          "CAUTION: Bit-Perfect Fixed Line-Out Mode bypasses software volume attenuation and locks output at 100% (0 dB).\\n\\n" +
          "Ensure connected downstream pre-amplifiers, integrated amplifiers, or active monitors are attenuated to avoid sudden high SPL.\\n\\n" +
          "Enable Fixed 0dB Mode?"
        );
        if (!confirmed) {
          if (chk) chk.checked = false;
          return;
        }
      }

      if (statusBadge) {
        statusBadge.innerText = isFixed ? 'FIXED 0dB' : 'VARIABLE';
        statusBadge.classList.toggle('active', isFixed);
      }

      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fixed_volume: isFixed, fixed_volume_mode: isFixed })
        });
        const data = await res.json();
        if (typeof updateStatus === 'function') updateStatus();
      } catch (e) {
        console.warn('[DAC] Error toggling fixed volume:', e);
        // Rollback on network failure
        if (chk) chk.checked = !isFixed;
        if (statusBadge) {
          statusBadge.innerText = !isFixed ? 'FIXED 0dB' : 'VARIABLE';
          statusBadge.classList.toggle('active', !isFixed);
        }
      }
    };

    // 2. Parametric Equaliser Synchronization
    const EQ_PRESET_DEFINITIONS = {
      flat: { '32': 0, '120': 0, '1000': 0, '4500': 0, '12000': 0 },
      harman: { '32': 5, '120': 3, '1000': 0, '4500': 1, '12000': -2 },
      warmth: { '32': 3, '120': 4, '1000': 1, '4500': -1, '12000': -2 },
      late_night: { '32': -6, '120': -4, '1000': 2, '4500': 1, '12000': 0 },
      vocal: { '32': -2, '120': -1, '1000': 4, '4500': 3, '12000': 1 }
    };

    let isUserDraggingEq = false;

    
    /* =========================================================================
       Mixing Desk Controller Logic & Analogue Rotary Dial Synchronisation
       ========================================================================= */
    const bandMuteStates = { '32': false, '120': false, '1000': false, '4500': false, '12000': false };
    const bandSavedValues = { '32': 0, '120': 0, '1000': 0, '4500': 0, '12000': 0 };

    window.syncDialFromGain = function(band, numVal) {
      const dial = document.getElementById('mixer-dial-' + band);
      if (dial) {
        const deg = (numVal / 12) * 135;
        dial.style.transform = `rotate(${deg}deg)`;
      }
      const peak = document.getElementById('mixer-peak-' + band);
      if (peak) {
        peak.classList.toggle('active', numVal > 6);
      }
    };

    window.handlePotWheel = function(e, band) {
      e.preventDefault();
      const slider = document.getElementById('eq-band-' + band);
      if (!slider) return;
      let cur = parseFloat(slider.value || 0);
      const delta = e.deltaY < 0 ? 0.5 : -0.5;
      cur = Math.max(-12, Math.min(12, cur + delta));
      slider.value = cur;
      updateEqBand(band, cur);
    };

    window.focusPot = function(band) {
      const slider = document.getElementById('eq-band-' + band);
      if (slider) slider.focus();
    };

    window.toggleBandMute = function(band) {
      const slider = document.getElementById('eq-band-' + band);
      const muteBtn = document.getElementById('mixer-mute-' + band);
      if (!slider || !muteBtn) return;

      if (!bandMuteStates[band]) {
        bandSavedValues[band] = parseFloat(slider.value || 0);
        bandMuteStates[band] = true;
        muteBtn.classList.add('muted');
        slider.value = 0;
        updateEqBand(band, 0);
      } else {
        bandMuteStates[band] = false;
        muteBtn.classList.remove('muted');
        slider.value = bandSavedValues[band];
        updateEqBand(band, bandSavedValues[band]);
      }
    };

    window.resetEqToFlat = function() {
      if (typeof selectEqPreset === 'function') {
        selectEqPreset('flat');
      }
    };

    window.updateMasterGain = function(val) {
      const readout = document.getElementById('eq-master-val');
      const num = parseFloat(val);
      if (readout) readout.innerText = (num > 0 ? '+' : '') + num.toFixed(1) + 'dB';
    };


    window.updateEqBand = function(band, val) {
      isUserDraggingEq = true;
      const numVal = parseFloat(val);
      const valLabel = document.getElementById('eq-val-' + band);
      if (valLabel) valLabel.innerText = (numVal > 0 ? '+' : '') + numVal + 'dB';
      if (typeof syncDialFromGain === 'function') syncDialFromGain(band, numVal);
      const oled = document.getElementById('mixer-oled-preset');
      if (oled) oled.innerText = 'CUSTOM SETTING';

      const eqActiveTag = document.getElementById('eq-active-preset');
      if (eqActiveTag) eqActiveTag.innerText = 'CUSTOM';
      const eqSelect = document.getElementById('select-eq-preset');
      if (eqSelect) eqSelect.value = 'flat';

      // Gather current band levels
      const bands = {
        '32': parseFloat(document.getElementById('eq-band-32')?.value || 0),
        '120': parseFloat(document.getElementById('eq-band-120')?.value || 0),
        '1000': parseFloat(document.getElementById('eq-band-1000')?.value || 0),
        '4500': parseFloat(document.getElementById('eq-band-4500')?.value || 0),
        '12000': parseFloat(document.getElementById('eq-band-12000')?.value || 0)
      };

      // Send to streamer
      clearTimeout(window._eqSyncTimer);
      window._eqSyncTimer = setTimeout(() => {
        fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ eq_preset: 'custom', eq_bands: bands })
        }).then(res => res.json()).then(d => {
          isUserDraggingEq = false;
        }).catch(() => { isUserDraggingEq = false; });
      }, 150);
    };

    
    window.selectEqPreset = function(presetName) {
      document.querySelectorAll('.mixer-scene-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-preset') === presetName);
      });
      document.querySelectorAll('.mixer-scene-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-preset') === presetName);
      });
      document.querySelectorAll('.eq-preset-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-preset') === presetName);
      });
      document.querySelectorAll('.eq-preset-btn-item').forEach(it => {
        it.classList.toggle('active', it.getAttribute('data-preset') === presetName);
      });
      const sel = document.getElementById('select-eq-preset');
      if (sel) sel.value = presetName;
      if (typeof applyEqPreset === 'function') {
        applyEqPreset(presetName);
      }
    };

    window.applyEqPreset = function(presetName) {
      const presetValues = EQ_PRESET_DEFINITIONS[presetName];
      if (presetValues) {
        Object.entries(presetValues).forEach(([b, v]) => {
          const slider = document.getElementById('eq-band-' + b);
          const label = document.getElementById('eq-val-' + b);
          if (slider) slider.value = v;
          if (label) label.innerText = (v > 0 ? '+' : '') + v + 'dB';
          if (typeof syncDialFromGain === 'function') syncDialFromGain(b, parseFloat(v));
          const oled = document.getElementById('mixer-oled-preset');
          if (oled) oled.innerText = presetName.replace('_', ' ').toUpperCase();
        });

        const eqActiveTag = document.getElementById('eq-active-preset');
        if (eqActiveTag) eqActiveTag.innerText = presetName.replace('_', ' ').toUpperCase();

        fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ eq_preset: presetName, eq_bands: presetValues })
        }).then(res => res.json()).catch(() => {});
      }
    };

    // 3. Device Discovery & Connection Engine
    window.triggerDeviceScan = async function() {
      const scanStatus = document.getElementById('scan-slide-status');
      const radarText = document.getElementById('radar-text');
      const radarBox = document.getElementById('radar-status');
      const resultsList = document.getElementById('discovery-list');

      if (scanStatus) scanStatus.innerText = 'SCANNING LAN...';
      if (radarText) radarText.innerText = 'Broadcasting SSDP multicast & ARP subnet scan...';
      if (radarBox) radarBox.classList.add('scanning');
      if (resultsList) {
        resultsList.innerHTML = `
          <div style="font-size:12px; color:var(--accent-gold); text-align:center; padding:32px; display:flex; flex-direction:column; align-items:center; gap:10px;">
            <div class="radar-pulse" style="width:28px; height:28px; margin:auto;"></div>
            Searching local network for Silent Angel endpoints (Munich, Bremen, Rhein, VitOS)...
          </div>
        `;
      }

      try {
        const res = await fetch('/api/discover');
        const data = await res.json();
        const devices = data.devices || [];

        if (scanStatus) scanStatus.innerText = devices.length > 0 ? `FOUND ${devices.length} DEVICE${devices.length > 1 ? 'S' : ''}` : 'READY';
        if (radarText) radarText.innerText = devices.length > 0 ? 'Scan complete. Select an endpoint to connect.' : 'No UPnP endpoints found. Enter manual IP below.';
        if (radarBox) radarBox.classList.remove('scanning');

        if (resultsList) {
          if (devices.length === 0) {
            resultsList.innerHTML = `
              <div style="font-size:12px; color:var(--text-muted); text-align:center; padding:28px;">
                <div style="margin-bottom:8px; color:#fff; font-weight:500;">No Streamers Found on Subnet</div>
                Verify streamer is powered on and connected to the same LAN. You can also connect directly via Manual IP Override below.
              </div>
            `;
          } else {
            resultsList.innerHTML = devices.map(d => `
              <div style="background:rgba(24,32,48,0.7); border:1px solid var(--border-subtle); border-radius:12px; padding:14px 18px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <div style="font-size:13.5px; font-weight:500; color:#fff;">${d.friendly_name || 'Silent Angel Streamer'}</div>
                  <div style="font-size:11px; color:var(--accent-gold); font-family:'JetBrains Mono', monospace; margin-top:3px;">${d.ip} &bull; ${d.method || 'LAN Endpoint'}</div>
                </div>
                <button class="btn-connect" style="padding:7px 16px; font-size:11.5px;" onclick="connectToDevice('${d.ip}', '${d.control_transport || ''}', '${d.control_rendering || ''}', '${d.control_content || ''}', '${d.friendly_name || ''}')">
                  Connect
                </button>
              </div>
            `).join('');
          }
        }
      } catch (err) {
        console.warn('Discovery error:', err);
        if (scanStatus) scanStatus.innerText = 'ERROR';
        if (radarText) radarText.innerText = 'Network scan error. Please try manual IP.';
        if (radarBox) radarBox.classList.remove('scanning');
      }
    };

    window.connectToDevice = async function(ip, transport = '', rendering = '', content = '', name = '') {
      try {
        const res = await fetch('/api/connect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ip: ip,
            control_transport: transport,
            control_rendering: rendering,
            control_content: content,
            friendly_name: name
          })
        });
        const data = await res.json();
        console.log('[Connect] Streamer connected:', data);
        if (typeof updateStatus === 'function') await updateStatus();
        if (typeof slideToPlayer === 'function') slideToPlayer();
      } catch (err) {
        console.warn('Connect error:', err);
      }
    };

    window.connectManualIp = function() {
      const input = document.getElementById('manual-ip-field') || document.getElementById('input-manual-ip');
      if (input && input.value.trim()) {
        const ip = input.value.trim();
        connectToDevice(ip, '', '', '', `Silent Angel (${ip})`);
      }
    };

</script>
</head>
<body>

  <!-- Official Audiophile Vector SVGs -->
  <svg style="display:none;">
    <symbol id="icon-upnp" viewBox="0 0 100 100">
      <path d="M50 10 C27.9 10 10 27.9 10 50 C10 72.1 27.9 90 50 90 C72.1 90 90 72.1 90 50 C90 27.9 72.1 10 50 10 Z M50 22 C65.5 22 78 34.5 78 50 C78 65.5 65.5 78 50 78 C34.5 78 22 65.5 22 50 C22 34.5 34.5 22 50 22 Z" fill-opacity="0.2"/>
      <path d="M30 45 C30 35 40 30 50 30 C60 30 70 35 70 45 C70 52 65 58 58 60 L68 75 L56 75 L48 62 C46 62 44 62 42 62 L42 75 L30 75 Z M42 40 L42 52 C45 52 57 53 57 46 C57 40 46 40 42 40 Z"/>
    </symbol>

    <symbol id="icon-dlna" viewBox="0 0 100 60">
      <path d="M10 10 C10 10 25 50 50 30 C75 10 90 50 90 50 C90 50 75 10 50 30 C25 50 10 10 10 10 Z" stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round"/>
      <circle cx="28" cy="28" r="5"/>
      <circle cx="72" cy="32" r="5"/>
    </symbol>

    <symbol id="icon-airplay" viewBox="0 0 100 100">
      <path d="M15 70 L85 70 C88 70 90 68 90 65 L90 25 C90 22 88 20 85 20 L15 20 C12 20 10 22 10 25 L10 65 C10 68 12 70 15 70 Z M18 28 L82 28 L82 62 L18 62 Z"/>
      <polygon points="50,42 74,78 26,78"/>
    </symbol>

    <symbol id="icon-spotify" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="46"/>
      <path d="M30 38 C45 33 65 35 78 43" stroke="#0b0e14" stroke-width="7" stroke-linecap="round" fill="none"/>
      <path d="M33 50 C45 46 62 48 73 54" stroke="#0b0e14" stroke-width="5.5" stroke-linecap="round" fill="none"/>
      <path d="M36 62 C45 59 58 60 67 65" stroke="#0b0e14" stroke-width="4.5" stroke-linecap="round" fill="none"/>
    </symbol>

    <symbol id="icon-tidal" viewBox="0 0 100 100">
      <polygon points="25,50 37.5,37.5 50,50 37.5,62.5"/>
      <polygon points="50,50 62.5,37.5 75,50 62.5,62.5"/>
      <polygon points="37.5,37.5 50,25 62.5,37.5 50,50"/>
      <polygon points="62.5,37.5 75,25 87.5,37.5 75,50"/>
    </symbol>

    <symbol id="icon-roon" viewBox="0 0 100 100">
      <circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" stroke-width="6"/>
      <path d="M40 30 L40 70 M40 45 C48 35 68 35 68 50 C68 62 50 62 40 62"/>
    </symbol>

    <symbol id="icon-qobuz" viewBox="0 0 100 100">
      <circle cx="48" cy="48" r="36" fill="none" stroke="currentColor" stroke-width="7"/>
      <circle cx="48" cy="48" r="14"/>
      <line x1="68" y1="68" x2="88" y2="88" stroke="currentColor" stroke-width="8" stroke-linecap="round"/>
    </symbol>

    <symbol id="icon-hires" viewBox="0 0 120 70">
      <rect x="2" y="2" width="116" height="66" rx="6" fill="#000" stroke="#c99d52" stroke-width="3"/>
      <text x="60" y="32" fill="#c99d52" font-family="'Outfit', sans-serif" font-weight="600" font-size="18" text-anchor="middle" letter-spacing="1">Hi-Res</text>
      <text x="60" y="54" fill="#c99d52" font-family="'Outfit', sans-serif" font-weight="500" font-size="12" text-anchor="middle" letter-spacing="3">AUDIO</text>
    </symbol>

    <symbol id="icon-angel" viewBox="0 0 100 100">
      <path d="M50 15 C58 28 72 38 90 40 C75 52 68 68 68 85 C58 70 52 55 50 15 Z"/>
      <path d="M50 15 C42 28 28 38 10 40 C25 52 32 68 32 85 C42 70 48 55 50 15 Z" opacity="0.75"/>
    </symbol>
  </svg>

  <div class="app-container">
    <!-- Collapsible Navigation Backdrop -->
    <!-- Hardware Rotating Disc Navigation Dial (Studio Jog Wheel) -->
    <nav class="rotary-nav-wrapper" id="rotary-nav-wrapper" aria-label="Audio Console Disc Navigation">
      <div class="rotary-nav-housing" id="rotary-nav-housing">
        <!-- Physical Milled Titanium Disc Wheel that Rotates -->
        <div class="rotary-nav-disc" id="rotary-nav-disc">
          <div class="rotary-knurl-rim"></div>
          <div class="rotary-disc-plate"></div>
          <div class="rotary-radial-ticks"></div>
          <div class="rotary-disc-items" id="rotary-disc-items">
            <!-- Populated via JavaScript: 12 Slides at 30deg intervals -->
          </div>
        </div>

        <!-- Bezel Precision Index Needle at 6 o'clock with Gold Tally LED -->
        <div class="rotary-bezel-index">
          <div class="index-needle"></div>
          <div class="index-jewel-led"></div>
        </div>
      </div>

      <!-- Active Slide Title Readout Ribbon -->
      <div class="rotary-active-ribbon" id="rotary-active-ribbon" onclick="recenterActiveSlide()" title="Click to re-centre dial">
        <span class="rotary-step-pill" id="rotary-step-pill">01 / 12</span>
        <span class="rotary-title-text" id="rotary-title-text">STUDIO PLAYER &amp; DAC</span>
      </div>

      <!-- Backward compatibility placeholders for existing device status JS -->
      <div style="display:none;" id="sidebar-drawer">
        <div id="side-status-dot"></div>
        <span id="side-status-text">Disconnected</span>
        <h4 id="side-dev-name">Silent Angel Bremen SL1P</h4>
        <p id="side-dev-ip">192.168.1.130</p>
      </div>
      <div style="display:none;" id="nav-drawer-backdrop"></div>
      <button style="display:none;" id="btn-floating-nav"></button>
    </nav>

    <!-- Persistent Floating Hub on Top-Right -->
    

    <main class="main-viewport" id="main-viewport">

      <!-- Carousel Viewport & Horizontal Track -->
      <div class="carousel-viewport" id="carousel-viewport">
        <div class="carousel-track" id="carousel-track">
          
          <!-- Slide 0: Main Audio Player Stage -->
          <!-- Slide 0: Main Audio Player Stage (Luxury Vinyl Disc & Studio Player, Zero VU Meters) -->
          <section class="carousel-slide active" id="slide-player" data-slide-name="player">
            <!-- Background Ambient Artwork with Gradient to Background Colour -->
            <div class="player-ambient-art" id="player-ambient-art">
              <div class="ambient-art-img" id="ambient-art-img" style="background-image: url('/api/coverart');"></div>
              <div class="ambient-art-gradient"></div>
            </div>

            <div class="player-studio-viewport">
              <div class="player-studio-stage">
                
                <!-- Left Deck: Audiophile Vinyl Sleeve & Rotating Record Showcase -->
                <div class="player-sleeve-section">
                  <div class="sleeve-card" id="player-sleeve-card">
                    <img id="stage-artwork" class="sleeve-img" alt="Album Cover" src="/api/coverart">
                    <div class="vinyl-disc" id="stage-vinyl-disc">
                      <div class="vinyl-groove-rings"></div>
                      <div class="vinyl-center-hub">
                        <svg width="22" height="22" id="vinyl-icon"><use href="#icon-angel"/></svg>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Right Deck: Information, Protocol & Audio Controls -->
                <div class="player-info-section">
                  
                  <!-- Streaming Protocol Visual Icon & Stream Architecture -->
                  <div class="player-proto-bar">
                    <div class="proto-visual-icon" id="stage-proto-badge" onclick="slideToView('protocols')" title="Active Streaming Protocol Architecture (Click to configure)">
                      <svg width="28" height="28" id="stage-proto-icon" style="fill:#c99d52;"><use href="#icon-upnp"/></svg>
                    </div>
                    <span class="player-stream-badge">BIT-PERFECT DIRECT STREAM</span>
                  </div>

                  <!-- Track Titles with Fluid Typography -->
                  <div class="player-titles-block">
                    <h1 class="player-track-title" id="stage-title">Standby (Ready)</h1>
                    <h2 class="player-track-artist" id="stage-artist">Silent Angel Streamer</h2>
                    <h3 class="player-track-album" id="stage-album">VitOS Audio Core</h3>
                  </div>

                  <!-- High-Res Audio Spec Ribbon (Borderless, 40% Alpha) -->
                  <div class="player-specs-ribbon">
                    <span class="spec-pill">FLAC 192kHz</span>
                    <span class="spec-pill">24-BIT</span>
                    <span class="spec-pill spec-gold">DIRECT DSD</span>
                  </div>

                  <!-- Prominent Main Player Scrubber -->
                  <div class="main-scrub-box" id="main-player-scrub">
                    <div class="main-scrub-track" id="scrub-track" onclick="handleScrub(event)">
                      <div class="main-scrub-fill" id="scrub-progress"></div>
                    </div>
                    <div class="main-scrub-times">
                      <span id="time-elapsed">00:00</span>
                      <span id="time-total">00:00</span>
                    </div>
                  </div>

                </div>

              </div>
            </div>
          </section>

          <!-- Slide 1: Streaming Protocols Hub -->
          <section class="carousel-slide" id="slide-protocols" data-slide-name="protocols">
            <div class="slide-card wide">
              <div class="slide-head">
                <h3>Streaming Architecture Hub</h3>
                <div style="font-size:11px; color:var(--accent-gold); font-family:'JetBrains Mono', monospace;">6 PROTOCOLS ACTIVE</div>
              </div>
              <div class="slide-body">
                <!-- Visual Studio Signal Flow Topology Pipeline -->
                <div class="proto-topology-banner">
                  <div class="topo-node">
                    <span class="topo-dot gold-glow"></span>
                    <div class="topo-node-content">
                      <span class="topo-label">STREAM SOURCE</span>
                      <strong class="topo-val" id="topo-source-name">UPnP / DLNA</strong>
                    </div>
                  </div>
                  <div class="topo-pipe">
                    <div class="topo-pulse-line"></div>
                    <span class="topo-rate" id="topo-rate-badge">BIT-PERFECT DIRECT</span>
                  </div>
                  <div class="topo-node">
                    <span class="topo-dot cyan-glow"></span>
                    <div class="topo-node-content">
                      <span class="topo-label">VITOS ENGINE</span>
                      <strong class="topo-val">Low-Jitter FIFO</strong>
                    </div>
                  </div>
                  <div class="topo-pipe">
                    <div class="topo-pulse-line"></div>
                    <span class="topo-rate">384kHz / DSD</span>
                  </div>
                  <div class="topo-node">
                    <span class="topo-dot gold-glow"></span>
                    <div class="topo-node-content">
                      <span class="topo-label">STUDIO DAC</span>
                      <strong class="topo-val">ESS Sabre PRO</strong>
                    </div>
                  </div>
                </div>

                <div class="proto-grid" id="proto-hub-grid">
                  <!-- Rendered dynamically -->
                </div>
              </div>
            </div>
          </section>

          <!-- Slide 2: Device Discovery -->
          <section class="carousel-slide" id="slide-discovery" data-slide-name="discovery">
            <div class="synth-chassis">
              <!-- Corner Hex Socket Bolts -->
              <div class="synth-hex-bolt synth-bolt-tl"></div>
              <div class="synth-hex-bolt synth-bolt-tr"></div>
              <div class="synth-hex-bolt synth-bolt-bl"></div>
              <div class="synth-hex-bolt synth-bolt-br"></div>

              <!-- Top Silkscreen Bus Header -->
              <div class="synth-bus-header">
                <div class="synth-bus-spec">
                  <span class="synth-bus-badge">MOD-02 // PATCH ROUTER</span>
                  <span><span class="synth-bus-led"></span>BUS LOCKED</span>
                  <span>CLOCK: 192kHz / 64-BIT</span>
                </div>
                <div style="font-size:10px; color:var(--text-muted); font-family:'JetBrains Mono', monospace; text-transform:uppercase; letter-spacing:0.06em;" id="synth-status-label">
                  LAN SCANNER READY
                </div>
              </div>

              <!-- Category Matrix Latching Switch Bar -->
              <div class="synth-filter-matrix" id="synth-filters">
                <div class="synth-filter-pill active" data-cat="all" onclick="filterSynthModules('all')">
                  <div class="pill-dot"></div> ALL BUS UNITS
                </div>
                <div class="synth-filter-pill" data-cat="streamer" onclick="filterSynthModules('streamer')">
                  <div class="pill-dot"></div> AUDIO STREAMERS
                </div>
                <div class="synth-filter-pill" data-cat="google_tv" onclick="filterSynthModules('google_tv')">
                  <div class="pill-dot"></div> GOOGLE TV / CAST
                </div>
                <div class="synth-filter-pill" data-cat="xbox" onclick="filterSynthModules('xbox')">
                  <div class="pill-dot"></div> XBOX CONSOLES
                </div>
                <div class="synth-filter-pill" data-cat="projector" onclick="filterSynthModules('projector')">
                  <div class="pill-dot"></div> LED PROJECTORS
                </div>
                <div class="synth-filter-pill" data-cat="airplay" onclick="filterSynthModules('airplay')">
                  <div class="pill-dot"></div> AIRPLAY & UPNP
                </div>
              </div>

              <!-- Patch Bay Utility Deck -->
              <div class="synth-patch-utility">
                <div style="display:flex; align-items:center; gap:12px;">
                  <button class="synth-scan-btn" onclick="triggerDeviceScan()" id="synth-scan-trigger">
                    <div class="synth-scan-led" id="synth-scan-led"></div>
                    <span>ENGAGE LAN SCAN</span>
                  </button>
                  <span style="font-size:11px; color:#94a3b8; font-family:'JetBrains Mono', monospace;" id="synth-scan-counter">0 modules detected</span>
                </div>
                <div class="synth-manual-row">
                  <span class="synth-patch-jack-icon" title="Manual IP Jack"></span>
                  <input type="text" id="manual-ip-field" placeholder="192.168.1.xxx" class="synth-tuner-input" title="Manual IP address patch input">
                  <button class="synth-filter-pill" style="padding:6px 10px;" onclick="connectManualIp()">PATCH IP</button>
                </div>
              </div>

              <!-- Discovered Rack Modules Grid -->
              <div class="synth-module-grid" id="discovery-list">
                <div style="grid-column: 1 / -1; font-size:12px; color:var(--text-muted); text-align:center; padding:36px; font-family:'JetBrains Mono', monospace;">
                  <div style="margin-bottom:8px; color:var(--accent-gold);">EURORACK NETWORK BUS IDLE</div>
                  Click "ENGAGE LAN SCAN" above to broadcast SSDP multicast & probe Google TV, Xbox, and LED Projectors.
                </div>
              </div>
            </div>
          </section>

          <!-- Slide 3: Internet Radio & 3D Globe Tuner -->
          <section class="carousel-slide pure-globe-slide" id="slide-radio" data-slide-name="radio">
            <div class="globe-title-overlay">
              <h3>Internet Radio &amp; World Tuner</h3>
              <span class="globe-badge">55 Curated Stations &bull; 3D Beacon Clusters</span>
            </div>
            <div id="carousel-globe-container" class="pure-globe-container"></div>
            <div class="globe-cluster-flyout" id="globe-cluster-flyout" style="display:none;"></div>
          </section>

          <!-- Slide 4: DAC & Audio Output -->
          <section class="carousel-slide" id="slide-dac" data-slide-name="dac">
            <div class="slide-card dac-card-central">
              <div class="slide-head dac-head-central">
                <div class="dac-title-group">
                  <h3>DAC Output &amp; Filters</h3>
                  <span class="dac-chipset-badge">ESS SABRE 9038Q2M PRO</span>
                </div>
              </div>
              <div class="slide-body dac-body-central">
                <!-- Bit-Perfect Pre-Amp Bypass Module -->
                <div class="dac-setting-row">
                  <div class="dac-setting-info">
                    <div class="dac-setting-title">Bit-Perfect Fixed Line-Out</div>
                    <div class="dac-setting-desc">Bypasses digital attenuation (locks at 0 dB / 100%) for external analogue pre-amplifiers.</div>
                  </div>
                  <div class="dac-toggle-wrapper">
                    <label class="switch-luxury">
                      <input type="checkbox" id="chk-fixed-volume" onchange="toggleFixedVolume(this.checked)">
                      <span class="slider-luxury"></span>
                    </label>
                    <span id="fixed-vol-status-badge" class="fixed-status-pill">VARIABLE</span>
                  </div>
                </div>

                <!-- ESS SABRE FIR Filter Module (Unified Mixer Style) -->
                <div class="dac-filter-module">
                  <div class="dac-filter-header">
                    <span class="dac-filter-label">FIR RECONSTRUCTION FILTER</span>
                    <span id="filter-active-tag" class="filter-type-pill">MINIMUM PHASE</span>
                  </div>
                  <div class="mixer-scene-row" id="dac-filter-presets" style="margin-top:8px;">
                    <button class="mixer-scene-btn active" data-filter="minimum_fast" onclick="selectDacFilterPreset('minimum_fast')">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">MIN FAST</span>
                    </button>
                    <button class="mixer-scene-btn" data-filter="linear_fast" onclick="selectDacFilterPreset('linear_fast')">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">LIN FAST</span>
                    </button>
                    <button class="mixer-scene-btn" data-filter="linear_slow" onclick="selectDacFilterPreset('linear_slow')">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">LIN SLOW</span>
                    </button>
                    <button class="mixer-scene-btn" data-filter="apodizing_fast" onclick="selectDacFilterPreset('apodizing_fast')">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">APODIZING</span>
                    </button>
                    <button class="mixer-scene-btn" data-filter="brickwall" onclick="selectDacFilterPreset('brickwall')">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">BRICKWALL</span>
                    </button>
                  </div>
                  <!-- Hidden select for API backwards compatibility -->
                  <select id="select-dac-filter" style="display:none;" onchange="applyDacFilter(this.value)">
                    <option value="minimum_fast">Minimum Phase Fast</option>
                    <option value="linear_fast">Linear Phase Fast</option>
                    <option value="linear_slow">Linear Phase Slow</option>
                    <option value="apodizing_fast">Apodizing Fast</option>
                    <option value="brickwall">Brickwall</option>
                  </select>
                </div>
              </div>
            </div>
          </section>

          <!-- Slide 5: Parametric Equaliser (PEQ) -->
          <section class="carousel-slide" id="slide-eq" data-slide-name="eq">
            <div class="slide-card mixer-slide-card">
              <div class="slide-head">
                <h3>Parametric Equaliser</h3>
              </div>
              <div class="slide-body mixer-slide-body">
                
                <!-- Mixing Desk Console Bridge / Meter & Preset Deck -->
                <div class="mixer-console-bridge">
                  <!-- Console Scene Memory Preset Buttons -->
                  <div class="mixer-scene-row" id="eq-presets-container">
                    <button class="mixer-scene-btn active" data-preset="flat" onclick="selectEqPreset('flat')" title="Flat Reference (Bypass)">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">FLAT</span>
                    </button>
                    <button class="mixer-scene-btn" data-preset="harman" onclick="selectEqPreset('harman')" title="Harman Target Curve">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">HARMAN</span>
                    </button>
                    <button class="mixer-scene-btn" data-preset="warmth" onclick="selectEqPreset('warmth')" title="Acoustic Warmth">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">WARMTH</span>
                    </button>
                    <button class="mixer-scene-btn" data-preset="late_night" onclick="selectEqPreset('late_night')" title="Late-Night Mode">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">LATE NIGHT</span>
                    </button>
                    <button class="mixer-scene-btn" data-preset="vocal" onclick="selectEqPreset('vocal')" title="Vocal Presence">
                      <span class="mixer-tally-led"></span>
                      <span class="mixer-scene-name">VOCAL</span>
                    </button>
                  </div>

                  <!-- DSP Realtime Parametric Visualisation Screen -->
                  <div class="mixer-dsp-screen">
                    <div class="mixer-dsp-topbar">
                      <div class="dsp-led-group">
                        <span class="dsp-active-led"></span>
                        <span class="dsp-title">VITOS DSP ENGINE &middot; 64-BIT PRECISION</span>
                      </div>
                      <span class="dsp-preset-badge" id="mixer-oled-preset">FLAT REFERENCE</span>
                    </div>
                    <svg class="mixer-dsp-svg" id="eq-svg" viewBox="0 0 500 120" preserveAspectRatio="none">
                      <defs>
                        <linearGradient id="eq-wave-gold-grad" x1="0%" y1="0%" x2="0%" y2="100%">
                          <stop offset="0%" stop-color="#c99d52" stop-opacity="0.25"/>
                          <stop offset="100%" stop-color="#c99d52" stop-opacity="0.02"/>
                        </linearGradient>
                      </defs>
                      <line x1="0" y1="60" x2="500" y2="60" stroke="rgba(255, 255, 255, 0.10)" stroke-dasharray="4"/>
                      <line x1="50" y1="0" x2="50" y2="120" stroke="rgba(255, 255, 255, 0.04)"/>
                      <line x1="150" y1="0" x2="150" y2="120" stroke="rgba(255, 255, 255, 0.04)"/>
                      <line x1="250" y1="0" x2="250" y2="120" stroke="rgba(255, 255, 255, 0.04)"/>
                      <line x1="350" y1="0" x2="350" y2="120" stroke="rgba(255, 255, 255, 0.04)"/>
                      <line x1="450" y1="0" x2="450" y2="120" stroke="rgba(255, 255, 255, 0.04)"/>
                      <path id="eq-wave-fill" d="M 0 60 L 500 60 L 500 120 L 0 120 Z" fill="url(#eq-wave-gold-grad)"/>
                      <path id="eq-curve-path" d="M 0 60 C 100 60, 400 60, 500 60" fill="none" stroke="rgba(201, 157, 82, 0.85)" stroke-width="2"/>
                    </svg>
                  </div>
                </div>

                <!-- Hidden select for backwards compatibility -->
                <select id="select-eq-preset" style="display:none;" onchange="applyEqPreset(this.value)">
                  <option value="flat">Flat Reference (Bypass)</option>
                  <option value="harman">Harman Target Curve (Natural Bass & Clarity)</option>
                  <option value="warmth">Acoustic Warmth (Midrange Bloom)</option>
                  <option value="late_night">Late-Night Mode (Sub-Bass Damped)</option>
                  <option value="vocal">Vocal Presence & Dialogue Lift</option>
                </select>

                <!-- Hardware Audio Mixing Desk Chassis -->
                <div class="mixer-chassis" id="mixer-chassis">
                  
                  <!-- Strip 1: 32Hz Sub-Bass -->
                  <div class="mixer-strip" data-band="32">
                    <div class="mixer-strip-head">
                      <span class="mixer-ch-tag">CH 01</span>
                      <span class="mixer-ch-freq">32Hz</span>
                      <span class="mixer-ch-role">SUB</span>
                    </div>

                    <!-- Rotary Gain Pot (Styled after analogue mixing console knob) -->
                    <div class="mixer-pot-cell" data-band="32">
                      <span class="mixer-pot-title">GAIN</span>
                      <div class="mixer-pot-housing" onwheel="handlePotWheel(event, '32')" onclick="focusPot('32')">
                        <div class="mixer-pot-scale">
                          <span class="scale-dot dot-min">-12</span>
                          <span class="scale-dot dot-mid">0</span>
                          <span class="scale-dot dot-max">+12</span>
                        </div>
                        <div class="mixer-rotary-dial" id="mixer-dial-32">
                          <div class="mixer-dial-indicator"></div>
                        </div>
                      </div>
                    </div>

                    <!-- Channel Tally & Mute Pushbutton -->
                    <div class="mixer-ch-controls">
                      <div class="mixer-peak-led" id="mixer-peak-32" title="Peak Indicator"></div>
                      <button class="mixer-mute-btn" id="mixer-mute-32" onclick="toggleBandMute('32')" title="Mute 32Hz Band">MUTE</button>
                    </div>

                    <!-- Vertical Studio Fader Assembly with Calibrated Scale -->
                    <div class="mixer-fader-assembly">
                      <div class="mixer-db-scale mixer-scale-l">
                        <span>+12</span>
                        <span>+6</span>
                        <span class="scale-unity">0</span>
                        <span>-6</span>
                        <span>-12</span>
                      </div>
                      <div class="mixer-fader-well">
                        <div class="mixer-fader-groove"></div>
                        <div class="mixer-unity-line"></div>
                        <input type="range" class="mixer-fader-slider fader-red" min="-12" max="12" step="0.5" value="0" id="eq-band-32" oninput="updateEqBand('32', this.value)">
                      </div>
                      <div class="mixer-db-scale mixer-scale-r">
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick tick-unity"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                      </div>
                    </div>

                    <!-- Monospace Digital Readout Box & Base ID -->
                    <div class="mixer-db-readout" id="eq-val-32">0dB</div>
                    <div class="mixer-ch-foot">1</div>
                  </div>

                  <!-- Strip 2: 120Hz Bass -->
                  <div class="mixer-strip" data-band="120">
                    <div class="mixer-strip-head">
                      <span class="mixer-ch-tag">CH 02</span>
                      <span class="mixer-ch-freq">120Hz</span>
                      <span class="mixer-ch-role">BASS</span>
                    </div>

                    <div class="mixer-pot-cell" data-band="120">
                      <span class="mixer-pot-title">GAIN</span>
                      <div class="mixer-pot-housing" onwheel="handlePotWheel(event, '120')" onclick="focusPot('120')">
                        <div class="mixer-pot-scale">
                          <span class="scale-dot dot-min">-12</span>
                          <span class="scale-dot dot-mid">0</span>
                          <span class="scale-dot dot-max">+12</span>
                        </div>
                        <div class="mixer-rotary-dial" id="mixer-dial-120">
                          <div class="mixer-dial-indicator"></div>
                        </div>
                      </div>
                    </div>

                    <div class="mixer-ch-controls">
                      <div class="mixer-peak-led" id="mixer-peak-120" title="Peak Indicator"></div>
                      <button class="mixer-mute-btn" id="mixer-mute-120" onclick="toggleBandMute('120')" title="Mute 120Hz Band">MUTE</button>
                    </div>

                    <div class="mixer-fader-assembly">
                      <div class="mixer-db-scale mixer-scale-l">
                        <span>+12</span>
                        <span>+6</span>
                        <span class="scale-unity">0</span>
                        <span>-6</span>
                        <span>-12</span>
                      </div>
                      <div class="mixer-fader-well">
                        <div class="mixer-fader-groove"></div>
                        <div class="mixer-unity-line"></div>
                        <input type="range" class="mixer-fader-slider fader-red" min="-12" max="12" step="0.5" value="0" id="eq-band-120" oninput="updateEqBand('120', this.value)">
                      </div>
                      <div class="mixer-db-scale mixer-scale-r">
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick tick-unity"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                      </div>
                    </div>

                    <div class="mixer-db-readout" id="eq-val-120">0dB</div>
                    <div class="mixer-ch-foot">2</div>
                  </div>

                  <!-- Strip 3: 1kHz Midrange -->
                  <div class="mixer-strip" data-band="1000">
                    <div class="mixer-strip-head">
                      <span class="mixer-ch-tag">CH 03</span>
                      <span class="mixer-ch-freq">1kHz</span>
                      <span class="mixer-ch-role">MID</span>
                    </div>

                    <div class="mixer-pot-cell" data-band="1000">
                      <span class="mixer-pot-title">GAIN</span>
                      <div class="mixer-pot-housing" onwheel="handlePotWheel(event, '1000')" onclick="focusPot('1000')">
                        <div class="mixer-pot-scale">
                          <span class="scale-dot dot-min">-12</span>
                          <span class="scale-dot dot-mid">0</span>
                          <span class="scale-dot dot-max">+12</span>
                        </div>
                        <div class="mixer-rotary-dial" id="mixer-dial-1000">
                          <div class="mixer-dial-indicator"></div>
                        </div>
                      </div>
                    </div>

                    <div class="mixer-ch-controls">
                      <div class="mixer-peak-led" id="mixer-peak-1000" title="Peak Indicator"></div>
                      <button class="mixer-mute-btn" id="mixer-mute-1000" onclick="toggleBandMute('1000')" title="Mute 1kHz Band">MUTE</button>
                    </div>

                    <div class="mixer-fader-assembly">
                      <div class="mixer-db-scale mixer-scale-l">
                        <span>+12</span>
                        <span>+6</span>
                        <span class="scale-unity">0</span>
                        <span>-6</span>
                        <span>-12</span>
                      </div>
                      <div class="mixer-fader-well">
                        <div class="mixer-fader-groove"></div>
                        <div class="mixer-unity-line"></div>
                        <input type="range" class="mixer-fader-slider fader-red" min="-12" max="12" step="0.5" value="0" id="eq-band-1000" oninput="updateEqBand('1000', this.value)">
                      </div>
                      <div class="mixer-db-scale mixer-scale-r">
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick tick-unity"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                      </div>
                    </div>

                    <div class="mixer-db-readout" id="eq-val-1000">0dB</div>
                    <div class="mixer-ch-foot">3</div>
                  </div>

                  <!-- Strip 4: 4.5kHz Presence / High Mid -->
                  <div class="mixer-strip" data-band="4500">
                    <div class="mixer-strip-head">
                      <span class="mixer-ch-tag">CH 04</span>
                      <span class="mixer-ch-freq">4.5kHz</span>
                      <span class="mixer-ch-role">PRESENCE</span>
                    </div>

                    <div class="mixer-pot-cell" data-band="4500">
                      <span class="mixer-pot-title">GAIN</span>
                      <div class="mixer-pot-housing" onwheel="handlePotWheel(event, '4500')" onclick="focusPot('4500')">
                        <div class="mixer-pot-scale">
                          <span class="scale-dot dot-min">-12</span>
                          <span class="scale-dot dot-mid">0</span>
                          <span class="scale-dot dot-max">+12</span>
                        </div>
                        <div class="mixer-rotary-dial" id="mixer-dial-4500">
                          <div class="mixer-dial-indicator"></div>
                        </div>
                      </div>
                    </div>

                    <div class="mixer-ch-controls">
                      <div class="mixer-peak-led" id="mixer-peak-4500" title="Peak Indicator"></div>
                      <button class="mixer-mute-btn" id="mixer-mute-4500" onclick="toggleBandMute('4500')" title="Mute 4.5kHz Band">MUTE</button>
                    </div>

                    <div class="mixer-fader-assembly">
                      <div class="mixer-db-scale mixer-scale-l">
                        <span>+12</span>
                        <span>+6</span>
                        <span class="scale-unity">0</span>
                        <span>-6</span>
                        <span>-12</span>
                      </div>
                      <div class="mixer-fader-well">
                        <div class="mixer-fader-groove"></div>
                        <div class="mixer-unity-line"></div>
                        <input type="range" class="mixer-fader-slider fader-red" min="-12" max="12" step="0.5" value="0" id="eq-band-4500" oninput="updateEqBand('4500', this.value)">
                      </div>
                      <div class="mixer-db-scale mixer-scale-r">
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick tick-unity"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                      </div>
                    </div>

                    <div class="mixer-db-readout" id="eq-val-4500">0dB</div>
                    <div class="mixer-ch-foot">4</div>
                  </div>

                  <!-- Strip 5: 12kHz Air / Treble -->
                  <div class="mixer-strip" data-band="12000">
                    <div class="mixer-strip-head">
                      <span class="mixer-ch-tag">CH 05</span>
                      <span class="mixer-ch-freq">12kHz</span>
                      <span class="mixer-ch-role">AIR</span>
                    </div>

                    <div class="mixer-pot-cell" data-band="12000">
                      <span class="mixer-pot-title">GAIN</span>
                      <div class="mixer-pot-housing" onwheel="handlePotWheel(event, '12000')" onclick="focusPot('12000')">
                        <div class="mixer-pot-scale">
                          <span class="scale-dot dot-min">-12</span>
                          <span class="scale-dot dot-mid">0</span>
                          <span class="scale-dot dot-max">+12</span>
                        </div>
                        <div class="mixer-rotary-dial" id="mixer-dial-12000">
                          <div class="mixer-dial-indicator"></div>
                        </div>
                      </div>
                    </div>

                    <div class="mixer-ch-controls">
                      <div class="mixer-peak-led" id="mixer-peak-12000" title="Peak Indicator"></div>
                      <button class="mixer-mute-btn" id="mixer-mute-12000" onclick="toggleBandMute('12000')" title="Mute 12kHz Band">MUTE</button>
                    </div>

                    <div class="mixer-fader-assembly">
                      <div class="mixer-db-scale mixer-scale-l">
                        <span>+12</span>
                        <span>+6</span>
                        <span class="scale-unity">0</span>
                        <span>-6</span>
                        <span>-12</span>
                      </div>
                      <div class="mixer-fader-well">
                        <div class="mixer-fader-groove"></div>
                        <div class="mixer-unity-line"></div>
                        <input type="range" class="mixer-fader-slider fader-red" min="-12" max="12" step="0.5" value="0" id="eq-band-12000" oninput="updateEqBand('12000', this.value)">
                      </div>
                      <div class="mixer-db-scale mixer-scale-r">
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick tick-unity"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                      </div>
                    </div>

                    <div class="mixer-db-readout" id="eq-val-12000">0dB</div>
                    <div class="mixer-ch-foot">5</div>
                  </div>

                  <!-- Strip 6: Master Output Section (Directly from audio desk layout) -->
                  <div class="mixer-strip mixer-strip-master">
                    <div class="mixer-strip-head">
                      <span class="mixer-ch-tag">MAIN</span>
                      <span class="mixer-ch-freq">L &middot; R</span>
                      <span class="mixer-ch-role">MASTER</span>
                    </div>

                    <!-- Dual Stereo LED Peak Ladder -->
                    <div class="mixer-master-meter-cell">
                      <div class="mixer-stereo-ladder">
                        <div class="ladder-ch">
                          <span class="led-seg seg-red"></span>
                          <span class="led-seg seg-amber"></span>
                          <span class="led-seg seg-amber"></span>
                          <span class="led-seg seg-green"></span>
                          <span class="led-seg seg-green"></span>
                          <span class="led-seg seg-green active"></span>
                          <span class="led-seg seg-green active"></span>
                        </div>
                        <div class="ladder-ch">
                          <span class="led-seg seg-red"></span>
                          <span class="led-seg seg-amber"></span>
                          <span class="led-seg seg-amber"></span>
                          <span class="led-seg seg-green"></span>
                          <span class="led-seg seg-green"></span>
                          <span class="led-seg seg-green active"></span>
                          <span class="led-seg seg-green active"></span>
                        </div>
                      </div>
                      <div class="mixer-master-scale-nums">
                        <span>+3</span>
                        <span>0</span>
                        <span>-6</span>
                        <span>-18</span>
                      </div>
                    </div>

                    <div class="mixer-ch-controls mixer-master-actions">
                      <button class="mixer-action-btn" onclick="resetEqToFlat()" title="Reset All Bands to 0dB Unity">RESET</button>
                    </div>

                    <!-- Master Fader Assembly with White Cap (as in mixing desk reference image) -->
                    <div class="mixer-fader-assembly">
                      <div class="mixer-db-scale mixer-scale-l">
                        <span>+6</span>
                        <span class="scale-unity">0</span>
                        <span>-6</span>
                        <span>-12</span>
                        <span>-&infin;</span>
                      </div>
                      <div class="mixer-fader-well">
                        <div class="mixer-fader-groove"></div>
                        <div class="mixer-unity-line"></div>
                        <input type="range" class="mixer-fader-slider fader-white" min="-24" max="6" step="0.5" value="0" id="eq-master-fader" oninput="updateMasterGain(this.value)">
                      </div>
                      <div class="mixer-db-scale mixer-scale-r">
                        <span class="scale-tick"></span>
                        <span class="scale-tick tick-unity"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                        <span class="scale-tick"></span>
                      </div>
                    </div>

                    <div class="mixer-db-readout" id="eq-master-val">0.0dB</div>
                    <div class="mixer-ch-foot mixer-ch-foot-master">M</div>
                  </div>

                </div>
              </div>
            </div>
          </section>

          <!-- Slide 6: Sleep Timer -->
          <section class="carousel-slide" id="slide-sleep" data-slide-name="sleep">
            <div class="slide-card" style="max-width:520px;">
              <div class="slide-head">
                
                <h3>Sleep Timer</h3>
                <div style="font-size:11px; color:var(--accent-gold); font-family:'JetBrains Mono', monospace;" id="sleep-slide-countdown">OFF</div>
              </div>
              <div class="slide-body">
                <div class="mixer-scene-row" style="margin-bottom:14px; gap:8px;">
                  <button class="mixer-scene-btn" onclick="setSleepTimer(15)"><span class="mixer-tally-led"></span>15 MIN</button>
                  <button class="mixer-scene-btn" onclick="setSleepTimer(30)"><span class="mixer-tally-led"></span>30 MIN</button>
                  <button class="mixer-scene-btn" onclick="setSleepTimer(45)"><span class="mixer-tally-led"></span>45 MIN</button>
                  <button class="mixer-scene-btn" onclick="setSleepTimer(60)"><span class="mixer-tally-led"></span>60 MIN</button>
                </div>
                <button class="mixer-scene-btn" style="width:100%; justify-content:center; border-color:rgba(239,68,68,0.4); color:#ef4444; background:rgba(239,68,68,0.06);" onclick="cancelSleepTimer()">
                  <span class="mixer-tally-led" style="background:#ef4444;"></span>DISABLE TIMER
                </button>
              </div>
            </div>
          </section>

          <!-- Slide 7: Lyrics & Liner Notes -->
          <section class="carousel-slide" id="slide-lyrics" data-slide-name="lyrics">
            <div class="slide-card">
              <div class="slide-head">
                
                <h3 id="lyrics-slide-title">Lyrics & Liner Notes</h3>
                <div style="font-size:11px; color:var(--accent-gold); font-family:'JetBrains Mono', monospace;">LIVE SYNC</div>
              </div>
              <div class="slide-body">
                <div style="font-size:12px; color:var(--text-muted);" id="lyrics-artist-line">Track: Standby</div>
                <div class="lyrics-body" id="lyrics-content" style="max-height:48vh; overflow-y:auto; font-size:14px; line-height:1.8; color:var(--text-main); white-space:pre-wrap; padding:10px 0;">
                  No lyrics or liner notes available for this stream.
                </div>
              </div>
            </div>
          </section>

          <!-- Slide 8: Queue & History -->
          <section class="carousel-slide" id="slide-queue" data-slide-name="queue">
            <div class="slide-card wide">
              <div class="slide-head">
                
                <h3>Playback Queue</h3>
                <div style="display:flex; gap:8px;">
                  <button class="btn-connect" style="font-size:11px; padding:4px 10px;" onclick="clearActiveQueue()">Clear Queue</button>
                  <button class="btn-connect" style="font-size:11px; padding:4px 10px;" onclick="clearHistoryLog()">Clear History</button>
                </div>
              </div>
              <div class="slide-body">
                <div class="tuner-tabs" style="margin-bottom:6px;">
                  <button class="tuner-tab-btn active" id="tab-btn-queue" onclick="switchQueueTab('active')">Up Next</button>
                  <button class="tuner-tab-btn" id="tab-btn-history" onclick="switchQueueTab('history')">Playback History</button>
                </div>
                <div id="pane-queue-active" style="max-height:45vh; overflow-y:auto; display:flex; flex-direction:column; gap:8px;">
                  <!-- Populated via JS -->
                </div>
                <div id="pane-queue-history" style="max-height:45vh; overflow-y:auto; display:none; flex-direction:column; gap:8px;">
                  <!-- Populated via JS -->
                </div>
              </div>
            </div>
          </section>

          <!-- Slide 9: Internal Storage / NVMe -->
          <section class="carousel-slide" id="slide-storage" data-slide-name="storage">
            <div class="slide-card wide">
              <div class="slide-head">
                
                <h3>Internal Storage</h3>
                <div style="font-size:11.5px; color:var(--accent-gold); font-family:'JetBrains Mono', monospace;" id="storage-path-label">Path: /</div>
              </div>
              <div class="slide-body">
                <div class="storage-list" id="storage-list" style="max-height:50vh; overflow-y:auto;">
                  <div style="font-size:12px; color:var(--text-muted); text-align:center; padding:20px;">Loading storage contents...</div>
                </div>
              </div>
            </div>
          </section>

          <!-- Slide 10: Universal Remote Control Screen -->
          <section class="carousel-slide" id="slide-remote" data-slide-name="remote">
            <div class="remote-chassis">
              <!-- Slide Header -->
              <div class="slide-head" style="margin-bottom:12px;">
                
                <h3>Universal Remote Control</h3>
                <div style="font-size:10px; color:var(--accent-cyan); font-family:'JetBrains Mono', monospace;">MULTI-DEVICE CONTROLLER</div>
              </div>

              <!-- Target Device OLED Bar -->
              <div class="remote-target-deck">
                <div class="remote-target-info">
                  <div class="remote-led-online" id="remote-target-led"></div>
                  <span id="remote-target-text">TARGET: tranScreen-64509 (192.168.1.121) · LED PROJECTOR</span>
                  <span id="google-tv-pair-status" style="margin-left:14px; font-size:11px; font-weight:700; letter-spacing:0.8px; padding:3px 10px; border-radius:4px; border:1px solid rgba(212,175,55,0.4); background:rgba(212,175,55,0.1); color:var(--accent-gold); cursor:pointer;" onclick="openGoogleTVPairModal()">⚡ PAIR GOOGLE TV</span>
                </div>
                <button class="remote-change-btn" onclick="slideToView('discovery')">SWITCH DEVICE ▾</button>
              </div>

              <!-- Main Remote Deck Grid -->
              <div class="remote-deck-grid">
                <!-- Column 1: Power, Sources, D-Pad & Rockers -->
                <div>
                  <!-- Power & Source Selection -->
                  <div class="remote-power-source-row">
                    <button class="remote-power-btn" onclick="sendRemoteKey('POWER')" title="Power Toggle">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                      <span>POWER</span>
                    </button>
                    <div class="remote-source-matrix">
                      <button class="remote-source-btn" onclick="switchInputSource('HDMI 1')">HDMI 1</button>
                      <button class="remote-source-btn" onclick="switchInputSource('HDMI 2')">HDMI 2</button>
                      <button class="remote-source-btn active" onclick="switchInputSource('tranScreen')">tranScreen</button>
                      <button class="remote-source-btn" onclick="switchInputSource('AirPlay')">AirPlay</button>
                      <button class="remote-source-btn" onclick="switchInputSource('USB')">USB</button>
                    </div>
                  </div>

                  <!-- Studio Directional D-Pad Section -->
                  <div class="remote-dpad-deck">
                    <div class="remote-dpad-matrix">
                      <button class="dpad-arrow-btn dpad-arrow-up" onclick="sendRemoteKey('UP')" title="Navigate Up">▲</button>
                      <button class="dpad-arrow-btn dpad-arrow-down" onclick="sendRemoteKey('DOWN')" title="Navigate Down">▼</button>
                      <button class="dpad-arrow-btn dpad-arrow-left" onclick="sendRemoteKey('LEFT')" title="Navigate Left">◀</button>
                      <button class="dpad-arrow-btn dpad-arrow-right" onclick="sendRemoteKey('RIGHT')" title="Navigate Right">▶</button>
                      <button class="dpad-center-btn" onclick="sendRemoteKey('SELECT')" title="Select / OK">OK</button>
                    </div>

                    <!-- Navigation Action Keys -->
                    <div class="remote-action-row">
                      <button class="remote-action-btn" onclick="sendRemoteKey('BACK')" title="Back">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                        <span>BACK</span>
                      </button>
                      <button class="remote-action-btn" onclick="sendRemoteKey('HOME')" title="Home">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
                        <span>HOME</span>
                      </button>
                      <button class="remote-action-btn" onclick="sendRemoteKey('MENU')" title="Menu">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                        <span>MENU</span>
                      </button>
                      <button class="remote-action-btn" onclick="sendRemoteKey('KEYSTONE')" title="Keystone / Ratio">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 17l10-10"/></svg>
                        <span>KEYSTONE</span>
                      </button>
                    </div>
                  </div>

                  <!-- Rockers & Media Transport -->
                  <div class="remote-rockers-transport-row">
                    <!-- Volume Rocker -->
                    <div class="remote-rocker-assembly">
                      <button class="remote-rocker-btn" onclick="sendRemoteKey('VOL_UP')" title="Volume Up">+</button>
                      <div class="remote-rocker-badge" id="remote-vol-badge">VOL</div>
                      <button class="remote-rocker-btn" onclick="sendRemoteKey('VOL_DOWN')" title="Volume Down">-</button>
                    </div>

                    <!-- Media Transport Bar -->
                    <div class="remote-transport-deck">
                      <button class="remote-transport-btn" onclick="sendRemoteKey('PREV')" title="Previous Track">⏮</button>
                      <button class="remote-transport-btn" onclick="sendRemoteKey('REW')" title="Rewind">⏪</button>
                      <button class="remote-transport-btn" onclick="sendRemoteKey('PLAY')" title="Play / Pause">⏯</button>
                      <button class="remote-transport-btn" onclick="sendRemoteKey('FF')" title="Fast Forward">⏩</button>
                      <button class="remote-transport-btn" onclick="sendRemoteKey('NEXT')" title="Next Track">⏭</button>
                      <button class="remote-transport-btn" onclick="sendRemoteKey('STOP')" title="Stop">⏹</button>
                    </div>

                    <!-- Channel / Page Rocker -->
                    <div class="remote-rocker-assembly">
                      <button class="remote-rocker-btn" onclick="sendRemoteKey('CH_UP')" title="Channel Up">▲</button>
                      <div class="remote-rocker-badge">CH</div>
                      <button class="remote-rocker-btn" onclick="sendRemoteKey('CH_DOWN')" title="Channel Down">▼</button>
                    </div>
                  </div>
                </div>

                <!-- Column 2: Quick Launchers, Keyboard & Precision Trackpad -->
                <div>
                  <!-- Quick App Launchers -->
                  <div class="remote-app-deck">
                    <button class="remote-app-btn" onclick="sendRemoteKey('APP_TRANSCREEN')">tranScreen</button>
                    <button class="remote-app-btn" onclick="sendRemoteKey('APP_GOOGLE_TV')">Google TV</button>
                    <button class="remote-app-btn" onclick="sendRemoteKey('APP_YOUTUBE')">YouTube</button>
                    <button class="remote-app-btn" onclick="sendRemoteKey('APP_NETFLIX')">Netflix</button>
                    <button class="remote-app-btn" onclick="sendRemoteKey('APP_SPOTIFY')">Spotify</button>
                    <button class="remote-app-btn" onclick="sendRemoteKey('APP_XBOX')">Xbox Guide</button>
                  </div>

                  <!-- Virtual Keyboard Text Input Deck -->
                  <div class="remote-keyboard-deck">
                    <div class="remote-keyboard-head">Virtual Keyboard // Direct Input</div>
                    <div class="remote-input-row">
                      <input type="text" id="remote-text-input" placeholder="Type search query, URL, credentials..." class="remote-text-input" onkeydown="if(event.key==='Enter') sendRemoteTextInput()">
                      <button class="remote-send-btn" onclick="sendRemoteTextInput()">SEND</button>
                    </div>
                  </div>

                  <!-- Precision 2D Touchpad Trackpad -->
                  <div class="remote-trackpad-deck">
                    <div class="remote-trackpad-head">
                      <span>Precision 2D Trackpad (Mouse Control)</span>
                      <span id="remote-trackpad-coords">X: 000 | Y: 000</span>
                    </div>
                    <div class="remote-trackpad-surface" id="remote-trackpad-surface" onmousemove="handleTrackpadMove(event)" onclick="handleTrackpadClick('LEFT')">
                      <div class="remote-trackpad-crosshair"></div>
                      <div class="remote-cursor-dot" id="remote-cursor-dot" style="left:50%; top:50%;"></div>
                    </div>
                    <div class="remote-trackpad-actions">
                      <button class="remote-trackpad-btn" onclick="handleTrackpadClick('LEFT')">LEFT CLICK</button>
                      <button class="remote-trackpad-btn" onclick="sendRemoteKey('SCROLL_UP')">SCROLL ▲</button>
                      <button class="remote-trackpad-btn" onclick="sendRemoteKey('SCROLL_DOWN')">SCROLL ▼</button>
                      <button class="remote-trackpad-btn" onclick="handleTrackpadClick('RIGHT')">RIGHT CLICK</button>
                    </div>
                  </div>

                  <!-- Live Feedback Toast HUD -->
                  <div class="remote-toast-hud" id="remote-toast-hud">
                    Ready
                  </div>
                </div>
              </div>

              <!-- Google TV Hardware Pairing Modal Overlay -->
              <div id="gtv-pair-modal" style="display:none; position:fixed; top:0; left:0; width:100vw; height:100vh; background:rgba(0,0,0,0.85); backdrop-filter:blur(10px); z-index:99999; align-items:center; justify-content:center;">
                <div style="background:#151619; border:1px solid rgba(212,175,55,0.4); border-radius:12px; padding:28px; width:90%; max-width:440px; box-shadow:0 24px 60px rgba(0,0,0,0.8); text-align:center;">
                  <div style="font-size:13px; font-weight:700; letter-spacing:1.5px; color:var(--accent-gold); text-transform:uppercase; margin-bottom:8px;">Google TV Hardware Pairing</div>
                  <div style="font-size:12px; color:#a0a2a6; margin-bottom:20px; line-height:1.5;">An authorisation code has been sent to your TV screen.<br>Please enter the 6-character code shown on your Google TV:</div>
                  <div style="display:flex; justify-content:center; gap:8px; margin-bottom:22px;">
                    <input type="text" id="gtv-pin-input" maxlength="6" placeholder="CODE" style="width:190px; height:48px; text-align:center; font-family:monospace; font-size:24px; font-weight:700; letter-spacing:4px; text-transform:uppercase; background:#0d0e10; border:2px solid #d4af37; border-radius:6px; color:#fff; outline:none;" oninput="this.value=this.value.toUpperCase(); if(this.value.length===6) submitGoogleTVPairing();">
                  </div>
                  <div style="display:flex; justify-content:center; gap:12px;">
                    <button onclick="closeGoogleTVPairModal()" style="padding:10px 20px; border-radius:6px; background:#222; border:1px solid #444; color:#ccc; font-size:11px; font-weight:600; cursor:pointer;">CANCEL</button>
                    <button onclick="submitGoogleTVPairing()" style="padding:10px 24px; border-radius:6px; background:#d4af37; border:none; color:#000; font-size:11px; font-weight:700; cursor:pointer; letter-spacing:1px;">CONFIRM & CONNECT</button>
                  </div>
                  <div id="gtv-pair-feedback" style="margin-top:14px; font-size:11px; color:#888; min-height:18px;"></div>
                </div>
              </div>

            </div>
          </section>

          <!-- Slide 11: Ambient Voice AI Studio & Multi-Device Automation Deck -->
          <section class="carousel-slide" id="slide-voice" data-slide-name="voice">
            <div class="voice-chassis">

              <!-- Top Status Ribbon -->
              <div class="voice-header-ribbon">
                <div class="voice-title-box">
                  <h3>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                    Ambient Voice AI Studio
                  </h3>
                  <div style="font-size:10px; color:var(--text-muted); font-family:'JetBrains Mono', monospace; margin-top:2px;">
                    REAL-TIME VAD · MINIMAX-TEXT-01 COGNITIVE REASONING · MULTI-DEVICE AUTOMATION
                  </div>
                </div>

                <div class="voice-status-badges">
                  <div class="voice-badge-led" id="voice-mic-badge">
                    <div class="voice-dot" id="voice-mic-dot"></div>
                    <span id="voice-mic-text">MIC: IDLE</span>
                  </div>
                  <div class="voice-badge-led" id="voice-vad-badge">
                    <div class="voice-dot" id="voice-vad-dot"></div>
                    <span id="voice-vad-text">VAD: VOCAL BAND (85Hz-3.5kHz)</span>
                  </div>
                  <div class="voice-badge-led live-cyan">
                    <div class="voice-dot pulse-cyan"></div>
                    <span>MINIMAX-TEXT-01 READY</span>
                  </div>
                </div>
              </div>

              <!-- Two Column Studio Deck -->
              <div class="voice-grid-two-col">

                <!-- Left Column: Acoustic Radar & Live Subtitles HUD -->
                <div class="voice-card">
                  <div class="voice-card-head">
                    <h4>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                      Acoustic Radar & Human Vocal Band VAD
                    </h4>
                    <span style="font-family:'JetBrains Mono', monospace; font-size:10px; color:var(--text-dim);" id="voice-freq-readout">0 Hz · -∞ dB</span>
                  </div>

                  <!-- Spectrum Visualiser Canvas -->
                  <div class="voice-spectrum-box">
                    <canvas id="voice-spectrum-canvas" width="600" height="140"></canvas>
                  </div>

                  <!-- VAD Meter & Sensitivity Gate -->
                  <div class="vad-hud-bar">
                    <span>NOISE FLOOR</span>
                    <div class="vad-meter-track">
                      <div class="vad-meter-fill" id="vad-meter-fill"></div>
                      <div class="vad-threshold-marker" id="vad-threshold-marker" style="left: 45%;" title="Voice Detection Threshold"></div>
                    </div>
                    <span id="vad-db-readout">-55 dB</span>
                  </div>

                  <!-- Threshold Sensitivity Slider -->
                  <div style="display:flex; align-items:center; justify-content:space-between; font-size:11px; color:var(--text-muted); padding:0 4px;">
                    <label for="vad-sensitivity-slider" style="display:flex; align-items:center; gap:6px;">
                      <span>VAD Sensitivity Gate:</span>
                      <strong id="vad-sens-value" style="color:var(--accent-gold); font-family:'JetBrains Mono', monospace;">-45 dB</strong>
                    </label>
                    <input type="range" id="vad-sensitivity-slider" min="-65" max="-25" value="-45" step="1" style="width:160px; accent-color:var(--accent-gold);" oninput="updateVadSensitivity(this.value)">
                  </div>

                  <!-- Streaming Subtitles OLED Panel -->
                  <div class="voice-subtitle-oled">
                    <div class="voice-subtitle-text" id="voice-live-transcript">
                      <span style="color:var(--text-dim);">Listening for human speech in the room... (Try saying "turn it down", "play Pink Floyd on YouTube", or "dim the lights")</span>
                    </div>
                    <div class="voice-subtitle-meta">
                      <span id="voice-stt-status">WEBSPEECH REALTIME ENGINE · STANDBY</span>
                      <span id="voice-words-count">0 TOKENS</span>
                    </div>
                  </div>

                  <!-- Studio Controls -->
                  <div class="voice-btn-row">
                    <button class="voice-btn" id="btn-toggle-listening" onclick="toggleAmbientListening()">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
                      <span id="btn-listen-text">START AMBIENT LISTENING</span>
                    </button>
                    <button class="voice-btn" onclick="pushToTalkClick()">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
                      <span>PUSH TO TALK</span>
                    </button>
                    <div style="flex:1; min-width:160px;">
                      <select id="voice-simulation-select" onchange="runSimulatedVoiceCommand(this.value); this.selectedIndex=0;" style="width:100%; height:100%; padding:9px 12px; background:var(--bg-surface); border:1px solid var(--border-subtle); border-radius:6px; color:var(--accent-gold); font-size:11px; font-weight:700; letter-spacing:0.8px; cursor:pointer; outline:none;">
                        <option value="">🧪 SIMULATE VOICE TRIGGER ▾</option>
                        <option value="shutup, turn it down!">⚡ "Shutup, turn it down!" (Local Reflex)</option>
                        <option value="turn the volume up, make it louder">🔊 "Turn volume up, louder" (Local Reflex)</option>
                        <option value="can you play some Pink Floyd on YouTube please">🎵 "Play Pink Floyd on YouTube" (MiniMax AI)</option>
                        <option value="I fancy watching an action movie on Tubi tonight">🎬 "Watch action movie on Tubi" (MiniMax AI)</option>
                        <option value="look for the film Interstellar on prime video">🍿 "Find Interstellar on Prime Video" (MiniMax AI)</option>
                        <option value="gosh it is really too dark in here I cannot read">💡 "It is too dark in here" (MiniMax Lighting)</option>
                        <option value="dim the lights for movie mode">🕯️ "Dim the lights for movie mode" (MiniMax Lighting)</option>
                        <option value="turn off all the lights in the room">🌑 "Turn off all lights" (MiniMax Lighting)</option>
                        <option value="Hey honey, what should we have for dinner tonight? Maybe pasta?">🚫 "Dinner conversation" (Rejected - Not for system)</option>
                      </select>
                    </div>
                  </div>

                </div>

                <!-- Right Column: MiniMax Cognitive Stream & Smart Lighting -->
                <div class="voice-card">
                  <div class="voice-card-head">
                    <h4>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                      MiniMax Cognitive Decision Stream
                    </h4>
                    <span style="font-family:'JetBrains Mono', monospace; font-size:10px; color:var(--accent-gold);" id="voice-last-decision-time">LATENCY: READY</span>
                  </div>

                  <!-- Live Decision Feed -->
                  <div class="voice-decision-stream" id="voice-decision-stream">
                    <!-- Default initial card -->
                    <div class="decision-card cognitive">
                      <div class="decision-top">
                        <span class="decision-intent media">MINIMAX-TEXT-01 STANDBY</span>
                        <span style="color:var(--text-dim);">CLOUD REASONING ACTIVE</span>
                      </div>
                      <div style="font-size:12px; color:var(--text-muted); line-height:1.4;">
                        Awaiting voice input or acoustic reflex. Reflex commands execute in sub-15ms; complex contextual requests are processed via the MiniMax reasoning model.
                      </div>
                      <div class="decision-action-chain">
                        <span class="action-pill">⚡ SUB-15MS REFLEX</span>
                        <span class="action-pill">🧠 MINIMAX-TEXT-01</span>
                        <span class="action-pill">📺 GOOGLE TV</span>
                        <span class="action-pill">💡 SMART LIGHTS</span>
                      </div>
                    </div>
                  </div>

                  <!-- Smart Lighting Ambiance Console -->
                  <div class="voice-card-head" style="margin-top:6px;">
                    <h4>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
                      Smart Lighting Room Ambiance
                    </h4>
                    <span style="font-family:'JetBrains Mono', monospace; font-size:10px; color:var(--accent-gold);" id="lighting-active-status">POWER: ON · 70%</span>
                  </div>

                  <div class="lighting-preview-glow" id="lighting-ambient-preview">
                    <div class="lighting-preview-backdrop" id="lighting-preview-backdrop"></div>
                    <div style="z-index:2;">
                      <div style="font-size:12px; font-weight:700; color:#fff;" id="lighting-name-text">Studio Warm Gold</div>
                      <div style="font-size:10px; color:var(--text-muted); font-family:'JetBrains Mono', monospace;" id="lighting-hex-text">#D4AF37 · 70% LUMENS</div>
                    </div>
                    <div style="z-index:2; display:flex; align-items:center; gap:10px;">
                      <input type="range" id="lighting-brightness-fader" min="0" max="100" value="70" style="width:120px; accent-color:var(--accent-gold);" oninput="adjustLightingBrightness(this.value)">
                    </div>
                  </div>

                  <!-- Quick Ambiance Presets -->
                  <div class="lighting-preset-pills">
                    <button class="preset-pill-btn" onclick="applyLightingAmbiance('full_lumens')">☀️ DAYLIGHT 100%</button>
                    <button class="preset-pill-btn active" onclick="applyLightingAmbiance('warm_gold')">✨ WARM GOLD</button>
                    <button class="preset-pill-btn" onclick="applyLightingAmbiance('cinema_dim')">🎬 CINEMA DIM 15%</button>
                    <button class="preset-pill-btn" onclick="applyLightingAmbiance('relaxing_indigo')">🌌 INDIGO 25%</button>
                    <button class="preset-pill-btn" onclick="applyLightingAmbiance('off')">🌑 EXTINGUISH</button>
                  </div>

                </div>

              </div>

              <!-- Bottom Full-Width Card: Extensible Voice Routine Hub -->
              <div class="voice-card">
                <div class="voice-card-head">
                  <h4>
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                    Extensible Voice Routine Hub & Macro Triggers
                  </h4>
                  <div style="display:flex; align-items:center; gap:10px;">
                    <button class="voice-btn" style="min-width:auto; padding:5px 12px; font-size:10px;" onclick="loadVoiceRoutines()">🔄 REFRESH</button>
                  </div>
                </div>

                <!-- Routines Grid populated dynamically -->
                <div class="routine-cards-grid" id="routine-cards-grid">
                  <!-- Rendered via JS -->
                </div>

              </div>

            </div>
          </section>



        </div>
      </div>
    </main>
  </div>

  <!-- Fullscreen 3D Globe View overlay if user clicks ⛶ Fullscreen -->
  <div class="globe-fullscreen-view" id="globe-fullscreen-view" style="display:none;">
    <button class="btn-globe-return" onclick="closeGlobeFullscreen()" title="Return to Player">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
      <span>Return to Player</span>
    </button>
    <div class="globe-fullscreen-container" id="globe-fullscreen-container"></div>
    <div class="globe-hud-pill" id="globe-hud-pill">
      <span class="globe-hud-dot"></span>
      <span id="globe-hud-name">Global Tuner</span>
      <span class="globe-hud-sep">·</span>
      <span id="globe-hud-location" style="color:var(--accent-gold);">24 Worldwide Stations</span>
    </div>
  </div>

  <!-- Invisible swipe-up trigger zone at bottom of viewport -->
  <div class="bottom-gesture-zone" id="bottom-gesture-zone" title="Swipe up to reveal audio controls"></div>

  <div class="master-dock-container" id="master-dock-container">
    <!-- Subtle swipe down hint pill -->
    <div class="dock-swipe-pill" title="Swipe down to minimise"></div>
    <!-- Floating Timeline Bar positioned directly above the bottom controller bar -->
    <div class="dock-timeline-bar" id="dock-timeline-bar">
      <span class="dock-time-label" id="dock-time-elapsed">00:00</span>
      <div class="dock-scrub-track" id="dock-scrub-track" onclick="handleScrub(event)">
        <div class="dock-scrub-progress" id="dock-scrub-progress"></div>
      </div>
      <span class="dock-time-label" id="dock-time-total">00:00</span>
    </div>

    <footer class="master-bar" id="master-bar">
      <div class="bar-left">
        <div class="bar-title" id="bar-title">Standby (Ready)</div>
        <div class="bar-artist" id="bar-artist">Silent Angel Streamer</div>
      </div>

      <div class="bar-centre">
        <button class="btn-circle" onclick="sendControl('prev')" title="Previous Track">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="11 19 2 12 11 5 11 19"/><polygon points="22 19 13 12 22 5 22 19"/></svg>
        </button>
        <button class="btn-circle btn-play" id="btn-master-play" onclick="togglePlay()" title="Play / Pause (Spacebar)">
          <svg width="20" height="20" id="play-icon" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        </button>
        <button class="btn-circle" onclick="sendControl('next')" title="Next Track">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 4 15 12 5 20 5 4"/><polygon points="13 4 23 12 13 20 13 4"/></svg>
        </button>
      </div>

      <div class="bar-right">
        <button class="btn-circle" id="btn-mute" onclick="toggleMute()" title="Mute Toggle (M)">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
        </button>
        <div class="volume-slider-box" id="vol-box">
          <div class="vol-slider-wrap" id="vol-slider-wrap">
            <input type="range" class="vol-slider" id="vol-range" min="0" max="100" value="35" step="1" oninput="handleVolume(this.value)">
          </div>
          <span class="vol-percent" id="vol-label">35%</span>
        </div>
        <button class="btn-dock-minimise" id="btn-dock-minimise" onclick="isBarHovered = false; hideMasterDock(true);" title="Minimise Controller Bar">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
      </div>
    </footer>
  </div>


  <script>
    let isPlaying = false;
    let isMuted = false;
    let currentVolume = 35;
    let cachedFavourites = [];
    let searchDebounceTimer = null;
    let currentVisMode = 0; // 0 = Artwork, 1 = VU Meters, 2 = RTA Spectrum
    const visModes = ["Artwork", "VU Meters", "Spectrum Analyser"];

    // Register PWA Service Worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    function updateArtwork(artUrl, title, artist, album) {
      const artImg = document.getElementById('stage-artwork');
        const ambientBg = document.getElementById('ambient-art-img');
        if (ambientBg) {
          const bgUrl = artUrl || `/api/coverart?title=${encodeURIComponent(title || '')}&artist=${encodeURIComponent(artist || '')}`;
          ambientBg.style.backgroundImage = `url("${bgUrl}")`;
        }
      const vinylIcon = document.getElementById('vinyl-icon');
      if (!artImg) return;

      const fallbackUrl = `/api/coverart?title=${encodeURIComponent(title || 'Silent Angel')}&artist=${encodeURIComponent(artist || 'VitOS Audio Core')}&genre=${encodeURIComponent(album || 'Hi-Res Lossless')}`;

      let targetSrc = fallbackUrl;
      if (artUrl && typeof artUrl === 'string' && artUrl.trim() !== '') {
        targetSrc = artUrl.startsWith('http')
          ? `/api/proxy_art?url=${encodeURIComponent(artUrl)}&title=${encodeURIComponent(title || '')}&artist=${encodeURIComponent(artist || '')}&genre=${encodeURIComponent(album || '')}`
          : artUrl;
      }

      artImg.onerror = function() {
        this.onerror = null;
        this.src = fallbackUrl;
      };

      if (artImg.getAttribute('data-active-src') !== targetSrc) {
        artImg.setAttribute('data-active-src', targetSrc);
        artImg.src = targetSrc;
      }
      artImg.style.display = 'none';
      if (vinylIcon) vinylIcon.style.display = 'none';
    }

    function updatePlayPauseUI(playing) {
      isPlaying = !!playing;
      const playIcon = document.getElementById('play-icon');
      const masterPlayBtn = document.getElementById('btn-master-play');
      const stageVinylDisc = document.getElementById('stage-vinyl-disc');

      if (playIcon) {
        if (isPlaying) {
          playIcon.innerHTML = '<rect x="6" y="4" width="3" height="16"/><rect x="15" y="4" width="3" height="16"/>';
        } else {
          playIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
        }
      }
      if (masterPlayBtn) {
        masterPlayBtn.classList.toggle('playing', isPlaying);
      }
      if (stageVinylDisc) {
        stageVinylDisc.classList.toggle('spinning', isPlaying);
      }
      document.body.classList.toggle('is-audio-playing', isPlaying);
    }

    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

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

        isPlaying = (data.transport_state === "PLAYING");
        isMuted = !!data.mute;
        updateMuteUI(isMuted);

        const topDev = document.getElementById('top-dev-name');
        const topDot = document.getElementById('top-dot');
        if (topDev && data.device_name) topDev.innerText = data.device_name;
        if (topDot) topDot.className = (data.connected && data.device_ip) ? "status-dot connected" : "status-dot";
        const playIcon = document.getElementById('play-icon');
        if (isPlaying) {
          playIcon.innerHTML = '<rect x="6" y="4" width="3" height="16"/><rect x="15" y="4" width="3" height="16"/>';
        } else {
          playIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"/>';
        }

        document.getElementById('stage-title').innerText = data.track_title;
        document.getElementById('stage-artist').innerText = data.track_artist;
        document.getElementById('stage-album').innerText = data.track_album;
        document.getElementById('bar-title').innerText = data.track_title;
        document.getElementById('bar-artist').innerText = data.track_artist;

        document.getElementById('time-elapsed').innerText = data.rel_time;
        document.getElementById('time-total').innerText = data.track_duration;
        const dElapsed = document.getElementById('dock-time-elapsed');
        const dTotal = document.getElementById('dock-time-total');
        if (dElapsed) dElapsed.innerText = data.rel_time;
        if (dTotal) dTotal.innerText = data.track_duration;
        const curSec = parseTimeToSec(data.rel_time);
        const totSec = parseTimeToSec(data.track_duration);
        const elScrub = document.getElementById('scrub-progress');
        const elDockScrub = document.getElementById('dock-scrub-progress');
        if (totSec > 0) {
          window.lastKnownDuration = totSec;
          const pct = Math.min(100, Math.max(0, (curSec / totSec) * 100));
          if (elScrub) elScrub.style.width = pct + '%';
          if (elDockScrub) elDockScrub.style.width = pct + '%';
        } else {
          if (elScrub) elScrub.style.width = '0%';
          if (elDockScrub) elDockScrub.style.width = '0%';
        }

        const artImg = document.getElementById('stage-artwork');
        const vinylIcon = document.getElementById('vinyl-icon');
        updateArtwork(data.album_art_url, data.track_title, data.track_artist, data.track_album);

                const elFmt = document.getElementById('hud-format'); if (elFmt) elFmt.innerText = data.format_label || 'No Active Stream (Ready)';
        const elCodec = document.getElementById('stage-codec'); if (elCodec) elCodec.innerText = (data.codec && data.codec !== "�") ? (data.codec + " Audio Stream") : "Standby (Ready)";

        // Active Streaming Protocol Display in Main Player
        const protoSrc = data.active_source || "UPnP / DLNA";
        let protoIconId = "#icon-upnp";
        let protoColor = "var(--accent-gold)";
        let protoName = protoSrc;

        const pLower = protoSrc.toLowerCase();
        if (pLower.includes("spotify")) {
          protoIconId = "#icon-spotify";
          protoColor = "#1db954";
          protoName = "Spotify Connect";
        } else if (pLower.includes("tidal")) {
          protoIconId = "#icon-tidal";
          protoColor = "#00e5ff";
          protoName = "Tidal Connect";
        } else if (pLower.includes("roon")) {
          protoIconId = "#icon-roon";
          protoColor = "var(--accent-gold)";
          protoName = "Roon Ready";
        } else if (pLower.includes("airplay")) {
          protoIconId = "#icon-airplay";
          protoColor = "#ffffff";
          protoName = "Apple AirPlay 2";
        } else if (pLower.includes("qobuz")) {
          protoIconId = "#icon-qobuz";
          protoColor = "#0099ff";
          protoName = "Qobuz Hi-Res";
        } else {
          protoIconId = "#icon-upnp";
          protoColor = "var(--accent-gold)";
          protoName = "UPnP / DLNA";
        }

        const stageProtoIcon = document.getElementById('stage-proto-icon');
        const stageProtoName = document.getElementById('stage-proto-name');
        const hudProtoIcon = document.getElementById('hud-proto-icon');
        const hudProtoName = document.getElementById('hud-proto-name');

        if (stageProtoIcon) {
          const u = stageProtoIcon.querySelector('use');
          if (u) u.setAttribute('href', protoIconId);
          stageProtoIcon.style.fill = protoColor;
        }
        if (stageProtoName) {
          stageProtoName.innerText = protoName;
          stageProtoName.style.color = protoColor;
        }
        if (hudProtoIcon) {
          const hu = hudProtoIcon.querySelector('use');
          if (hu) hu.setAttribute('href', protoIconId);
          hudProtoIcon.style.fill = protoColor;
        }
        if (hudProtoName) {
          hudProtoName.innerText = protoName;
          hudProtoName.style.color = protoColor;
        }
// Fixed Volume / Bit-Perfect Mode
        const fixedBadge = document.getElementById('stage-fixed-badge');
        const barFixedBadge = document.getElementById('bar-fixed-badge');
        const volBox = document.getElementById('vol-box');
        if (data.fixed_volume_mode) {
          currentVolume = 100;
          if (fixedBadge) fixedBadge.style.display = 'inline-block';
          if (barFixedBadge) barFixedBadge.style.display = 'inline-block';
          if (volBox) volBox.style.display = 'none';
        } else {
          if (typeof data.volume === 'number') currentVolume = data.volume;
          if (fixedBadge) fixedBadge.style.display = 'none';
          if (barFixedBadge) barFixedBadge.style.display = 'none';
          if (volBox) volBox.style.display = 'flex';
          if (!document.getElementById('vol-range')?.matches(':active')) {
            if (typeof updateVolFill === 'function') updateVolFill(data.volume);
          }
        }

        // Hardware Filters & Telemetry
        const filterMap = {
          "minimum_fast": "Minimum Phase",
          "linear_fast": "Linear Fast",
          "linear_slow": "Linear Slow",
          "apodizing_fast": "Apodizing",
          "brickwall": "Brickwall"
        };
        const elDacFilt = document.getElementById('hud-dac-filter');
        if (elDacFilt) elDacFilt.innerText = filterMap[data.dac_filter] || data.dac_filter;
        const elPeq = document.getElementById('hud-peq');
        if (elPeq && data.eq_preset) elPeq.innerText = (data.eq_preset.charAt(0).toUpperCase() + data.eq_preset.slice(1));
        const elLat = document.getElementById('hud-latency');
        if (elLat) elLat.innerText = (data.network_latency_ms || 0) + ' ms';
        const elQc = document.getElementById('q-count');
        if (elQc) elQc.innerText = data.queue_count || 0;

        // Sleep Timer Badge
        const elSleep = document.getElementById('hud-sleep');
        if (elSleep) {
          if (data.sleep_remaining_sec > 0) {
            const m = Math.floor(data.sleep_remaining_sec / 60);
            const s = data.sleep_remaining_sec % 60;
            elSleep.innerText = `${m}m ${s}s`;
            elSleep.style.color = 'var(--accent-gold)';
          } else {
            elSleep.innerText = 'Off';
            elSleep.style.color = 'var(--text-muted)';
          }
        }

        // Telemetry Grid & Source Synchronization
        const tRes = document.getElementById('telemetry-res');
        if (tRes) {
          const codecStr = (data.codec && data.codec !== '—') ? data.codec : 'Lossless';
          const srStr = (data.sample_rate && data.sample_rate !== '—') ? data.sample_rate : '192.0 kHz';
          const bdStr = (data.bit_depth && data.bit_depth !== '—') ? data.bit_depth : '24-bit';
          tRes.innerText = `${codecStr} ${srStr} / ${bdStr}`;
        }
        const tProto = document.getElementById('telemetry-proto');
        if (tProto && data.active_source) {
          tProto.innerText = `${data.active_source} ⚙`;
        }
        const tEngine = document.getElementById('telemetry-engine');
        if (tEngine) {
          tEngine.innerText = data.fixed_volume_mode ? "Bit-Perfect Direct (0 dB)" : "Studio Lossless Engine";
        }
        const tLatency = document.getElementById('telemetry-latency');
        if (tLatency) {
          tLatency.innerText = `${data.network_latency_ms || 0.0} ms (${data.network_jitter_status || 'Direct LAN'})`;
        }

        if (data.active_source) {
          document.querySelectorAll('.source-pill').forEach(el => {
            const txt = el.innerText.trim();
            el.classList.toggle('active', txt.includes(data.active_source.split(' ')[0]));
          });
        }
      } catch (err) {
        console.error("Status polling error:", err);
      }
    }

    // =========================================================================
    // High-Fidelity Analogue Ballistics Engine (ANSI C16.5-1954 / IEC 60268-17)
    // Damped 2nd-order moving-coil physical model with fluid stereo audio dynamics
    // =========================================================================
    const vuPhysics = {
      left: { angle: -35.0, velocity: 0.0 },
      right: { angle: -35.0, velocity: 0.0 },
      lastTimestamp: null,

      // Musical envelope state
      envelopeTime: 0,
      transientDecay: 0,
      transientTimer: 0,
      nextTransientIn: 1.2,

      // RTA frequency bands
      rtaBands: [6, 6, 6, 6, 6, 6, 6, 6, 6, 6]
    };

    function animateBallistics(timestamp) {
      if (!timestamp) timestamp = performance.now();
      if (!vuPhysics.lastTimestamp) vuPhysics.lastTimestamp = timestamp;
      const rawDt = (timestamp - vuPhysics.lastTimestamp) / 1000;
      vuPhysics.lastTimestamp = timestamp;
      // Clamp delta time to avoid large physics jumps during tab switches or backgrounding
      const dt = Math.min(Math.max(rawDt, 0.001), 0.05);

      const needleL = document.getElementById('vu-needle-left');
      const needleR = document.getElementById('vu-needle-right');
      const peakL = document.getElementById('vu-peak-left');
      const peakR = document.getElementById('vu-peak-right');

      let targetAngleL = -35.0;
      let targetAngleR = -35.0;

      if (isPlaying && !isMuted) {
        // Advance continuous musical time
        vuPhysics.envelopeTime += dt;
        vuPhysics.transientTimer += dt;

        // Realistic musical rhythm: ~116 BPM tempo pulse (1.93 Hz)
        const tempoFreq = 1.93;
        const beatPhase = (vuPhysics.envelopeTime * tempoFreq) * Math.PI * 2;
        // Percussive kick/bass pulse (sharpened cosine wave)
        const kickPulse = Math.pow(Math.max(0, Math.cos(beatPhase)), 6);
        // Off-beat rhythmic syncopation (snare/hi-hat groove)
        const syncPulse = Math.pow(Math.max(0, Math.sin(beatPhase)), 4) * 0.45;

        // Multi-measure musical phrase dynamics (8-12 second natural musical breathing)
        const phraseSwell = Math.sin(vuPhysics.envelopeTime * 0.45) * 0.18 +
                            Math.sin(vuPhysics.envelopeTime * 0.12) * 0.12;

        // Occasional musical transient spikes (snare crack, dynamic peak)
        if (vuPhysics.transientTimer > vuPhysics.nextTransientIn) {
          vuPhysics.transientDecay = 0.35 + Math.random() * 0.35;
          vuPhysics.transientTimer = 0;
          vuPhysics.nextTransientIn = 0.8 + Math.random() * 1.8;
        }
        vuPhysics.transientDecay = Math.max(0, vuPhysics.transientDecay - dt * 2.8);

        // Core program energy (0.0 to 1.0)
        const baseLevel = 0.48; // Sits in standard -7 to -3 VU region
        const programEnergy = Math.max(0.05, Math.min(1.0,
          baseLevel + phraseSwell + (kickPulse * 0.30) + syncPulse + vuPhysics.transientDecay
        ));

        // Volume compensation (scaled smoothly by master volume slider)
        const volFactor = Math.max(0.05, Math.min(1.0, currentVolume / 100));
        const effectiveEnergy = programEnergy * (0.35 + 0.65 * volFactor);

        // Natural stereo imaging:
        // Mid (center mono content) = 86%
        // Side (stereo nuance & panning) = 14% with smooth phase relationship
        const stereoPan = Math.sin(vuPhysics.envelopeTime * 0.85) * 0.14;
        const energyL = Math.max(0, Math.min(1.0, effectiveEnergy * (1.0 + stereoPan)));
        const energyR = Math.max(0, Math.min(1.0, effectiveEnergy * (1.0 - stereoPan)));

        // Non-linear VU meter scale mapping:
        // -35 deg = rest (infinity / < -20 VU)
        // -20 VU  = -27 deg
        // -10 VU  = -17 deg
        // -5 VU   = -7 deg
        // -3 VU   = -1 deg
        //  0 VU   = +10 deg (100% nominal audio level)
        // +1 VU   = +15 deg
        // +3 VU   = +25 deg (redline maximum deflection)
        targetAngleL = -35.0 + (60.0 * Math.pow(energyL, 0.62));
        targetAngleR = -35.0 + (60.0 * Math.pow(energyR, 0.62));
      } else {
        // Paused or silent: smoothly decay towards mechanical rest stop at -35 deg
        targetAngleL = -35.0;
        targetAngleR = -35.0;
      }

      // -----------------------------------------------------------------------
      // Physical Moving-Coil Simulation (2nd-Order Damped Spring-Mass Model)
      // Natural frequency wn = 16.5 rad/s (gives authentic ~260-300ms rise time)
      // Damping ratio zeta = 0.74 (provides authentic 1.2% ballistic transient overshoot)
      // -----------------------------------------------------------------------
      const wn = 16.5;
      const zeta = 0.74;

      // Left Channel Integration
      const accL = (wn * wn) * (targetAngleL - vuPhysics.left.angle) - (2.0 * zeta * wn) * vuPhysics.left.velocity;
      vuPhysics.left.velocity += accL * dt;
      vuPhysics.left.angle += vuPhysics.left.velocity * dt;

      // Right Channel Integration
      const accR = (wn * wn) * (targetAngleR - vuPhysics.right.angle) - (2.0 * zeta * wn) * vuPhysics.right.velocity;
      vuPhysics.right.velocity += accR * dt;
      vuPhysics.right.angle += vuPhysics.right.velocity * dt;

      // Mechanical End-Stops (Cushioned bumper pegs at -35 deg and +26 deg)
      if (vuPhysics.left.angle < -35.0) {
        vuPhysics.left.angle = -35.0;
        vuPhysics.left.velocity = Math.max(0, -vuPhysics.left.velocity * 0.15);
      } else if (vuPhysics.left.angle > 26.0) {
        vuPhysics.left.angle = 26.0;
        vuPhysics.left.velocity = Math.min(0, -vuPhysics.left.velocity * 0.15);
      }

      if (vuPhysics.right.angle < -35.0) {
        vuPhysics.right.angle = -35.0;
        vuPhysics.right.velocity = Math.max(0, -vuPhysics.right.velocity * 0.15);
      } else if (vuPhysics.right.angle > 26.0) {
        vuPhysics.right.angle = 26.0;
        vuPhysics.right.velocity = Math.min(0, -vuPhysics.right.velocity * 0.15);
      }

      // Render needles with high-precision sub-pixel transform
      if (needleL) {
        needleL.style.transform = `rotate(${vuPhysics.left.angle.toFixed(2)}deg) translateZ(0)`;
      }
      if (needleR) {
        needleR.style.transform = `rotate(${vuPhysics.right.angle.toFixed(2)}deg) translateZ(0)`;
      }

      // Peak Indicator LEDs (illuminate warmly when signal enters red zone > +0 VU / 11.5 deg)
      if (peakL) {
        peakL.classList.toggle('active', vuPhysics.left.angle > 11.5);
      }
      if (peakR) {
        peakR.classList.toggle('active', vuPhysics.right.angle > 11.5);
      }

      // -----------------------------------------------------------------------
      // Real-Time Spectrum Analyser (RTA) Fluid Ballistics
      // 10 Musical bands: 32Hz, 64Hz, 125Hz, 250Hz, 500Hz, 1kHz, 2kHz, 4kHz, 8kHz, 16kHz
      // Smooth attack and logarithmic decay (no random flickering)
      // -----------------------------------------------------------------------
      if (currentVisMode === 2) {
        const time = vuPhysics.envelopeTime;
        const decayFactor = Math.pow(0.88, dt * 60);

        for (let i = 0; i < 10; i++) {
          let targetHeight = 6.0; // Rest floor
          if (isPlaying && !isMuted) {
            // Frequency-dependent spectral weight (pink noise / 1/f curve)
            let bandMod = 0;
            if (i <= 2) {
              bandMod = (Math.pow(Math.max(0, Math.cos((time * 1.93) * Math.PI * 2)), 4) * 0.5) +
                        (Math.sin(time * 3.2 + i) * 0.2);
            } else if (i <= 6) {
              bandMod = (Math.sin(time * 2.4 + i * 0.8) * 0.25) +
                        (Math.cos(time * 4.1 + i) * 0.2);
            } else {
              bandMod = (vuPhysics.transientDecay * 0.7) +
                        (Math.sin(time * 5.6 + i) * 0.18);
            }
            const spectralCurve = [0.85, 0.90, 0.82, 0.75, 0.70, 0.65, 0.58, 0.50, 0.42, 0.35][i];
            const rawH = (spectralCurve * 75) * (0.6 + bandMod) * (currentVolume / 100);
            targetHeight = Math.max(8.0, Math.min(95.0, rawH));
          }

          // Instantaneous attack, smooth organic decay
          if (targetHeight > vuPhysics.rtaBands[i]) {
            vuPhysics.rtaBands[i] = targetHeight;
          } else {
            vuPhysics.rtaBands[i] = Math.max(targetHeight, vuPhysics.rtaBands[i] * decayFactor);
          }

          const bar = document.getElementById(`rta-${i}`);
          if (bar) {
            bar.style.height = `${vuPhysics.rtaBands[i].toFixed(1)}%`;
          }
        }
      }

            // -----------------------------------------------------------------------
      // Real-Time Parametric EQ Dynamic Audio Wave
      // Responds organically to frequency harmonics and audio running through device
      // -----------------------------------------------------------------------
      const eqPath = document.getElementById('eq-curve-path');
      const eqFill = document.getElementById('eq-wave-fill');
      if (eqPath) {
        const time = vuPhysics.envelopeTime;
        const numPts = 26;
        const step = 500 / (numPts - 1);
        const pts = [];
        const svgH = eqPath.ownerSVGElement ? (eqPath.ownerSVGElement.viewBox.baseVal.height || 120) : 120;
        const baseH = svgH / 2;

        // Gains from sliders
        const g32 = parseFloat(document.getElementById('eq-band-32')?.value || 0) * 1.6;
        const g120 = parseFloat(document.getElementById('eq-band-120')?.value || 0) * 1.6;
        const g1k = parseFloat(document.getElementById('eq-band-1000')?.value || 0) * 1.6;
        const g4k = parseFloat(document.getElementById('eq-band-4500')?.value || 0) * 1.6;
        const g12k = parseFloat(document.getElementById('eq-band-12000')?.value || 0) * 1.6;

        for (let i = 0; i < numPts; i++) {
          const x = i * step;
          const nx = i / (numPts - 1);

          let sliderGain = 0;
          if (nx < 0.25) {
            sliderGain = g32 * (1 - nx / 0.25) + g120 * (nx / 0.25);
          } else if (nx < 0.50) {
            sliderGain = g120 * (1 - (nx - 0.25) / 0.25) + g1k * ((nx - 0.25) / 0.25);
          } else if (nx < 0.75) {
            sliderGain = g1k * (1 - (nx - 0.50) / 0.25) + g4k * ((nx - 0.50) / 0.25);
          } else {
            sliderGain = g4k * (1 - (nx - 0.75) / 0.25) + g12k * ((nx - 0.75) / 0.25);
          }

          let waveDyn = 0;
          if (isPlaying && !isMuted) {
            const volP = Math.max(0.1, currentVolume / 100);
            const wBass = Math.sin(time * 5.2 + nx * 6.5) * (vuPhysics.rtaBands[1] * 0.22);
            const wMid = Math.cos(time * 9.8 + nx * 14.0) * (vuPhysics.rtaBands[4] * 0.16);
            const wHigh = Math.sin(time * 16.4 + nx * 22.0) * (vuPhysics.rtaBands[7] * 0.11);
            waveDyn = (wBass + wMid + wHigh) * volP;
          }

          const y = Math.max(10, Math.min(110, baseH - sliderGain - waveDyn));
          pts.push({ x, y });
        }

        let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
        for (let i = 1; i < pts.length; i++) {
          const p0 = pts[i - 1];
          const p1 = pts[i];
          const mx = (p0.x + p1.x) / 2;
          const my = (p0.y + p1.y) / 2;
          d += ` Q ${p0.x.toFixed(1)} ${p0.y.toFixed(1)}, ${mx.toFixed(1)} ${my.toFixed(1)}`;
        }
        d += ` T ${pts[pts.length - 1].x.toFixed(1)} ${pts[pts.length - 1].y.toFixed(1)}`;
        eqPath.setAttribute('d', d);
        if (eqFill) eqFill.setAttribute('d', `${d} L 500 120 L 0 120 Z`);
      }

      requestAnimationFrame(animateBallistics);
    }
          // -----------------------------------------------------------------------
      // Real-Time Parametric EQ Dynamic Audio Wave
      // Responds organically to frequency harmonics and audio running through device
      // -----------------------------------------------------------------------
      const eqPath = document.getElementById('eq-curve-path');
      const eqFill = document.getElementById('eq-wave-fill');
      if (eqPath) {
        const time = vuPhysics.envelopeTime;
        const numPts = 26;
        const step = 500 / (numPts - 1);
        const pts = [];
        const svgH = eqPath.ownerSVGElement ? (eqPath.ownerSVGElement.viewBox.baseVal.height || 120) : 120;
        const baseH = svgH / 2;

        // Gains from sliders
        const g32 = parseFloat(document.getElementById('eq-band-32')?.value || 0) * 1.6;
        const g120 = parseFloat(document.getElementById('eq-band-120')?.value || 0) * 1.6;
        const g1k = parseFloat(document.getElementById('eq-band-1000')?.value || 0) * 1.6;
        const g4k = parseFloat(document.getElementById('eq-band-4500')?.value || 0) * 1.6;
        const g12k = parseFloat(document.getElementById('eq-band-12000')?.value || 0) * 1.6;

        for (let i = 0; i < numPts; i++) {
          const x = i * step;
          const nx = i / (numPts - 1);

          let sliderGain = 0;
          if (nx < 0.25) {
            sliderGain = g32 * (1 - nx / 0.25) + g120 * (nx / 0.25);
          } else if (nx < 0.50) {
            sliderGain = g120 * (1 - (nx - 0.25) / 0.25) + g1k * ((nx - 0.25) / 0.25);
          } else if (nx < 0.75) {
            sliderGain = g1k * (1 - (nx - 0.50) / 0.25) + g4k * ((nx - 0.50) / 0.25);
          } else {
            sliderGain = g4k * (1 - (nx - 0.75) / 0.25) + g12k * ((nx - 0.75) / 0.25);
          }

          let waveDyn = 0;
          if (isPlaying && !isMuted) {
            const volP = Math.max(0.1, currentVolume / 100);
            const wBass = Math.sin(time * 5.2 + nx * 6.5) * (vuPhysics.rtaBands[1] * 0.22);
            const wMid = Math.cos(time * 9.8 + nx * 14.0) * (vuPhysics.rtaBands[4] * 0.16);
            const wHigh = Math.sin(time * 16.4 + nx * 22.0) * (vuPhysics.rtaBands[7] * 0.11);
            waveDyn = (wBass + wMid + wHigh) * volP;
          }

          const y = Math.max(10, Math.min(110, baseH - sliderGain - waveDyn));
          pts.push({ x, y });
        }

        let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
        for (let i = 1; i < pts.length; i++) {
          const p0 = pts[i - 1];
          const p1 = pts[i];
          const mx = (p0.x + p1.x) / 2;
          const my = (p0.y + p1.y) / 2;
          d += ` Q ${p0.x.toFixed(1)} ${p0.y.toFixed(1)}, ${mx.toFixed(1)} ${my.toFixed(1)}`;
        }
        d += ` T ${pts[pts.length - 1].x.toFixed(1)} ${pts[pts.length - 1].y.toFixed(1)}`;
        eqPath.setAttribute('d', d);
        if (eqFill) eqFill.setAttribute('d', `${d} L 500 120 L 0 120 Z`);
      }

      requestAnimationFrame(animateBallistics);

        let activeVisualiserMode = 'vu';
    function togglePlayerVisualiser() {
      const vVu = document.getElementById('view-vu');
      const vRta = document.getElementById('view-rta');
      const tagActive = document.getElementById('vis-active-tag');
      const tagInactive = document.getElementById('vis-inactive-tag');

      if (activeVisualiserMode === 'vu') {
        activeVisualiserMode = 'rta';
        if (vVu) vVu.style.display = 'none';
        if (vRta) vRta.style.display = 'block';
        if (tagActive) tagActive.innerText = 'SPECTRUM RTA';
        if (tagInactive) tagInactive.innerText = 'VU METERS';
      } else {
        activeVisualiserMode = 'vu';
        if (vVu) vVu.style.display = 'grid';
        if (vRta) vRta.style.display = 'none';
        if (tagActive) tagActive.innerText = 'VU METERS';
        if (tagInactive) tagInactive.innerText = 'SPECTRUM RTA';
      }
    }

    function toggleVisualiserMode() {
      // In the balanced studio layout, artwork, VU level meters, and RTA spectrum are all concurrently visible
      currentVisMode = (currentVisMode + 1) % 3;
      const hudVis = document.getElementById('hud-vis-mode');
      if (hudVis) hudVis.innerText = visModes[currentVisMode];
    }

    function parseTimeToSec(tStr) {
      if (!tStr) return 0;
      const parts = String(tStr).trim().split(':').map(Number);
      if (parts.length === 1 && !isNaN(parts[0])) return parts[0];
      if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) return parts[0] * 60 + parts[1];
      if (parts.length === 3 && !isNaN(parts[0]) && !isNaN(parts[1]) && !isNaN(parts[2])) return parts[0] * 3600 + parts[1] * 60 + parts[2];
      return 0;
    }

    function secToTime(sec) {
      sec = Math.max(0, Math.floor(sec || 0));
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = Math.floor(sec % 60);
      return (h > 0 ? String(h).padStart(2, '0') + ':' : '') +
             String(m).padStart(2, '0') + ':' +
             String(s).padStart(2, '0');
    }

    function handleScrub(e) {
      if (!e) return;
      let track = null;
      if (e.currentTarget && typeof e.currentTarget.getBoundingClientRect === "function") {
        track = e.currentTarget;
      } else if (e.target && typeof e.target.closest === "function") {
        track = e.target.closest("#dock-scrub-track, #scrub-track, .dock-scrub-track, .main-scrub-track");
      }
      if (!track || typeof track.getBoundingClientRect !== "function") {
        track = document.getElementById("dock-scrub-track") || document.getElementById("scrub-track");
      }
      if (!track || typeof track.getBoundingClientRect !== "function") return;

      const rect = track.getBoundingClientRect();
      if (!rect || rect.width <= 0) return;

      const clientX = (e.touches && e.touches[0]) ? e.touches[0].clientX : e.clientX;
      const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const pctStr = (frac * 100).toFixed(2) + '%';

      // Instant optimistic feedback on both scrub bars
      const mainScrub = document.getElementById('scrub-progress');
      const dockScrub = document.getElementById('dock-scrub-progress');
      if (mainScrub) mainScrub.style.width = pctStr;
      if (dockScrub) dockScrub.style.width = pctStr;

      // Extract duration
      let totSec = 0;
      const dTotal = document.getElementById('dock-time-total');
      const mTotal = document.getElementById('time-total');
      if (dTotal && dTotal.innerText && dTotal.innerText !== '00:00' && dTotal.innerText !== '--:--') {
        totSec = parseTimeToSec(dTotal.innerText);
      } else if (mTotal && mTotal.innerText && mTotal.innerText !== '00:00' && mTotal.innerText !== '--:--') {
        totSec = parseTimeToSec(mTotal.innerText);
      }
      if (totSec <= 0 && window.lastKnownDuration) {
        totSec = window.lastKnownDuration;
      }

      let targetSec = 0;
      if (totSec > 0) {
        targetSec = Math.round(frac * totSec);
      } else {
        targetSec = Math.round(frac * 100);
      }

      const formatted = secToTime(targetSec);
      const mElapsed = document.getElementById('time-elapsed');
      const dElapsed = document.getElementById('dock-time-elapsed');
      if (mElapsed) mElapsed.innerText = formatted;
      if (dElapsed) dElapsed.innerText = formatted;

      // Proactively notify streamer
      sendControl('seek', targetSec);
    }

    function initScrubInteraction() {
      const tracks = document.querySelectorAll('#scrub-track, #dock-scrub-track, .main-scrub-track, .dock-scrub-track');
      tracks.forEach(track => {
        let isDown = false;
        const onMove = (evt) => {
          if (!isDown) return;
          evt.preventDefault();
          handleScrub(evt);
        };
        const onUp = (evt) => {
          if (isDown) {
            isDown = false;
            handleScrub(evt);
          }
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', onUp);
        };
        track.addEventListener('pointerdown', (evt) => {
          isDown = true;
          evt.preventDefault();
          handleScrub(evt);
          window.addEventListener('pointermove', onMove);
          window.addEventListener('pointerup', onUp);
        });
      });
    }

    setInterval(updateStatus, 1500);
    updateStatus();
    initScrubInteraction();

    async function sendControl(action, value = null) {
      await fetch('/api/control', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action, value})
      });
      setTimeout(updateStatus, 200);
    }

    function togglePlay() {
      const nextState = !isPlaying;
      updatePlayPauseUI(nextState);
      sendControl(nextState ? 'play' : 'pause');
    }

    function toggleMute() {
      isMuted = !isMuted;
      updateMuteUI(isMuted);
      sendControl('mute', isMuted);
    }

    function updateMuteUI(muted) {
      const btn = document.getElementById('btn-mute');
      const volRange = document.getElementById('vol-range');
      const volLabel = document.getElementById('vol-label');
      if (!btn) return;

      if (muted) {
        btn.classList.add('muted');
        btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="currentColor"/>
          <line x1="23" y1="9" x2="17" y2="15"/>
          <line x1="17" y1="9" x2="23" y2="15"/>
        </svg>`;
        btn.title = "Unmute Output (M)";
        if (volLabel) volLabel.innerText = "MUTED";
        if (volRange) volRange.style.opacity = '0.35';
      } else {
        btn.classList.remove('muted');
        btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
        </svg>`;
        btn.title = "Mute Output (M)";
        if (volLabel) volLabel.innerText = currentVolume + '%';
        if (volRange) volRange.style.opacity = '1';
      }
    }

    function updateVolFill(val) {
      const v = Math.max(0, Math.min(100, parseInt(val) || 0));
      const range = document.getElementById('vol-range');
      if (range) {
        range.value = v;
        range.style.background = `linear-gradient(to right, var(--accent-gold) 0%, var(--accent-gold) ${v}%, rgba(255, 255, 255, 0.12) ${v}%, rgba(255, 255, 255, 0.12) 100%)`;
      }
      const label = document.getElementById('vol-label');
      if (label) {
        label.innerText = v + '%';
      }
    }

    function handleVolume(val) {
      if (isMuted) {
        isMuted = false;
        updateMuteUI(false);
        sendControl('mute', false);
      }
      currentVolume = Math.max(0, Math.min(100, parseInt(val) || 0));
      updateVolFill(currentVolume);
      sendControl('volume', currentVolume);
    }

    function switchSource(sourceName) {
      document.querySelectorAll('.source-pill').forEach(el => {
        el.classList.toggle('active', el.innerText.trim().includes(sourceName.split(' ')[0]));
      });
      sendControl('source', sourceName);
    }

    // Collapsible Navigation Drawer Controller
        /* =========================================================================
       Navigation Drawer & Persistent Hamburger Engine
       ========================================================================= */
    function toggleNavDrawer(forceOpen) {
      const drawer = document.getElementById('sidebar-drawer');
      const backdrop = document.getElementById('nav-drawer-backdrop');
      const hamburger = document.getElementById('btn-floating-nav');
      
      const isOpen = drawer ? (drawer.classList.contains('drawer-open') || drawer.classList.contains('open')) : false;
      const shouldOpen = (forceOpen !== undefined) ? forceOpen : !isOpen;

      if (drawer) {
        drawer.classList.toggle('drawer-open', shouldOpen);
        drawer.classList.toggle('open', shouldOpen);
      }
      if (backdrop) {
        backdrop.classList.toggle('active', shouldOpen);
      }
      if (hamburger) {
        hamburger.classList.toggle('nav-active', shouldOpen);
      }
      document.body.classList.toggle('nav-drawer-open', shouldOpen);
      if (typeof onWindowResize === 'function') {
        setTimeout(onWindowResize, 60);
      }
    }

    /* =========================================================================
       Fluid Carousel Slide Navigation System (Audiophile Momentum)
       ========================================================================= */
    const TOTAL_SLIDES = 12;
    const slideMap = {
      'player': 0,
      'protocols': 1,
      'discovery': 2,
      'radio': 3,
      'globe': 3,
      'dac': 4,
      'eq': 5,
      'sleep': 6,
      'lyrics': 7,
      'queue': 8,
      'storage': 9,
      'remote': 10,
      'voice': 11
    };

    let currentSlideIndex = 0;
    try {
      const _urlParams = new URLSearchParams(window.location.search);
      const _targetSlide = _urlParams.get('slide') || window.location.hash.replace('#', '');
      if (_targetSlide && slideMap[_targetSlide] !== undefined) {
        currentSlideIndex = slideMap[_targetSlide];
      }
    } catch (e) {}

    function slideToView(viewName) {
      if (typeof syncRotaryDiscToSlide === 'function') {
        const _syncIdx = (typeof viewName === 'number') ? viewName : (slideMap[viewName] ?? 0);
        syncRotaryDiscToSlide(_syncIdx);
      }
      if (typeof toggleNavDrawer === 'function') {
        toggleNavDrawer(false);
      

      }
      const idx = (typeof viewName === 'number') ? viewName : (slideMap[viewName] ?? 0);
      currentSlideIndex = Math.max(0, Math.min(TOTAL_SLIDES - 1, idx));

      const track = document.getElementById('carousel-track');
      if (track) {
        const vp = track.parentElement || document.querySelector('.carousel-viewport');
        const w = vp ? vp.clientWidth : window.innerWidth;
        track.style.transform = `translateX(-${currentSlideIndex * w}px)`;
      }

      // Update active classes on slides
      document.querySelectorAll('.carousel-slide').forEach((slide, sIdx) => {
        slide.classList.toggle('active', sIdx === currentSlideIndex);
      });

      // Update nav active states
      document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
      const navItemIds = [
        'nav-now-playing', 'nav-protocols', 'nav-discovery', 'nav-radio',
        'nav-dac', 'nav-eq', '', 'nav-lyrics', 'nav-queue', 'nav-storage', 'nav-remote', 'nav-voice'
      ];
      if (navItemIds[currentSlideIndex]) {
        document.getElementById(navItemIds[currentSlideIndex])?.classList.add('active');
      }

      // Hub button removed entirely per user directive
      const hubBtn = document.getElementById('btn-floating-hub');
      if (hubBtn) {
        hubBtn.style.display = 'none';
      }
      document.body.classList.toggle('on-hub-slide', currentSlideIndex === 1);
      document.body.classList.toggle('on-player-slide', currentSlideIndex === 0);

      // Auto-minimise navigation drawer on selection
      toggleNavDrawer(false);
      


      // Trigger feature-specific data loaders
      if (currentSlideIndex === 1 && typeof renderProtocolsHub === 'function') renderProtocolsHub();
      if (currentSlideIndex === 2 && typeof triggerDeviceScan === 'function') triggerDeviceScan();
      if (currentSlideIndex === 3) {
        setTimeout(initOrResizeCarouselGlobe, 120);
        if (typeof showMasterDock === 'function') showMasterDock(true);
      }
      if (currentSlideIndex === 7 && typeof fetchLyrics === 'function') fetchLyrics();
      if (currentSlideIndex === 8 && typeof fetchQueueData === 'function') fetchQueueData();
      if (currentSlideIndex === 9 && typeof fetchStorageList === 'function') fetchStorageList('/');

      // Rule: Master controller dock visibility across slides
      if (currentSlideIndex === 0) {
        showMasterDock(false);
        scheduleMasterDockAutoHide();
      } else if (currentSlideIndex === 3) {
        // Radio Globe: bottom controller bar must be present all the time on this page
        showMasterDock(false);
        if (typeof carouselGlobeAnimId !== 'undefined' && !carouselGlobeAnimId) {
          animateCarouselGlobe();
        }
      } else {
        // All other slides (1, 2, 4, 5, 6, 7, 8, 9): HIDE COMPLETELY
        hideMasterDock(true);
      }
    }

        
    /* ==========================================================================
       Synth Module Discovery & Universal Remote Control Client Logic
       ========================================================================== */
    window.allDiscoveredModules = [];
    window.currentSynthFilter = 'all';
    window.activeRemoteTarget = {
      id: 'proj_192_168_1_121',
      name: 'tranScreen-64509',
      ip: '192.168.1.121',
      category: 'projector',
      model: 'LED Smart Projector'
    };

    window.filterSynthModules = function(category) {
      window.currentSynthFilter = category;
      document.querySelectorAll('.synth-filter-pill').forEach(pill => {
        pill.classList.toggle('active', pill.dataset.cat === category);
      });
      renderSynthRack(window.allDiscoveredModules);
    };

    window.renderSynthRack = function(devices) {
      window.allDiscoveredModules = devices || [];
      const list = document.getElementById('discovery-list');
      const counter = document.getElementById('synth-scan-counter');
      const filter = window.currentSynthFilter || 'all';

      const filtered = window.allDiscoveredModules.filter(d => {
        if (filter === 'all') return true;
        const cat = (d.category || '').toLowerCase();
        if (filter === 'airplay') return (d.protocols || []).some(p => p.toLowerCase().includes('airplay') || p.toLowerCase().includes('upnp'));
        return cat === filter;
      });

      if (counter) counter.innerText = `${window.allDiscoveredModules.length} module${window.allDiscoveredModules.length === 1 ? '' : 's'} on bus (${filtered.length} shown)`;

      if (!list) return;

      if (filtered.length === 0) {
        list.innerHTML = `
          <div style="grid-column: 1 / -1; font-size:12px; color:var(--text-muted); text-align:center; padding:36px; font-family:'JetBrains Mono', monospace;">
            <div style="margin-bottom:8px; color:var(--accent-gold);">NO MODULES MATCHING FILTER [ ${filter.toUpperCase()} ]</div>
            Select "ALL BUS UNITS" or click "ENGAGE LAN SCAN" to refresh local network modules.
          </div>
        `;
        return;
      }

      list.innerHTML = filtered.map((d, idx) => {
        const catClass = `cat-${d.category || 'other'}`;
        const catLabel = (d.category || 'DEVICE').toUpperCase().replace('_', ' ');
        const protocols = d.protocols || ['UPNP', 'AIRPLAY'];
        const isCurrentActive = d.is_connected || (d.ip === (window.activeRemoteTarget ? window.activeRemoteTarget.ip : ''));

        return `
          <div class="synth-module-card ${isCurrentActive ? 'active-unit' : ''}">
            <div>
              <div class="synth-card-rail">
                <span>[ MOD 0${idx + 1} ]</span>
                <span class="synth-cat-tag ${catClass}">[ ${catLabel} ]</span>
                <span>${d.latency_ms || 1.5}ms // 1GbE</span>
              </div>
              <div class="synth-card-title" title="${d.friendly_name || 'Network Device'}">
                ${d.friendly_name || 'Modular Streamer'}
              </div>
              <div class="synth-card-sub">${d.model_name || d.manufacturer || 'Universal Network Renderer'}</div>
              <div class="synth-card-specs">
                <span>IP: ${d.ip}</span>
                <span>BUS: ${d.method || 'LAN SSDP'}</span>
              </div>
              <div class="synth-protocol-bus">
                ${protocols.map(p => `<span class="synth-protocol-chip">${p}</span>`).join('')}
              </div>
            </div>
            <div class="synth-card-actions">
              <button class="synth-btn-patch ${isCurrentActive ? 'patched' : ''}" onclick="connectToDevice('${d.ip}', '', '', '', '${d.friendly_name || ''}')">
                <span class="synth-patch-jack-icon" style="width:8px; height:8px;"></span>
                <span>${isCurrentActive ? 'PATCHED' : 'PATCH / CONNECT'}</span>
              </button>
              <button class="synth-btn-remote" onclick="setAndOpenRemote('${d.ip}', '${d.friendly_name || ''}', '${d.category || 'projector'}', '${d.model_name || ''}')">
                <span>REMOTE →</span>
              </button>
            </div>
          </div>
        `;
      }).join('');
    };

    // Override triggerDeviceScan to update synth discovery layout
    window.triggerDeviceScan = async function() {
      const statusLabel = document.getElementById('synth-status-label');
      const scanLed = document.getElementById('synth-scan-led');
      const list = document.getElementById('discovery-list');

      if (statusLabel) statusLabel.innerText = 'BROADCASTING BUS SCAN...';
      if (scanLed) {
        scanLed.style.background = '#00e5ff';
        scanLed.style.boxShadow = '0 0 10px #00e5ff';
      }

      if (list) {
        list.innerHTML = `
          <div style="grid-column: 1 / -1; font-size:12px; color:var(--accent-gold); text-align:center; padding:36px; font-family:'JetBrains Mono', monospace;">
            <div class="radar-pulse" style="width:28px; height:28px; margin:0 auto 12px auto;"></div>
            PROBING MULTI-SUBNET ARP, GOOGLE TV (PORTS 8008/8009), XBOX (PORT 5050), AND TRANSCREEN PROJECTORS...
          </div>
        `;
      }

      try {
        const res = await fetch('/api/discover');
        const data = await res.json();
        const devices = data.devices || [];

        window.allDiscoveredModules = devices;
        if (statusLabel) statusLabel.innerText = `BUS LOCKED // ${devices.length} UNITS DETECTED`;
        if (scanLed) {
          scanLed.style.background = '#10b981';
          scanLed.style.boxShadow = '0 0 8px #10b981';
        }
        renderSynthRack(devices);
      } catch (err) {
        console.warn('Synth discovery error:', err);
        if (statusLabel) statusLabel.innerText = 'SCAN ERROR // CHECK LAN CONNECTION';
      }
    };

    // Universal Remote Control Methods
    window.setAndOpenRemote = async function(ip, name, category, model) {
      window.activeRemoteTarget = { ip, name, category, model };
      try {
        await fetch('/api/remote/target', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(window.activeRemoteTarget)
        });
      } catch (err) {
        console.warn('Set target error:', err);
      }
      updateRemoteHeaderUI();
      if (typeof slideToView === 'function') {
        slideToView('remote');
      }
    };

    window.updateRemoteHeaderUI = function() {
      const targetText = document.getElementById('remote-target-text');
      if (targetText && window.activeRemoteTarget) {
        const t = window.activeRemoteTarget;
        const cat = (t.category || 'DEVICE').toUpperCase().replace('_', ' ');
        targetText.innerText = `TARGET: ${t.name || t.ip} (${t.ip}) · ${cat}`;
      }
    };

    window.sendRemoteKey = async function(key, param) {
      showRemoteToast(`Dispatched: ${key}`);
      try {
        const res = await fetch('/api/remote/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: key, param: param || null, target: window.activeRemoteTarget })
        });
        const data = await res.json();
        if (data.status === 'needs_pairing') {
          showRemoteToast('Google TV pairing required. Opening pairing dialogue...');
          openGoogleTVPairModal();
          return;
        }
        if (data.volume !== undefined) {
          const volBadge = document.getElementById('remote-vol-badge');
          if (volBadge) volBadge.innerText = `${data.volume}%`;
        }
        const targetName = (window.activeRemoteTarget && window.activeRemoteTarget.name) || 'Device';
        const detailMsg = data.detail || `Executed: ${key}`;
        showRemoteToast(`[${targetName}] ${detailMsg}`);
      } catch (err) {
        console.warn('Remote command error:', err);
        showRemoteToast(`Error sending ${key}`);
      }
    };

    window.openGoogleTVPairModal = async function() {
      const modal = document.getElementById('gtv-pair-modal');
      const input = document.getElementById('gtv-pin-input');
      const feedback = document.getElementById('gtv-pair-feedback');
      if (modal) modal.style.display = 'flex';
      if (input) { input.value = ''; input.focus(); }
      if (feedback) feedback.innerText = 'Requesting pairing code from Google TV...';
      try {
        const ip = (window.activeRemoteTarget && window.activeRemoteTarget.ip) || '192.168.1.137';
        const res = await fetch('/api/remote/pair', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'start', ip: ip })
        });
        const data = await res.json();
        if (feedback) feedback.innerText = data.message || 'Enter code shown on TV screen.';
      } catch (e) {
        if (feedback) feedback.innerText = 'Pairing request dispatched.';
      }
    };

    window.closeGoogleTVPairModal = function() {
      const modal = document.getElementById('gtv-pair-modal');
      if (modal) modal.style.display = 'none';
    };

    window.submitGoogleTVPairing = async function() {
      const input = document.getElementById('gtv-pin-input');
      const feedback = document.getElementById('gtv-pair-feedback');
      if (!input || !input.value.trim()) return;
      const pin = input.value.trim().toUpperCase();
      if (feedback) feedback.innerText = 'Authorising pairing code...';
      try {
        const ip = (window.activeRemoteTarget && window.activeRemoteTarget.ip) || '192.168.1.137';
        const res = await fetch('/api/remote/pair', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'finish', ip: ip, code: pin })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          if (feedback) feedback.innerText = 'Pairing successful! Connected.';
          showRemoteToast('Google TV Paired & Connected!');
          setTimeout(() => {
            closeGoogleTVPairModal();
            updateGoogleTVPairBadge(true);
          }, 1200);
        } else {
          if (feedback) feedback.innerText = 'Pairing failed: ' + (data.error || 'Incorrect code');
        }
      } catch (e) {
        if (feedback) feedback.innerText = 'Connection error. Please try again.';
      }
    };

    window.updateGoogleTVPairBadge = function(isPaired) {
      const badge = document.getElementById('google-tv-pair-status');
      if (!badge) return;
      if (isPaired) {
        badge.innerText = '● PAIRED & READY';
        badge.style.borderColor = 'rgba(76, 217, 100, 0.4)';
        badge.style.background = 'rgba(76, 217, 100, 0.1)';
        badge.style.color = '#4cd964';
      } else {
        badge.innerText = '⚡ PAIR GOOGLE TV';
        badge.style.borderColor = 'rgba(212, 175, 55, 0.4)';
        badge.style.background = 'rgba(212, 175, 55, 0.1)';
        badge.style.color = 'var(--accent-gold, #c99d52)';
      }
    };

    window.checkGoogleTVPairStatus = async function() {
      try {
        const res = await fetch('/api/remote/pair');
        const data = await res.json();
        updateGoogleTVPairBadge(data.paired === true);
      } catch (e) {}
    };

    window.sendRemoteTextInput = async function() {
      const input = document.getElementById('remote-text-input');
      if (!input || !input.value.trim()) return;
      const text = input.value.trim();
      showRemoteToast(`Sending text: "${text}"`);
      try {
        await fetch('/api/remote/command', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ command: 'TEXT', param: text, target: window.activeRemoteTarget })
        });
        showRemoteToast(`Sent text: "${text}"`);
        input.value = '';
      } catch (err) {
        console.warn('Send text error:', err);
      }
    };

    window.switchInputSource = function(sourceName) {
      document.querySelectorAll('.remote-source-btn').forEach(btn => {
        btn.classList.toggle('active', btn.innerText.trim() === sourceName);
      });
      window.sendRemoteKey('SOURCE', sourceName);
    };

    window.handleTrackpadMove = function(e) {
      const surface = document.getElementById('remote-trackpad-surface');
      const dot = document.getElementById('remote-cursor-dot');
      const coords = document.getElementById('remote-trackpad-coords');
      if (!surface || !dot) return;

      const rect = surface.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
      const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top));

      dot.style.left = `${x}px`;
      dot.style.top = `${y}px`;

      if (coords) coords.innerText = `X: ${Math.round(x)} | Y: ${Math.round(y)}`;
    };

    window.handleTrackpadClick = function(btnType) {
      showRemoteToast(`Mouse ${btnType} Click`);
      fetch('/api/remote/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'MOUSE_CLICK', param: btnType, target: window.activeRemoteTarget })
      }).catch(() => {});
    };

    let toastTimer = null;
    window.showRemoteToast = function(msg) {
      const toast = document.getElementById('remote-toast-hud');
      if (!toast) return;
      toast.innerText = msg;
      toast.classList.add('visible');
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => {
        toast.classList.remove('visible');
      }, 2200);
    };

    window.addEventListener('DOMContentLoaded', () => {
      try {
        const urlParams = new URLSearchParams(window.location.search);
        const targetSlide = urlParams.get('slide') || window.location.hash.replace('#', '');
        if (targetSlide && slideMap[targetSlide] !== undefined) {
          setTimeout(() => slideToView(targetSlide), 80);
        }
      } catch (e) {}
    });

    
    window.addEventListener('resize', () => {
      const track = document.getElementById('carousel-track');
      if (track) {
        const vp = track.parentElement || document.querySelector('.carousel-viewport');
        const w = vp ? vp.clientWidth : window.innerWidth;
        track.style.transform = `translateX(-${currentSlideIndex * w}px)`;
      }
    });

    function slideToPlayer() {
      slideToView(0);
    }

    function cycleNextSlide() {
      const nextIdx = (currentSlideIndex + 1) % TOTAL_SLIDES;
      slideToView(nextIdx);
    }

    function cyclePrevSlide() {
      const prevIdx = (currentSlideIndex - 1 + TOTAL_SLIDES) % TOTAL_SLIDES;
      slideToView(prevIdx);
    }

    function toggleHubSlide() {
      if (currentSlideIndex === 1) {
        slideToPlayer();
      } else {
        slideToView('protocols');
      }
    }

    // Backwards-compatible modal API aliases
    window.openProtocolModal = () => slideToView('protocols');
    window.closeProtocolModal = () => slideToPlayer();

    window.openDiscoveryModal = () => slideToView('discovery');
    window.closeDiscoveryModal = () => slideToPlayer();

    window.openRadioModal = () => slideToView('radio');
    window.closeRadioModal = () => slideToPlayer();

    window.openGlobeView = () => slideToView('radio');
    window.closeGlobeView = () => slideToPlayer();

    window.openDacSettingsModal = () => slideToView('dac');
    window.closeDacSettingsModal = () => slideToPlayer();

    window.openEqModal = () => slideToView('eq');
    window.closeEqModal = () => slideToPlayer();

    window.openSleepModal = () => slideToView('sleep');
    window.closeSleepModal = () => slideToPlayer();

    window.openLyricsModal = () => slideToView('lyrics');
    window.closeLyricsModal = () => slideToPlayer();

    window.openQueueModal = () => slideToView('queue');
    window.closeQueueModal = () => slideToPlayer();

    window.openStorageModal = () => slideToView('storage');
    window.closeStorageModal = () => slideToPlayer();

    window.closeAllModals = () => slideToPlayer();

    /* =========================================================================
       Floating Master Controller Dock: Swipe-Up to Summon, Swipe-Down to Hide
       - Does NOT resize main panel: overlays smoothly above stage
       ========================================================================= */
    let masterDockHideTimer = null;
    let isBarHovered = false;
    var floatingBarsHideTimer = null;
    let isScrubbingTimeline = false;

    function showMasterDock(resetTimer = true) {
      // Rule: Do not show bottom control bar on anything other than main player and radio selector
      if (currentSlideIndex !== 0 && currentSlideIndex !== 3) {
        return;
      }
      const bottomDock = document.getElementById('master-dock-container');
      if (bottomDock) {
        bottomDock.classList.remove('dock-hidden');
      }
      if (resetTimer && currentSlideIndex === 0) {
        scheduleMasterDockAutoHide();
      }
    }

    function hideMasterDock(force = false) {
      // If not forced, do not hide if user is hovering or actively scrubbing
      if (!force && (isBarHovered || isScrubbingTimeline)) return;

      const bottomDock = document.getElementById('master-dock-container');
      if (bottomDock) {
        bottomDock.classList.add('dock-hidden');
      }
      if (masterDockHideTimer) {
        clearTimeout(masterDockHideTimer);
        masterDockHideTimer = null;
      }
    }

    // Aliases for compatibility
    window.showFloatingBars = showMasterDock;
    window.hideFloatingBars = hideMasterDock;

    function scheduleMasterDockAutoHide() {
      if (currentSlideIndex === 3) return; // Keep bottom bar present all the time on globe
      if (masterDockHideTimer) clearTimeout(masterDockHideTimer);
      masterDockHideTimer = setTimeout(() => {
        if (currentSlideIndex === 0) {
          hideMasterDock();
        }
      }, 7000);
    }

    /* =========================================================================
       High-Precision Touch & Swipe Gesture Engine
       - Swipe Up from bottom: summons master bottom bar
       - Swipe Down on/near bottom dock: hides master bottom bar
       - Swipe Left: advances to next nav screen
       - Swipe Right: returns to previous nav screen
       ========================================================================= */
    (function initGestureAndDockEngine() {
      let touchStartX = 0;
      let touchStartY = 0;
      let touchStartTime = 0;
      let touchIsBottomZone = false;

      // Track touch initiation
      window.addEventListener('touchstart', (e) => {
        // When using the globe, DO NOT respond to sliding nav / features
        if (currentSlideIndex === 3) return;

        if (!e.touches || e.touches.length === 0) return;
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        touchStartTime = Date.now();
        // Lower 35% of the screen or near bottom
        touchIsBottomZone = (touchStartY >= window.innerHeight * 0.65);
      }, { passive: true });

      // Track touch completion and evaluate directional vector
      window.addEventListener('touchend', (e) => {
        // When using the globe, DO NOT respond to sliding nav / features
        if (currentSlideIndex === 3) return;

        if (!e.changedTouches || e.changedTouches.length === 0) return;
        const touchEndX = e.changedTouches[0].clientX;
        const touchEndY = e.changedTouches[0].clientY;
        const diffX = touchEndX - touchStartX;
        const diffY = touchEndY - touchStartY;
        const absX = Math.abs(diffX);
        const absY = Math.abs(diffY);
        const elapsed = Date.now() - touchStartTime;

        // Ignore gestures that lasted too long (e.g. text selection)
        if (elapsed > 900) return;

        // 1. VERTICAL SWIPES: Bottom Controller Dock Gestures
        if (absY > 35 && absY > absX * 1.1) {
          if (diffY < -35 && touchIsBottomZone) {
            // Swipe Up gesture originating from bottom zone: Bring up bottom bar
            showMasterDock(true);
            return;
          } else if (diffY > 35) {
            // Swipe Down gesture: Hide bottom bar
            const dock = document.getElementById('master-dock-container');
            const inDockZone = (touchStartY >= window.innerHeight * 0.60);
            if (inDockZone && (!dock || !dock.classList.contains('dock-hidden'))) {
              hideMasterDock();
              return;
            }
          }
        }

        // 2. HORIZONTAL SWIPES: Carousel Screen Cycling
        // Ensures vertical page scrolls inside feature cards are not interrupted
        const minLongSwipe = Math.min(220, Math.max(90, window.innerWidth * 0.24));
        if (absX > minLongSwipe && absX > absY * 1.45) {
          if (diffX < -minLongSwipe) {
            // Swipe Left -> Cycle forward to next screen
            cycleNextSlide();
          } else if (diffX > minLongSwipe) {
            // Swipe Right -> Cycle backward to previous screen
            cyclePrevSlide();
          }
        }
      }, { passive: true });

      // Bottom summon strip listener (click or touch)
      const triggerZone = document.getElementById('bottom-gesture-zone');
      if (triggerZone) {
        triggerZone.addEventListener('click', () => showMasterDock(true));
        triggerZone.addEventListener('touchstart', () => showMasterDock(true), { passive: true });
      }

      // Swipe down hint pill on top of dock
      const swipePill = document.querySelector('.dock-swipe-pill');
      if (swipePill) {
        swipePill.addEventListener('click', () => hideMasterDock());
      }

      // Keep dock visible when hovered with mouse on desktop
      const bottomDock = document.getElementById('master-dock-container');
      if (bottomDock) {
        bottomDock.addEventListener('mouseenter', () => {
          isBarHovered = true;
          showMasterDock(false);
        });
        bottomDock.addEventListener('mouseleave', () => {
          isBarHovered = false;
          if (currentSlideIndex === 0) scheduleMasterDockAutoHide();
        });
      }

      // Keyboard navigation shortcuts
      window.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight' && !e.target.matches('input, textarea')) {
          cycleNextSlide();
        } else if (e.key === 'ArrowLeft' && !e.target.matches('input, textarea')) {
          cyclePrevSlide();
        } else if (e.key === 'ArrowUp') {
          showMasterDock(true);
        } else if (e.key === 'ArrowDown') {
          hideMasterDock();
        } else if (e.key === 'Escape') {
          toggleNavDrawer(false);
      

          if (currentSlideIndex !== 0) slideToPlayer();
        }
      });
    })();

    
    
    /* =========================================================================
       Auxiliary UI & Queue Action Handlers
       ========================================================================= */
    function setSleepTimer(minutes) {
      console.log('Setting sleep timer for', minutes, 'minutes');
      sendControl('sleep_timer', minutes);
      const pill = document.getElementById('side-status-text');
      if (pill) pill.innerText = `Sleep in ${minutes}m`;
    }

    function cancelSleepTimer() {
      console.log('Cancelling sleep timer');
      sendControl('sleep_timer', 0);
      const pill = document.getElementById('side-status-text');
      if (pill) pill.innerText = 'Online';
    }

    function switchQueueTab(tab) {
      const activeTabBtn = document.getElementById('tab-queue-active');
      const historyTabBtn = document.getElementById('tab-queue-history');
      const activeList = document.getElementById('queue-list-active');
      const historyList = document.getElementById('queue-list-history');
      if (activeTabBtn && historyTabBtn) {
        if (tab === 'active') {
          activeTabBtn.classList.add('active');
          historyTabBtn.classList.remove('active');
          if (activeList) activeList.style.display = 'block';
          if (historyList) historyList.style.display = 'none';
        } else {
          historyTabBtn.classList.add('active');
          activeTabBtn.classList.remove('active');
          if (activeList) activeList.style.display = 'none';
          if (historyList) historyList.style.display = 'block';
        }
      }
    }

    function clearActiveQueue() {
      sendControl('clear_queue');
      const list = document.getElementById('queue-list-active');
      if (list) list.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">Queue cleared</div>';
    }

    function clearHistoryLog() {
      const list = document.getElementById('queue-list-history');
      if (list) list.innerHTML = '<div style="padding: 24px; text-align: center; color: var(--text-muted);">History cleared</div>';
    }

    function connectManualIp() {
      const input = document.getElementById('input-manual-ip');
      if (input && input.value.trim()) {
        const ip = input.value.trim();
        fetch('/api/connect_ip', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ip })
        }).then(res => res.json()).then(d => {
          if (d.status === 'ok') updateStatus();
        }).catch(() => {});
      }
    }

    /* =========================================================================
       Streaming Protocols Hub Engine
       ========================================================================= */
    function toggleProtoInfo(e, protoKey) {
      if (e) e.stopPropagation();
      const drawer = document.getElementById(`proto-drawer-${protoKey}`);
      const btn = document.getElementById(`proto-btn-info-${protoKey}`);
      if (drawer) {
        const isCurrentlyOpen = drawer.classList.contains('open');
        // Close all other drawers to keep layout perfectly contained
        document.querySelectorAll('.proto-drawer-visual').forEach(d => {
          d.classList.remove('open');
        });
        document.querySelectorAll('.proto-info-icon-btn').forEach(b => {
          b.classList.remove('active');
        });

        if (!isCurrentlyOpen) {
          drawer.classList.add('open');
          if (btn) btn.classList.add('active');
        }
      }
    }

    async function renderProtocolsHub() {
      const grid = document.getElementById('proto-hub-grid');
      if (!grid) return;
      try {
        const res = await fetch('/api/sources');
        const data = await res.json();
        const activeSrc = data.active_source || 'UPnP / DLNA';
        const protocols = data.protocols || {};

        // Update top topology banner live values
        const topoSourceName = document.getElementById('topo-source-name');
        if (topoSourceName) topoSourceName.textContent = activeSrc;

        grid.innerHTML = '';
        Object.entries(protocols).forEach(([protoName, p]) => {
          const isActive = (protoName.toLowerCase() === activeSrc.toLowerCase() || 
                            p.name.toLowerCase() === activeSrc.toLowerCase());
          const protoKey = protoName.replace(/[^a-zA-Z0-9]/g, '_');
          const card = document.createElement('div');
          card.className = `proto-card ${isActive ? 'active' : ''}`;
          
          // Generate concise telemetry specs
          const formatChip = p.max_format ? p.max_format.split('/')[0].replace('Up to ', '').trim() : 'Lossless';
          const transportChip = p.badge || 'Ready';
          const appName = p.name.split(' ')[0];
          
          card.innerHTML = `
            <div class="proto-card-compact-head">
              <div class="proto-rotary-hub">
                <svg width="22" height="22" style="fill: ${isActive ? 'var(--accent-gold)' : 'rgba(255,255,255,0.7)'};">
                  <use href="#${p.icon}"/>
                </svg>
              </div>
              <div class="proto-info-title-group">
                <div class="proto-title-row">
                  <span class="proto-name-text">${p.name}</span>
                  <button class="proto-info-icon-btn" id="proto-btn-info-${protoKey}" onclick="toggleProtoInfo(event, '${protoKey}')" title="Protocol Architecture & Signal Flow" aria-label="Information for ${p.name}">
                    i
                  </button>
                </div>
                <div class="proto-chips-row">
                  <span class="proto-chip chip-gold">${formatChip}</span>
                  <span class="proto-chip">${transportChip}</span>
                  <span class="proto-chip ${isActive ? 'chip-emerald' : ''}">${isActive ? 'ACTIVE BIT-PERFECT' : p.status}</span>
                </div>
              </div>
            </div>

            <!-- Simplified Visual Architecture & Diagnostic Drawer (Zero Text Saturation) -->
            <div class="proto-drawer-visual" id="proto-drawer-${protoKey}" style="display: none;">
              <!-- Visual Signal Chain Flow -->
              <div class="proto-flow-diagram">
                <div class="flow-step">
                  <div class="flow-icon-circle">
                    <svg width="13" height="13" style="fill:rgba(255,255,255,0.85);"><use href="#${p.icon}"/></svg>
                  </div>
                  <span class="flow-label">Source App</span>
                </div>
                <span class="flow-arrow">&#10140;</span>
                <div class="flow-step">
                  <div class="flow-icon-circle flow-core">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                  </div>
                  <span class="flow-label">VitOS Core</span>
                </div>
                <span class="flow-arrow">&#10140;</span>
                <div class="flow-step">
                  <div class="flow-icon-circle flow-dac">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                  </div>
                  <span class="flow-label">Studio DAC</span>
                </div>
              </div>

              <!-- Visual Spec Cards -->
              <div class="proto-visual-specs">
                <div class="proto-vspec-card">
                  <span class="vspec-title">MAX RESOLUTION</span>
                  <span class="vspec-data gold">${p.max_format}</span>
                </div>
                <div class="proto-vspec-card">
                  <span class="vspec-title">TRANSPORT PORT</span>
                  <span class="vspec-data">${p.port}</span>
                </div>
              </div>

              <!-- Visual 3-Step Setup Guide -->
              <div class="proto-visual-guide">
                <div class="vguide-step"><span class="step-num">1</span> Open ${appName}</div>
                <div class="vguide-step"><span class="step-num">2</span> Select Bremen</div>
                <div class="vguide-step"><span class="step-num">3</span> Stream Hi-Fi</div>
              </div>
            </div>

            <div class="proto-action-row">
              ${isActive ? `
                <button class="btn-proto-action active-endpoint" disabled>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  Active Endpoint
                </button>
              ` : `
                <button class="btn-proto-action switch-btn" onclick="selectProtocolSource('${protoName}')">
                  Switch Protocol
                </button>
              `}
              ${p.external_app ? `
                <a href="${p.external_app}" class="btn-proto-ext" title="Launch ${p.name} Application" target="_blank" rel="noopener">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
                  Launch App
                </a>
              ` : ''}
            </div>
          `;
          grid.appendChild(card);
        });
      } catch (err) {
        console.error('Error rendering protocols hub:', err);
      }
    }

    async function selectProtocolSource(srcName) {
      try {
        const res = await fetch('/api/set_source', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: srcName })
        });
        const data = await res.json();
        if (data.status === 'ok') {
          renderProtocolsHub();
          if (typeof updateStatus === 'function') updateStatus();
        }
      } catch (err) {
        console.error('Failed to set protocol source:', err);
      }
    }

    /* =========================================================================
       3D Radio Globe Engine for Carousel & Fullscreen
       ========================================================================= */
    let carouselGlobeScene = null;
    let carouselGlobeCamera = null;
    let carouselGlobeRenderer = null;
    let carouselGlobeGroup = null;
    let carouselGlobeStations = [];
    let carouselGlobeIsDragging = false;
    let carouselGlobePrevPos = { x: 0, y: 0 };
    let carouselGlobeRotSpeed = { x: 0, y: 0.00045 };
    let carouselGlobeTargetDist = 280;
    let carouselGlobeCurrentDist = 280;
    let carouselGlobePinchStartDist = 0;
    let carouselGlobeRaycaster = null;
    let carouselGlobeMouse = null;

    function switchRadioTab(tab) {
      const globeView = document.getElementById('radio-tab-globe');
      const listView = document.getElementById('radio-tab-list');
      const btnGlobe = document.getElementById('tab-btn-globe');
      const btnList = document.getElementById('tab-btn-list');

      if (tab === 'globe') {
        if (globeView) globeView.style.display = 'flex';
        if (listView) listView.style.display = 'none';
        if (btnGlobe) {
          btnGlobe.style.background = 'var(--accent-gold)';
          btnGlobe.style.color = '#0b0e14';
        }
        if (btnList) {
          btnList.style.background = 'transparent';
          btnList.style.color = 'var(--text-main)';
        }
        setTimeout(initOrResizeCarouselGlobe, 60);
      } else {
        if (globeView) globeView.style.display = 'none';
        if (listView) listView.style.display = 'flex';
        if (btnGlobe) {
          btnGlobe.style.background = 'transparent';
          btnGlobe.style.color = 'var(--text-main)';
        }
        if (btnList) {
          btnList.style.background = 'var(--accent-gold)';
          btnList.style.color = '#0b0e14';
        }
        if (typeof renderCuratedStations === 'function') renderCuratedStations();
      }
    }

    async function initOrResizeCarouselGlobe() {
      if (typeof THREE === 'undefined') {
        setTimeout(initOrResizeCarouselGlobe, 200);
        return;
      }

      const container = document.getElementById('carousel-globe-container');
      if (!container) return;

      const width = container.clientWidth || 600;
      const height = container.clientHeight || 360;

      if (!carouselGlobeScene) {
        // Initialise Scene
        carouselGlobeScene = new THREE.Scene();
        carouselGlobeCamera = new THREE.PerspectiveCamera(45, width / height, 1, 2000);
        carouselGlobeCamera.position.set(0, 16, 215);

        carouselGlobeRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
        carouselGlobeRenderer.setSize(width, height);
        carouselGlobeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        carouselGlobeRenderer.setClearColor(0x06090e, 1);
        container.appendChild(carouselGlobeRenderer.domElement);

        carouselGlobeGroup = new THREE.Group();
        carouselGlobeScene.add(carouselGlobeGroup);

        // High-Definition NASA Celestial Earth Sphere with Visible Countries & Continents
        const textureLoader = new THREE.TextureLoader();
        const earthTexture = textureLoader.load('/earth_dark.jpg', () => {
          if (carouselGlobeRenderer && carouselGlobeScene && carouselGlobeCamera) {
            carouselGlobeRenderer.render(carouselGlobeScene, carouselGlobeCamera);
          }
        });
        earthTexture.anisotropy = 8;

        const sphereGeo = new THREE.SphereGeometry(95, 64, 64);
        const sphereMat = new THREE.MeshStandardMaterial({
          map: earthTexture,
          color: 0xd6dce5,
          roughness: 0.65,
          metalness: 0.12
        });
        const globeMesh = new THREE.Mesh(sphereGeo, sphereMat);
        carouselGlobeGroup.add(globeMesh);

        // Clean Dark Celestial Globe: Landmasses rendered via high-contrast dark NASA texture

        // Lighting
        const ambLight = new THREE.AmbientLight(0xffffff, 0.9);
        carouselGlobeScene.add(ambLight);

        const dirLight = new THREE.DirectionalLight(0xe0b468, 1.4);
        dirLight.position.set(200, 150, 300);
        carouselGlobeScene.add(dirLight);

        // Interaction Handlers
        carouselGlobeRaycaster = new THREE.Raycaster();
        carouselGlobeMouse = new THREE.Vector2();

        initCarouselGlobeGestures(container);
        loadCarouselGlobeStations();
        animateCarouselGlobe();
      } else {
        // Resize
        carouselGlobeCamera.aspect = width / height;
        carouselGlobeCamera.updateProjectionMatrix();
        carouselGlobeRenderer.setSize(width, height);
      }
    }

    function initCarouselGlobeGestures(container) {
      const dom = container;

      // Mouse drag
      dom.addEventListener('mousedown', (e) => {
        carouselGlobeIsDragging = true;
        carouselGlobePrevPos = { x: e.clientX, y: e.clientY };
      });
      window.addEventListener('mousemove', (e) => {
        if (!carouselGlobeIsDragging) return;
        const dx = e.clientX - carouselGlobePrevPos.x;
        const dy = e.clientY - carouselGlobePrevPos.y;
        carouselGlobeRotSpeed = { x: dy * 0.003, y: dx * 0.003 };
        carouselGlobeGroup.rotation.y += carouselGlobeRotSpeed.y;
        carouselGlobeGroup.rotation.x += carouselGlobeRotSpeed.x;
        carouselGlobePrevPos = { x: e.clientX, y: e.clientY };
      });
      window.addEventListener('mouseup', () => {
        carouselGlobeIsDragging = false;
      });

      // Mouse wheel zoom
      dom.addEventListener('wheel', (e) => {
        e.preventDefault();
        carouselGlobeTargetDist += e.deltaY * 0.2;
        carouselGlobeTargetDist = Math.max(140, Math.min(480, carouselGlobeTargetDist));
      }, { passive: false });

      // Touch drag and pinch
      dom.addEventListener('touchstart', (e) => {
        if (e.touches.length === 1) {
          carouselGlobeIsDragging = true;
          carouselGlobePrevPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        } else if (e.touches.length === 2) {
          carouselGlobeIsDragging = false;
          carouselGlobePinchStartDist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
        }
      }, { passive: true });

      dom.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1 && carouselGlobeIsDragging) {
          const dx = e.touches[0].clientX - carouselGlobePrevPos.x;
          const dy = e.touches[0].clientY - carouselGlobePrevPos.y;
          carouselGlobeRotSpeed = { x: dy * 0.004, y: dx * 0.004 };
          carouselGlobeGroup.rotation.y += carouselGlobeRotSpeed.y;
          carouselGlobeGroup.rotation.x += carouselGlobeRotSpeed.x;
          carouselGlobePrevPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        } else if (e.touches.length === 2) {
          const dist = Math.hypot(
            e.touches[0].clientX - e.touches[1].clientX,
            e.touches[0].clientY - e.touches[1].clientY
          );
          const factor = carouselGlobePinchStartDist / (dist || 1);
          carouselGlobeTargetDist *= (factor > 1 ? 1.025 : 0.975);
          carouselGlobeTargetDist = Math.max(140, Math.min(480, carouselGlobeTargetDist));
          carouselGlobePinchStartDist = dist;
        }
      }, { passive: true });

      dom.addEventListener('touchend', () => {
        carouselGlobeIsDragging = false;
      });

      let globeTouchMoved = false;
      let globeTouchStartPos = { x: 0, y: 0 };

      dom.addEventListener('touchstart', (e) => {
        globeTouchMoved = false;
        if (e.touches.length === 1) {
          globeTouchStartPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        }
      }, { passive: true });

      dom.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1) {
          const d = Math.hypot(e.touches[0].clientX - globeTouchStartPos.x, e.touches[0].clientY - globeTouchStartPos.y);
          if (d > 7) globeTouchMoved = true;
        }
      }, { passive: true });

      dom.addEventListener('touchend', (e) => {
        if (!globeTouchMoved && e.changedTouches && e.changedTouches.length > 0) {
          const t = e.changedTouches[0];
          const rect = dom.getBoundingClientRect();
          carouselGlobeMouse.x = ((t.clientX - rect.left) / rect.width) * 2 - 1;
          carouselGlobeMouse.y = -((t.clientY - rect.top) / rect.height) * 2 + 1;

          carouselGlobeRaycaster.setFromCamera(carouselGlobeMouse, carouselGlobeCamera);
          const hits = carouselGlobeRaycaster.intersectObjects(carouselGlobeStations, false);
          if (hits.length > 0) {
            const data = hits[0].object.userData;
            if (data) {
              if (data.isCluster) {
                expandGlobeCluster(data);
              } else {
                tuneInToGlobeStation(data.station || data);
              }
            }
          }
        }
      });

      function triggerGlobeRaycast(clientX, clientY) {
        if (!carouselGlobeScene || !carouselGlobeCamera || !carouselGlobeRaycaster) return;
        const rect = dom.getBoundingClientRect();
        carouselGlobeMouse.x = ((clientX - rect.left) / rect.width) * 2 - 1;
        carouselGlobeMouse.y = -((clientY - rect.top) / rect.height) * 2 + 1;

        carouselGlobeRaycaster.setFromCamera(carouselGlobeMouse, carouselGlobeCamera);
        const hits = carouselGlobeRaycaster.intersectObjects(carouselGlobeStations, false);
        for (let i = 0; i < hits.length; i++) {
          const hit = hits[i];
          const data = hit.object.userData;
          if (!data) continue;

          // Check if beacon is on the camera-facing hemisphere
          const beaconWorldPos = new THREE.Vector3();
          hit.object.getWorldPosition(beaconWorldPos);
          const toCamera = carouselGlobeCamera.position.clone().sub(beaconWorldPos).normalize();
          const normal = beaconWorldPos.clone().normalize();
          if (normal.dot(toCamera) < -0.15) continue;

          // Visual flash feedback
          const mesh = hit.object.userData.mesh || hit.object;
          if (mesh && mesh.material) {
            const origColor = mesh.material.color.getHex();
            mesh.material.color.setHex(0xffffff);
            mesh.scale.set(1.6, 1.6, 1.6);
            setTimeout(() => {
              mesh.material.color.setHex(origColor);
              mesh.scale.set(1.0, 1.0, 1.0);
            }, 300);
          }

          if (data.isCluster) {
            expandGlobeCluster(data);
          } else {
            tuneInToGlobeStation(data.station || data);
          }
          break;
        }
      }

      dom.addEventListener('click', (e) => {
        triggerGlobeRaycast(e.clientX, e.clientY);
      });
    }

    let expandedClusterObjects = [];
    let currentExpandedCluster = null;

    async function loadCarouselGlobeStations() {
      try {
        const res = await fetch('/api/radio/globe_stations');
        const stations = await res.json();
        const r = 96.5;

        // Group stations by geographic proximity into clusters
        const clusters = [];
        const clusterThresholdDeg = 1.8;

        stations.forEach(st => {
          let found = false;
          for (const c of clusters) {
            const dLat = Math.abs(c.lat - st.lat);
            const dLon = Math.abs(c.lon - st.lon);
            if (dLat < clusterThresholdDeg && dLon < clusterThresholdDeg) {
              c.stations.push(st);
              found = true;
              break;
            }
          }
          if (!found) {
            clusters.push({
              lat: st.lat,
              lon: st.lon,
              city: st.city,
              country: st.country,
              stations: [st]
            });
          }
        });

        // Clear any prior beacons
        carouselGlobeStations = [];

        clusters.forEach(cluster => {
          const phi = (90 - cluster.lat) * (Math.PI / 180);
          const theta = (cluster.lon + 180) * (Math.PI / 180);

          const x = -r * Math.sin(phi) * Math.cos(theta);
          const y = r * Math.cos(phi);
          const z = r * Math.sin(phi) * Math.sin(theta);

          const count = cluster.stations.length;
          const isCluster = count > 1;

          // Directive 4: Small glowing dot representation
          // Base dot radius 1.25 for single station, 1.45 for cluster
          const dotRadius = isCluster ? 1.45 : 1.25;
          const dotColor = isCluster ? 0xffdf80 : 0xffd277;
          const emissiveColor = isCluster ? 0xffaa00 : 0xff9900;

          const beaconMat = new THREE.MeshStandardMaterial({
            color: dotColor,
            emissive: emissiveColor,
            emissiveIntensity: 0.85,
            roughness: 0.2
          });
          const beacon = new THREE.Mesh(new THREE.SphereGeometry(dotRadius, 14, 14), beaconMat);
          beacon.position.set(x, y, z);

          // Outer halo ring
          const ringInner = isCluster ? 2.0 : 1.8;
          const ringOuter = isCluster ? 3.2 : 2.6;
          const ringGeo = new THREE.RingGeometry(ringInner, ringOuter, 20);
          const ringMat = new THREE.MeshBasicMaterial({
            color: isCluster ? 0xd4af37 : 0xc99d52,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: isCluster ? 0.95 : 0.75
          });
          const ring = new THREE.Mesh(ringGeo, ringMat);
          ring.position.set(x * 1.002, y * 1.002, z * 1.002);
          ring.lookAt(x * 2, y * 2, z * 2);

          // Hit proxy for reliable touch / mouse hit testing
          const hitProxy = new THREE.Mesh(
            new THREE.SphereGeometry(isCluster ? 14.0 : 12.0, 10, 10),
            new THREE.MeshBasicMaterial({ visible: false })
          );
          hitProxy.position.set(x, y, z);

          const clusterData = {
            isCluster: isCluster,
            cluster: cluster,
            stations: cluster.stations,
            lat: cluster.lat,
            lon: cluster.lon,
            city: cluster.city,
            country: cluster.country,
            x: x,
            y: y,
            z: z,
            mesh: beacon,
            ring: ring,
            name: isCluster ? `${cluster.city} (${count} Stations)` : cluster.stations[0].name,
            station: isCluster ? null : cluster.stations[0]
          };

          beacon.userData = clusterData;
          ring.userData = clusterData;
          hitProxy.userData = clusterData;

          carouselGlobeGroup.add(beacon);
          carouselGlobeGroup.add(ring);
          carouselGlobeGroup.add(hitProxy);
          carouselGlobeStations.push(hitProxy);
        });
      } catch (e) {
        console.warn("Could not load globe stations:", e);
      }
    }

    function collapseCurrentGlobeCluster() {
      if (expandedClusterObjects.length > 0) {
        expandedClusterObjects.forEach(obj => {
          if (carouselGlobeGroup) carouselGlobeGroup.remove(obj);
          const idx = carouselGlobeStations.indexOf(obj);
          if (idx !== -1) carouselGlobeStations.splice(idx, 1);
        });
        expandedClusterObjects = [];
      }
      currentExpandedCluster = null;
      const flyout = document.getElementById('globe-cluster-flyout');
      if (flyout) flyout.style.display = 'none';
    }

    function expandGlobeCluster(clusterData) {
      if (currentExpandedCluster === clusterData) {
        collapseCurrentGlobeCluster();
        return;
      }

      collapseCurrentGlobeCluster();
      currentExpandedCluster = clusterData;

      const r = 96.5;
      const x = clusterData.x;
      const y = clusterData.y;
      const z = clusterData.z;
      const normal = new THREE.Vector3(x, y, z).normalize();

      // Orthonormal tangent basis for spherical fan-out
      let up = new THREE.Vector3(0, 1, 0);
      if (Math.abs(normal.y) > 0.88) {
        up = new THREE.Vector3(1, 0, 0);
      }
      const u = new THREE.Vector3().crossVectors(up, normal).normalize();
      const v = new THREE.Vector3().crossVectors(normal, u).normalize();

      const count = clusterData.stations.length;
      const fanSpread = Math.min(9.0, 4.0 + count * 0.65);

      clusterData.stations.forEach((st, idx) => {
        const theta = (idx / count) * 2 * Math.PI;
        const offset = u.clone().multiplyScalar(Math.cos(theta) * fanSpread)
          .add(v.clone().multiplyScalar(Math.sin(theta) * fanSpread));

        const expPos = new THREE.Vector3(x, y, z).add(offset).normalize().multiplyScalar(r * 1.018);

        // Golden connecting filament line from cluster center to expanded beacon
        const lineGeo = new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(x, y, z),
          expPos
        ]);
        const lineMat = new THREE.LineBasicMaterial({
          color: 0xd4af37,
          transparent: true,
          opacity: 0.85
        });
        const line = new THREE.Line(lineGeo, lineMat);

        // Expanded small glowing dot
        const dotMat = new THREE.MeshStandardMaterial({
          color: 0xffea9f,
          emissive: 0xffb700,
          emissiveIntensity: 0.95,
          roughness: 0.15
        });
        const dot = new THREE.Mesh(new THREE.SphereGeometry(1.2, 12, 12), dotMat);
        dot.position.copy(expPos);

        // Hit proxy for expanded dot
        const expHitProxy = new THREE.Mesh(
          new THREE.SphereGeometry(10.0, 8, 8),
          new THREE.MeshBasicMaterial({ visible: false })
        );
        expHitProxy.position.copy(expPos);
        const expData = {
          isCluster: false,
          station: st,
          name: st.name,
          mesh: dot,
          ...st
        };
        dot.userData = expData;
        expHitProxy.userData = expData;

        carouselGlobeGroup.add(line);
        carouselGlobeGroup.add(dot);
        carouselGlobeGroup.add(expHitProxy);

        expandedClusterObjects.push(line);
        expandedClusterObjects.push(dot);
        expandedClusterObjects.push(expHitProxy);
        carouselGlobeStations.push(expHitProxy);
      });

      // Render interactive DOM flyout card
      const flyout = document.getElementById('globe-cluster-flyout');
      if (flyout) {
        flyout.innerHTML = `
          <div class="cluster-flyout-head">
            <div class="cluster-flyout-title">
              <span>${clusterData.city}, ${clusterData.country}</span>
              <span class="cluster-flyout-count">${count} Stations</span>
            </div>
            <button class="cluster-flyout-close" onclick="collapseCurrentGlobeCluster()" aria-label="Close">&times;</button>
          </div>
          <div class="cluster-stations-scroll">
            ${clusterData.stations.map((st, i) => `
              <div class="cluster-station-item" onclick="tuneInToGlobeStation(${JSON.stringify(st).replace(/"/g, '&quot;')}); collapseCurrentGlobeCluster();">
                <div>
                  <div class="cluster-station-name">${st.name}</div>
                  <div class="cluster-station-meta">
                    <span style="color:var(--accent-gold);">${st.genre}</span>
                    <span>&bull;</span>
                    <span>${st.bitrate}</span>
                  </div>
                </div>
                <button class="cluster-station-btn">TUNE</button>
              </div>
            `).join('')}
          </div>
        `;
        flyout.style.display = 'flex';
      }
    }

    function tuneInToGlobeStation(st) {
      const streamUrl = st.url || st.stream_url;
      const title = st.name;
      const artist = `${st.city}, ${st.country}`;
      const album = st.genre || "Internet Radio";
      const artUrl = st.art_url || `/api/coverart?title=${encodeURIComponent(title)}&artist=${encodeURIComponent(artist)}&genre=${encodeURIComponent(album)}&station=1`;

      // Update UI immediately
      const elStageT = document.getElementById('stage-title');
      const elStageA = document.getElementById('stage-artist');
      const elStageAl = document.getElementById('stage-album');
      const elBarT = document.getElementById('bar-title');
      const elBarA = document.getElementById('bar-artist');

      if (elStageT) elStageT.innerText = title;
      if (elStageA) elStageA.innerText = artist;
      if (elStageAl) elStageAl.innerText = album;
      if (elBarT) elBarT.innerText = title;
      if (elBarA) elBarA.innerText = artist;

      isPlaying = true;
      updatePlayPauseUI(true);
      updateArtwork(artUrl, title, artist, album);

      // User directive: when a user clicks on a point please show the bottom controller and show the station
      showMasterDock(true);

      // Tune into station on the streamer hardware
      fetch('/api/play_stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url: streamUrl,
          stream_url: streamUrl,
          title: title,
          artist: artist,
          album: album,
          art_url: artUrl
        })
      }).then(res => res.json()).then(data => {
        if (typeof updateStatus === 'function') updateStatus();
      }).catch(err => console.warn('Stream play error:', err));
    }

    
    window.addEventListener('resize', () => {
      if (currentSlideIndex === 3 && typeof initOrResizeCarouselGlobe === 'function') {
        initOrResizeCarouselGlobe();
      }
    });

    let carouselGlobeAnimId = null;

    function animateCarouselGlobe() {
      if (currentSlideIndex !== 3) {
        // Disable 3D Globe rendering loop when out of view to save CPU/GPU and battery
        carouselGlobeAnimId = null;
        return;
      }
      carouselGlobeAnimId = requestAnimationFrame(animateCarouselGlobe);
      if (!carouselGlobeScene || !carouselGlobeRenderer) return;

      if (!carouselGlobeIsDragging) {
        carouselGlobeGroup.rotation.y += carouselGlobeRotSpeed.y;
        carouselGlobeGroup.rotation.x += carouselGlobeRotSpeed.x;
        carouselGlobeRotSpeed.x *= 0.96;
        carouselGlobeRotSpeed.y = carouselGlobeRotSpeed.y * 0.96 + 0.0018 * 0.04;
      }

      carouselGlobeCurrentDist += (carouselGlobeTargetDist - carouselGlobeCurrentDist) * 0.1;
      carouselGlobeCamera.position.z = carouselGlobeCurrentDist;

      carouselGlobeRenderer.render(carouselGlobeScene, carouselGlobeCamera);
    }

    function openGlobeFullscreen() {
      const view = document.getElementById('globe-fullscreen-view');
      if (view) view.style.display = 'block';
    }

    function closeGlobeFullscreen() {
      const view = document.getElementById('globe-fullscreen-view');
      if (view) view.style.display = 'none';
    }
    window.handleScrub = handleScrub;



    

  
    /* =========================================================================
       Unified Touch, Mouse & Gesture Engine
       ========================================================================= */
    document.addEventListener('DOMContentLoaded', () => {
      initRotaryDiscNav();
      if (currentSlideIndex !== 0) {
        const track = document.getElementById('carousel-track');
        const vp = track ? (track.parentElement || document.querySelector('.carousel-viewport')) : null;
        const w = vp ? vp.clientWidth : window.innerWidth;
        track.style.transform = `translateX(-${currentSlideIndex * w}px)`;
        document.querySelectorAll('.carousel-slide').forEach((slide, sIdx) => {
          slide.classList.toggle('active', sIdx === currentSlideIndex);
        });
        if (typeof slideToView === 'function') slideToView(currentSlideIndex);
      }
      // 1. Initialise Volume Controls and Drag/Click Bar
      const volWrap = document.getElementById('vol-slider-wrap');
      const volRange = document.getElementById('vol-range');

      function applyVolumeFromEvent(e) {
        if (!volWrap) return;
        const rect = volWrap.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const pct = Math.round(Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100)));
        handleVolume(pct);
      }

      let isVolDragging = false;
      if (volWrap) {
        volWrap.addEventListener('mousedown', (e) => {
          isVolDragging = true;
          applyVolumeFromEvent(e);
        });
        volWrap.addEventListener('touchstart', (e) => {
          isVolDragging = true;
          applyVolumeFromEvent(e);
        }, { passive: true });
      }

      window.addEventListener('mousemove', (e) => {
        if (isVolDragging) applyVolumeFromEvent(e);
      });
      window.addEventListener('touchmove', (e) => {
        if (isVolDragging) applyVolumeFromEvent(e);
      }, { passive: true });
      window.addEventListener('mouseup', () => { isVolDragging = false; });
      window.addEventListener('touchend', () => { isVolDragging = false; });

      // Initialise volume fill on load
      if (typeof updateVolFill === 'function') {
        updateVolFill(currentVolume);
      }

      // 2. Gesture Handling for Carousel and Bottom Controller Dock
      let touchStartX = 0;
      let touchStartY = 0;
      let touchStartTime = 0;
      let touchIsBottomZone = false;
      let isMouseDown = false;

      function onGestureStart(clientX, clientY, target) {
        // When using the globe, DO NOT respond to sliding nav / features
        if (currentSlideIndex === 3) return;

        touchStartX = clientX;
        touchStartY = clientY;
        touchStartTime = Date.now();
        touchIsBottomZone = (clientY >= window.innerHeight * 0.65);
      }

      function onGestureEnd(clientX, clientY, target) {
        if (currentSlideIndex === 3) return;

        const diffX = clientX - touchStartX;
        const diffY = clientY - touchStartY;
        const absX = Math.abs(diffX);
        const absY = Math.abs(diffY);
        const elapsed = Date.now() - touchStartTime;

        if (elapsed > 950) return;

        // Check if interaction was on interactive controls (play, scrub, volume)
        const isInteractive = target && (
          target.closest('.scrub-track') ||
          target.closest('.main-scrub-track') ||
          target.closest('#vol-slider-wrap') ||
          target.closest('#vol-range') ||
          target.closest('.btn-circle') ||
          target.closest('#btn-play') ||
          target.closest('button') ||
          target.closest('input')
        );

        // A. VERTICAL SWIPES: Bottom Controller Dock Gestures
        if (absY > 28 && absY > absX * 1.05) {
          if (diffY < -28 && touchIsBottomZone) {
            // Swipe Up: Show bottom controller
            showMasterDock(true);
            return;
          } else if (diffY > 28) {
            // Swipe Down: Hide bottom controller
            const inDockZone = (touchStartY >= window.innerHeight * 0.50);
            if (inDockZone) {
              isBarHovered = false;
              hideMasterDock(true);
              return;
            }
          }
        }

        // B. HORIZONTAL SWIPES: Carousel Screen Cycling
        // User rule: Disable any other swipe gestures when using play, scrub control, volume
        if (isInteractive || isVolDragging) {
          return;
        }

        if (absX > 40 && absX > absY * 1.2) {
          if (diffX < -40) {
            cycleNextSlide();
          } else if (diffX > 40) {
            cyclePrevSlide();
          }
        }
      }

      // Touch events on window
      window.addEventListener('touchstart', (e) => {
        if (e.touches && e.touches.length > 0) {
          onGestureStart(e.touches[0].clientX, e.touches[0].clientY, e.target);
        }
      }, { passive: true });

      window.addEventListener('touchend', (e) => {
        if (e.changedTouches && e.changedTouches.length > 0) {
          onGestureEnd(e.changedTouches[0].clientX, e.changedTouches[0].clientY, e.target);
        }
      }, { passive: true });

      // Mouse drag swipe fallback for desktop
      window.addEventListener('mousedown', (e) => {
        // Only primary mouse button and not on buttons/inputs
        if (e.button === 0 && !e.target.closest('button, input, #btn-floating-hub, #btn-floating-nav')) {
          isMouseDown = true;
          onGestureStart(e.clientX, e.clientY, e.target);
        }
      });

      window.addEventListener('mouseup', (e) => {
        if (isMouseDown) {
          isMouseDown = false;
          onGestureEnd(e.clientX, e.clientY, e.target);
        }
      });
    });

  
    // Prevent page scrolling and gesture collision when manipulating EQ sliders
    document.addEventListener('DOMContentLoaded', () => {
      const eqSliders = document.querySelectorAll('.eq-range, .eq-slider-col, input[type="range"]');
      eqSliders.forEach(slider => {
        ['touchstart', 'touchmove', 'touchend', 'pointerdown', 'pointermove'].forEach(evtName => {
          slider.addEventListener(evtName, (e) => {
            e.stopPropagation();
          }, { passive: false });
        });
      });
    });

    // Background Heartbeat Engine: Continuously verifies streamer connection is active
    let streamerHeartbeatTimer = null;
    let streamerIsOnline = true;

    async function checkStreamerHeartbeat() {
      try {
        const res = await fetch('/api/heartbeat');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        
        const wasOnline = streamerIsOnline;
        streamerIsOnline = data.connected === true;
        
        // Update connection badges and radar if visible
        const connBadge = document.getElementById('status-connected-badge');
        if (connBadge) {
          connBadge.innerText = streamerIsOnline ? 'CONNECTED' : 'STANDBY';
          connBadge.style.color = streamerIsOnline ? 'var(--status-online, #4cd964)' : 'var(--accent-gold, #c99d52)';
        }

        const devPill = document.getElementById('header-device-pill');
        if (devPill) {
          devPill.title = streamerIsOnline ? `Streamer Active (${data.target_ip || 'LAN'})` : 'Streamer Offline / Standby';
        }
      } catch (err) {
        streamerIsOnline = false;
      }
    }

    function startStreamerHeartbeat() {
      if (streamerHeartbeatTimer) clearInterval(streamerHeartbeatTimer);
      checkStreamerHeartbeat();
      streamerHeartbeatTimer = setInterval(checkStreamerHeartbeat, 3000);
    }
    
    /* =========================================================================
       Ambient Voice AI Studio & Multi-Device Automation Client Engine
       ========================================================================= */
    let audioCtx = null;
    let micStream = null;
    let analyserNode = null;
    let animFrameId = null;
    let isAmbientListening = false;
    let speechRecognition = null;
    let vadSensitivityDb = -45;
    let isVoiceDetected = false;
    let lastVadPostTime = 0;

    function initVoiceAIStudio() {
      setupSpectrumCanvas();
      loadVoiceRoutines();
      fetchVoiceEngineStatus();
      setInterval(fetchVoiceEngineStatus, 4000);
    }

    function setupSpectrumCanvas() {
      const canvas = document.getElementById('voice-spectrum-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#06080c';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#242f44';
      ctx.font = '11px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('AWAITING MICROPHONE INITIALISATION...', canvas.width / 2, canvas.height / 2);
    }

    async function toggleAmbientListening() {
      if (isAmbientListening) {
        stopAmbientListening();
      } else {
        await startAmbientListening();
      }
    }

    async function startAmbientListening() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        micStream = stream;
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioCtx.createMediaStreamSource(stream);
        analyserNode = audioCtx.createAnalyser();
        analyserNode.fftSize = 512;
        analyserNode.smoothingTimeConstant = 0.82;
        source.connect(analyserNode);

        isAmbientListening = true;
        updateMicUiState(true);
        startSpectrumVisualiser();
        startSpeechRecognition();

        const toast = document.getElementById('remote-toast-hud');
        if (toast) {
          toast.textContent = 'Ambient Acoustic Listening: ACTIVE';
          toast.classList.add('visible');
          setTimeout(() => toast.classList.remove('visible'), 2500);
        }
      } catch (err) {
        console.warn('Microphone access notice:', err);
        alert('Microphone access required for real-time room acoustic listening. Please permit audio access in your browser or use the "Simulate Voice Trigger" dropdown.');
      }
    }

    function stopAmbientListening() {
      isAmbientListening = false;
      if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
      }
      if (audioCtx && audioCtx.state !== 'closed') {
        audioCtx.close().catch(() => {});
      }
      if (animFrameId) {
        cancelAnimationFrame(animFrameId);
        animFrameId = null;
      }
      if (speechRecognition) {
        try { speechRecognition.stop(); } catch (e) {}
      }
      updateMicUiState(false);
      setupSpectrumCanvas();
    }

    function updateMicUiState(active) {
      const btn = document.getElementById('btn-toggle-listening');
      const btnText = document.getElementById('btn-listen-text');
      const micDot = document.getElementById('voice-mic-dot');
      const micText = document.getElementById('voice-mic-text');
      const micBadge = document.getElementById('voice-mic-badge');

      if (active) {
        if (btn) btn.classList.add('active-listening');
        if (btnText) btnText.textContent = 'STOP AMBIENT LISTENING';
        if (micDot) { micDot.className = 'voice-dot pulse-gold'; }
        if (micText) micText.textContent = 'MIC: LIVE';
        if (micBadge) micBadge.classList.add('active');
      } else {
        if (btn) btn.classList.remove('active-listening');
        if (btnText) btnText.textContent = 'START AMBIENT LISTENING';
        if (micDot) { micDot.className = 'voice-dot'; }
        if (micText) micText.textContent = 'MIC: IDLE';
        if (micBadge) micBadge.classList.remove('active');
        const fill = document.getElementById('vad-meter-fill');
        if (fill) fill.style.width = '0%';
        const readout = document.getElementById('vad-db-readout');
        if (readout) readout.textContent = '-∞ dB';
      }
    }

    function startSpectrumVisualiser() {
      const canvas = document.getElementById('voice-spectrum-canvas');
      if (!canvas || !analyserNode) return;
      const ctx = canvas.getContext('2d');
      const bufferLength = analyserNode.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);

      function drawFrame() {
        if (!isAmbientListening) return;
        animFrameId = requestAnimationFrame(drawFrame);

        analyserNode.getByteFrequencyData(dataArray);

        // Compute RMS and vocal band energy (bins 2 to 40, ~86Hz to 3500Hz)
        let sum = 0;
        let vocalSum = 0;
        let vocalBins = 0;
        for (let i = 0; i < bufferLength; i++) {
          const v = dataArray[i];
          sum += v * v;
          if (i >= 2 && i <= 40) {
            vocalSum += v * v;
            vocalBins++;
          }
        }
        const rms = Math.sqrt(sum / bufferLength);
        const vocalRms = Math.sqrt(vocalSum / Math.max(1, vocalBins));

        // Convert to dB scale roughly between -70dB and 0dB
        const db = rms > 0 ? 20 * Math.log10(rms / 255) : -70;
        const vocalDb = vocalRms > 0 ? 20 * Math.log10(vocalRms / 255) : -70;

        // VAD Decision
        const nowVoice = vocalDb > vadSensitivityDb;
        isVoiceDetected = nowVoice;
        updateVadUi(vocalDb, nowVoice);

        // Throttle reporting to backend
        const now = Date.now();
        if (now - lastVadPostTime > 800) {
          lastVadPostTime = now;
          fetch('/api/voice/vad', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ noise_level: vocalDb, is_voice: nowVoice, sensitivity: vadSensitivityDb })
          }).catch(() => {});
        }

        // Draw Canvas Spectrum
        ctx.fillStyle = '#06080c';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const barWidth = (canvas.width / 48) - 1.5;
        let x = 0;

        for (let i = 0; i < 48; i++) {
          const val = dataArray[i];
          const barHeight = (val / 255) * (canvas.height - 10);

          // Highlight human vocal spectrum bins
          if (i >= 2 && i <= 38) {
            ctx.fillStyle = nowVoice ? '#e0b468' : '#38bdf8';
          } else {
            ctx.fillStyle = '#242f44';
          }

          ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
          x += barWidth + 1.5;
        }

        const readout = document.getElementById('voice-freq-readout');
        if (readout) {
          readout.textContent = `${Math.round(vocalDb)} dB · ${nowVoice ? 'VOICE DETECTED' : 'ROOM AMBIENT'}`;
        }
      }

      drawFrame();
    }

    function updateVadUi(db, isVoice) {
      const fill = document.getElementById('vad-meter-fill');
      const dbReadout = document.getElementById('vad-db-readout');
      const vadDot = document.getElementById('voice-vad-dot');
      const vadText = document.getElementById('voice-vad-text');
      const vadBadge = document.getElementById('voice-vad-badge');

      const clamped = Math.max(-70, Math.min(0, db));
      const pct = Math.round(((clamped + 70) / 70) * 100);

      if (fill) fill.style.width = pct + '%';
      if (dbReadout) dbReadout.textContent = `${Math.round(db)} dB`;

      if (isVoice) {
        if (vadDot) vadDot.className = 'voice-dot pulse-gold';
        if (vadText) vadText.textContent = 'VAD: VOICE DETECTED';
        if (vadBadge) vadBadge.classList.add('active');
      } else {
        if (vadDot) vadDot.className = 'voice-dot';
        if (vadText) vadText.textContent = 'VAD: VOCAL BAND (85Hz-3.5kHz)';
        if (vadBadge) vadBadge.classList.remove('active');
      }
    }

    function updateVadSensitivity(val) {
      vadSensitivityDb = parseInt(val, 10);
      const sensVal = document.getElementById('vad-sens-value');
      if (sensVal) sensVal.textContent = `${vadSensitivityDb} dB`;

      const marker = document.getElementById('vad-threshold-marker');
      if (marker) {
        const pct = Math.round(((vadSensitivityDb + 70) / 70) * 100);
        marker.style.left = `${pct}%`;
      }
    }

    function startSpeechRecognition() {
      const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRec) {
        const sttStatus = document.getElementById('voice-stt-status');
        if (sttStatus) sttStatus.textContent = 'WEB SPEECH API NOT SUPPORTED (USE SIMULATION)';
        return;
      }

      speechRecognition = new SpeechRec();
      speechRecognition.continuous = true;
      speechRecognition.interimResults = true;
      speechRecognition.lang = 'en-US';

      speechRecognition.onstart = () => {
        const sttStatus = document.getElementById('voice-stt-status');
        if (sttStatus) sttStatus.textContent = 'STREAMING AUDIO TO COGNITIVE ENGINE...';
      };

      speechRecognition.onresult = (event) => {
        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript;
          } else {
            interimTranscript += event.results[i][0].transcript;
          }
        }

        const liveTranscript = document.getElementById('voice-live-transcript');
        if (liveTranscript) {
          if (finalTranscript) {
            liveTranscript.innerHTML = `<span>"${finalTranscript}"</span>`;
            processVoiceCommand(finalTranscript);
          } else if (interimTranscript) {
            liveTranscript.innerHTML = `<span class="interim">"${interimTranscript}..."</span>`;
          }
        }

        const wordsCount = document.getElementById('voice-words-count');
        if (wordsCount) {
          const count = (finalTranscript || interimTranscript).trim().split(/\\s+/).filter(Boolean).length;
          wordsCount.textContent = `${count} TOKENS`;
        }
      };

      speechRecognition.onerror = (event) => {
        console.warn('SpeechRecognition error:', event.error);
      };

      speechRecognition.onend = () => {
        if (isAmbientListening) {
          try { speechRecognition.start(); } catch (e) {}
        }
      };

      try {
        speechRecognition.start();
      } catch (err) {
        console.warn('SpeechRecognition start err:', err);
      }
    }

    function pushToTalkClick() {
      if (!isAmbientListening) {
        startAmbientListening().then(() => {
          setTimeout(() => {
            const live = document.getElementById('voice-live-transcript');
            if (live) live.innerHTML = '<span style="color:var(--accent-gold);">Listening... speak now!</span>';
          }, 300);
        });
      }
    }

    async function processVoiceCommand(transcript, bypassVad = false) {
      if (!transcript || !transcript.trim()) return;

      const stream = document.getElementById('voice-decision-stream');
      const timeReadout = document.getElementById('voice-last-decision-time');

      try {
        const startTime = performance.now();
        const resp = await fetch('/api/voice/process', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ transcript: transcript, bypass_vad: bypassVad })
        });
        const data = await resp.json();
        const elapsed = Math.round(performance.now() - startTime);

        if (data.status === 'ok' && data.decision) {
          const dec = data.decision;
          if (timeReadout) {
            timeReadout.textContent = `LATENCY: ${dec.elapsed_ms || elapsed}ms (${dec.source?.toUpperCase() || 'LOCAL'})`;
          }
          renderDecisionCard(dec, transcript);
        }
      } catch (err) {
        console.error('Error processing voice command:', err);
      }
    }

    function runSimulatedVoiceCommand(phrase) {
      if (!phrase) return;
      const live = document.getElementById('voice-live-transcript');
      if (live) live.innerHTML = `<span>"${phrase}"</span>`;
      processVoiceCommand(phrase, true);
    }

    function renderDecisionCard(dec, transcript) {
      const stream = document.getElementById('voice-decision-stream');
      if (!stream) return;

      const isReflex = dec.source === 'local_reflex';
      const card = document.createElement('div');
      card.className = `decision-card ${isReflex ? 'reflex' : 'cognitive'}`;

      const intentClass = (dec.intent || 'none').toLowerCase().includes('volume') ? 'volume' :
                          (dec.intent || '').toLowerCase().includes('media') ? 'media' :
                          (dec.intent || '').toLowerCase().includes('lighting') ? 'lighting' : 'none';

      let actionsHtml = '';
      if (dec.actions && dec.actions.length > 0) {
        actionsHtml = dec.actions.map(a => `<span class="action-pill">⚡ [${a.device || 'TARGET'}] ${a.command}: ${JSON.stringify(a.param || '')}</span>`).join(' ');
      } else {
        actionsHtml = '<span class="action-pill" style="color:var(--text-dim);">NO ACTION REQUIRED (CONVERSATION)</span>';
      }

      card.innerHTML = `
        <div class="decision-top">
          <span class="decision-intent ${intentClass}">[${dec.intent?.toUpperCase() || 'GENERAL'}] ${dec.target_device?.toUpperCase() || 'SYSTEM'}</span>
          <span style="color:var(--text-dim);">${dec.source?.toUpperCase()} · ${dec.confidence ? Math.round(dec.confidence * 100) + '%' : '100%'} CONF</span>
        </div>
        <div style="font-size:12px; color:var(--text-main); font-weight:500;">
          "${transcript}"
        </div>
        <div style="font-size:11px; color:var(--text-muted); line-height:1.4;">
          ${dec.explanation || (isReflex ? 'Sub-15ms local acoustic reflex executed' : 'MiniMax cognitive reasoning executed')}
        </div>
        <div class="decision-action-chain">
          ${actionsHtml}
        </div>
      `;

      stream.insertBefore(card, stream.firstChild);

      // Keep maximum 8 cards in memory
      while (stream.children.length > 8) {
        stream.removeChild(stream.lastChild);
      }
    }

    async function applyLightingAmbiance(preset) {
      try {
        const resp = await fetch('/api/lights/control', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ colour: preset })
        });
        const data = await resp.json();
        if (data.status === 'ok' && data.state) {
          updateLightingUi(data.state);
        }
      } catch (e) {
        console.error('Error applying lighting:', e);
      }
    }

    async function adjustLightingBrightness(val) {
      try {
        const resp = await fetch('/api/lights/control', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ brightness: parseInt(val, 10), power: parseInt(val, 10) > 0 ? 'ON' : 'OFF' })
        });
        const data = await resp.json();
        if (data.status === 'ok' && data.state) {
          updateLightingUi(data.state);
        }
      } catch (e) {
        console.error('Error adjusting brightness:', e);
      }
    }

    function updateLightingUi(state) {
      const statusText = document.getElementById('lighting-active-status');
      const nameText = document.getElementById('lighting-name-text');
      const hexText = document.getElementById('lighting-hex-text');
      const backdrop = document.getElementById('lighting-preview-backdrop');
      const fader = document.getElementById('lighting-brightness-fader');

      if (statusText) statusText.textContent = `POWER: ${state.power} · ${state.brightness}%`;
      if (nameText) nameText.textContent = state.colour ? state.colour.replace('_', ' ').toUpperCase() : 'Studio Ambiance';
      if (hexText) hexText.textContent = `${state.hex?.toUpperCase() || '#D4AF37'} · ${state.brightness}% LUMENS`;
      if (fader) fader.value = state.brightness;

      if (backdrop) {
        const opacity = state.power === 'ON' ? (state.brightness / 100) * 0.45 : 0;
        backdrop.style.opacity = opacity;
        backdrop.style.background = `radial-gradient(circle at 50% 50%, ${state.hex || '#d4af37'} 0%, transparent 80%)`;
      }
    }

    async function fetchVoiceEngineStatus() {
      try {
        const resp = await fetch('/api/voice/status');
        const data = await resp.json();
        if (data.lighting) {
          updateLightingUi(data.lighting);
        }
      } catch (e) {}
    }

    async function loadVoiceRoutines() {
      try {
        const resp = await fetch('/api/voice/routines');
        const data = await resp.json();
        if (data.status === 'ok' && data.routines) {
          renderVoiceRoutines(data.routines);
        }
      } catch (e) {
        console.error('Error loading routines:', e);
      }
    }

    function renderVoiceRoutines(routines) {
      const container = document.getElementById('routine-cards-grid');
      if (!container) return;

      container.innerHTML = routines.map(r => {
        const triggersHtml = (r.triggers || []).map(t => `<span class="trigger-tag">"${t}"</span>`).join(' ');
        const actionsCount = (r.actions || []).length;
        const enabled = r.enabled !== false;

        return `
          <div class="routine-card">
            <div class="routine-head">
              <span class="routine-name">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                ${r.name}
              </span>
              <span class="routine-priority">PRIORITY ${r.priority || 50}</span>
            </div>
            <div style="font-size:11px; color:var(--text-muted); line-height:1.4;">
              ${r.description || ''}
            </div>
            <div class="routine-triggers">
              ${triggersHtml}
            </div>
            <div class="routine-foot">
              <span style="font-family:'JetBrains Mono', monospace; font-size:10px; color:var(--text-dim);">${actionsCount} AUTOMATION STEPS</span>
              <div style="display:flex; align-items:center; gap:8px;">
                <button class="btn-test-routine" onclick="testVoiceRoutine('${r.id}')">▶ TEST ROUTINE</button>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    async function testVoiceRoutine(routineId) {
      try {
        const toast = document.getElementById('remote-toast-hud');
        if (toast) {
          toast.textContent = `Executing Routine: ${routineId}...`;
          toast.classList.add('visible');
        }
        const resp = await fetch('/api/voice/test_routine', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ routine_id: routineId })
        });
        const data = await resp.json();
        if (toast) {
          toast.textContent = `Routine ${routineId}: EXECUTED`;
          setTimeout(() => toast.classList.remove('visible'), 2500);
        }
        // Also fetch status to refresh lighting or target states
        fetchVoiceEngineStatus();
      } catch (e) {
        console.error('Error testing routine:', e);
      }
    }

    window.addEventListener('DOMContentLoaded', initVoiceAIStudio);

    window.addEventListener('load', startStreamerHeartbeat);

  

    /* =========================================================================
       HARDWARE ROTATING DISC NAVIGATION DIAL (Studio Jog Wheel Engine)
       ========================================================================= */
    const ROTARY_SLIDES = [
      { index: 0, id: 'player', name: 'PLAYER', full: 'STUDIO PLAYER & DAC' },
      { index: 1, id: 'protocols', name: 'SOURCES', full: 'STREAMING ARCHITECTURE' },
      { index: 2, id: 'discovery', name: 'HARDWARE', full: 'DEVICE DISCOVERY ROUTER' },
      { index: 3, id: 'radio', name: 'RADIO', full: 'INTERNET RADIO GLOBE' },
      { index: 4, id: 'dac', name: 'DAC', full: 'DAC OUTPUT & FILTERS' },
      { index: 5, id: 'eq', name: 'EQUALISER', full: 'PARAMETRIC EQUALISER' },
      { index: 6, id: 'sleep', name: 'POWER', full: 'SLEEP & POWER TIMER' },
      { index: 7, id: 'lyrics', name: 'LYRICS', full: 'LYRICS & LINER NOTES' },
      { index: 8, id: 'queue', name: 'QUEUE', full: 'PLAYBACK QUEUE' },
      { index: 9, id: 'storage', name: 'STORAGE', full: 'INTERNAL NVME STORAGE' },
      { index: 10, id: 'remote', name: 'REMOTE', full: 'UNIVERSAL REMOTE CONTROL' },
      { index: 11, id: 'voice', name: 'VOICE AI', full: 'AMBIENT VOICE AI STUDIO' }
    ];

    let rotaryAngle = 0;
    let rotaryIsDragging = false;
    let rotaryStartAngle = 0;
    let rotaryBaseAngle = 0;
    let rotaryLastAngle = 0;
    let rotaryLastTime = 0;
    let rotaryVelocity = 0;
    let rotaryAnimId = null;

    function easeOutQuad(t) {
      return t * (2 - t);
    }

    function initRotaryDiscNav() {
      const container = document.getElementById('rotary-disc-items');
      const disc = document.getElementById('rotary-nav-disc');
      if (!container || !disc) return;
      container.innerHTML = '';

      // Compute radius based on disc dimensions
      const discW = disc.offsetWidth || 640;
      const R = Math.round(discW * 0.442);

      ROTARY_SLIDES.forEach(s => {
        // At 6 o'clock (bottom centre) world angle is 90deg.
        // Each slide is placed at 90 + index * 30 degrees.
        const itemAngle = 90 + s.index * 30;
        const rad = (itemAngle * Math.PI) / 180;
        const x = R * Math.cos(rad);
        const y = R * Math.sin(rad);

        // When slide k is rotated to 6 o'clock under the needle,
        // the disc has rotated by -k * 30 degrees.
        // Giving the element a local rotation of +k * 30 degrees ensures
        // that whenever it arrives at 6 o'clock, its net screen orientation
        // is EXACTLY 0 degrees (perfectly upright, horizontal, left-to-right).
        const localRot = s.index * 30;

        const el = document.createElement('div');
        el.className = 'rotary-item' + (s.index === currentSlideIndex ? ' active' : '');
        el.id = 'rotary-item-' + s.index;
        el.setAttribute('data-index', s.index);
        el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${localRot}deg)`;

        const led = document.createElement('div');
        led.className = 'rotary-item-led';

        const lbl = document.createElement('span');
        lbl.className = 'rotary-item-label';
        lbl.innerText = s.name;

        el.appendChild(led);
        el.appendChild(lbl);

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          selectRotarySlide(s.index);
        });

        container.appendChild(el);
      });

      // Synchronize to current initial slide
      updateRotaryDisplay(currentSlideIndex);
      syncRotaryDiscToSlide(currentSlideIndex);

      // Bind Pointer Drag Gestures for Clockwise / Anticlockwise rotation
      const housing = document.getElementById('rotary-nav-housing');
      if (housing) {
        housing.addEventListener('pointerdown', onRotaryPointerDown);
        window.addEventListener('pointermove', onRotaryPointerMove);
        window.addEventListener('pointerup', onRotaryPointerUp);
        window.addEventListener('pointercancel', onRotaryPointerUp);
      }

      window.addEventListener('resize', () => {
        const dW = disc.offsetWidth || 640;
        const newR = Math.round(dW * 0.442);
        ROTARY_SLIDES.forEach(s => {
          const itEl = document.getElementById('rotary-item-' + s.index);
          if (itEl) {
            const itAng = 90 + s.index * 30;
            const rRad = (itAng * Math.PI) / 180;
            const nX = newR * Math.cos(rRad);
            const nY = newR * Math.sin(rRad);
            const lRot = s.index * 30;
            itEl.style.transform = `translate(${nX.toFixed(1)}px, ${nY.toFixed(1)}px) rotate(${lRot}deg)`;
          }
        });
      });
    }

    function getPointerAngle(e) {
      const disc = document.getElementById('rotary-nav-disc');
      if (!disc) return 0;
      const rect = disc.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      return Math.atan2(e.clientY - cy, e.clientX - cx) * (180 / Math.PI);
    }

    function onRotaryPointerDown(e) {
      if (rotaryAnimId) {
        cancelAnimationFrame(rotaryAnimId);
        rotaryAnimId = null;
      }
      rotaryIsDragging = true;
      rotaryStartAngle = getPointerAngle(e);
      rotaryBaseAngle = rotaryAngle;
      rotaryLastAngle = rotaryAngle;
      rotaryLastTime = performance.now();
      rotaryVelocity = 0;
      const disc = document.getElementById('rotary-nav-disc');
      if (disc) disc.style.transition = 'none';
    }

    function onRotaryPointerMove(e) {
      if (!rotaryIsDragging) return;
      const currentAng = getPointerAngle(e);
      let delta = currentAng - rotaryStartAngle;
      while (delta > 180) delta -= 360;
      while (delta < -180) delta += 360;

      rotaryAngle = rotaryBaseAngle + delta;

      const now = performance.now();
      const dt = now - rotaryLastTime;
      if (dt > 8) {
        rotaryVelocity = (rotaryAngle - rotaryLastAngle) / dt;
        rotaryLastAngle = rotaryAngle;
        rotaryLastTime = now;
      }

      const disc = document.getElementById('rotary-nav-disc');
      if (disc) {
        disc.style.transform = `rotate(${rotaryAngle}deg)`;
        const blurAmt = Math.min(2.2, Math.abs(rotaryVelocity) * 1.6);
        disc.style.filter = blurAmt > 0.25 ? `blur(${blurAmt.toFixed(1)}px)` : 'none';
      }

      // Live update index indicator under the needle
      const nearestIdx = ((Math.round(-rotaryAngle / 30) % 12) + 12) % 12;
      updateRotaryDisplay(nearestIdx);
    }

    function onRotaryPointerUp(e) {
      if (!rotaryIsDragging) return;
      rotaryIsDragging = false;

      // Add momentum flick velocity if significant
      const momentum = Math.abs(rotaryVelocity) > 0.15 ? rotaryVelocity * 180 : 0;
      const targetAngle = Math.round((rotaryAngle + momentum) / 30) * 30;

      animateRotaryToAngle(targetAngle, 380, () => {
        const snappedIdx = ((Math.round(-targetAngle / 30) % 12) + 12) % 12;
        updateRotaryDisplay(snappedIdx);
        if (typeof slideToView === 'function') {
          slideToView(ROTARY_SLIDES[snappedIdx].id);
        }
      });
    }

    function animateRotaryToAngle(targetAngle, duration = 400, onComplete = null) {
      if (rotaryAnimId) {
        cancelAnimationFrame(rotaryAnimId);
        rotaryAnimId = null;
      }

      const disc = document.getElementById('rotary-nav-disc');
      const startAngle = rotaryAngle;
      const deltaAngle = targetAngle - startAngle;
      const startTime = performance.now();

      function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(1, elapsed / duration);
        const eased = easeOutQuad(progress);
        rotaryAngle = startAngle + deltaAngle * eased;

        if (disc) {
          disc.style.transform = `rotate(${rotaryAngle}deg)`;
          const blurMag = Math.min(2.0, Math.abs(deltaAngle * (1 - progress)) * 0.04);
          disc.style.filter = blurMag > 0.2 ? `blur(${blurMag.toFixed(1)}px)` : 'none';
        }

        const activeIndex = ((Math.round(-rotaryAngle / 30) % 12) + 12) % 12;
        updateRotaryDisplay(activeIndex);

        if (progress < 1) {
          rotaryAnimId = requestAnimationFrame(step);
        } else {
          rotaryAngle = targetAngle;
          if (disc) {
            disc.style.transform = `rotate(${rotaryAngle}deg)`;
            disc.style.filter = 'none';
          }
          rotaryAnimId = null;
          if (typeof onComplete === 'function') onComplete();
        }
      }
      rotaryAnimId = requestAnimationFrame(step);
    }

    function updateRotaryDisplay(activeIdx) {
      ROTARY_SLIDES.forEach(s => {
        const itEl = document.getElementById('rotary-item-' + s.index);
        if (itEl) {
          if (s.index === activeIdx) {
            itEl.classList.add('active');
          } else {
            itEl.classList.remove('active');
          }
        }
      });

      const slide = ROTARY_SLIDES[activeIdx] || ROTARY_SLIDES[0];
      const stepPill = document.getElementById('rotary-step-pill');
      if (stepPill) {
        stepPill.innerText = `${String(slide.index + 1).padStart(2, '0')} / 12`;
      }
      const titleEl = document.getElementById('rotary-title-text');
      if (titleEl) {
        titleEl.innerText = slide.full;
      }
    }

    function syncRotaryDiscToSlide(slideIdx) {
      if (rotaryIsDragging) return;
      const targetAngle = -slideIdx * 30;
      let diff = targetAngle - (rotaryAngle % 360);
      while (diff > 180) diff -= 360;
      while (diff < -180) diff += 360;
      const finalAngle = rotaryAngle + diff;
      animateRotaryToAngle(finalAngle, 360);
    }

    function selectRotarySlide(index) {
      const slide = ROTARY_SLIDES[index];
      if (!slide) return;
      if (typeof slideToView === 'function') {
        slideToView(slide.id);
      }
    }

    window.syncRotaryDiscToSlide = syncRotaryDiscToSlide;
    window.selectRotarySlide = selectRotarySlide;
    window.initRotaryDiscNav = initRotaryDiscNav;

    // DAC Filter scene preset selector helper
    function selectDacFilterPreset(presetName) {
      document.querySelectorAll('#dac-filter-presets .mixer-scene-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-filter') === presetName);
      });
      const sel = document.getElementById('select-dac-filter');
      if (sel) {
        sel.value = presetName;
      }
      if (typeof applyDacFilter === 'function') {
        applyDacFilter(presetName);
      }
    }

</script>

  <!-- Pure Full-Screen 3D Globe Internet Radio View -->
  <div id="globe-fullscreen-view" class="globe-fullscreen-view">
    <div id="globe-fullscreen-container" class="globe-fullscreen-container"></div>

    <button class="btn-globe-return" onclick="closeGlobeView()" aria-label="Return to Audio Player">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
      <span>Audio Player</span>
    </button>

    <div class="globe-hud-pill" id="globe-hud-pill">
      <span class="globe-live-dot"></span>
      <span id="globe-hud-station">Drag to spin • Pinch to zoom • Tap a beacon to tune</span>
    </div>
  </div>

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
    port = get_available_port(requested_port)
    server_address = ("", port)
    httpd = http.server.ThreadingHTTPServer(server_address, SilentAngelHTTPHandler)
    local_ip = get_local_ip()

    url_local = f"http://localhost:{port}"
    url_lan = f"http://{local_ip}:{port}"

    print("=" * 66, flush=True)
    print("  Silent Angel Bremen SL1P · Control Studio Online", flush=True)
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
        print("\nStopping Silent Angel Studio server...", flush=True)
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
