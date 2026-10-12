import os
import time
import subprocess
import shutil
import pyautogui
from pathlib import Path
from config.settings import CACHE_DIR

# Common Linux & Flatpak application mappings
FLATPAK_APPS = {
    "discord": "com.discordapp.Discord",
    "brave": "com.brave.Browser",
    "obs": "com.obsproject.Studio",
    "heroic": "com.heroicgameslauncher.hgl",
    "mgba": "io.mgba.mGBA",
    "kdenlive": "org.kde.kdenlive",
}

NATIVE_APPS = {
    "terminal": ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"],
    "calculator": ["gnome-calculator", "kcalc", "xcalc"],
    "files": ["nautilus", "dolphin", "thunar", "pcmanfm"],
    "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "firefox": ["firefox"],
    "vlc": ["vlc"],
    "vscode": ["code"],
    "spotify": ["spotify"],
    "settings": ["gnome-control-center", "systemsettings"],
    "text_editor": ["gedit", "kate", "xed", "mousepad", "nano"]
}

class AppManager:
    """Controls desktop applications, window typing, media, and system actions."""

    @staticmethod
    def launch_app(app_name: str) -> dict:
        app_clean = app_name.lower().strip()

        # 1. Check Flatpak applications
        if app_clean in FLATPAK_APPS:
            flatpak_id = FLATPAK_APPS[app_clean]
            try:
                subprocess.Popen(["flatpak", "run", flatpak_id], start_new_session=True)
                return {"status": "success", "message": f"Launched {app_name} via Flatpak ({flatpak_id})."}
            except Exception as e:
                return {"status": "error", "message": f"Failed to launch Flatpak {flatpak_id}: {e}"}

        # 2. Check native predefined aliases
        binary_candidates = NATIVE_APPS.get(app_clean, [app_clean])
        for binary in binary_candidates:
            if shutil.which(binary):
                try:
                    subprocess.Popen([binary], start_new_session=True)
                    return {"status": "success", "message": f"Launched {binary}."}
                except Exception as e:
                    return {"status": "error", "message": f"Failed to launch {binary}: {e}"}

        # 3. Try gtk-launch
        if shutil.which("gtk-launch"):
            res = subprocess.run(["gtk-launch", app_clean], capture_output=True)
            if res.returncode == 0:
                return {"status": "success", "message": f"Launched {app_name} via desktop entry."}

        # 4. Try generic xdg-open if user passed a file or path
        if os.path.exists(app_name):
            subprocess.Popen(["xdg-open", app_name], start_new_session=True)
            return {"status": "success", "message": f"Opened file {app_name} with default handler."}

        return {"status": "error", "message": f"Application '{app_name}' not found on system."}

    @staticmethod
    def close_app(app_name: str) -> dict:
        """Terminates or kills an application by name."""
        app_clean = app_name.lower().strip()
        binary = app_clean
        if app_clean in FLATPAK_APPS:
            subprocess.run(["flatpak", "kill", FLATPAK_APPS[app_clean]], capture_output=True)
            return {"status": "success", "message": f"Closed Flatpak application {app_name}."}

        subprocess.run(["pkill", "-f", binary], capture_output=True)
        return {"status": "success", "message": f"Sent termination signal to {app_name}."}

    @staticmethod
    def type_message(text: str, press_enter: bool = False, delay_sec: float = 0.3) -> dict:
        """Types or pastes text into the currently active window on your desktop.
        Uses system clipboard paste (pyperclip + Ctrl+V) for instantaneous, unicode-safe typing,
        with automatic fallback to key simulation.
        """
        try:
            time.sleep(delay_sec)
            pasted = False
            try:
                import pyperclip
                pyperclip.copy(text)
                time.sleep(0.05)
                pyautogui.hotkey('ctrl', 'v')
                pasted = True
            except Exception:
                pass

            if not pasted:
                pyautogui.write(text, interval=0.005)

            if press_enter:
                time.sleep(0.1)
                pyautogui.press('enter')

            preview = text[:60] + ("..." if len(text) > 60 else "")
            return {
                "status": "success",
                "message": f"Successfully typed: '{preview}'{' and pressed Enter' if press_enter else ''}."
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to type text: {e}"}

    @staticmethod
    def dictate_text(text: str, press_enter: bool = False) -> dict:
        """Dedicated dictation tool: types exactly what the user dictates into their active window."""
        return AppManager.type_message(text=text, press_enter=press_enter, delay_sec=0.2)

    @staticmethod
    def press_key(key: str) -> dict:
        """Presses a single key (e.g. 'enter', 'tab', 'esc', 'backspace', 'down')."""
        try:
            pyautogui.press(key.lower().strip())
            return {"status": "success", "message": f"Pressed key '{key}'."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to press key: {e}"}

    @staticmethod
    def press_hotkey(keys: list) -> dict:
        """Presses a combination of keys (e.g. ['ctrl', 's'], ['ctrl', 'c'], ['alt', 'tab'])."""
        try:
            pyautogui.hotkey(*[k.lower().strip() for k in keys])
            return {"status": "success", "message": f"Pressed shortcut: {'+'.join(keys)}."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to press shortcut: {e}"}

    @staticmethod
    def send_discord_message(message: str) -> dict:
        """Launches Discord (if not already open), waits for focus, and types the message into active chat."""
        # Ensure Discord is launched
        AppManager.launch_app("discord")
        time.sleep(1.8)
        # Type the message and send
        return AppManager.type_message(message, press_enter=True)

    @staticmethod
    def take_screenshot() -> dict:
        """Takes a full screen screenshot and saves it to cache."""
        try:
            filename = f"screenshot_{int(time.time())}.png"
            path = CACHE_DIR / filename
            img = pyautogui.screenshot()
            img.save(str(path))
            return {"status": "success", "message": f"Screenshot saved to {path}.", "path": str(path)}
        except Exception as e:
            return {"status": "error", "message": f"Screenshot failed: {e}"}

    @staticmethod
    def play_media_file(media_path: str) -> dict:
        """Plays a local movie, video, or song file."""
        if not os.path.exists(media_path):
            return {"status": "error", "message": f"File '{media_path}' does not exist."}

        player = shutil.which("vlc") or shutil.which("mpv") or shutil.which("totem")
        if player:
            subprocess.Popen([player, media_path], start_new_session=True)
            return {"status": "success", "message": f"Playing {media_path} via {player}."}

        subprocess.Popen(["xdg-open", media_path], start_new_session=True)
        return {"status": "success", "message": f"Playing {media_path} with default media player."}
