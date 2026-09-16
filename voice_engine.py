# -*- coding: utf-8 -*-
"""
Voice Engine for Silent Angel Bremen SL1P / Studio Controller.
Combines Voice Activity Detection metadata, Sub-15ms Local Reflex matching,
and the MiniMax Cognitive AI Model (MiniMax-Text-01) for intelligent
ambient room voice-to-command decision making and multi-device routines.
"""

import os
import re
import json
import time
import logging
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

logger = logging.getLogger("VoiceEngine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def load_dotenv(env_path: str = ".env") -> None:
    """Load environment variables from a .env file if present without overriding existing env vars."""
    candidate_paths = [
        env_path,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), env_path),
        os.path.join(os.getcwd(), env_path),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k and k not in os.environ:
                                os.environ[k] = v
                break
            except Exception as e:
                logger.warning(f"Failed to read .env from {path}: {e}")

load_dotenv()

DEFAULT_MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY", "")

ROUTINES_FILE = "voice_routines.json"


class SmartLightingController:
    """
    Smart Lighting controller supporting Philips Hue bridges,
    Home Assistant REST webhooks, and the built-in Studio Ambiance Engine.
    """

    PRESETS = {
        "full_lumens": {"power": "ON", "brightness": 100, "colour": "daylight_white", "hex": "#ffffff", "name": "Full Lumens (Daylight)"},
        "daylight_white": {"power": "ON", "brightness": 100, "colour": "daylight_white", "hex": "#f4f8ff", "name": "Daylight White"},
        "warm_gold": {"power": "ON", "brightness": 35, "colour": "warm_gold", "hex": "#d4af37", "name": "Studio Warm Gold"},
        "cinema_dim": {"power": "ON", "brightness": 12, "colour": "cinema_dim", "hex": "#ff9900", "name": "Cinema Atmosphere"},
        "relaxing_indigo": {"power": "ON", "brightness": 25, "colour": "relaxing_indigo", "hex": "#5e35b1", "name": "Late Night Indigo"},
        "off": {"power": "OFF", "brightness": 0, "colour": "off", "hex": "#0d0e10", "name": "Extinguish All Lights"}
    }

    def __init__(self):
        self.state = {
            "power": "ON",
            "brightness": 70,
            "colour": "warm_gold",
            "hex": "#d4af37",
            "last_preset": "warm_gold",
            "active_mode": "Studio Ambiance Engine"
        }
        self._lock = threading.Lock()

    def set_state(self, power: Optional[str] = None, brightness: Optional[int] = None, colour: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if colour and colour.lower() in self.PRESETS:
                preset = self.PRESETS[colour.lower()]
                self.state["power"] = preset["power"]
                self.state["brightness"] = preset["brightness"]
                self.state["colour"] = preset["colour"]
                self.state["hex"] = preset["hex"]
                self.state["last_preset"] = colour.lower()
            else:
                if power is not None:
                    self.state["power"] = power.upper()
                    if self.state["power"] == "OFF":
                        self.state["brightness"] = 0
                if brightness is not None:
                    self.state["brightness"] = max(0, min(100, int(brightness)))
                    if self.state["brightness"] > 0:
                        self.state["power"] = "ON"
                if colour is not None:
                    self.state["colour"] = colour
            return dict(self.state)

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.state)


class VoiceDecisionEngine:
    """
    Cognitive Voice Decision & Automation Engine.
    Evaluates speech transcripts via local reflex or MiniMax AI,
    chains multi-device routines, and logs decisions for the UI HUD.
    """

    def __init__(self, multi_device_controller=None, routines_path=ROUTINES_FILE):
        self.mdc = multi_device_controller
        self.lighting = SmartLightingController()
        self.routines_path = routines_path
        self.api_key = DEFAULT_MINIMAX_KEY
        self.model = "MiniMax-Text-01"
        self.api_url = "https://api.minimax.io/v1/text/chatcompletion_v2"
        self.routines = []
        self.history = []
        self._lock = threading.Lock()
        self.vad_state = {
            "listening": True,
            "voice_detected": False,
            "last_noise_level": -45.0,
            "noise_threshold": -36.0,
            "sensitivity": 75,
            "last_transcript": "",
            "last_action_timestamp": time.time()
        }
        self.load_routines()

    def load_routines(self):
        try:
            if os.path.exists(self.routines_path):
                with open(self.routines_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.routines = data.get("routines", [])
                logger.info(f"Loaded {len(self.routines)} voice routines from {self.routines_path}")
            else:
                self.routines = []
        except Exception as e:
            logger.error(f"Error loading routines: {e}")
            self.routines = []

    def save_routines(self):
        try:
            with open(self.routines_path, "w", encoding="utf-8") as f:
                json.dump({"version": "1.0.0", "routines": self.routines}, f, indent=2)
            logger.info("Saved voice routines successfully.")
            return True
        except Exception as e:
            logger.error(f"Error saving routines: {e}")
            return False

    def update_vad_status(self, noise_level: float, is_voice: bool, sensitivity: Optional[int] = None):
        with self._lock:
            self.vad_state["last_noise_level"] = noise_level
            self.vad_state["voice_detected"] = is_voice
            if sensitivity is not None:
                self.vad_state["sensitivity"] = sensitivity

    def evaluate_local_reflex(self, transcript: str) -> Optional[Dict[str, Any]]:
        t_clean = transcript.lower().strip()
        for ch in [".", ",", "!", "?", ";", ":", "\x27", "\x22"]:
            t_clean = t_clean.replace(ch, "")

        # 1. Urgent volume suppress / silence cues
        urgent_silence_tokens = [
            "shutup", "shut up", "ssshhh", "shhh", "ssh", "be quiet",
            "quiet please", "turn the volume down", "turn down the volume",
            "turn it down", "too loud", "mute", "silence"
        ]
        for token in urgent_silence_tokens:
            if token in t_clean:
                return {
                    "source": "local_reflex",
                    "routine_id": "urgent_volume_suppress",
                    "intent": "volume_control",
                    "target_device": "active_target",
                    "actions": [
                        {"device": "active_target", "command": "VOL_DOWN", "param": 20, "delay_ms": 0}
                    ],
                    "confidence": 0.99,
                    "explanation": f"Acoustic reflex trigger matched: {token}. Promptly suppressing volume."
                }

        # 2. Volume boost cues
        boost_tokens = [
            "turn it up", "turn the volume up", "louder", "volume up",
            "make it louder", "cant hear"
        ]
        for token in boost_tokens:
            if token in t_clean:
                return {
                    "source": "local_reflex",
                    "routine_id": "volume_boost",
                    "intent": "volume_control",
                    "target_device": "active_target",
                    "actions": [
                        {"device": "active_target", "command": "VOL_UP", "param": 10, "delay_ms": 0}
                    ],
                    "confidence": 0.98,
                    "explanation": f"Acoustic reflex trigger matched: {token}. Increasing playback volume."
                }

        # 3. Urgent transport controls
        if t_clean in ["pause", "pause music", "pause playback", "freeze"]:
            return {
                "source": "local_reflex",
                "routine_id": "transport_pause",
                "intent": "playback_control",
                "target_device": "active_target",
                "actions": [
                    {"device": "active_target", "command": "PAUSE", "param": None, "delay_ms": 0}
                ],
                "confidence": 0.99,
                "explanation": "Acoustic reflex trigger matched: pause. Pausing current playback."
            }

        if t_clean in ["resume", "play", "continue", "unpause"]:
            return {
                "source": "local_reflex",
                "routine_id": "transport_play",
                "intent": "playback_control",
                "target_device": "active_target",
                "actions": [
                    {"device": "active_target", "command": "PLAY", "param": None, "delay_ms": 0}
                ],
                "confidence": 0.98,
                "explanation": "Acoustic reflex trigger matched: play. Resuming playback."
            }

        # 4. Darkness complaints (Lighting)
        dark_tokens = ["its too dark", "it is too dark", "too dark in here", "cant see anything", "turn on the lights", "lights to full"]
        for token in dark_tokens:
            if token in t_clean:
                return {
                    "source": "local_reflex",
                    "routine_id": "lights_brighten_dark",
                    "intent": "lighting_control",
                    "target_device": "smart_lighting",
                    "actions": [
                        {"device": "smart_lighting", "command": "POWER", "param": "ON", "delay_ms": 0},
                        {"device": "smart_lighting", "command": "BRIGHTNESS", "param": 100, "delay_ms": 100},
                        {"device": "smart_lighting", "command": "COLOUR", "param": "daylight_white", "delay_ms": 200}
                    ],
                    "confidence": 0.98,
                    "explanation": f"Acoustic reflex trigger matched: {token}. Raising lights to maximum brightness."
                }

        # 5. Cinema / Dim lighting
        dim_tokens = ["dim the lights", "movie mode", "cinema mode", "lights for movie", "dim lighting"]
        for token in dim_tokens:
            if token in t_clean:
                return {
                    "source": "local_reflex",
                    "routine_id": "lights_cinema_dim",
                    "intent": "lighting_control",
                    "target_device": "smart_lighting",
                    "actions": [
                        {"device": "smart_lighting", "command": "BRIGHTNESS", "param": 15, "delay_ms": 0},
                        {"device": "smart_lighting", "command": "COLOUR", "param": "warm_gold", "delay_ms": 100}
                    ],
                    "confidence": 0.98,
                    "explanation": f"Acoustic reflex trigger matched: {token}. Dims room lighting to warm gold ambiance."
                }

        return None

    def query_minimax_cognitive_engine(self, transcript: str) -> Dict[str, Any]:
        if not self.api_key:
            self.api_key = os.environ.get("MINIMAX_API_KEY", "")

        if not self.api_key:
            logger.warning("MiniMax API key is not configured in environment or .env file.")
            return {
                "source": "unconfigured_key",
                "is_intended_for_system": False,
                "intent": "none",
                "target_device": "none",
                "actions": [],
                "confidence": 0.0,
                "explanation": "MiniMax API key is not configured in .env file."
            }

        system_prompt = (
            "You are the intelligent ambient acoustic brain for a high-end studio entertainment system.\n"
            "Devices connected on the local network:\n"
            "1. Google TV (IP: 192.168.1.137) - Supports launching apps (YOUTUBE, TUBI, PRIME_VIDEO, NETFLIX, SPOTIFY), searching and playing media directly without voice assistant dialogs, volume, navigation.\n"
            "   IMPORTANT: To play a track, artist, song or genre on YouTube, output actions:\n"
            "     [{\"device\": \"google_tv\", \"command\": \"APP\", \"param\": \"YOUTUBE\", \"delay_ms\": 0}, {\"device\": \"google_tv\", \"command\": \"SEARCH_AND_PLAY\", \"param\": \"<artist or track>\", \"delay_ms\": 500}]\n"
            "   IMPORTANT: To search or watch a movie or show on Tubi, output actions:\n"
            "     [{\"device\": \"google_tv\", \"command\": \"APP\", \"param\": \"TUBI\", \"delay_ms\": 0}, {\"device\": \"google_tv\", \"command\": \"SEARCH_AND_PLAY\", \"param\": \"<title or genre>\", \"delay_ms\": 500}]\n"
            "   IMPORTANT: To search or watch on Prime Video, output actions:\n"
            "     [{\"device\": \"google_tv\", \"command\": \"APP\", \"param\": \"PRIME_VIDEO\", \"delay_ms\": 0}, {\"device\": \"google_tv\", \"command\": \"SEARCH_AND_PLAY\", \"param\": \"<title>\", \"delay_ms\": 500}]\n"
            "2. Vevshao Projector (IP: 192.168.1.121) - Supports UPnP/DLNA and AirPlay playback, volume adjustment, keystone setup.\n"
            "3. Silent Angel Bremen SL1P (Hi-Fi Streamer) - Supports pristine audio streaming and transport control.\n"
            "4. Smart Lighting - Supports brightness (0-100%), power (ON/OFF), and colour ambiance (daylight_white, warm_gold, cinema_dim, relaxing_indigo).\n\n"
            "Analyse the room speech transcript. Determine if the speaker wants action on connected devices or if it is merely conversational banter.\n"
            "Respond ONLY with valid JSON conforming to this schema:\n"
            "{\n"
            "  \"is_intended_for_system\": true or false,\n"
            "  \"intent\": \"media_search\" | \"volume_control\" | \"lighting_control\" | \"playback_control\" | \"app_launch\" | \"none\",\n"
            "  \"target_device\": \"google_tv\" | \"projector\" | \"streamer\" | \"smart_lighting\" | \"none\",\n"
            "  \"actions\": [\n"
            "    {\"device\": \"google_tv\", \"command\": \"APP\", \"param\": \"YOUTUBE\", \"delay_ms\": 0},\n"
            "    {\"device\": \"google_tv\", \"command\": \"SEARCH_AND_PLAY\", \"param\": \"Pink Floyd\", \"delay_ms\": 500}\n"
            "  ],\n"
            "  \"confidence\": 0.0 to 1.0,\n"
            "  \"explanation\": \"Concise explanation in UK English\"\n"
            "}"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Heard in room: \"{transcript}\""}
            ],
            "temperature": 0.1
        }

        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                raw_body = resp.read().decode("utf-8")
                resp_json = json.loads(raw_body)
                content = resp_json["choices"][0]["message"]["content"]
                
                clean_json = content.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()

                parsed = json.loads(clean_json)
                parsed["source"] = "minimax_ai"
                return parsed
        except Exception as e:
            logger.error(f"MiniMax API query failed: {e}")
            return {
                "source": "error_fallback",
                "is_intended_for_system": False,
                "intent": "none",
                "target_device": "none",
                "actions": [],
                "confidence": 0.0,
                "explanation": f"MiniMax cognitive query encountered an error: {e}"
            }

    def process_transcript(self, transcript: str, bypass_vad: bool = False) -> Dict[str, Any]:
        if not transcript or not transcript.strip():
            return {"status": "ignored", "reason": "empty_transcript"}

        t_clean = transcript.strip()
        start_time = time.time()

        decision = self.evaluate_local_reflex(t_clean)
        if not decision:
            decision = self.query_minimax_cognitive_engine(t_clean)
        
        elapsed_ms = round((time.time() - start_time) * 1000, 1)
        decision["elapsed_ms"] = elapsed_ms
        decision["transcript"] = t_clean
        decision["timestamp"] = time.strftime("%H:%M:%S")

        executed_results = []
        if decision.get("is_intended_for_system", True) and decision.get("actions"):
            executed_results = self.execute_actions(decision["actions"])
            decision["executed"] = True
            decision["action_results"] = executed_results
        else:
            decision["executed"] = False

        with self._lock:
            self.history.insert(0, decision)
            if len(self.history) > 60:
                self.history = self.history[:60]
            self.vad_state["last_transcript"] = t_clean
            self.vad_state["last_action_timestamp"] = time.time()

        return decision

    def execute_actions(self, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []

        def _runner():
            current_app = "YOUTUBE"
            for action in actions:
                device = action.get("device")
                command = action.get("command")
                param = action.get("param")
                delay_ms = action.get("delay_ms", 0)

                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

                res = {"device": device, "command": command, "param": param, "status": "ok"}

                try:
                    if device == "smart_lighting":
                        if command == "POWER":
                            l_res = self.lighting.set_state(power=param)
                            res["state"] = l_res
                        elif command == "BRIGHTNESS":
                            l_res = self.lighting.set_state(brightness=int(param))
                            res["state"] = l_res
                        elif command == "COLOUR":
                            l_res = self.lighting.set_state(colour=str(param))
                            res["state"] = l_res
                        logger.info(f"Lighting action executed: {command} -> {param}")

                    elif self.mdc:
                        if device == "active_target":
                            target_dict = self.mdc.active_target or {"ip": "192.168.1.137", "category": "google_tv"}
                            self.mdc.dispatch_command(target_dict, command, param)
                        elif device == "google_tv":
                            target_dict = {"ip": "192.168.1.137", "category": "google_tv"}
                            if command == "APP":
                                current_app = str(param or "YOUTUBE").upper()
                                self.mdc.dispatch_command(target_dict, command, param)
                            elif command in ["SEARCH_AND_PLAY", "SEARCH", "PLAY_MEDIA"]:
                                self._execute_google_tv_search(str(param or ""), app=current_app)
                            elif command in ["DISMISS_MIC", "DISMISS_ASSISTANT"]:
                                self.mdc.dismiss_google_tv_overlay("192.168.1.137")
                            else:
                                self.mdc.dispatch_command(target_dict, command, param)
                        elif device == "projector":
                            target_dict = {"ip": "192.168.1.121", "category": "projector"}
                            self.mdc.dispatch_command(target_dict, command, param)
                        elif device == "streamer":
                            target_dict = {"ip": "192.168.1.188", "category": "silent_angel"}
                            self.mdc.dispatch_command(target_dict, command, param)
                except Exception as ex:
                    logger.error(f"Error executing action {action}: {ex}")
                    res["status"] = "error"
                    res["error"] = str(ex)

                results.append(res)

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        return [{"status": "dispatched", "count": len(actions)}]

    def _execute_google_tv_search(self, query: str, app: str = "YOUTUBE"):
        """Directly search and play media on Google TV without summoning Google Assistant / 'Press mic button to speak'."""
        if not self.mdc:
            return
        try:
            # Ensure any lingering on-screen mic overlay is dismissed
            self.mdc.dismiss_google_tv_overlay("192.168.1.137")
            time.sleep(0.2)
            # Directly search and play media cleanly
            res = self.mdc.search_media_google_tv("192.168.1.137", app=app, query=query)
            logger.info(f"Google TV direct media action executed cleanly for '{query}' on {app}: {res.get('detail')}")
        except Exception as e:
            logger.error(f"Google TV direct search error: {e}")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "vad": self.vad_state,
                "lighting": self.lighting.get_state(),
                "routines_count": len(self.routines),
                "model": self.model,
                "history": self.history[:20]
            }
