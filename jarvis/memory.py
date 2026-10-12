import sqlite3
import json
import datetime
from pathlib import Path
from config.settings import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "memory.db"
DB_PATH.parent.mkdir(exist_ok=True)

class MemoryManager:
    """Stores chat conversations, user preferences, and learned facts locally and syncs to Google Drive backup."""
    
    def __init__(self):
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Conversations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    sender TEXT,
                    message TEXT,
                    tools_used TEXT
                )
            """)
            # Long-term knowledge / Learned memory
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learned_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT UNIQUE,
                    content TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()

    def save_message(self, sender: str, message: str, tools: list = None):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_history (timestamp, sender, message, tools_used)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.datetime.now().isoformat(),
                sender,
                message,
                json.dumps(tools or [])
            ))
            conn.commit()

    def get_recent_history(self, limit: int = 15) -> list:
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

    def remember_fact(self, topic: str, content: str):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO learned_facts (topic, content, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(topic) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at
            """, (topic, content, datetime.datetime.now().isoformat()))
            conn.commit()

    def get_all_facts(self) -> dict:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT topic, content FROM learned_facts")
            return {r[0]: r[1] for r in cursor.fetchall()}

    def export_backup_json(self) -> Path:
        """Exports full database to a clean JSON file ready for Google Drive backup."""
        backup_file = PROJECT_ROOT / "data" / "esraa_gdrive_sync.json"
        data = {
            "exported_at": datetime.datetime.now().isoformat(),
            "facts": self.get_all_facts(),
            "chat_history": self.get_recent_history(1000)
        }
        backup_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return backup_file

memory_service = MemoryManager()
