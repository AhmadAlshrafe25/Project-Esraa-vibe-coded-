"""Safety gates for high-impact runtime and desktop actions."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

DESTRUCTIVE_ACTIONS = {"shutdown", "poweroff", "restart", "reboot", "suspend", "sleep", "lock_screen"}
CONFIRMATION_ACTIONS = DESTRUCTIVE_ACTIONS | {"type_text", "press_key", "mouse_click", "scroll", "close_window"}


def is_destructive_action(action: str) -> bool:
    """Return whether an action can disrupt the active desktop session."""
    return (action or "").strip().lower() in DESTRUCTIVE_ACTIONS


def requires_confirmation(action: str) -> bool:
    """Return whether an action should require explicit user confirmation."""
    return (action or "").strip().lower() in CONFIRMATION_ACTIONS


def is_destructive_action_allowed(env: Mapping[str, str] | None = None) -> bool:
    """Allow destructive desktop actions only when explicitly enabled via environment variable."""
    env = os.environ if env is None else env
    return env.get("EZRA_ALLOW_DESTRUCTIVE_ACTIONS", "").strip().lower() in {"1", "true", "yes", "on"}


def block_message(action: str) -> str:
    """Return an actionable user-facing safety message."""
    return (
        f"I blocked the {action} action, sir. "
        "It can interrupt or terminate your active desktop session. "
        "To enable it, set EZRA_ALLOW_DESTRUCTIVE_ACTIONS=true in your environment."
    )


def build_confirmation_prompt(action: str, params: dict[str, Any] | None = None) -> str:
    """Build a concise confirmation prompt for sensitive actions."""
    detail = f" Parameters: {params}" if params else ""
    return f"Ezra requires authorization for a sensitive action: {action}.{detail}"
