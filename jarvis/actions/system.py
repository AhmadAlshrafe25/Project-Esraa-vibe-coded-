import shutil
import subprocess
import psutil
import datetime
from pathlib import Path

class SystemManager:
    """Manages system metrics, volume, media control, and command execution."""

    @staticmethod
    def get_system_status() -> dict:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        battery = psutil.sensors_battery()
        battery_str = f"{round(battery.percent)}% ({'Charging' if battery.power_plugged else 'Discharging'})" if battery else "Desktop / No battery"

        return {
            "status": "success",
            "cpu_percent": f"{cpu_percent}%",
            "ram_used_gb": f"{ram.used / (1024**3):.2f} GB / {ram.total / (1024**3):.2f} GB ({ram.percent}%)",
            "disk_free_gb": f"{disk.free / (1024**3):.2f} GB free",
            "battery": battery_str,
            "current_time": datetime.datetime.now().strftime("%I:%M %p, %A %d %B %Y")
        }

    @staticmethod
    def get_time() -> dict:
        """Returns the current formatted time."""
        now = datetime.datetime.now().strftime("%I:%M %p")
        return {"status": "success", "time": now, "speech": f"The current time is {now}, sir."}

    @staticmethod
    def get_date() -> dict:
        """Returns today's date formatted."""
        now = datetime.datetime.now().strftime("%A, %B %d, %Y")
        return {"status": "success", "date": now, "speech": f"Today is {now}, sir."}

    @staticmethod
    def get_battery() -> dict:
        """Returns battery percentage and power status."""
        battery = psutil.sensors_battery()
        if battery:
            status = "charging" if battery.power_plugged else "on battery"
            speech = f"Battery is at {int(battery.percent)} percent and {status}, sir."
            return {"status": "success", "percent": int(battery.percent), "plugged": battery.power_plugged, "speech": speech}
        return {"status": "success", "speech": "No battery detected, sir. Running on desktop AC power."}

    @staticmethod
    def get_ram() -> dict:
        """Returns RAM utilization metrics."""
        ram = psutil.virtual_memory()
        speech = f"Memory usage is at {ram.percent} percent. {round(ram.used / (1024**3), 1)} of {round(ram.total / (1024**3), 1)} gigabytes in use, sir."
        return {"status": "success", "percent": ram.percent, "used_gb": round(ram.used / (1024**3), 1), "total_gb": round(ram.total / (1024**3), 1), "speech": speech}

    @staticmethod
    def get_cpu() -> dict:
        """Returns CPU utilization metric."""
        cpu = psutil.cpu_percent(interval=0.1)
        speech = f"CPU utilization is currently at {cpu} percent, sir."
        return {"status": "success", "cpu_percent": cpu, "speech": speech}

    @staticmethod
    def read_clipboard() -> dict:
        """Reads contents of system clipboard."""
        try:
            import pyperclip
            text = pyperclip.paste().strip()
            if not text:
                return {"status": "success", "clipboard": "", "speech": "Your clipboard is currently empty, sir."}
            preview = text[:200]
            return {"status": "success", "clipboard": text, "speech": f"Clipboard contents: {preview}"}
        except Exception as e:
            return {"status": "error", "message": str(e), "speech": "Unable to read the clipboard, sir."}

    @staticmethod
    def summarize_clipboard() -> dict:
        """Provides concise local extractive summary of clipboard content."""
        try:
            import pyperclip
            text = pyperclip.paste().strip()
            if not text:
                return {"status": "success", "speech": "Your clipboard is empty, sir."}
            clean_text = " ".join(text.split())
            sentences = [p.strip() for p in clean_text.replace("?", ".").replace("!", ".").split(".") if p.strip()]
            summary = ". ".join(sentences[:2]) + "." if sentences else clean_text[:200]
            return {"status": "success", "summary": summary, "speech": f"Clipboard summary: {summary}"}
        except Exception as e:
            return {"status": "error", "message": str(e), "speech": "Could not summarize clipboard, sir."}

    @staticmethod
    def set_volume(percent: int) -> dict:
        """Sets master audio volume on Arch Linux & Pop!_OS (WirePlumber/PulseAudio/ALSA)."""
        percent = max(0, min(100, percent))
        if shutil.which("wpctl"):
            frac = round(percent / 100.0, 2)
            res = subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(frac)], capture_output=True)
            if res.returncode == 0:
                return {"status": "success", "message": f"Volume set to {percent}%."}
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], capture_output=True)
            return {"status": "success", "message": f"Volume set to {percent}%."}
        if shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], capture_output=True)
            return {"status": "success", "message": f"Volume set to {percent}%."}
        return {"status": "warning", "message": "Audio volume tools not detected."}

    @staticmethod
    def media_control(action: str) -> dict:
        """Controls media playback: play, pause, play-pause, next, previous."""
        action_clean = action.lower().strip()
        if shutil.which("playerctl"):
            if action_clean in ("play", "pause", "play-pause", "next", "previous", "stop"):
                subprocess.run(["playerctl", action_clean], capture_output=True)
                return {"status": "success", "message": f"Media command '{action_clean}' executed."}
        return {"status": "warning", "message": f"playerctl not available or invalid action '{action}'."}

    @staticmethod
    def execute_shell_command(command: str) -> dict:
        """Executes a safe shell command on user request and returns output."""
        try:
            # Run command with 10s timeout
            res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
            output = (res.stdout + res.stderr).strip()[:1000]
            return {
                "status": "success" if res.returncode == 0 else "error",
                "returncode": res.returncode,
                "output": output or "Command completed with no output."
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to execute command: {e}"}

    @staticmethod
    def send_desktop_notification(title: str, message: str, urgency: str = "normal") -> dict:
        """Sends native Linux desktop toast notification using notify-send with Ezra icon."""
        from config.settings import PROJECT_ROOT
        icon_path = PROJECT_ROOT / "assets" / "ezra_icon.png"
        
        if not shutil.which("notify-send"):
            return {"status": "warning", "message": "notify-send is not installed on system."}

        cmd = ["notify-send", "-a", "Project Ezra", "-u", urgency]
        if icon_path.exists():
            cmd.extend(["-i", str(icon_path)])
        cmd.extend([title, message])

        try:
            subprocess.run(cmd, check=True)
            return {"status": "success", "message": f"Desktop notification sent: '{title}'"}
        except Exception as e:
            return {"status": "error", "message": f"Notification error: {e}"}

    @staticmethod
    def schedule_timer(seconds: int, note: str = "Timer complete") -> dict:
        """Schedules a non-blocking background timer that alerts user via voice and desktop notification."""
        import threading
        import time

        def _timer_worker():
            time.sleep(max(1, seconds))
            # Desktop notification
            SystemManager.send_desktop_notification("⏰ Ezra Timer Alert", note, urgency="critical")
            # Voice announcement
            try:
                from jarvis.voice.speaker import voice_speaker
                voice_speaker.speak(f"Timer alert, sir. {note}.", prefix="\n\033[1;33m[Timer Alert]:\033[0m ")
            except Exception:
                pass

        thread = threading.Thread(target=_timer_worker, daemon=True)
        thread.start()

        mins = seconds // 60
        secs = seconds % 60
        duration_str = f"{mins}m {secs}s" if mins > 0 else f"{secs}s"
        return {"status": "success", "message": f"Timer set for {duration_str}: '{note}'."}

    @staticmethod
    def git_status(repo_dir: str = None) -> dict:
        """Inspects Git repository status (branch, dirty status, uncommitted changes)."""
        from config.settings import PROJECT_ROOT
        target_dir = repo_dir or str(PROJECT_ROOT)

        try:
            branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=target_dir, text=True).strip()
            status_out = subprocess.check_output(["git", "status", "-s"], cwd=target_dir, text=True).strip()
            modified_count = len(status_out.splitlines()) if status_out else 0

            return {
                "status": "success",
                "branch": branch or "main",
                "modified_files_count": modified_count,
                "is_clean": modified_count == 0,
                "details": status_out or "Working tree is clean."
            }
        except Exception as e:
            return {"status": "error", "message": f"Git status failed: {e}"}

    @staticmethod
    def git_publish(commit_message: str = "", repo_dir: str = None) -> dict:
        """Stages all changes, creates a commit, and pushes to remote main (adheres to publish rule)."""
        from config.settings import PROJECT_ROOT
        target_dir = repo_dir or str(PROJECT_ROOT)
        msg = commit_message.strip() or f"update: Ezra automated checkpoint ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})"

        try:
            # 1. Stage all
            subprocess.run(["git", "add", "-A"], cwd=target_dir, check=True)
            # 2. Check if anything to commit
            status = subprocess.check_output(["git", "status", "-s"], cwd=target_dir, text=True).strip()
            if not status:
                return {"status": "success", "message": "Working tree clean, nothing to commit. Repository up to date."}

            # 3. Commit
            subprocess.run(["git", "commit", "-m", msg], cwd=target_dir, check=True)
            # 4. Push to remote
            branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=target_dir, text=True).strip() or "main"
            push_res = subprocess.run(["git", "push", "origin", branch], cwd=target_dir, capture_output=True, text=True)

            if push_res.returncode == 0:
                return {"status": "success", "message": f"Published changes to {branch} with commit '{msg}'."}
            else:
                return {"status": "error", "message": f"Git push failed: {push_res.stderr.strip()}"}
        except Exception as e:
            return {"status": "error", "message": f"Git publish failed: {e}"}

    @staticmethod
    def git_log_recent(limit: int = 3, repo_dir: str = None) -> dict:
        """Retrieves recent commit history."""
        from config.settings import PROJECT_ROOT
        target_dir = repo_dir or str(PROJECT_ROOT)
        try:
            log_out = subprocess.check_output(["git", "log", f"-n{limit}", "--oneline"], cwd=target_dir, text=True).strip()
            commits = log_out.splitlines() if log_out else []
            return {"status": "success", "commits": commits, "summary": "; ".join(commits)}
        except Exception as e:
            return {"status": "error", "message": f"Git log failed: {e}"}

    @staticmethod
    def git_pull(repo_dir: str = None) -> dict:
        """Pulls latest changes from origin repository."""
        from config.settings import PROJECT_ROOT
        target_dir = repo_dir or str(PROJECT_ROOT)
        try:
            branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=target_dir, text=True).strip() or "main"
            pull_out = subprocess.check_output(["git", "pull", "origin", branch], cwd=target_dir, text=True).strip()
            return {"status": "success", "branch": branch, "message": f"Git pull complete on {branch}: {pull_out}"}
        except Exception as e:
            return {"status": "error", "message": f"Git pull failed: {e}"}

    @staticmethod
    def sync_gdrive() -> dict:
        """Executes bidirectional Google Drive sync between work and home laptops."""
        try:
            from jarvis.gdrive_sync import GDriveSync
            res = GDriveSync.sync_bidirectional()
            return {"status": "success", "message": res.get("message", "Cloud memory sync complete.")}
        except Exception as e:
            return {"status": "error", "message": f"Google Drive sync failed: {e}"}

    @staticmethod
    def get_top_processes(limit: int = 3) -> dict:
        """Finds top RAM and CPU consuming processes on the system."""
        try:
            procs = []
            for p in psutil.process_iter(['name', 'memory_percent', 'cpu_percent']):
                try:
                    info = p.info
                    name = info.get('name') or 'unknown'
                    mem = round(info.get('memory_percent') or 0.0, 1)
                    procs.append((name, mem))
                except Exception:
                    pass
            procs.sort(key=lambda x: x[1], reverse=True)
            top = procs[:limit]
            summary = ", ".join([f"{name} using {mem}% RAM" for name, mem in top])
            return {"status": "success", "top_processes": top, "summary": summary}
        except Exception as e:
            return {"status": "error", "message": f"Failed to inspect processes: {e}"}

    @staticmethod
    def lock_screen() -> dict:
        """Locks desktop session on Arch Linux (KDE/Sway/Hyprland) and Pop!_OS (Cosmic/GNOME)."""
        try:
            if shutil.which("loginctl"):
                subprocess.run(["loginctl", "lock-session"], check=True)
                return {"status": "success", "message": "Screen locked."}
            elif shutil.which("gnome-screensaver-command"):
                subprocess.run(["gnome-screensaver-command", "-l"], check=True)
                return {"status": "success", "message": "Screen locked."}
            elif shutil.which("xdg-screensaver"):
                subprocess.run(["xdg-screensaver", "lock"], check=True)
                return {"status": "success", "message": "Screen locked."}
            return {"status": "warning", "message": "No screen lock utility found."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to lock screen: {e}"}

    @staticmethod
    def add_note(note: str) -> dict:
        """Appends a timestamped note to data/notes.md."""
        from config.settings import PROJECT_ROOT
        notes_file = PROJECT_ROOT / "data" / "notes.md"
        notes_file.parent.mkdir(parents=True, exist_ok=True)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(f"- [{now_str}] {note.strip()}\n")
        return {"status": "success", "message": f"Saved note: '{note.strip()}'"}

    @staticmethod
    def get_notes(limit: int = 5) -> dict:
        """Reads recent notes from data/notes.md."""
        from config.settings import PROJECT_ROOT
        notes_file = PROJECT_ROOT / "data" / "notes.md"
        if not notes_file.exists():
            return {"status": "success", "notes": [], "summary": "You have no notes recorded yet."}
        with open(notes_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        recent = lines[-limit:]
        return {"status": "success", "notes": recent, "summary": " | ".join(recent)}

    @staticmethod
    def clear_notes() -> dict:
        """Clears all stored voice notes."""
        from config.settings import PROJECT_ROOT
        notes_file = PROJECT_ROOT / "data" / "notes.md"
        if notes_file.exists():
            notes_file.unlink()
        return {"status": "success", "message": "Cleared all notes."}

    @staticmethod
    def add_todo(task: str) -> dict:
        """Adds a task to the interactive todo list in data/todos.json."""
        import json
        from config.settings import PROJECT_ROOT
        todo_file = PROJECT_ROOT / "data" / "todos.json"
        todo_file.parent.mkdir(parents=True, exist_ok=True)
        todos = []
        if todo_file.exists():
            try:
                with open(todo_file, "r", encoding="utf-8") as f:
                    todos = json.load(f)
            except Exception:
                todos = []
        todos.append({"task": task.strip(), "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
        with open(todo_file, "w", encoding="utf-8") as f:
            json.dump(todos, f, indent=2, ensure_ascii=False)
        return {"status": "success", "message": f"Added task: '{task.strip()}'"}

    @staticmethod
    def get_todos() -> dict:
        """Lists active todos from data/todos.json."""
        import json
        from config.settings import PROJECT_ROOT
        todo_file = PROJECT_ROOT / "data" / "todos.json"
        if not todo_file.exists():
            return {"status": "success", "todos": [], "summary": "No pending tasks."}
        try:
            with open(todo_file, "r", encoding="utf-8") as f:
                todos = json.load(f)
            tasks = [t.get("task", "") for t in todos if t.get("task")]
            summary = ", ".join(tasks) if tasks else "No pending tasks."
            return {"status": "success", "todos": todos, "summary": summary}
        except Exception as e:
            return {"status": "error", "message": f"Failed to read todos: {e}"}

    @staticmethod
    def clear_todos() -> dict:
        """Clears all tasks from todo list."""
        from config.settings import PROJECT_ROOT
        todo_file = PROJECT_ROOT / "data" / "todos.json"
        if todo_file.exists():
            todo_file.unlink()
        return {"status": "success", "message": "Cleared all pending tasks."}

    @staticmethod
    def get_recent_downloads(limit: int = 5) -> dict:
        """Lists recently downloaded files in ~/Downloads."""
        dl_dir = Path.home() / "Downloads"
        if not dl_dir.exists():
            return {"status": "error", "message": "Downloads folder not found."}
        try:
            files = [p for p in dl_dir.iterdir() if p.is_file() and not p.name.startswith(".")]
            files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            recent = [p.name for p in files[:limit]]
            summary = ", ".join(recent) if recent else "Downloads folder is empty."
            return {"status": "success", "files": recent, "summary": summary}
        except Exception as e:
            return {"status": "error", "message": f"Failed to inspect downloads: {e}"}
