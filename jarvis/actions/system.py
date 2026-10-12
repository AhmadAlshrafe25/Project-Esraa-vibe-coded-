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
