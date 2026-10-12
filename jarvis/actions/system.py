import shutil
import subprocess
import psutil
import datetime

class SystemManager:
    """Manages system metrics, volume, time, and power controls."""

    @staticmethod
    def get_system_status() -> dict:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "status": "success",
            "cpu_percent": f"{cpu_percent}%",
            "ram_used_gb": f"{ram.used / (1024**3):.2f} GB / {ram.total / (1024**3):.2f} GB ({ram.percent}%)",
            "disk_free_gb": f"{disk.free / (1024**3):.2f} GB free",
            "current_time": datetime.datetime.now().strftime("%I:%M %p, %A %d %B %Y")
        }

    @staticmethod
    def set_volume(percent: int) -> dict:
        """Sets master audio volume on Linux systems (ALSA/PulseAudio)."""
        percent = max(0, min(100, percent))
        # Try amixer
        if shutil.which("amixer"):
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{percent}%"], capture_output=True)
            return {"status": "success", "message": f"Volume set to {percent}%."}
        # Try pactl
        if shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], capture_output=True)
            return {"status": "success", "message": f"Volume set to {percent}%."}
        return {"status": "warning", "message": f"Audio volume tools (amixer/pactl) not detected."}
