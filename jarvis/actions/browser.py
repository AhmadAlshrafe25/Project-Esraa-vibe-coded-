import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import webbrowser

class BrowserManager:
    """Manages browser tabs, video searches, web navigation with native Linux & Flatpak support."""

    @staticmethod
    def _launch_url_reliably(url: str):
        """Launches a URL in the user's browser with Open.Jarvis protocol safety validation."""
        clean_url = (url or "").strip()
        if not clean_url:
            return

        # Open.Jarvis security hardening: block dangerous URL schemes
        low_url = clean_url.lower()
        if low_url.startswith(("javascript:", "data:", "powershell:", "cmd:")):
            return

        # Ensure valid web protocol or search
        if not low_url.startswith(("http://", "https://")):
            clean_url = f"https://{clean_url}"

        # 1. Try xdg-open directly (most reliable on modern Linux desktops)
        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(
                    ["xdg-open", clean_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return
            except Exception:
                pass

        # 2. Try Brave Flatpak directly if installed
        try:
            subprocess.Popen(
                ["flatpak", "run", "com.brave.Browser", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return
        except Exception:
            pass

        # 3. Standard Python webbrowser fallback
        webbrowser.open_new_tab(url)

    @staticmethod
    def _resolve_first_youtube_video(query: str) -> str:
        """Finds the first video ID on YouTube for query so playback starts automatically."""
        clean_q = query.strip()
        encoded = urllib.parse.quote_plus(clean_q)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"
        
        try:
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            
            # Find first watch link (11-character video ID)
            match = re.search(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
            if match:
                video_id = match.group(1)
                return f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
        except Exception:
            pass

        return search_url

    @staticmethod
    def open_url(url: str) -> dict:
        from jarvis.actions.url_safety import normalize_web_url
        safe_url = normalize_web_url(url)
        if not safe_url:
            return {"status": "error", "message": f"Blocked unsafe or malformed URL: {url}"}
        BrowserManager._launch_url_reliably(safe_url)
        return {"status": "success", "message": f"Opened {safe_url} in browser."}

    @staticmethod
    def search_web(query: str, engine: str = "google") -> dict:
        clean_q = query.strip()
        if not clean_q:
            return {"status": "error", "message": "No search query provided."}
        encoded = urllib.parse.quote_plus(clean_q)
        if engine.lower() == "youtube":
            url = BrowserManager._resolve_first_youtube_video(clean_q)
        elif engine.lower() == "wikipedia":
            url = f"https://en.wikipedia.org/wiki/Special:Search?search={encoded}"
        else:
            url = f"https://www.google.com/search?q={encoded}"
        BrowserManager._launch_url_reliably(url)
        return {"status": "success", "message": f"Searching {engine} for '{clean_q}'."}

    @staticmethod
    def play_youtube_video_or_music(query: str) -> dict:
        """Finds the requested song/video and automatically starts playback directly."""
        clean_q = query.strip()
        direct_url = BrowserManager._resolve_first_youtube_video(clean_q)
        BrowserManager._launch_url_reliably(direct_url)
        return {"status": "success", "message": f"Starting playback of '{clean_q}' on YouTube now, sir."}

    @staticmethod
    def close_tab() -> dict:
        """Closes the current browser tab via Ctrl+W hotkey."""
        from jarvis.actions.apps import AppManager
        return AppManager.press_hotkey(["ctrl", "w"])

    @staticmethod
    def close_browser(browser_name: str = "") -> dict:
        """Closes browser instances (Chrome, Brave, Firefox)."""
        from jarvis.actions.apps import AppManager
        targets = [browser_name] if browser_name else ["google-chrome", "google-chrome-stable", "brave", "firefox"]
        for b in targets:
            AppManager.close_app(b)
        return {"status": "success", "message": "Closed browser session, sir."}

    @staticmethod
    def search_portal(portal: str, query: str) -> dict:
        """Searches developer portals: archwiki, github, stackoverflow, reddit."""
        clean_q = urllib.parse.quote_plus(query.strip())
        p = portal.lower().strip()
        if "arch" in p or "wiki" in p:
            url = f"https://wiki.archlinux.org/index.php?search={clean_q}"
            name = "Arch Linux Wiki"
        elif "git" in p:
            url = f"https://github.com/search?q={clean_q}"
            name = "GitHub"
        elif "stack" in p or "overflow" in p:
            url = f"https://stackoverflow.com/search?q={clean_q}"
            name = "Stack Overflow"
        elif "reddit" in p:
            url = f"https://www.reddit.com/search/?q={clean_q}"
            name = "Reddit"
        else:
            url = f"https://www.google.com/search?q={clean_q}"
            name = "Google"
        BrowserManager._launch_url_reliably(url)
        return {"status": "success", "message": f"Searching {name} for '{query}'."}

    @staticmethod
    def open_folder(folder_name: str = "downloads") -> dict:
        """Opens user folders in native file manager."""
        from pathlib import Path
        clean_f = folder_name.lower().strip()
        if "download" in clean_f:
            target = Path.home() / "Downloads"
        elif "document" in clean_f:
            target = Path.home() / "Documents"
        elif "picture" in clean_f or "photo" in clean_f:
            target = Path.home() / "Pictures"
        elif "project" in clean_f or "code" in clean_f or "ezra" in clean_f:
            from config.settings import PROJECT_ROOT
            target = PROJECT_ROOT
        else:
            target = Path.home()

        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"status": "success", "message": f"Opened {target.name} folder."}
        return {"status": "error", "message": "xdg-open not found."}
