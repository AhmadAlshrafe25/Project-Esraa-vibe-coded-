import shutil
import subprocess
import psutil
import datetime

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
    def set_volume(percent: int) -> dict:
        """Sets master audio volume on Linux systems (ALSA/PulseAudio/PipeWire)."""
        percent = max(0, min(100, percent))
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], capture_output=True)
            return {"status": "success", "message": f"Volume set to {percent}%."}
        if shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], capture_output=True)
            return {"status": "success", "message": f"Volume set to {percent}%."}
        return {"status": "warning", "message": f"Audio volume tools (pactl/amixer) not detected."}

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
