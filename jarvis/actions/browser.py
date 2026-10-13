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
        """Launches a URL in the user's browser, silencing all GPU driver/stdout logs."""
        # 1. Try xdg-open directly (most reliable on modern Linux desktops)
        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(
                    ["xdg-open", url],
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
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        BrowserManager._launch_url_reliably(url)
        return {"status": "success", "message": f"Opened {url} in browser."}

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
