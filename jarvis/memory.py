import os
import re
import sqlite3
import json
import datetime
from pathlib import Path
from config.settings import PROJECT_ROOT, GEMINI_API_KEY

DB_PATH = PROJECT_ROOT / "data" / "memory.db"
DB_PATH.parent.mkdir(exist_ok=True)

def mask_secrets(text: str) -> str:
    """Masks API keys, tokens, and private secrets before storing or exporting (Open.Jarvis parity)."""
    if not text:
        return text
    # Mask Gemini / Groq / OpenAI keys and generic tokens
    text = re.sub(r"\b(AIzaSy[a-zA-Z0-9_-]{33})\b", r"AIzaSy...[REDACTED]", text)
    text = re.sub(r"\b(gsk_[a-zA-Z0-9]{48,})\b", r"gsk_...[REDACTED]", text)
    text = re.sub(r"\b(ghp_[a-zA-Z0-9]{36,})\b", r"ghp_...[REDACTED]", text)
    text = re.sub(r"\b([0-9]{8,12}:[a-zA-Z0-9_-]{35})\b", r"...[TELEGRAM_TOKEN_REDACTED]", text)
    return text

class MemoryManager:
    """Stores chat conversations, user preferences, and continuously adapts by learning from every turn."""

    def __init__(self):
        self.privacy_mode: bool = False
        self._init_db()

    def set_privacy_mode(self, enabled: bool):
        """Enables or disables privacy mode (Open.Jarvis data control)."""
        self.privacy_mode = bool(enabled)

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    sender TEXT,
                    message TEXT,
                    tools_used TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT UNIQUE,
                    content TEXT,
                    updated_at TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT UNIQUE,
                    value TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def save_message(self, sender: str, message: str, tools: list = None):
        if self.privacy_mode:
            return
        safe_msg = mask_secrets(message)
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_history (timestamp, sender, message, tools_used)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.datetime.now().isoformat(),
                sender,
                safe_msg,
                json.dumps(tools or [])
            ))
            conn.commit()

    def get_recent_history(self, limit: int = 15) -> list:
        if self.privacy_mode:
            return []
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, sender, message, tools_used FROM chat_history
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            history = []
            for r in reversed(rows):
                history.append({
                    "timestamp": r[0],
                    "sender": r[1],
                    "message": r[2],
                    "tools": json.loads(r[3] or "[]")
                })
            return history

    def _sync_to_gdrive(self):
        try:
            from jarvis.gdrive_sync import gdrive_sync
            gdrive_sync.push_to_drive()
        except Exception:
            pass

    def remember_fact(self, topic: str, content: str):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learned_facts (topic, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(topic) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at
            """, (topic, content, datetime.datetime.now().isoformat()))
            conn.commit()
        self._sync_to_gdrive()

    def update_profile(self, key: str, value: str):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_profile (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value, datetime.datetime.now().isoformat()))
            conn.commit()
        self._sync_to_gdrive()

    def get_all_facts(self) -> dict:
        facts = {}
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT topic, content FROM learned_facts")
            for r in cursor.fetchall():
                facts[r[0]] = r[1]
            cursor.execute("SELECT key, value FROM user_profile")
            for r in cursor.fetchall():
                facts[f"profile_{r[0]}"] = r[1]
        return facts

    async def auto_learn_from_interaction(self, user_text: str, reply_text: str):
        """Asynchronously reflects on conversation to automatically extract corrections, habits, and preferences."""
        if self.privacy_mode:
            return

        raw_key = os.getenv("GEMINI_API_KEY", "") or GEMINI_API_KEY or ""
        gemini_key = raw_key.split(",")[0].strip() if raw_key else ""
        if not gemini_key or len(user_text.strip()) < 4:
            return

        try:
            import google.genai as genai
            client = genai.Client(api_key=gemini_key)
            prompt = f"""
Analyze this user turn and identify if the user stated any preferences, corrections, feedback, personal facts, or instructions for the assistant.
User said: "{user_text}"
Assistant replied: "{reply_text}"

If there is a learned preference, correction, or fact, extract it as concise JSON with "topic" and "content".
If nothing relevant to remember, return: {{"learned": false}}

Example format:
{{"learned": true, "topic": "voice_preference", "content": "Prefers a smooth, natural voice and hates robotic voices."}}
Return ONLY valid JSON.
"""
            resp = None
            for m_candidate in ("gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-flash-latest"):
                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=m_candidate,
                            contents=prompt
                        ),
                        timeout=3.5
                    )
                    if resp and resp.text:
                        break
                except Exception:
                    continue
            if resp and resp.text:
                import re
                match = re.search(r"\{.*\}", resp.text, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    if data.get("learned") and "topic" in data and "content" in data:
                        self.remember_fact(data["topic"], data["content"])
                        print(f"\n\033[1;32m[🧠 Ezra Adapted & Learned]:\033[0m {data['topic']} -> {data['content']}\n")
        except Exception:
            pass

    def export_backup_json(self) -> Path:
        """Exports full database to a clean JSON file ready for Google Drive backup."""
        backup_file = PROJECT_ROOT / "data" / "ezra_gdrive_sync.json"
        data = {
            "exported_at": datetime.datetime.now().isoformat(),
            "facts": self.get_all_facts(),
            "chat_history": self.get_recent_history(1000)
        }
        backup_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return backup_file

memory_service = MemoryManager()
