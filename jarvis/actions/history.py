"""Command history and suggestion tracking for Ezra."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any


class CommandHistory:
    """Keep track of recent commands and provide execution history with optional undo."""

    def __init__(self, limit: int = 50):
        self.limit = limit
        self._items: deque[dict[str, Any]] = deque(maxlen=limit)
        self._undo: dict[str, Callable[[], None]] = {}
        self._ids: set[str] = set()
        self._next_id = 0

    def record(self, command: str, undo: Callable[[], None] | None = None, result: Any = None) -> dict[str, Any]:
        """Record a command execution."""
        self._next_id += 1
        item = {
            "id": f"cmd-{self._next_id}",
            "command": command,
            "undoable": undo is not None,
            "created_at": time.time(),
            "result": result,
        }
        if len(self._items) == self.limit and self._items:
            expired = self._items[0]
            expired_id = str(expired["id"])
            self._undo.pop(expired_id, None)
            self._ids.discard(expired_id)
        self._items.append(item)
        self._ids.add(str(item["id"]))
        if undo is not None:
            self._undo[str(item["id"])] = undo
        return item

    def list(self) -> list[dict[str, Any]]:
        """Return a copy of recent recorded commands."""
        return [dict(item) for item in self._items]

    def last(self) -> dict[str, Any] | None:
        """Return the most recently executed command."""
        return dict(self._items[-1]) if self._items else None

    def undo(self, command_id: str | None = None) -> dict[str, str]:
        """Undo a command by ID, or the most recent undoable command if no ID is specified."""
        if not self._items:
            return {"status": "empty", "message": "No commands in history to undo."}

        target_id = command_id
        if target_id is None:
            for item in reversed(self._items):
                if item.get("undoable"):
                    target_id = item["id"]
                    break

        if not target_id or target_id not in self._ids:
            return {"status": "expired", "message": "No undoable command found in recent history."}

        callback = self._undo.pop(target_id, None)
        if callback is None:
            return {"status": "not_undoable", "message": f"Command {target_id} is not undoable."}

        try:
            callback()
            return {"status": "undone", "message": f"Successfully reversed command {target_id}."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to undo command {target_id}: {e}"}


def suggest_commands(context: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Suggest context-aware commands without proposing destructive actions."""
    context = context or {}
    suggestions: list[dict[str, str]] = []

    last_action = context.get("last_action", "")
    if "music" in last_action or "media" in last_action:
        suggestions.append({
            "command": "play lo-fi beats",
            "category": "media",
            "why": "Continue your background listening session."
        })

    suggestions.extend([
        {
            "command": "dev news",
            "category": "information",
            "why": "Hear top tech headlines from Hacker News."
        },
        {
            "command": "battery status",
            "category": "telemetry",
            "why": "Check current battery and power levels."
        },
        {
            "command": "read clipboard",
            "category": "tools",
            "why": "Review or summarize what is currently copied."
        },
        {
            "command": "set a timer for 15 minutes",
            "category": "productivity",
            "why": "Keep track of focused work intervals."
        }
    ])
    return suggestions


# Global singleton command history tracker
command_history = CommandHistory(limit=50)
