import os
import sys
import time
import json
import asyncio
import threading
import subprocess
import shutil
from pathlib import Path
from typing import Set

import psutil
from aiohttp import web, WSMsgType

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import HOST, PORT, STATIC_DIR, DEFAULT_BROWSER
from jarvis.brain.engine import brain_service
from jarvis.voice.speaker import voice_speaker
from jarvis.memory import memory_service
from jarvis.actions.apps import AppManager
from jarvis.actions.vision import screen_vision

BOOT_TIME = psutil.boot_time()

def detect_distro_name() -> str:
    """Detects Linux distribution name cleanly."""
    try:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            for line in os_release.read_text(encoding="utf-8").splitlines():
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip('"\'')
    except Exception:
        pass
    return "Linux"

DISTRO_NAME = detect_distro_name()


class EzraUIServer:
    """
    JARVIS Holographic UI Web & WebSocket Server.
    Provides real-time telemetry streaming, interactive chat, and desktop control station.
    """

    def __init__(self, host: str = None, port: int = None):
        self.host = host or HOST or "127.0.0.1"
        self.port = port or PORT or 8080
        self.app = web.Application()
        self.ws_clients: Set[web.WebSocketResponse] = set()
        self.current_state = "idle"  # 'idle' | 'listening' | 'thinking' | 'speaking'
        self.dwell_remaining = 25.0
        self._bg_task = None
        self._setup_routes()

    def _setup_routes(self):
        # Web Pages
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/ws", self.handle_websocket)

        # REST APIs
        self.app.router.add_get("/api/status", self.handle_api_status)
        self.app.router.add_post("/api/chat", self.handle_api_chat)
        self.app.router.add_post("/api/action", self.handle_api_action)
        self.app.router.add_get("/api/screenshot", self.handle_api_screenshot)

        # Static file serving
        static_path = STATIC_DIR
        if static_path.exists():
            self.app.router.add_static("/static/", path=str(static_path), name="static")

    async def handle_index(self, request: web.Request):
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return web.FileResponse(index_file)
        return web.Response(text="<h1>Project Ezra UI Initializing...</h1>", content_type="text/html")

    async def handle_api_status(self, request: web.Request):
        data = self._gather_telemetry()
        return web.json_response(data)

    async def handle_api_chat(self, request: web.Request):
        try:
            body = await request.json()
            text = body.get("text", "").strip()
            if not text:
                return web.json_response({"error": "Empty prompt"}, status=400)

            await self.broadcast({"type": "state_change", "state": "thinking", "detail": "Reasoning with AI..."})
            resp = await brain_service.think(text)
            reply_speech = resp.get("speech_text", "")

            await self.broadcast({"type": "speech", "speaker": "EZRA", "text": reply_speech})
            await self.broadcast({"type": "state_change", "state": "speaking", "detail": "Vocalizing..."})

            # Voice output
            voice_speaker.speak(reply_speech, live_print=False)
            await self.broadcast({"type": "state_change", "state": "idle", "detail": "Standby"})

            return web.json_response(resp)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_api_action(self, request: web.Request):
        try:
            body = await request.json()
            action = body.get("action", "")
            result = self._execute_action(action)
            return web.json_response({"status": "success", "action": action, "result": result})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_api_screenshot(self, request: web.Request):
        try:
            img = screen_vision.capture_screen()
            if img:
                out_path = PROJECT_ROOT / "cache" / "latest_screen.png"
                img.save(str(out_path), format="PNG")
                return web.FileResponse(out_path)
            return web.Response(text="Screenshot capture failed", status=500)
        except Exception as e:
            return web.Response(text=str(e), status=500)

    def _gather_telemetry(self) -> dict:
        uptime_sec = int(time.time() - BOOT_TIME)
        hrs = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60

        # Memory items
        mems = []
        try:
            mems = memory_service.get_all_memories()[:5]
        except Exception:
            pass

        # Active engine
        engine_name = "Groq 14.4k"
        if getattr(brain_service, "groq_key", ""):
            engine_name = "Groq 14.4k"
        elif getattr(brain_service, "gemini_key", ""):
            engine_name = "Gemini Pro"
        else:
            engine_name = "Ollama Offline"

        return {
            "type": "telemetry",
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
            "uptime": f"{hrs}h {mins}m",
            "distro": DISTRO_NAME,
            "engine": engine_name,
            "user_name": "Ahmad",
            "tier": "verified",
            "lid_status": "open",
            "dwell_sec": self.dwell_remaining,
            "memories_count": len(mems),
            "state": self.current_state,
        }

    async def broadcast(self, msg: dict):
        if not self.ws_clients:
            return
        payload = json.dumps(msg)
        dead = []
        for ws in self.ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.ws_clients.discard(ws)

    async def handle_websocket(self, request: web.Request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.ws_clients.add(ws)

        # Send initial telemetry snapshot
        telem = self._gather_telemetry()
        await ws.send_str(json.dumps(telem))

        # Send memory list
        try:
            mems = memory_service.get_all_memories()[:10]
            await ws.send_str(json.dumps({"type": "memories", "items": mems}))
        except Exception:
            pass

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        msg_type = data.get("type")

                        if msg_type == "chat":
                            text = data.get("text", "").strip()
                            if text:
                                await self.broadcast({"type": "state_change", "state": "thinking", "detail": "Reasoning with AI..."})
                                resp = await brain_service.think(text)
                                reply_speech = resp.get("speech_text", "")
                                await self.broadcast({"type": "speech", "speaker": "EZRA", "text": reply_speech})
                                await self.broadcast({"type": "state_change", "state": "speaking", "detail": "Vocalizing..."})
                                voice_speaker.speak(reply_speech, live_print=False)
                                await self.broadcast({"type": "state_change", "state": "idle", "detail": "Standby"})

                        elif msg_type == "voice_trigger":
                            v_action = data.get("action", "stop")
                            if v_action == "start":
                                await self.broadcast({"type": "state_change", "state": "listening", "detail": "Mic active"})
                            else:
                                await self.broadcast({"type": "state_change", "state": "idle", "detail": "Standby"})

                        elif msg_type == "action":
                            action = data.get("action", "")
                            res = self._execute_action(action)
                            await self.broadcast({"type": "action_result", "action": action, "result": res})

                        elif msg_type == "control":
                            action = data.get("action")
                            val = data.get("value")
                            if action == "mute":
                                voice_speaker.set_muted(bool(val))
                            elif action == "robotic_voice":
                                voice_speaker.set_robotic_mode(bool(val))
                            elif action == "volume":
                                # Native PipeWire / PulseAudio volume
                                try:
                                    vol = max(0, min(100, int(val)))
                                    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                except Exception:
                                    pass

                    except Exception as err:
                        print(f"[WS Handler Error] {err}")

                elif msg.type == WSMsgType.ERROR:
                    print(f"[WS Error] {ws.exception()}")

        finally:
            self.ws_clients.discard(ws)

        return ws

    def _execute_action(self, action: str):
        if action == "open_antigravity":
            return AppManager.open_app("antigravity")
        elif action == "open_terminal":
            return AppManager.open_terminal()
        elif action == "open_browser":
            # Brave is installed as Flatpak (com.brave.Browser)
            try:
                import subprocess as _sp
                _sp.Popen(["flatpak", "run", "com.brave.Browser"], start_new_session=True)
                return "Brave launched"
            except Exception:
                browser = DEFAULT_BROWSER or "google-chrome"
                return AppManager.open_app(browser)
        elif action == "capture_screen":
            img = screen_vision.capture_screen()
            return "Screenshot captured successfully" if img else "Failed"
        return "Unknown action"

    async def _telemetry_broadcast_loop(self):
        while True:
            try:
                await asyncio.sleep(1.0)
                if self.ws_clients:
                    telem = self._gather_telemetry()
                    await self.broadcast(telem)
            except asyncio.CancelledError:
                break
            except Exception:
                pass


def open_ui_in_browser(host: str = "127.0.0.1", port: int = 8080):
    """Opens Ezra Holographic UI in dedicated borderless App Window or default browser."""
    url = f"http://{host}:{port}"
    for browser in ["google-chrome", "brave", "chromium", "firefox"]:
        if shutil.which(browser):
            try:
                if browser in ("google-chrome", "brave", "chromium"):
                    subprocess.Popen([browser, f"--app={url}", "--title=Project Ezra // Holographic Core"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                else:
                    subprocess.Popen([browser, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
            except Exception:
                pass

    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


def run_ui_standalone():
    """Runs Ezra Holographic UI Server standalone."""
    print("\n\033[1;36m╔═══════════════════════════════════════════════════════════════╗\033[0m")
    print("\033[1;36m║          ⚡ PROJECT EZRA // HOLOGRAPHIC JARVIS UI CORE         ║\033[0m")
    print("\033[1;36m╚═══════════════════════════════════════════════════════════════╝\033[0m")
    print(f"\033[1;32m[+] Server Online:\033[0m http://{HOST}:{PORT}")
    print("\033[1;32m[+] Hologram Engine:\033[0m 3D Neural Cortex & Orbiting Gyroscope Active\n")

    server = EzraUIServer(host=HOST, port=PORT)

    async def _start():
        runner = web.AppRunner(server.app)
        await runner.setup()
        site = web.TCPSite(runner, server.host, server.port)
        await site.start()
        # Start background telemetry broadcaster
        asyncio.create_task(server._telemetry_broadcast_loop())
        # Open browser window
        open_ui_in_browser(server.host, server.port)
        # Keep running
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(_start())
    except (KeyboardInterrupt, SystemExit):
        print("\n\033[1;33m[!] Shutting down Ezra UI server cleanly.\033[0m")


def start_ui_server_thread(host: str = "127.0.0.1", port: int = 8080):
    """Starts the UI server in a daemon thread so it runs alongside app.py."""
    def _runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        server = EzraUIServer(host=host, port=port)

        async def _run():
            app_runner = web.AppRunner(server.app)
            await app_runner.setup()
            site = web.TCPSite(app_runner, server.host, server.port)
            await site.start()
            asyncio.create_task(server._telemetry_broadcast_loop())
            while True:
                await asyncio.sleep(3600)

        loop.run_until_complete(_run())

    t = threading.Thread(target=_runner, daemon=True, name="EzraUIServerThread")
    t.start()
    return t


if __name__ == "__main__":
    run_ui_standalone()
