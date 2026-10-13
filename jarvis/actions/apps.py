import os
import time
import subprocess
import shutil
import glob
import tempfile
import sys
import types
from pathlib import Path
from typing import Optional, List, Dict, Any
from config.settings import CACHE_DIR

# Ensure DISPLAY variable exists to prevent mouseinfo crash on headless/Wayland
if "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

# Stub mouseinfo to prevent its sys.exit() crash on Linux systems lacking tkinter
if "mouseinfo" not in sys.modules:
    mock_mouseinfo = types.ModuleType("mouseinfo")
    mock_mouseinfo.position = lambda: (0, 0)
    mock_mouseinfo.MouseInfoWindow = lambda: None
    sys.modules["mouseinfo"] = mock_mouseinfo

try:
    import pyautogui
except Exception:
    pyautogui = None


def set_clipboard(text: str) -> bool:
    """Multi-distro clipboard setter:
    1. KDE Plasma DBus (qdbus6 / qdbus / busctl to org.kde.klipper) -> Instant sub-5ms on Arch Linux KDE Wayland.
    2. wl-copy (Wayland on Pop!_OS / GNOME / COSMIC).
    3. xclip (X11 on Pop!_OS / Ubuntu).
    4. xsel (X11).
    5. pyperclip fallback.
    """
    if not isinstance(text, str):
        text = str(text)

    # 1. KDE Plasma DBus (Arch Linux / KDE Plasma 6 Wayland)
    for qdbus_bin in ["qdbus6", "qdbus"]:
        if shutil.which(qdbus_bin):
            try:
                res = subprocess.run(
                    [qdbus_bin, "org.kde.klipper", "/klipper", "org.kde.klipper.klipper.setClipboardContents", text],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
                if res.returncode == 0:
                    return True
            except Exception:
                pass

    if shutil.which("busctl"):
        try:
            res = subprocess.run(
                ["busctl", "--user", "call", "org.kde.klipper", "/klipper", "org.kde.klipper.klipper", "setClipboardContents", "s", text],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 2. wl-copy (Wayland on Pop!_OS / GNOME / COSMIC)
    if shutil.which("wl-copy"):
        try:
            res = subprocess.run(["wl-copy"], input=text.encode("utf-8"), capture_output=True, timeout=1.0)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 3. xclip (X11 on Pop!_OS / Ubuntu)
    if shutil.which("xclip"):
        try:
            res = subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode("utf-8"), capture_output=True, timeout=1.0)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 4. xsel (X11)
    if shutil.which("xsel"):
        try:
            res = subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode("utf-8"), capture_output=True, timeout=1.0)
            if res.returncode == 0:
                return True
        except Exception:
            pass

    # 5. pyperclip fallback
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        pass

    return False


def get_clipboard() -> str:
    """Multi-distro clipboard getter."""
    # 1. wl-paste (Wayland on Pop!_OS / GNOME / COSMIC)
    if shutil.which("wl-paste"):
        try:
            res = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    # 2. KDE Plasma DBus (Arch Linux / KDE Plasma 6 Wayland)
    for qdbus_bin in ["qdbus6", "qdbus"]:
        if shutil.which(qdbus_bin):
            try:
                res = subprocess.run(
                    [qdbus_bin, "org.kde.klipper", "/klipper", "org.kde.klipper.klipper.getClipboardContents"],
                    capture_output=True,
                    text=True,
                    timeout=1.0
                )
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass

    if shutil.which("busctl"):
        try:
            res = subprocess.run(
                ["busctl", "--user", "call", "org.kde.klipper", "/klipper", "org.kde.klipper.klipper", "getClipboardContents"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if res.returncode == 0 and res.stdout:
                # busctl outputs: s "content"
                lines = res.stdout.strip().split('"', 1)
                if len(lines) > 1:
                    return lines[1].rstrip('"')
        except Exception:
            pass

    # 3. xclip (X11)
    if shutil.which("xclip"):
        try:
            res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                return res.stdout
        except Exception:
            pass

    # 4. pyperclip fallback
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception:
        pass

    return ""


def find_antigravity_bin() -> Optional[Path]:
    """Dynamically detects the Antigravity binary across Arch Linux and Pop!_OS."""
    # 1. Inspect running processes in /proc to find actual running instance
    for proc_cmdline in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            with open(proc_cmdline, "rb") as f:
                cmd = f.read().split(b"\0")
                if cmd and b"antigravity" in cmd[0].lower() and b"python" not in cmd[0].lower():
                    exe_target = os.readlink(proc_cmdline.replace("cmdline", "exe"))
                    if os.path.exists(exe_target) and os.access(exe_target, os.X_OK):
                        return Path(exe_target)
        except Exception:
            continue

    # 2. Check standard candidate filesystem locations
    home = Path.home()
    candidates = [
        home / "Desktop" / "Antigravity-x64" / "antigravity",
        home / "Desktop" / "Antigravity" / "antigravity",
        home / "Downloads" / "Antigravity" / "Antigravity-x64" / "antigravity",
        home / "Downloads" / "Antigravity-x64" / "antigravity",
        home / "Downloads" / "Antigravity" / "antigravity",
        home / ".local" / "bin" / "antigravity",
        home / "bin" / "antigravity",
        Path("/opt/antigravity/antigravity"),
        Path("/usr/local/bin/antigravity"),
    ]
    for c in candidates:
        if c.exists() and os.access(str(c), os.X_OK):
            return c

    # 3. PATH lookup
    which_bin = shutil.which("antigravity")
    if which_bin:
        return Path(which_bin)

    return None


def focus_window_by_pattern(pattern: str) -> bool:
    """Activates and raises a window matching the pattern across KDE Plasma, GNOME, X11, Wayland."""
    p_lower = pattern.lower().strip()
    focused = False

    # 1. KDE Plasma KWin Scripting (Wayland & X11 on Arch Linux)
    qdbus_cmd = "qdbus6" if shutil.which("qdbus6") else ("qdbus" if shutil.which("qdbus") else None)
    if qdbus_cmd:
        script = f"""
        var windows = workspace.windowList();
        for (var i = 0; i < windows.length; ++i) {{
            var w = windows[i];
            var title = (w.caption || '').toLowerCase();
            var cls = (w.resourceClass || '').toLowerCase();
            if (title.indexOf('{p_lower}') !== -1 || cls.indexOf('{p_lower}') !== -1) {{
                workspace.activeWindow = w;
                break;
            }}
        }}
        """
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(script)
                temp_name = f.name
            script_name = f"focus_{int(time.time() * 1000)}"
            load_res = subprocess.run(
                [qdbus_cmd, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", temp_name, script_name],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            s_id = load_res.stdout.strip()
            if s_id and s_id.isdigit():
                subprocess.run(
                    [qdbus_cmd, "org.kde.KWin", f"/Scripting/Script{s_id}", "org.kde.kwin.Script.run"],
                    capture_output=True,
                    timeout=1.0
                )
                time.sleep(0.04)
                subprocess.run(
                    [qdbus_cmd, "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", script_name],
                    capture_output=True,
                    timeout=1.0
                )
                focused = True
        except Exception:
            pass
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except Exception:
                    pass

    # 2. wmctrl (Standard on Pop!_OS / X11 / XWayland)
    if not focused and shutil.which("wmctrl"):
        try:
            res = subprocess.run(["wmctrl", "-a", p_lower], capture_output=True, timeout=1.0)
            if res.returncode == 0:
                focused = True
        except Exception:
            pass

    # 3. xdotool (X11 / XWayland)
    if not focused and shutil.which("xdotool"):
        try:
            res = subprocess.run(["xdotool", "search", "--name", p_lower, "windowactivate"], capture_output=True, timeout=1.0)
            if res.returncode == 0:
                focused = True
        except Exception:
            pass

    return focused


# Common Linux & Flatpak application mappings
FLATPAK_APPS = {
    "discord": "com.discordapp.Discord",
    "brave": "com.brave.Browser",
    "obs": "com.obsproject.Studio",
    "heroic": "com.heroicgameslauncher.hgl",
    "mgba": "io.mgba.mGBA",
    "kdenlive": "org.kde.kdenlive",
}

# Predefined application executable candidates
_detected_ag = find_antigravity_bin()
_ag_candidates = [str(_detected_ag)] if _detected_ag else []
_ag_candidates.extend([
    str(Path.home() / "Desktop" / "Antigravity-x64" / "antigravity"),
    str(Path.home() / "Downloads" / "Antigravity" / "Antigravity-x64" / "antigravity"),
    "antigravity"
])

NATIVE_APPS = {
    "antigravity": _ag_candidates,
    "anti-gravity": _ag_candidates,
    "antique gravity": _ag_candidates,
    "the gravity": _ag_candidates,
    "gravity": _ag_candidates,
    "terminal": ["kitty", "alacritty", "cosmic-term", "gnome-terminal", "konsole", "xfce4-terminal", "foot", "wezterm", "xterm"],
    "calculator": ["gnome-calculator", "kcalc", "xcalc"],
    "files": ["cosmic-files", "nautilus", "dolphin", "thunar", "pcmanfm"],
    "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "firefox": ["firefox"],
    "brave": ["com.brave.Browser", "brave-browser", "brave"],
    "vlc": ["vlc"],
    "vscode": ["code", "com.microsoft.VSCode"],
    "code": ["code", "com.microsoft.VSCode"],
    "spotify": ["spotify"],
    "settings": ["cosmic-settings", "gnome-control-center", "systemsettings"],
    "text_editor": ["cosmic-edit", "gedit", "kate", "xed", "mousepad", "nano"]
}


class AppManager:
    """Controls desktop applications, window typing, Antigravity bridge, media, and system actions."""

    @staticmethod
    def launch_app(app_name: str) -> dict:
        """Launches or brings up an application by name."""
        app_clean = app_name.lower().strip()

        # 0. Check direct Antigravity shortcuts
        if any(g in app_clean for g in ("antigravity", "anti-gravity", "antique gravity", "gravity")):
            ag_bin = find_antigravity_bin()
            if ag_bin and ag_bin.exists():
                try:
                    subprocess.Popen(
                        [str(ag_bin)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    return {"status": "success", "message": "Launched Antigravity IDE."}
                except Exception as e:
                    return {"status": "error", "message": f"Failed to launch Antigravity: {e}"}

        # 1. Check Flatpak applications
        if app_clean in FLATPAK_APPS:
            flatpak_id = FLATPAK_APPS[app_clean]
            try:
                subprocess.Popen(
                    ["flatpak", "run", flatpak_id],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return {"status": "success", "message": f"Launched {app_name} via Flatpak ({flatpak_id})."}
            except Exception as e:
                return {"status": "error", "message": f"Failed to launch Flatpak {flatpak_id}: {e}"}

        # 2. Check native predefined aliases or direct executable binaries
        binary_candidates = NATIVE_APPS.get(app_clean, [app_clean])
        for binary in binary_candidates:
            if shutil.which(binary) or (os.path.exists(binary) and os.access(binary, os.X_OK)):
                try:
                    subprocess.Popen(
                        [binary],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    return {"status": "success", "message": f"Launched {binary}."}
                except Exception as e:
                    return {"status": "error", "message": f"Failed to launch {binary}: {e}"}

        # 3. Try gtk-launch
        if shutil.which("gtk-launch"):
            res = subprocess.run(["gtk-launch", app_clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                return {"status": "success", "message": f"Launched {app_name} via desktop entry."}

        # 4. Try generic xdg-open if user passed a file or path
        if os.path.exists(app_name):
            subprocess.Popen(
                ["xdg-open", app_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return {"status": "success", "message": f"Opened file {app_name} with default handler."}

        return {"status": "error", "message": f"Application '{app_name}' not found on system."}

    @staticmethod
    def focus_app(app_name: str) -> dict:
        """Brings an application window to the foreground across KDE Plasma and GNOME/Cosmic."""
        app_clean = app_name.lower().strip()
        is_antigravity = any(g in app_clean for g in ("antigravity", "anti-gravity", "antique gravity", "gravity"))
        target_pattern = "antigravity" if is_antigravity else app_clean

        # Attempt window focus
        focused = focus_window_by_pattern(target_pattern)

        # For Antigravity, also trigger single-instance launcher to guarantee raise
        if is_antigravity:
            ag_bin = find_antigravity_bin()
            if ag_bin:
                try:
                    subprocess.Popen(
                        [str(ag_bin)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    focused = True
                except Exception:
                    pass

        if focused:
            return {"status": "success", "message": f"Focused application '{app_name}'."}

        # If not focused yet, try launching it
        return AppManager.launch_app(app_name)

    @staticmethod
    def prompt_antigravity(prompt_text: str) -> dict:
        """Focuses Antigravity IDE, pastes the prompt into the active chat prompt input,
        and presses Enter to submit directly to Antigravity.
        """
        clean_prompt = prompt_text.strip() if prompt_text else ""
        if not clean_prompt:
            return {"status": "error", "message": "No prompt text provided for Antigravity."}

        # 1. Bring Antigravity to foreground
        AppManager.focus_app("antigravity")
        time.sleep(0.35)

        # 2. Stage prompt into multi-distro clipboard
        copied = set_clipboard(clean_prompt)

        # 3. Paste via Ctrl+V into active chat input
        pasted = False
        if copied:
            try:
                time.sleep(0.05)
                pyautogui.hotkey('ctrl', 'v')
                pasted = True
            except Exception:
                pass

        if not pasted:
            try:
                pyautogui.write(clean_prompt, interval=0.002)
            except Exception:
                pass

        # 4. Hit Enter to submit prompt directly to Antigravity
        time.sleep(0.12)
        try:
            pyautogui.press('enter')
        except Exception:
            pass

        preview = clean_prompt[:60] + ("..." if len(clean_prompt) > 60 else "")
        return {
            "status": "success",
            "message": f"Successfully submitted prompt to Antigravity: '{preview}'."
        }

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
    def type_message(text: str, press_enter: bool = False, delay_sec: float = 0.2) -> dict:
        """Types or pastes text into the currently active window on your desktop.
        Uses multi-distro clipboard paste (Ctrl+V) for instantaneous, unicode-safe typing,
        with automatic fallback to key simulation.
        """
        try:
            time.sleep(delay_sec)
            pasted = False
            if set_clipboard(text):
                try:
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
    def copy_to_clipboard(text: str) -> dict:
        """Copies text to the system clipboard across Arch Linux and Pop!_OS."""
        ok = set_clipboard(text)
        if ok:
            return {"status": "success", "message": f"Copied '{text[:40]}' to clipboard."}
        return {"status": "error", "message": "Failed to set clipboard."}

    @staticmethod
    def read_clipboard() -> dict:
        """Reads current text from the system clipboard."""
        val = get_clipboard()
        return {"status": "success", "clipboard": val, "message": f"Clipboard contents: '{val[:60]}'"}

    @staticmethod
    def dictate_text(text: str, press_enter: bool = False) -> dict:
        """Dedicated dictation tool: types exactly what the user dictates into their active window."""
        return AppManager.type_message(text=text, press_enter=press_enter, delay_sec=0.2)

    @staticmethod
    def press_key(key: str) -> dict:
        """Presses a single key (e.g. 'enter', 'tab', 'esc', 'backspace', 'down', 'space')."""
        try:
            clean_k = key.lower().strip()
            # Map aliases
            alias_map = {
                "return": "enter",
                "escape": "esc",
                "spacebar": "space",
                "del": "delete",
            }
            clean_k = alias_map.get(clean_k, clean_k)
            pyautogui.press(clean_k)
            return {"status": "success", "message": f"Pressed key '{clean_k}'."}
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
        AppManager.focus_app("discord")
        time.sleep(1.8)
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
