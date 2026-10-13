import os
import sys
import asyncio
import logging
import aiohttp
from pathlib import Path
from typing import Optional, Dict, Any

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PROJECT_ROOT
from jarvis.actions.system import SystemManager
from jarvis.actions.apis import api_manager
from jarvis.actions.apps import AppManager
from jarvis.voice.speaker import voice_speaker

logger = logging.getLogger("telegram_daemon")

class TelegramRemoteDaemon:
    """
    Two-Way Free Telegram Remote Control Daemon for Project Ezra.
    Uses Telegram Bot API long-polling (getUpdates): 100% free, zero webhook or public IP needed.
    """

    def __init__(self, token: Optional[str] = None, allowed_chat_id: Optional[str] = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.allowed_chat_id = allowed_chat_id or TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.is_running = False
        self.last_update_id = 0

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
        """Sends a text message to Telegram."""
        if not self.token:
            return False
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    return bool(data.get("ok"))
        except Exception as e:
            logger.warning(f"Failed to send Telegram message: {e}")
            return False

    async def send_photo(self, chat_id: str, photo_path: Path, caption: str = "") -> bool:
        """Uploads and sends a photo file to Telegram."""
        if not self.token or not photo_path.exists():
            return False
        url = f"{self.base_url}/sendPhoto"
        try:
            data = aiohttp.FormData()
            data.add_field("chat_id", str(chat_id))
            if caption:
                data.add_field("caption", caption)
            with open(photo_path, "rb") as f:
                data.add_field("photo", f.read(), filename=photo_path.name, content_type="image/png")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    res_data = await resp.json()
                    return bool(res_data.get("ok"))
        except Exception as e:
            logger.warning(f"Failed to send photo: {e}")
            return False

    async def handle_update(self, update: Dict[str, Any]):
        """Dispatches an incoming Telegram message update."""
        msg = update.get("message")
        if not msg:
            return

        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()
        from_user = msg.get("from", {}).get("first_name", "Sir")

        # Security check: if allowed_chat_id is set, reject unauthorized chats
        if self.allowed_chat_id and str(chat_id) != str(self.allowed_chat_id):
            await self.send_message(
                chat_id,
                f"⛔ *Access Denied*\nProject Ezra is locked to authorized master devices.\nYour Chat ID: `{chat_id}`"
            )
            return

        if not text:
            return

        # 1. /start or /help
        if text.lower() in ("/start", "/help"):
            help_text = (
                f"🇬🇧 *Project Ezra // Mobile Link Active*\n"
                f"Good day, {from_user}. Standing by for desktop commands:\n\n"
                f"📊 `/status` — Live CPU, RAM, Battery & Git state\n"
                f"📸 `/snap` — Capture live desktop screenshot\n"
                f"☕ `/brief` — Executive Morning Briefing\n"
                f"🗣 `/say <text>` — Speak phrase aloud through PC speakers\n"
                f"💻 `/run <cmd>` — Execute terminal command\n"
                f"💬 *Any other text* — Conversational brain query\n\n"
                f"_Chat ID: {chat_id}_"
            )
            await self.send_message(chat_id, help_text)
            return

        # 2. /status
        if text.lower() == "/status":
            sys_stat = SystemManager.get_system_status()
            git_stat = SystemManager.git_status()
            clean_str = "Working tree clean" if git_stat.get("is_clean") else f"{git_stat.get('modified_files_count')} dirty files"
            status_reply = (
                f"⚡ *System Diagnostics*\n"
                f"• CPU Load: `{sys_stat.get('cpu_percent')}`\n"
                f"• RAM: `{sys_stat.get('ram_used_gb')}`\n"
                f"• Battery: `{sys_stat.get('battery')}`\n"
                f"• Disk: `{sys_stat.get('disk_free_gb')}`\n"
                f"• Git: `{git_stat.get('branch', 'main')}` ({clean_str})\n"
                f"• Time: `{sys_stat.get('current_time')}`"
            )
            await self.send_message(chat_id, status_reply)
            return

        # 3. /snap or /screen
        if text.lower() in ("/snap", "/screen", "/screenshot"):
            await self.send_message(chat_id, "📸 Capturing desktop screenshot...")
            res = AppManager.take_screenshot()
            if res.get("status") == "success" and "path" in res:
                img_path = Path(res["path"])
                await self.send_photo(chat_id, img_path, caption="🖥️ Desktop snapshot")
            else:
                await self.send_message(chat_id, f"Failed to capture screen: {res.get('message', 'unknown error')}")
            return

        # 4. /brief
        if text.lower() == "/brief":
            await self.send_message(chat_id, "☕ Compiling executive briefing...")
            brief = api_manager.get_daily_briefing()
            await self.send_message(chat_id, f"☕ *Executive Briefing:*\n{brief.get('summary', 'Unavailable.')}")
            return

        # 5. /say <text>
        if text.lower().startswith("/say "):
            phrase = text[5:].strip()
            if phrase:
                # Play over speakers
                voice_speaker.speak(phrase, prefix="\n\033[1;35m[Telegram Voice Remote]:\033[0m ")
                await self.send_message(chat_id, f"🗣 Broadcasted through PC speakers: \"{phrase}\"")
            else:
                await self.send_message(chat_id, "Usage: `/say hello sir`")
            return

        # 6. /run or /exec
        if text.lower().startswith(("/run ", "/exec ")):
            cmd = text.split(" ", 1)[1].strip()
            exec_res = SystemManager.execute_shell_command(cmd)
            out = exec_res.get("output", "") or exec_res.get("message", "")
            await self.send_message(chat_id, f"💻 *Output for `{cmd}`:*\n```\n{out[:3500]}\n```")
            return

        # 7. Conversational reasoning via Ezra brain
        try:
            from jarvis.brain.engine import brain_service
            brain_res = await brain_service.think(text, speaker_tier="verified")
            reply = brain_res.get("speech_text", "Command processed.")
            await self.send_message(chat_id, f"🤖 *Ezra:*\n{reply}")
        except Exception as e:
            await self.send_message(chat_id, f"Brain processing error: {e}")

    async def run(self):
        """Asynchronous long-polling worker loop."""
        if not self.token:
            print("\033[1;33m[Telegram]: TELEGRAM_BOT_TOKEN not configured in .env. Remote daemon idle.\033[0m")
            return

        print(f"\033[1;32m[+] Telegram Remote Daemon active! Polling for commands...\033[0m")
        self.is_running = True

        async with aiohttp.ClientSession() as session:
            while self.is_running:
                try:
                    poll_url = f"{self.base_url}/getUpdates?offset={self.last_update_id + 1}&timeout=20"
                    async with session.get(poll_url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            for update in data.get("result", []):
                                self.last_update_id = max(self.last_update_id, update.get("update_id", 0))
                                await self.handle_update(update)
                        elif resp.status in (401, 404):
                            print(f"\033[1;31m[-] Telegram Bot Token is invalid (HTTP {resp.status}).\033[0m")
                            await asyncio.sleep(60)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await asyncio.sleep(3)

    def stop(self):
        self.is_running = False

def start_telegram_daemon_background():
    """Launches the Telegram daemon in a background thread."""
    import threading
    if not TELEGRAM_BOT_TOKEN:
        return None

    daemon = TelegramRemoteDaemon()

    def _thread_target():
        asyncio.run(daemon.run())

    t = threading.Thread(target=_thread_target, daemon=True, name="EzraTelegramDaemon")
    t.start()
    return daemon

if __name__ == "__main__":
    print("Starting Project Ezra Telegram Remote Daemon...")
    d = TelegramRemoteDaemon()
    try:
        asyncio.run(d.run())
    except KeyboardInterrupt:
        print("Telegram daemon stopped.")
