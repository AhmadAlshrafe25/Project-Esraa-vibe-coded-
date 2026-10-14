"""Natural language duration timer and background alert manager for Ezra."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

_active_timers: list[dict[str, Any]] = []
_timer_lock = threading.Lock()
_timer_seq = 0


def parse_duration(command: str) -> int:
    """Extract a duration in seconds from a natural language string.
    Supports hours, minutes, seconds, composite phrases like '5 minutes and 30 seconds',
    and colloquial expressions like 'half an hour'.
    """
    text = (command or "").lower().strip()
    seconds = 0

    if "half an hour" in text or "half hour" in text:
        seconds += 1800
        text = text.replace("half an hour", "").replace("half hour", "")

    if "an hour" in text or "one hour" in text:
        # Avoid duplicate match with regex if already handled
        if not re.search(r"\d+\s*hour", text):
            seconds += 3600

    # Hours
    m_hour = re.search(r"(\d+)\s*(?:hours?|hrs?|hr|h\b)", text)
    if m_hour:
        seconds += int(m_hour.group(1)) * 3600

    # Minutes
    m_min = re.search(r"(\d+)\s*(?:minutes?|mins?|min|m\b)", text)
    if m_min:
        seconds += int(m_min.group(1)) * 60

    # Seconds
    m_sec = re.search(r"(\d+)\s*(?:seconds?|secs?|sec|s\b)", text)
    if m_sec:
        seconds += int(m_sec.group(1))

    return seconds


def format_duration(seconds: int) -> str:
    """Format duration in seconds into a friendly British spoken string."""
    hours = seconds // 3600
    remainder = seconds % 3600
    minutes = remainder // 60
    secs = remainder % 60

    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes > 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs > 1 else ''}")

    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def start_timer(seconds: int, note: str = "Timer complete") -> dict[str, Any]:
    """Start a non-blocking background countdown alert."""
    global _timer_seq
    if seconds <= 0:
        return {"status": "error", "message": "Timer duration must be greater than zero."}

    with _timer_lock:
        _timer_seq += 1
        timer_id = f"timer-{_timer_seq}"

    stop_event = threading.Event()
    start_time = time.time()
    duration_str = format_duration(seconds)

    def _worker():
        finished = not stop_event.wait(timeout=seconds)
        with _timer_lock:
            # Remove from active
            for i, t in enumerate(_active_timers):
                if t["id"] == timer_id:
                    _active_timers.pop(i)
                    break

        if finished:
            alert_msg = f"Sir, your {duration_str} timer for '{note}' is up."
            # Native desktop notification
            try:
                from jarvis.actions.system import SystemManager
                SystemManager.send_desktop_notification("⏰ Ezra Timer Alert", f"{duration_str} - {note}", urgency="critical")
            except Exception:
                pass

            # Spoken voice output
            try:
                from jarvis.voice.speaker import voice_speaker
                voice_speaker.speak(alert_msg, prefix="\n\033[1;33m[Ezra Timer]:\033[0m ")
            except Exception:
                pass

    thread = threading.Thread(target=_worker, daemon=True)
    timer_info = {
        "id": timer_id,
        "seconds": seconds,
        "note": note,
        "start_time": start_time,
        "end_time": start_time + seconds,
        "duration_str": duration_str,
        "stop_event": stop_event,
        "thread": thread,
    }

    with _timer_lock:
        _active_timers.append(timer_info)

    thread.start()
    return {
        "status": "success",
        "timer_id": timer_id,
        "duration_str": duration_str,
        "seconds": seconds,
        "speech": f"Timer set for {duration_str}, sir. I shall notify you when it completes."
    }


def get_active_timers() -> list[dict[str, Any]]:
    """Return a list of currently active timers with remaining time."""
    now = time.time()
    with _timer_lock:
        results = []
        for t in _active_timers:
            remaining = max(0, int(t["end_time"] - now))
            results.append({
                "id": t["id"],
                "note": t["note"],
                "remaining_seconds": remaining,
                "remaining_str": format_duration(remaining),
                "total_seconds": t["seconds"],
            })
        return results


def cancel_timer(timer_id: str | None = None) -> dict[str, str]:
    """Cancel a specific timer or the latest active timer."""
    with _timer_lock:
        if not _active_timers:
            return {"status": "none", "speech": "There are no active timers to cancel, sir."}

        target = None
        if timer_id:
            for t in _active_timers:
                if t["id"] == timer_id:
                    target = t
                    break
        else:
            target = _active_timers[-1]

        if not target:
            return {"status": "not_found", "speech": f"Could not find timer {timer_id}, sir."}

        target["stop_event"].set()
        _active_timers.remove(target)
        return {"status": "cancelled", "speech": f"I have cancelled the {target['duration_str']} timer, sir."}
