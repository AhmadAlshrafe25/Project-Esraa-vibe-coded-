import os
import subprocess
import shutil
from pathlib import Path

# Common Linux & Desktop application mappings
APP_MAP = {
    "terminal": ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"],
    "calculator": ["gnome-calculator", "kcalc", "xcalc"],
    "files": ["nautilus", "dolphin", "thunar", "pcmanfm"],
    "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "firefox": ["firefox"],
    "vlc": ["vlc"],
    "vscode": ["code"],
    "spotify": ["spotify"],
    "settings": ["gnome-control-center", "systemsettings"]
}

class AppManager:
    """Launches local desktop applications, movies, and media."""

    @staticmethod
    def launch_app(app_name: str) -> dict:
        app_clean = app_name.lower().strip()
        
        # Check predefined aliases
        binary_candidates = APP_MAP.get(app_clean, [app_clean])
        
        found_binary = None
        for binary in binary_candidates:
            if shutil.which(binary):
                found_binary = binary
                break
                
        if found_binary:
            try:
                subprocess.Popen([found_binary], start_new_session=True)
                return {"status": "success", "message": f"Successfully launched {found_binary}."}
            except Exception as e:
                return {"status": "error", "message": f"Failed to launch {found_binary}: {str(e)}"}
        
        # Try generic xdg-open if user passed a file or path
        if os.path.exists(app_name):
            subprocess.Popen(["xdg-open", app_name], start_new_session=True)
            return {"status": "success", "message": f"Opened file {app_name} with default handler."}

        return {"status": "error", "message": f"Application '{app_name}' not found on system."}

    @staticmethod
    def play_media_file(media_path: str) -> dict:
        """Plays a local movie, video, or song file."""
        if not os.path.exists(media_path):
            return {"status": "error", "message": f"File '{media_path}' does not exist."}
        
        # Use VLC if available, else xdg-open
        player = shutil.which("vlc") or shutil.which("mpv") or shutil.which("totem")
        if player:
            subprocess.Popen([player, media_path], start_new_session=True)
            return {"status": "success", "message": f"Playing {media_path} via {player}."}
        
        subprocess.Popen(["xdg-open", media_path], start_new_session=True)
        return {"status": "success", "message": f"Playing {media_path} with default media player."}
