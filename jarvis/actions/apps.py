import os
import re
import json
import time
import subprocess
import shutil
import glob
import tempfile
import sys
import types
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
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

try:
    import evdev
    from evdev import ecodes, UInput, AbsInfo
except Exception:
    evdev = None
    ecodes = None
    UInput = None
    AbsInfo = None


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


def capture_desktop_screenshot(target_path: Optional[str] = None) -> str:
    """Universal multi-distro desktop screenshot capturer.
    Works natively across KDE Plasma 6/5 (Wayland & X11), wlroots Wayland, COSMIC, GNOME, and X11.
    """
    if target_path:
        out_file = Path(target_path)
    else:
        out_file = CACHE_DIR / f"ezra_screen_{int(time.time() * 1000)}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_str = str(out_file)

    # 1. KDE Plasma 6 & 5 Wayland & X11 (spectacle)
    if shutil.which("spectacle"):
        try:
            res = subprocess.run(["spectacle", "-b", "-n", "-o", out_str], capture_output=True, timeout=3.5)
            if res.returncode == 0 and os.path.exists(out_str) and os.path.getsize(out_str) > 0:
                return out_str
        except Exception:
            pass

    # 2. Wayland wlroots (Sway, Hyprland, Wayfire via grim)
    if shutil.which("grim"):
        try:
            res = subprocess.run(["grim", out_str], capture_output=True, timeout=3.0)
            if res.returncode == 0 and os.path.exists(out_str) and os.path.getsize(out_str) > 0:
                return out_str
        except Exception:
            pass

    # 3. Pop!_OS COSMIC Wayland native screenshot
    if shutil.which("cosmic-screenshot"):
        try:
            res = subprocess.run(
                ["cosmic-screenshot", "--interactive=false", "--notify=false", f"--save-dir={out_file.parent}"],
                capture_output=True,
                text=True,
                timeout=3.5
            )
            out_p = res.stdout.strip()
            if out_p and os.path.exists(out_p):
                return out_p
            shots = sorted(glob.glob(str(out_file.parent / "Screenshot_*.png")), key=os.path.getmtime)
            if shots and (time.time() - os.path.getmtime(shots[-1])) < 5:
                return shots[-1]
        except Exception:
            pass

    # 4. GNOME Screenshot
    if shutil.which("gnome-screenshot"):
        try:
            res = subprocess.run(["gnome-screenshot", "-f", out_str], capture_output=True, timeout=3.0)
            if res.returncode == 0 and os.path.exists(out_str) and os.path.getsize(out_str) > 0:
                return out_str
        except Exception:
            pass

    # 5. ImageMagick import (X11)
    if shutil.which("import"):
        try:
            res = subprocess.run(["import", "-window", "root", out_str], capture_output=True, timeout=3.0)
            if res.returncode == 0 and os.path.exists(out_str) and os.path.getsize(out_str) > 0:
                return out_str
        except Exception:
            pass

    # 6. Scrot / Maim (X11)
    for tool_cmd in [["scrot", out_str], ["maim", out_str]]:
        if shutil.which(tool_cmd[0]):
            try:
                res = subprocess.run(tool_cmd, capture_output=True, timeout=3.0)
                if res.returncode == 0 and os.path.exists(out_str) and os.path.getsize(out_str) > 0:
                    return out_str
            except Exception:
                pass

    # 7. PIL ImageGrab fallback
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(out_str)
        if os.path.exists(out_str) and os.path.getsize(out_str) > 0:
            return out_str
    except Exception:
        pass

    # 8. PyAutoGUI screenshot fallback
    if pyautogui:
        try:
            shot = pyautogui.screenshot()
            shot.save(out_str)
            if os.path.exists(out_str) and os.path.getsize(out_str) > 0:
                return out_str
        except Exception:
            pass

    raise RuntimeError("All desktop screenshot capture backends (spectacle, grim, cosmic-screenshot, gnome-screenshot, import, scrot, PIL) failed or are unavailable.")


class MouseController:
    """Universal Linux Mouse & Cursor Controller with native Wayland & X11 support.
    Uses kernel UInput via evdev for hardware-level cursor positioning and clicks on Wayland,
    with PyAutoGUI fallback on X11 / XWayland.
    """
    _instance = None
    _uinput = None

    def __init__(self, screen_w: int = 1366, screen_h: int = 768):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._init_screen_size()
        self._init_uinput()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_screen_size(self):
        try:
            if pyautogui:
                sz = pyautogui.size()
                if sz and sz.width > 0 and sz.height > 0:
                    self.screen_w = sz.width
                    self.screen_h = sz.height
                    return
        except Exception:
            pass
        if shutil.which("kscreen-doctor"):
            try:
                res = subprocess.run(["kscreen-doctor", "-o"], capture_output=True, text=True, timeout=1.0)
                m = re.search(r'(\d+)x(\d+)(?:@|\s)', res.stdout)
                if m:
                    self.screen_w = int(m.group(1))
                    self.screen_h = int(m.group(2))
            except Exception:
                pass

    def _init_uinput(self):
        if not evdev or not UInput or not AbsInfo:
            return
        if self._uinput is not None:
            return
        try:
            cap = {
                ecodes.EV_ABS: [
                    (ecodes.ABS_X, AbsInfo(value=self.screen_w // 2, min=0, max=self.screen_w, fuzz=0, flat=0, resolution=0)),
                    (ecodes.ABS_Y, AbsInfo(value=self.screen_h // 2, min=0, max=self.screen_h, fuzz=0, flat=0, resolution=0)),
                ],
                ecodes.EV_REL: [
                    ecodes.REL_X,
                    ecodes.REL_Y,
                ],
                ecodes.EV_KEY: [
                    ecodes.BTN_LEFT,
                    ecodes.BTN_RIGHT,
                    ecodes.BTN_MIDDLE,
                    ecodes.BTN_TOUCH,
                ]
            }
            self._uinput = UInput(cap, name="Ezra-Virtual-Pointer")
        except Exception:
            self._uinput = None

    def move_to(self, x: int, y: int) -> dict:
        clamped_x = max(0, min(self.screen_w, int(x)))
        clamped_y = max(0, min(self.screen_h, int(y)))

        # 1. Native UInput absolute movement (Wayland & X11)
        if self._uinput:
            try:
                self._uinput.write(ecodes.EV_ABS, ecodes.ABS_X, clamped_x)
                self._uinput.write(ecodes.EV_ABS, ecodes.ABS_Y, clamped_y)
                self._uinput.syn()
                return {"status": "success", "message": f"Moved mouse to ({clamped_x}, {clamped_y}).", "x": clamped_x, "y": clamped_y}
            except Exception:
                pass

        # 2. PyAutoGUI fallback
        if pyautogui:
            try:
                pyautogui.moveTo(clamped_x, clamped_y)
                return {"status": "success", "message": f"Moved mouse to ({clamped_x}, {clamped_y}).", "x": clamped_x, "y": clamped_y}
            except Exception as e:
                return {"status": "error", "message": f"Failed to move mouse: {e}"}

        return {"status": "error", "message": "No mouse controller backend available."}

    def move_relative(self, dx: int, dy: int) -> dict:
        if self._uinput:
            try:
                self._uinput.write(ecodes.EV_REL, ecodes.REL_X, int(dx))
                self._uinput.write(ecodes.EV_REL, ecodes.REL_Y, int(dy))
                self._uinput.syn()
                return {"status": "success", "message": f"Moved mouse by ({dx}, {dy})."}
            except Exception:
                pass
        if pyautogui:
            try:
                pyautogui.moveRel(int(dx), int(dy))
                return {"status": "success", "message": f"Moved mouse by ({dx}, {dy})."}
            except Exception as e:
                return {"status": "error", "message": f"Failed to move mouse relatively: {e}"}
        return {"status": "error", "message": "No mouse controller backend available."}

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> dict:
        if x is not None and y is not None:
            self.move_to(x, y)
            time.sleep(0.03)

        btn_clean = button.lower().strip()
        btn_code = ecodes.BTN_LEFT if ecodes else None
        if ecodes:
            if btn_clean == "right":
                btn_code = ecodes.BTN_RIGHT
            elif btn_clean == "middle":
                btn_code = ecodes.BTN_MIDDLE

        if self._uinput and btn_code is not None:
            try:
                for i in range(clicks):
                    self._uinput.write(ecodes.EV_KEY, btn_code, 1)
                    self._uinput.syn()
                    time.sleep(0.04)
                    self._uinput.write(ecodes.EV_KEY, btn_code, 0)
                    self._uinput.syn()
                    if clicks > 1 and i < clicks - 1:
                        time.sleep(0.08)
                loc_str = f" at ({x}, {y})" if (x is not None and y is not None) else ""
                c_str = f"{clicks}x " if clicks > 1 else ""
                return {"status": "success", "message": f"{c_str}{btn_clean.capitalize()} clicked{loc_str}."}
            except Exception:
                pass

        if pyautogui:
            try:
                pyautogui.click(x=x, y=y, button=btn_clean, clicks=clicks)
                loc_str = f" at ({x}, {y})" if (x is not None and y is not None) else ""
                c_str = f"{clicks}x " if clicks > 1 else ""
                return {"status": "success", "message": f"{c_str}{btn_clean.capitalize()} clicked{loc_str}."}
            except Exception as e:
                return {"status": "error", "message": f"Click failed: {e}"}

        return {"status": "error", "message": "No mouse backend available."}

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> dict:
        return self.click(x=x, y=y, button="left", clicks=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> dict:
        return self.click(x=x, y=y, button="right", clicks=1)

    def drag_to(self, to_x: int, to_y: int, from_x: Optional[int] = None, from_y: Optional[int] = None, button: str = "left", steps: int = 15, duration: float = 0.2) -> dict:
        if from_x is not None and from_y is not None:
            self.move_to(from_x, from_y)
            time.sleep(0.04)

        btn_clean = button.lower().strip()
        btn_code = ecodes.BTN_LEFT if ecodes else None
        if ecodes and btn_clean == "right":
            btn_code = ecodes.BTN_RIGHT

        if self._uinput and btn_code is not None:
            try:
                self._uinput.write(ecodes.EV_KEY, btn_code, 1)
                self._uinput.syn()
                time.sleep(0.04)

                sx = from_x if from_x is not None else to_x
                sy = from_y if from_y is not None else to_y
                step_delay = duration / max(1, steps)
                for s in range(1, steps + 1):
                    cx = int(sx + (to_x - sx) * (s / steps))
                    cy = int(sy + (to_y - sy) * (s / steps))
                    self.move_to(cx, cy)
                    time.sleep(step_delay)

                self._uinput.write(ecodes.EV_KEY, btn_code, 0)
                self._uinput.syn()
                return {"status": "success", "message": f"Dragged mouse to ({to_x}, {to_y})."}
            except Exception:
                pass

        if pyautogui:
            try:
                if from_x is not None and from_y is not None:
                    pyautogui.moveTo(from_x, from_y)
                pyautogui.dragTo(to_x, to_y, duration=duration, button=btn_clean)
                return {"status": "success", "message": f"Dragged mouse to ({to_x}, {to_y})."}
            except Exception as e:
                return {"status": "error", "message": f"Drag failed: {e}"}

        return {"status": "error", "message": "No mouse backend available."}

mouse_controller = MouseController.get_instance()


TERMINAL_CLASSES = [
    "kitty", "alacritty", "konsole", "cosmic-term", "gnome-terminal", "foot",
    "wezterm", "xterm", "xfce4-terminal", "tilix", "terminator", "urxvt", "rxvt", "st", "bash", "zsh"
]
BROWSER_CLASSES = [
    "brave-browser", "brave", "google-chrome", "google-chrome-stable", "chromium",
    "chromium-browser", "firefox", "microsoft-edge", "opera", "vivaldi", "epiphany"
]
EDITOR_CLASSES = [
    "code", "vscode", "vscodium", "cursor", "kate", "gedit", "sublime_text", "atom", "xed"
]


def focus_window_by_pattern(pattern: str, pick_other: bool = False) -> bool:
    """Activates and raises a window matching the pattern across KDE Plasma 6/5, GNOME, X11, Wayland.
    Supports smart category expansion (terminal, browser, editor) and switching between multiple windows.
    """
    p_lower = pattern.lower().strip()
    focused = False

    targets = [p_lower]
    if p_lower in ("terminal", "term", "console", "shell", "bash", "zsh", "ترمينال", "الترمينال"):
        targets.extend(TERMINAL_CLASSES)
    elif p_lower in ("browser", "web", "internet", "متصفح"):
        targets.extend(BROWSER_CLASSES)
    elif p_lower in ("code", "editor", "vscode", "محرر"):
        targets.extend(EDITOR_CLASSES)

    targets_json = json.dumps(targets)
    pick_other_js = "true" if pick_other else "false"

    # 1. KDE Plasma KWin Scripting (Wayland & X11 on Arch Linux / Fedora / Kubuntu)
    qdbus_cmd = "qdbus6" if shutil.which("qdbus6") else ("qdbus" if shutil.which("qdbus") else None)
    if qdbus_cmd:
        script = f"""
        var targets = {targets_json};
        var pickOther = {pick_other_js};
        var wins = workspace.windowList ? workspace.windowList() : workspace.stackingOrder;
        var matches = [];
        var activeWin = workspace.activeWindow;

        for (var i = 0; i < wins.length; ++i) {{
            var w = wins[i];
            var title = (w.caption || '').toLowerCase();
            var cls = (w.resourceClass || '').toLowerCase();
            var resName = (w.resourceName || '').toLowerCase();
            var dfn = (w.desktopFileName || '').toLowerCase();

            var hit = false;
            for (var t = 0; t < targets.length; ++t) {{
                var tgt = targets[t];
                if (cls === tgt || resName === tgt || title.indexOf(tgt) !== -1 || cls.indexOf(tgt) !== -1 || resName.indexOf(tgt) !== -1 || dfn.indexOf(tgt) !== -1) {{
                    hit = true;
                    break;
                }}
            }}
            if (hit) {{
                matches.push(w);
            }}
        }}

        var chosen = null;
        if (matches.length > 0) {{
            if (pickOther && matches.length > 1) {{
                for (var m = 0; m < matches.length; ++m) {{
                    if (matches[m] !== activeWin) {{
                        chosen = matches[m];
                        break;
                    }}
                }}
            }}
            if (!chosen) chosen = matches[0];

            if (chosen.desktops && chosen.desktops.length > 0 && workspace.currentDesktop) {{
                var onCurrent = false;
                for (var d = 0; d < chosen.desktops.length; ++d) {{
                    if (chosen.desktops[d] === workspace.currentDesktop) {{ onCurrent = true; break; }}
                }}
                if (!onCurrent && chosen.desktops[0]) {{
                    workspace.currentDesktop = chosen.desktops[0];
                }}
            }}

            chosen.minimized = false;
            workspace.activeWindow = chosen;
            if (workspace.raiseWindow) workspace.raiseWindow(chosen);
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
        for tgt in targets:
            try:
                res = subprocess.run(["wmctrl", "-x", "-a", tgt], capture_output=True, timeout=0.8)
                if res.returncode == 0:
                    focused = True
                    break
                res = subprocess.run(["wmctrl", "-a", tgt], capture_output=True, timeout=0.8)
                if res.returncode == 0:
                    focused = True
                    break
            except Exception:
                pass

    # 3. xdotool (X11 / XWayland)
    if not focused and shutil.which("xdotool"):
        for tgt in targets:
            try:
                res = subprocess.run(["xdotool", "search", "--class", tgt, "windowactivate"], capture_output=True, timeout=0.8)
                if res.returncode == 0:
                    focused = True
                    break
                res = subprocess.run(["xdotool", "search", "--name", tgt, "windowactivate"], capture_output=True, timeout=0.8)
                if res.returncode == 0:
                    focused = True
                    break
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
    """Controls desktop applications, window typing, Antigravity bridge, media, mouse, and system actions."""
    _last_focused_app: str = ""

    @staticmethod
    def is_terminal_target(name: str) -> bool:
        n = (name or "").lower().strip()
        return any(t in n for t in ("terminal", "term", "kitty", "konsole", "alacritty", "bash", "shell", "foot", "wezterm", "xterm", "ترمينال"))

    @classmethod
    def is_terminal_active(cls) -> bool:
        return cls.is_terminal_target(cls._last_focused_app)

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

        # 1.5. Dynamic Flatpak lookup for any installed app
        if shutil.which("flatpak"):
            try:
                fp_res = subprocess.run(["flatpak", "list", "--app", "--columns=application,name"], capture_output=True, text=True, timeout=1.0)
                if fp_res.returncode == 0:
                    for line in fp_res.stdout.splitlines():
                        cols = line.strip().split()
                        if cols and any(app_clean in c.lower() for c in cols):
                            f_id = cols[0]
                            subprocess.Popen(["flatpak", "run", f_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                            return {"status": "success", "message": f"Launched {app_name} via Flatpak ({f_id})."}
            except Exception:
                pass

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

    @classmethod
    def focus_app(cls, app_name: str, pick_other: bool = False) -> dict:
        """Brings an application window to the foreground across KDE Plasma and GNOME/Cosmic."""
        app_clean = app_name.lower().strip()
        is_antigravity = any(g in app_clean for g in ("antigravity", "anti-gravity", "antique gravity", "gravity"))
        target_pattern = "antigravity" if is_antigravity else app_clean

        if "other" in app_clean or "another" in app_clean or "ثاني" in app_clean or "تاني" in app_clean:
            pick_other = True
            target_pattern = re.sub(r'\b(?:the|other|another|window|الـ|الثاني|التاني)\b', '', target_pattern).strip() or "terminal"

        # Attempt window focus
        focused = focus_window_by_pattern(target_pattern, pick_other=pick_other)
        if focused:
            cls._last_focused_app = target_pattern

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
                    cls._last_focused_app = "antigravity"
                except Exception:
                    pass

        if focused:
            return {"status": "success", "message": f"Focused application '{app_name}'."}

        # If not focused yet, try launching it
        launch_res = AppManager.launch_app(target_pattern)
        if launch_res.get("status") == "success":
            cls._last_focused_app = target_pattern
        return launch_res

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

    @classmethod
    def prompt_app(cls, app_name: str, text: str, press_enter: bool = True) -> dict:
        """Universal Application Bridge: Focuses ANY application window,
        types/pastes the prompt or text, and presses Enter to submit.
        """
        app_clean = app_name.lower().strip()
        if any(g in app_clean for g in ("antigravity", "anti-gravity", "antique gravity", "gravity")):
            return cls.prompt_antigravity(text)

        # 1. Bring application window to foreground
        cls.focus_app(app_clean)
        time.sleep(0.25)

        # 2. Type/paste text into application with terminal detection
        is_term = cls.is_terminal_target(app_clean)
        res = cls.type_message(text, press_enter=press_enter, delay_sec=0.08, in_terminal=is_term)
        preview = text[:50] + ("..." if len(text) > 50 else "")
        return {
            "status": "success",
            "message": f"Submitted to {app_name}: '{preview}'."
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

    @classmethod
    def type_message(cls, text: str, press_enter: bool = False, delay_sec: float = 0.15, in_terminal: Optional[bool] = None, app_name: Optional[str] = None) -> dict:
        """Types or pastes text into the active window or target application.
        Fixes Linux terminal typing:
        - In terminal: avoids Ctrl+V (which triggers readline quoted-insert ^M), uses direct keystroke typing (pyautogui.write)
          for ASCII shell commands, or Ctrl+Shift+V for non-ASCII/unicode clipboard paste.
        - In desktop GUI apps: uses Ctrl+V clipboard paste with direct keystroke fallback.
        - Optionally presses Enter after typing.
        """
        try:
            if app_name:
                cls.focus_app(app_name)
                time.sleep(0.2)

            time.sleep(delay_sec)

            is_term = in_terminal if in_terminal is not None else cls.is_terminal_active()
            if app_name and cls.is_terminal_target(app_name):
                is_term = True

            if is_term:
                # Terminal mode: NEVER send Ctrl+V (prevents readline ^M)
                is_ascii = all(ord(c) < 128 for c in text)
                typed = False
                if is_ascii and pyautogui:
                    try:
                        pyautogui.write(text, interval=0.003)
                        typed = True
                    except Exception:
                        pass

                if not typed:
                    # Unicode or multiline terminal typing: use terminal paste Ctrl+Shift+V
                    if set_clipboard(text) and pyautogui:
                        try:
                            time.sleep(0.04)
                            pyautogui.hotkey('ctrl', 'shift', 'v')
                            typed = True
                        except Exception:
                            pass
                    if not typed and pyautogui:
                        try:
                            pyautogui.write(text, interval=0.003)
                            typed = True
                        except Exception:
                            pass
            else:
                # Standard GUI window (Antigravity, browser, Discord, editor)
                pasted = False
                if set_clipboard(text) and pyautogui:
                    try:
                        time.sleep(0.04)
                        pyautogui.hotkey('ctrl', 'v')
                        pasted = True
                    except Exception:
                        pass
                if not pasted and pyautogui:
                    try:
                        pyautogui.write(text, interval=0.003)
                    except Exception:
                        pass

            if press_enter and pyautogui:
                time.sleep(0.08)
                pyautogui.press('enter')

            preview = text[:60] + ("..." if len(text) > 60 else "")
            return {
                "status": "success",
                "message": f"Successfully typed: '{preview}'{' and pressed Enter' if press_enter else ''}."
            }
        except Exception as e:
            return {"status": "error", "message": f"Failed to type text: {e}"}

    @classmethod
    def type_text(cls, text: str, press_enter: bool = False, app_name: Optional[str] = None, in_terminal: Optional[bool] = None) -> dict:
        """Universal typing tool: types arbitrary text, words, code, or shell commands
        into any window or terminal, with optional automatic Enter.
        """
        return cls.type_message(text=text, press_enter=press_enter, in_terminal=in_terminal, app_name=app_name)

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

    @classmethod
    def dictate_text(cls, text: str, press_enter: bool = False) -> dict:
        """Dedicated dictation tool: types exactly what the user dictates into their active window."""
        return cls.type_message(text=text, press_enter=press_enter, delay_sec=0.15)

    @staticmethod
    def move_mouse(x: int, y: int) -> dict:
        """Moves mouse cursor to specified screen coordinates (x, y)."""
        return mouse_controller.move_to(x, y)

    @staticmethod
    def move_mouse_relative(dx: int, dy: int) -> dict:
        """Moves mouse cursor relatively by (dx, dy) pixels."""
        return mouse_controller.move_relative(dx, dy)

    @staticmethod
    def click_mouse(x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1) -> dict:
        """Clicks the mouse button ('left', 'right', 'middle') at current or specified position."""
        return mouse_controller.click(x=x, y=y, button=button, clicks=clicks)

    @staticmethod
    def double_click(x: Optional[int] = None, y: Optional[int] = None) -> dict:
        """Double-clicks left mouse button at current or specified position."""
        return mouse_controller.double_click(x=x, y=y)

    @staticmethod
    def right_click(x: Optional[int] = None, y: Optional[int] = None) -> dict:
        """Right-clicks mouse (context menu) at current or specified position."""
        return mouse_controller.right_click(x=x, y=y)

    @staticmethod
    def drag_mouse(to_x: int, to_y: int, from_x: Optional[int] = None, from_y: Optional[int] = None, button: str = "left") -> dict:
        """Drags mouse to specified coordinates."""
        return mouse_controller.drag_to(to_x=to_x, to_y=to_y, from_x=from_x, from_y=from_y, button=button)

    @staticmethod
    def point_at(x: Optional[int] = None, y: Optional[int] = None, target: Optional[str] = None) -> dict:
        """Points the mouse cursor at coordinates (x, y) or visually locates and points at target."""
        if x is not None and y is not None:
            return mouse_controller.move_to(x, y)
        if target:
            from jarvis.actions.vision import screen_vision
            return screen_vision.locate_and_point(target)
        return {"status": "error", "message": "Must provide either coordinates (x, y) or target description to point at."}

    @staticmethod
    def press_key(key: str) -> dict:
        """Presses a single key (e.g. 'enter', 'tab', 'esc', 'backspace', 'down', 'space')."""
        try:
            clean_k = key.lower().strip()
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

    @classmethod
    def send_discord_message(cls, message: str) -> dict:
        """Launches Discord (if not already open), waits for focus, and types the message into active chat."""
        cls.focus_app("discord")
        time.sleep(1.8)
        return cls.type_message(message, press_enter=True)

    @staticmethod
    def take_screenshot() -> dict:
        """Takes a full screen screenshot and saves it to cache across all Linux desktop environments."""
        try:
            filename = f"screenshot_{int(time.time() * 1000)}.png"
            path = CACHE_DIR / filename
            saved_path = capture_desktop_screenshot(str(path))
            return {"status": "success", "message": f"Screenshot saved to {saved_path}.", "path": str(saved_path)}
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
