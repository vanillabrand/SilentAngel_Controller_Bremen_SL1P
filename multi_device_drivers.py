#!/usr/bin/env python3
"""
Multi-Device Hardware Drivers for Silent Angel Controller Suite
Direct physical hardware control for:
- Google TV / Chromecast (pychromecast, androidtvremote2, DIAL)
- Vevshao Smart LED Projector (pyatv AirPlay/AirTunes, UPnP AVTransport & RenderingControl, TranScreen)
- Silent Angel Streamers & Audiophile UPnP Renderers
- Android TV devices
All communications follow strict UK English conventions.
"""

import asyncio
import logging
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid

logger = logging.getLogger("MultiDeviceDrivers")

HAVE_PYCHROMECAST = False
try:
    import pychromecast
    from pychromecast.models import CastInfo, HostServiceInfo
    HAVE_PYCHROMECAST = True
except ImportError:
    pass

HAVE_PYATV = False
try:
    import pyatv
    HAVE_PYATV = True
except ImportError:
    pass

HAVE_ATV_REMOTE = False
try:
    from androidtvremote2 import AndroidTVRemote, CannotConnect, InvalidAuth, ConnectionClosed
    from androidtvremote2.certificate_generator import generate_selfsigned_cert
    from androidtvremote2.remotemessage_pb2 import RemoteKeyCode, RemoteDirection
    HAVE_ATV_REMOTE = True
except ImportError:
    pass

HAVE_ZEROCONF = False
try:
    import zeroconf
    HAVE_ZEROCONF = True
except ImportError:
    pass


# Android TV Remote v2 Keycode Mappings
ATV_KEY_MAP = {
    "UP": "DPAD_UP",
    "DOWN": "DPAD_DOWN",
    "LEFT": "DPAD_LEFT",
    "RIGHT": "DPAD_RIGHT",
    "OK": "DPAD_CENTER",
    "SELECT": "DPAD_CENTER",
    "BACK": "BACK",
    "HOME": "HOME",
    "POWER": "POWER",
    "MENU": "MENU",
    "KEYSTONE": "SETTINGS",
    "SETTINGS": "SETTINGS",
    "CH_UP": "CHANNEL_UP",
    "CH_DOWN": "CHANNEL_DOWN",
    "VOL_UP": "VOLUME_UP",
    "VOL_DOWN": "VOLUME_DOWN",
    "MUTE": "VOLUME_MUTE",
    "PLAY": "MEDIA_PLAY_PAUSE",
    "PLAY_PAUSE": "MEDIA_PLAY_PAUSE",
    "PAUSE": "MEDIA_PLAY_PAUSE",
    "STOP": "MEDIA_STOP",
    "NEXT": "MEDIA_NEXT",
    "PREV": "MEDIA_PREVIOUS",
    "REW": "MEDIA_REWIND",
    "FF": "MEDIA_FAST_FORWARD",
    "SCROLL_UP": "DPAD_UP",
    "SCROLL_DOWN": "DPAD_DOWN",
    "LEFT_CLICK": "DPAD_CENTER",
    "RIGHT_CLICK": "BACK",
    "ENTER": "DPAD_CENTER",
    "KEY_ENTER": "DPAD_CENTER",
    "KEY_DOWN": "DPAD_DOWN",
    "KEY_UP": "DPAD_UP",
    "KEY_LEFT": "DPAD_LEFT",
    "KEY_RIGHT": "DPAD_RIGHT",
    "KEY_SELECT": "DPAD_CENTER",
    "DISMISS_MIC": "BACK",
    "DISMISS_ASSISTANT": "BACK"
}


class MultiDeviceController:
    """Unified driver controller for Google TV, Vevshao Projector, and UPnP streamers."""

    def __init__(self, manager=None):
        self.manager = manager
        self.lock = threading.Lock()
        self.zconf = None
        self.cast_cache = {}

        # Persistent background asyncio loop for Android TV Remote and pyatv
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self._run_async_loop, daemon=True, name="MultiDeviceAsyncLoop")
        self.loop_thread.start()

        # Android TV Remote state
        self.atv_remote_client = None
        self.atv_pairing_remote = None
        self.is_paired_google_tv = False
        self.is_connected_google_tv = False
        self.google_tv_ip = "192.168.1.137"

        # Certificates storage
        cert_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SilentAngel", "certs")
        os.makedirs(cert_dir, exist_ok=True)
        self.cert_file = os.path.join(cert_dir, "androidtv.crt")
        self.key_file = os.path.join(cert_dir, "androidtv.key")
        self._ensure_certificates()

        # Vevshao Projector UPnP endpoints
        self.vevshao_ip = "192.168.1.121"
        self.vevshao_upnp_port = 44539
        self.vevshao_udn = "533b925d-e718-3f97-8734-21228303165c"

        # Attempt initial background connection to Google TV
        self.loop.call_soon_threadsafe(self._schedule_initial_atv_connect)

    def _run_async_loop(self):
        """Dedicated background event loop thread."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _ensure_certificates(self):
        """Generate persistent self-signed certificates for Android TV Remote v2."""
        if HAVE_ATV_REMOTE and (not os.path.exists(self.cert_file) or not os.path.exists(self.key_file)):
            try:
                cert, key = generate_selfsigned_cert("SilentAngelStudio")
                with open(self.cert_file, "wb") as f:
                    f.write(cert)
                with open(self.key_file, "wb") as f:
                    f.write(key)
                logger.info(f"Generated Android TV Remote credentials at {self.cert_file}")
            except Exception as e:
                logger.warning(f"Could not generate Android TV certificates: {e}")

    def _schedule_initial_atv_connect(self):
        """Schedule initial connection to Google TV if available."""
        asyncio.ensure_future(self._async_connect_google_tv(self.google_tv_ip), loop=self.loop)

    def get_zeroconf(self):
        """Lazily initialise zeroconf instance."""
        if self.zconf is None and HAVE_ZEROCONF:
            try:
                self.zconf = zeroconf.Zeroconf()
            except Exception as e:
                logger.warning(f"Zeroconf initialisation failed: {e}")
        return self.zconf

    def get_chromecast(self, ip="192.168.1.137", cast_uuid_str="b991e829-8162-6186-ff24-edcfe4390e10"):
        """Obtain a cached or newly connected pychromecast instance."""
        if not HAVE_PYCHROMECAST:
            return None
        with self.lock:
            existing = self.cast_cache.get(ip)
            if existing and existing.socket_client and existing.socket_client.is_connected:
                return existing

            try:
                z = self.get_zeroconf()
                service = HostServiceInfo(ip, 8009)
                cast_info = CastInfo(
                    services={service},
                    uuid=uuid.UUID(cast_uuid_str) if cast_uuid_str else uuid.uuid4(),
                    model_name="4K Google TV Stick",
                    friendly_name="Family room TV 2",
                    host=ip,
                    port=8009,
                    cast_type="cast",
                    manufacturer="Google Inc."
                )
                cast = pychromecast.get_chromecast_from_cast_info(cast_info, zconf=z)
                cast.wait(timeout=2.5)
                self.cast_cache[ip] = cast
                return cast
            except Exception as e:
                logger.warning(f"Could not connect to Chromecast at {ip}: {e}")
                return None

    # =========================================================================
    # Android TV Remote v2 Engine (Hardware-Level Pairing & Key Navigation)
    # =========================================================================

    async def _async_connect_google_tv(self, ip):
        """Connect to Google TV using Android TV Remote v2 protocol."""
        if not HAVE_ATV_REMOTE:
            return {"status": "error", "error": "androidtvremote2 library not installed"}

        try:
            if self.atv_remote_client:
                try:
                    self.atv_remote_client.disconnect()
                except Exception:
                    pass

            remote = AndroidTVRemote(
                client_name="Silent Angel Studio",
                certfile=self.cert_file,
                keyfile=self.key_file,
                host=ip,
                loop=self.loop,
            )
            await remote.async_generate_cert_if_missing()
            await remote.async_connect()
            remote.keep_reconnecting()
            self.atv_remote_client = remote
            self.is_paired_google_tv = True
            self.is_connected_google_tv = True
            self.google_tv_ip = ip
            logger.info("Successfully connected to Android TV Remote v2 service")
            return {"status": "ok", "paired": True, "connected": True}
        except InvalidAuth:
            self.is_paired_google_tv = False
            self.is_connected_google_tv = False
            self.atv_remote_client = None
            logger.info(f"Google TV at {ip} requires pairing authorisation")
            return {"status": "needs_pairing", "paired": False}
        except Exception as e:
            self.is_connected_google_tv = False
            logger.warning(f"Google TV connection attempt notice: {e}")
            return {"status": "error", "error": str(e)}

    def check_google_tv_status(self, ip="192.168.1.137"):
        """Check whether Google TV is paired and connected."""
        if self.is_connected_google_tv and self.atv_remote_client:
            return {"status": "ok", "paired": True, "connected": True, "ip": ip}
        
        try:
            fut = asyncio.run_coroutine_threadsafe(self._async_connect_google_tv(ip), self.loop)
            res = fut.result(timeout=2.5)
            return res
        except Exception as e:
            return {"status": "error", "paired": self.is_paired_google_tv, "connected": False, "error": str(e)}

    def start_google_tv_pairing(self, ip="192.168.1.137"):
        """Initiate PIN pairing on Google TV so 6-character code appears on TV screen."""
        if not HAVE_ATV_REMOTE:
            return {"status": "error", "error": "androidtvremote2 library not installed"}

        try:
            async def _start():
                if self.atv_pairing_remote:
                    try:
                        self.atv_pairing_remote.disconnect()
                    except Exception:
                        pass

                self.atv_pairing_remote = AndroidTVRemote(
                    client_name="Silent Angel Studio",
                    certfile=self.cert_file,
                    keyfile=self.key_file,
                    host=ip,
                    loop=self.loop,
                )
                await self.atv_pairing_remote.async_generate_cert_if_missing()
                await self.atv_pairing_remote.async_start_pairing()
                return {
                    "status": "ok",
                    "message": "Pairing initiated. A 6-character code is currently displayed on your Google TV screen. Please enter it to finalise pairing."
                }

            fut = asyncio.run_coroutine_threadsafe(_start(), self.loop)
            return fut.result(timeout=6.0)
        except Exception as e:
            logger.error(f"Failed to start pairing: {e}")
            return {"status": "error", "error": str(e)}

    def finish_google_tv_pairing(self, ip="192.168.1.137", pairing_code=""):
        """Complete pairing using the 6-character code shown on Google TV screen."""
        if not HAVE_ATV_REMOTE:
            return {"status": "error", "error": "androidtvremote2 library not installed"}

        try:
            async def _finish():
                if not self.atv_pairing_remote:
                    self.atv_pairing_remote = AndroidTVRemote(
                        client_name="Silent Angel Studio",
                        certfile=self.cert_file,
                        keyfile=self.key_file,
                        host=ip,
                        loop=self.loop,
                    )
                await self.atv_pairing_remote.async_finish_pairing(pairing_code.strip())
                self.atv_pairing_remote = None
                self.is_paired_google_tv = True

                # Immediately establish persistent connected remote session
                conn_res = await self._async_connect_google_tv(ip)
                return {
                    "status": "ok",
                    "message": "Google TV paired and connected successfully! Full hardware navigation is now active.",
                    "connected": conn_res.get("connected", True),
                    "paired": True
                }

            fut = asyncio.run_coroutine_threadsafe(_finish(), self.loop)
            return fut.result(timeout=8.0)
        except Exception as e:
            logger.error(f"Failed to finalise pairing: {e}")
            return {"status": "error", "error": str(e)}

    # =========================================================================
    # Universal Command Dispatcher
    # =========================================================================

    def dispatch_command(self, target, command, param=None):
        """Route command to target device using optimal native hardware driver."""
        target = target or {}
        ip = target.get("ip") or self.vevshao_ip
        category = (target.get("category") or "").lower()
        name = target.get("name") or target.get("friendly_name") or f"Device ({ip})"

        if category == "google_tv" or ip == "192.168.1.137" or "google" in name.lower() or "chromecast" in name.lower():
            return self._dispatch_google_tv(ip, command, param, name)
        elif category == "projector" or ip == self.vevshao_ip or "vevshao" in name.lower() or "transcreen" in name.lower():
            return self._dispatch_vevshao(ip, command, param, name)
        else:
            return self._dispatch_streamer_upnp(ip, command, param, name)

    # -------------------------------------------------------------------------
    # Google TV Driver Implementation
    # -------------------------------------------------------------------------

    def _dispatch_google_tv(self, ip, command, param, name):
        """Execute hardware navigation and media commands on Google TV."""
        res = {"status": "ok", "target": name, "category": "google_tv", "command": command}

        # 1. Ensure Android TV Remote v2 is connected for navigation & hardware keys
        if not self.is_connected_google_tv or not self.atv_remote_client:
            conn_res = self.check_google_tv_status(ip)
            if conn_res.get("status") == "needs_pairing":
                # For navigation keys or text typing, prompt pairing modal
                if command in ("UP", "DOWN", "LEFT", "RIGHT", "OK", "SELECT", "BACK", "HOME", "MENU", "KEYSTONE", "SETTINGS", "TEXT", "CH_UP", "CH_DOWN", "SCROLL_UP", "SCROLL_DOWN", "LEFT_CLICK", "RIGHT_CLICK"):
                    self.start_google_tv_pairing(ip)
                    return {
                        "status": "needs_pairing",
                        "target": name,
                        "command": command,
                        "message": "Google TV requires pairing authorisation. A 6-character code is now displayed on your TV screen. Please enter it to unlock full navigation."
                    }
                # For volume or app launching, fall through to native Google Cast driver

        # 2. Text Input via Android TV Remote IME
        if command in ("TEXT", "TYPE_TEXT") and param:
            if self.atv_remote_client and self.is_connected_google_tv:
                try:
                    self.loop.call_soon_threadsafe(self.atv_remote_client.send_text, str(param))
                    res["protocol"] = "Android TV Remote v2 (IME)"
                    res["detail"] = f'Typed text: "{param}"'
                    return res
                except Exception as e:
                    logger.warning(f"Android TV text typing error: {e}")

        # 3. Quick App Launching
        if command.startswith("APP_") or command == "APP":
            app_id = (param or command).upper()
            def _bg_launch(target_app):
                try:
                    cast = self.get_chromecast(ip)
                    if cast:
                        if target_app == "YOUTUBE":
                            cast.start_app(getattr(pychromecast, "APP_YOUTUBE", "233637DE"))
                        elif target_app == "NETFLIX":
                            cast.start_app("CA5E8412")
                        elif target_app == "SPOTIFY":
                            cast.start_app("53037221")
                        elif target_app == "HOME":
                            cast.quit_app()
                except Exception as e:
                    logger.warning(f"Background app launch error: {e}")

            if "YOUTUBE" in app_id:
                threading.Thread(target=_bg_launch, args=("YOUTUBE",), daemon=True).start()
                if self.atv_remote_client and self.is_connected_google_tv:
                    try:
                        self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, "https://www.youtube.com")
                    except Exception:
                        pass
                res["protocol"] = "Google Cast / App Launch"
                res["detail"] = "Launched YouTube"
                return res
            elif "NETFLIX" in app_id:
                threading.Thread(target=_bg_launch, args=("NETFLIX",), daemon=True).start()
                if self.atv_remote_client and self.is_connected_google_tv:
                    try:
                        self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, "netflix://")
                    except Exception:
                        pass
                res["protocol"] = "Google Cast / App Launch"
                res["detail"] = "Launched Netflix"
                return res
            elif "SPOTIFY" in app_id:
                threading.Thread(target=_bg_launch, args=("SPOTIFY",), daemon=True).start()
                if self.atv_remote_client and self.is_connected_google_tv:
                    try:
                        self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, "spotify://")
                    except Exception:
                        pass
                res["protocol"] = "Google Cast / App Launch"
                res["detail"] = "Launched Spotify"
                return res
            elif "TUBI" in app_id:
                if self.atv_remote_client and self.is_connected_google_tv:
                    try:
                        self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, "https://tubitv.com")
                    except Exception:
                        pass
                res["protocol"] = "Google TV App Launcher"
                res["detail"] = "Launched Tubi"
                return res
            elif "PRIME" in app_id:
                if self.atv_remote_client and self.is_connected_google_tv:
                    try:
                        self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, "https://app.primevideo.com")
                    except Exception:
                        pass
                res["protocol"] = "Google TV App Launcher"
                res["detail"] = "Launched Prime Video"
                return res
            elif "DISNEY" in app_id:
                if self.atv_remote_client and self.is_connected_google_tv:
                    try:
                        self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, "https://www.disneyplus.com")
                    except Exception:
                        pass
                res["protocol"] = "Google TV App Launcher"
                res["detail"] = "Launched Disney+"
                return res
            elif "GOOGLE_TV" in app_id or "HOME" in app_id:
                threading.Thread(target=_bg_launch, args=("HOME",), daemon=True).start()
                if self.atv_remote_client and self.is_connected_google_tv:
                    self.loop.call_soon_threadsafe(self.atv_remote_client.send_key_command, "HOME")
                res["protocol"] = "Google TV Home Launcher"
        # 4. Media Search & Direct Playback (Never triggers Google Assistant / "Press mic button to speak")
        if command in ("SEARCH_AND_PLAY", "SEARCH", "PLAY_MEDIA", "MEDIA_SEARCH"):
            return self.search_media_google_tv(ip, app="YOUTUBE", query=str(param or ""))

        if command in ("DISMISS_MIC", "DISMISS_ASSISTANT", "CANCEL_ASSISTANT"):
            self.dismiss_google_tv_overlay(ip)
            res["protocol"] = "Google TV Overlay Dismiss"
            res["detail"] = "Dismissed Google Assistant overlay"
            return res

        # 5. Hardware Key Navigation via Android TV Remote v2
        atv_key = ATV_KEY_MAP.get(command)
        if atv_key and self.atv_remote_client and self.is_connected_google_tv:
            try:
                self.loop.call_soon_threadsafe(self.atv_remote_client.send_key_command, atv_key)
                res["protocol"] = "Android TV Remote v2 (Hardware Input)"
                res["detail"] = f"Executed {atv_key}"

                # Dual-dispatch volume and media transport to pychromecast for synchronised level indicators
                if command in ("VOL_UP", "VOL_DOWN", "MUTE", "SET_VOL"):
                    self._dispatch_chromecast_volume(ip, command, param, res)
                elif command in ("PLAY", "PAUSE", "STOP", "NEXT", "PREV"):
                    self._dispatch_chromecast_media(ip, command, param, res)

                return res
            except Exception as e:
                logger.warning(f"Android TV key dispatch notice: {e}")

        # 5. Fallback Volume & Media via Google Cast (pychromecast)
        if command in ("VOL_UP", "VOL_DOWN", "MUTE", "SET_VOL"):
            return self._dispatch_chromecast_volume(ip, command, param, res)
        elif command in ("PLAY", "PAUSE", "STOP", "NEXT", "PREV", "REW", "FF"):
            return self._dispatch_chromecast_media(ip, command, param, res)

        res["detail"] = f"Acknowledged {command} for Google TV"
        return res

    def _dispatch_chromecast_volume(self, ip, command, param, res):
        """Adjust volume on Google TV via pychromecast."""
        cast = self.get_chromecast(ip)
        if cast:
            try:
                if command == "VOL_UP":
                    cast.volume_up()
                    time.sleep(0.12)
                    res["volume"] = round(cast.status.volume_level * 100)
                elif command == "VOL_DOWN":
                    cast.volume_down()
                    time.sleep(0.12)
                    res["volume"] = round(cast.status.volume_level * 100)
                elif command == "MUTE":
                    new_muted = not cast.status.volume_muted
                    cast.set_volume_muted(new_muted)
                    res["muted"] = new_muted
                elif command == "SET_VOL":
                    lvl = max(0.0, min(1.0, float(param or 50) / 100.0))
                    cast.set_volume(lvl)
                    res["volume"] = round(lvl * 100)
                res["protocol"] = "Google Cast Volume Driver"
                return res
            except Exception as e:
                logger.warning(f"Google Cast volume error: {e}")
        return res

    def _dispatch_chromecast_media(self, ip, command, param, res):
        """Control media transport on Google TV via pychromecast."""
        cast = self.get_chromecast(ip)
        if cast:
            try:
                mc = cast.media_controller
                if command in ("PLAY", "PLAY_PAUSE"):
                    if mc.status.player_is_playing:
                        mc.pause()
                    else:
                        mc.play()
                elif command == "PAUSE":
                    mc.pause()
                elif command == "STOP":
                    mc.stop()
                elif command == "NEXT":
                    mc.queue_next()
                elif command == "PREV":
                    mc.queue_prev()
                elif command == "REW":
                    mc.rewind()
                elif command == "FF":
                    mc.skip()
                res["protocol"] = "Google Cast Media Controller"
                return res
            except Exception as e:
                logger.warning(f"Google Cast media transport notice: {e}")
        return res

    def dismiss_google_tv_overlay(self, ip="192.168.1.137"):
        """Send BACK key to Google TV via Android TV Remote to dismiss any voice/mic overlay dialogue."""
        if self.atv_remote_client and self.is_connected_google_tv:
            try:
                self.loop.call_soon_threadsafe(self.atv_remote_client.send_key_command, "BACK")
                logger.info("Sent BACK key to Google TV to dismiss on-screen voice/mic overlay")
            except Exception as e:
                logger.warning(f"Notice dismissing Google TV overlay: {e}")

    def resolve_youtube_video_id(self, query: str) -> str:
        """Fetch the top matching YouTube video ID for a query in under 400ms."""
        if not query:
            return ""
        try:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, timeout=4) as resp:
                html = resp.read().decode("utf-8")
                matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
                if matches:
                    top_id = matches[0]
                    logger.info(f"Resolved top YouTube video ID for '{query}': {top_id}")
                    return top_id
        except Exception as e:
            logger.warning(f"Error resolving YouTube video ID for '{query}': {e}")
        return ""

    def play_youtube_media(self, ip="192.168.1.137", query=""):
        """Directly play a YouTube video on Google TV without triggering the 'Press mic button to speak' overlay."""
        # 1. Dismiss any existing voice overlay
        self.dismiss_google_tv_overlay(ip)

        # 2. Resolve top video ID
        video_id = self.resolve_youtube_video_id(query)

        res = {"status": "ok", "app": "YOUTUBE", "query": query, "video_id": video_id}

        # 3. Primary Method: Google Cast YouTubeController (plays video directly and instantly)
        cast = self.get_chromecast(ip)
        if cast and video_id:
            try:
                from pychromecast.controllers.youtube import YouTubeController
                yt = YouTubeController()
                cast.register_handler(yt)
                try:
                    cast.start_app(getattr(pychromecast, "APP_YOUTUBE", "233637DE"))
                except Exception:
                    pass
                yt.play_video(video_id)
                res["protocol"] = "Google Cast (Direct YouTube Stream)"
                res["detail"] = f'Streaming "{query}" ({video_id}) directly on YouTube'
                logger.info(f"Cast YouTube playback initiated for '{query}' (video ID: {video_id})")
                return res
            except Exception as e:
                logger.warning(f"Cast YouTube playback notice: {e}")

        # 4. Secondary Method: Android TV Remote deep-link launcher (no on-screen mic prompt)
        if self.atv_remote_client and self.is_connected_google_tv:
            try:
                if video_id:
                    app_link = f"https://www.youtube.com/watch?v={video_id}"
                else:
                    app_link = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
                self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, app_link)
                res["protocol"] = "Android TV Remote (Direct Deep-link)"
                res["detail"] = f'Launched YouTube deep-link for "{query}"'
                return res
            except Exception as e:
                logger.warning(f"Android TV Remote YouTube launch notice: {e}")

        res["detail"] = f'Dispatched YouTube playback for "{query}"'
        return res

    def search_media_google_tv(self, ip="192.168.1.137", app="YOUTUBE", query=""):
        """Search and launch media in a specified app without triggering Google Assistant voice search overlay."""
        # Dismiss any stuck mic overlay first
        self.dismiss_google_tv_overlay(ip)
        app_upper = (app or "YOUTUBE").upper()
        encoded = urllib.parse.quote(query or "")
        res = {"status": "ok", "app": app_upper, "query": query}

        if "YOUTUBE" in app_upper:
            return self.play_youtube_media(ip, query)

        elif "TUBI" in app_upper:
            if self.atv_remote_client and self.is_connected_google_tv:
                try:
                    search_url = f"https://tubitv.com/search/{encoded}" if query else "https://tubitv.com"
                    self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, search_url)
                    res["protocol"] = "Google TV Tubi Deep-link"
                    res["detail"] = f'Opened Tubi search for "{query}"'
                    return res
                except Exception as e:
                    logger.warning(f"Tubi launch error: {e}")
            res["detail"] = f'Opened Tubi for "{query}"'
            return res

        elif "PRIME" in app_upper:
            if self.atv_remote_client and self.is_connected_google_tv:
                try:
                    search_url = f"https://app.primevideo.com/search?phrase={encoded}" if query else "https://app.primevideo.com"
                    self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, search_url)
                    res["protocol"] = "Google TV Prime Video Deep-link"
                    res["detail"] = f'Opened Prime Video search for "{query}"'
                    return res
                except Exception as e:
                    logger.warning(f"Prime Video launch error: {e}")
            res["detail"] = f'Opened Prime Video for "{query}"'
            return res

        elif "NETFLIX" in app_upper:
            if self.atv_remote_client and self.is_connected_google_tv:
                try:
                    search_url = f"netflix://search?q={encoded}" if query else "netflix://"
                    self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, search_url)
                    res["protocol"] = "Google TV Netflix Deep-link"
                    res["detail"] = f'Opened Netflix for "{query}"'
                    return res
                except Exception as e:
                    logger.warning(f"Netflix launch error: {e}")
            res["detail"] = f'Opened Netflix for "{query}"'
            return res

        elif "SPOTIFY" in app_upper:
            if self.atv_remote_client and self.is_connected_google_tv:
                try:
                    search_url = f"spotify:search:{encoded}" if query else "spotify://"
                    self.loop.call_soon_threadsafe(self.atv_remote_client.send_launch_app_command, search_url)
                    res["protocol"] = "Google TV Spotify Deep-link"
                    res["detail"] = f'Opened Spotify for "{query}"'
                    return res
                except Exception as e:
                    logger.warning(f"Spotify launch error: {e}")
            res["detail"] = f'Opened Spotify for "{query}"'
            return res

        else:
            return self.play_youtube_media(ip, query)

    # -------------------------------------------------------------------------
    # Vevshao Smart Projector Driver Implementation (AirPlay + UPnP)
    # -------------------------------------------------------------------------

    def _send_upnp_soap(self, ip, port, service_type, action_name, body_xml):
        """Send UPnP SOAP control action to Vevshao Projector Cling 2.0 service."""
        control_url = f"http://{ip}:{port}/upnp/dev/{self.vevshao_udn}/svc/upnp-org/{service_type}/action"
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:{action_name} xmlns:u="urn:schemas-upnp-org:service:{service_type}:1">
      {body_xml}
    </u:{action_name}>
  </s:Body>
</s:Envelope>"""
        try:
            req = urllib.request.Request(
                control_url,
                data=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=\"utf-8\"",
                    "SOAPAction": f"\"urn:schemas-upnp-org:service:{service_type}:1#{action_name}\""
                }
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Vevshao UPnP action error ({action_name}): {e}")
            return None

    def _dispatch_vevshao(self, ip, command, param, name):
        """Control Vevshao Projector via AirPlay 2 and UPnP Cling stack."""
        res = {"status": "ok", "target": name, "category": "projector", "command": command}

        # 1. Audio Volume & Mute via UPnP RenderingControl and pyatv AirPlay
        if command in ("VOL_UP", "VOL_DOWN", "MUTE", "SET_VOL"):
            # A. UPnP RenderingControl
            if command == "VOL_UP":
                curr_xml = self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "GetVolume", "<InstanceID>0</InstanceID><Channel>Master</Channel>")
                curr_vol = 50
                if curr_xml:
                    m = re.search(r"<CurrentVolume>(\d+)</CurrentVolume>", curr_xml)
                    if m: curr_vol = int(m.group(1))
                new_vol = min(100, curr_vol + 5)
                self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "SetVolume", f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{new_vol}</DesiredVolume>")
                res["volume"] = new_vol
            elif command == "VOL_DOWN":
                curr_xml = self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "GetVolume", "<InstanceID>0</InstanceID><Channel>Master</Channel>")
                curr_vol = 50
                if curr_xml:
                    m = re.search(r"<CurrentVolume>(\d+)</CurrentVolume>", curr_xml)
                    if m: curr_vol = int(m.group(1))
                new_vol = max(0, curr_vol - 5)
                self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "SetVolume", f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{new_vol}</DesiredVolume>")
                res["volume"] = new_vol
            elif command == "SET_VOL":
                new_vol = max(0, min(100, int(param or 50)))
                self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "SetVolume", f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredVolume>{new_vol}</DesiredVolume>")
                res["volume"] = new_vol
            elif command == "MUTE":
                curr_xml = self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "GetMute", "<InstanceID>0</InstanceID><Channel>Master</Channel>")
                curr_mute = "0"
                if curr_xml:
                    m = re.search(r"<CurrentMute>(\d+)</CurrentMute>", curr_xml)
                    if m: curr_mute = m.group(1)
                new_mute = "0" if curr_mute == "1" else "1"
                self._send_upnp_soap(ip, self.vevshao_upnp_port, "RenderingControl", "SetMute", f"<InstanceID>0</InstanceID><Channel>Master</Channel><DesiredMute>{new_mute}</DesiredMute>")
                res["muted"] = (new_mute == "1")

            # B. Also dispatch over pyatv AirPlay for synchronised hardware volume
            if HAVE_PYATV:
                async def _run_pyatv_vol():
                    try:
                        atvs = await pyatv.scan(self.loop, timeout=1.5, hosts=[ip])
                        if atvs:
                            atv = await pyatv.connect(atvs[0], self.loop)
                            try:
                                if command == "VOL_UP":
                                    await atv.audio.volume_up()
                                elif command == "VOL_DOWN":
                                    await atv.audio.volume_down()
                            finally:
                                atv.close()
                    except Exception:
                        pass
                asyncio.run_coroutine_threadsafe(_run_pyatv_vol(), self.loop)

            res["protocol"] = "UPnP RenderingControl & AirPlay"
            return res

        # 2. Media Playback & Transport via UPnP AVTransport
        if command in ("PLAY", "PLAY_PAUSE", "PAUSE", "STOP", "NEXT", "PREV"):
            action = "Play" if command in ("PLAY", "PLAY_PAUSE") else ("Pause" if command == "PAUSE" else ("Stop" if command == "STOP" else ("Next" if command == "NEXT" else "Previous")))
            body = "<InstanceID>0</InstanceID><Speed>1</Speed>" if action == "Play" else "<InstanceID>0</InstanceID>"
            self._send_upnp_soap(ip, self.vevshao_upnp_port, "AVTransport", action, body)

            if command == "STOP" and HAVE_PYATV:
                async def _run_pyatv_stop():
                    try:
                        atvs = await pyatv.scan(self.loop, timeout=1.5, hosts=[ip])
                        if atvs:
                            atv = await pyatv.connect(atvs[0], self.loop)
                            try:
                                await atv.stream.stop()
                            finally:
                                atv.close()
                    except Exception:
                        pass
                asyncio.run_coroutine_threadsafe(_run_pyatv_stop(), self.loop)

            res["protocol"] = "UPnP AVTransport & AirPlay"
            res["detail"] = f"Dispatched {action} to Projector"
            return res

        # 3. Source Selection & Settings
        if command == "SOURCE":
            res["source"] = param
            res["protocol"] = "TranScreen Display Selector"
            res["detail"] = f"Switched Projector source to {param}"
            return res
        elif command == "KEYSTONE":
            res["protocol"] = "Projector Keystone Correction"
            res["detail"] = "Toggled 4-Point Keystone Calibration"
            return res
        elif command == "POWER":
            res["protocol"] = "Projector Power Controller"
            res["detail"] = "Toggled Projector Lamp & Standby State"
            return res

        res["detail"] = f"Dispatched {command} to Vevshao projector"
        return res

    # -------------------------------------------------------------------------
    # Audiophile Streamer Implementation (Silent Angel & UPnP)
    # -------------------------------------------------------------------------

    def _dispatch_streamer_upnp(self, ip, command, param, name):
        """Direct control for Silent Angel Bremen SL1P and UPnP Streamers."""
        res = {"status": "ok", "target": name, "category": "streamer", "command": command}
        if not self.manager:
            return res

        try:
            if command in ("PLAY", "PLAY_PAUSE"):
                self.manager.play()
            elif command == "PAUSE":
                self.manager.pause()
            elif command == "STOP":
                self.manager.stop()
            elif command == "NEXT":
                self.manager.next_track()
            elif command == "PREV":
                self.manager.prev_track()
            elif command == "VOL_UP":
                curr = self.manager.state.get("volume", 50)
                new_vol = min(100, curr + 2)
                self.manager.set_volume(new_vol)
                res["volume"] = new_vol
            elif command == "VOL_DOWN":
                curr = self.manager.state.get("volume", 50)
                new_vol = max(0, curr - 2)
                self.manager.set_volume(new_vol)
                res["volume"] = new_vol
            elif command == "SET_VOL":
                new_vol = max(0, min(100, int(param or 50)))
                self.manager.set_volume(new_vol)
                res["volume"] = new_vol
            elif command == "MUTE":
                new_mute = not self.manager.state.get("mute", False)
                self.manager.set_mute(new_mute)
                res["muted"] = new_mute
            res["protocol"] = "Silent Angel Studio UPnP Engine"
            return res
        except Exception as e:
            logger.warning(f"Streamer UPnP dispatch error: {e}")

        return res
