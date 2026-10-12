import os
import shutil
import subprocess
import urllib.parse
import webbrowser

class BrowserManager:
    """Manages browser tabs, video searches, web navigation with native Linux & Flatpak support."""

    @staticmethod
    def _launch_url_reliably(url: str):
        # 1. Try xdg-open directly (most reliable on modern Linux desktops)
        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(["xdg-open", url], start_new_session=True)
                return
            except Exception:
                pass

        # 2. Try Brave Flatpak directly if installed
        try:
            subprocess.Popen(["flatpak", "run", "com.brave.Browser", url], start_new_session=True)
            return
        except Exception:
            pass

        # 3. Standard Python webbrowser fallback
        webbrowser.open_new_tab(url)

    @staticmethod
    def open_url(url: str) -> dict:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        BrowserManager._launch_url_reliably(url)
        return {"status": "success", "message": f"Opened {url} in browser."}

    @staticmethod
    def search_web(query: str, engine: str = "google") -> dict:
        encoded = urllib.parse.quote_plus(query)
        if engine.lower() == "youtube":
            url = f"https://www.youtube.com/results?search_query={encoded}"
        elif engine.lower() == "wikipedia":
            url = f"https://en.wikipedia.org/wiki/Special:Search?search={encoded}"
        else:
            url = f"https://www.google.com/search?q={encoded}"
        BrowserManager._launch_url_reliably(url)
        return {"status": "success", "message": f"Searching {engine} for '{query}'."}

    @staticmethod
    def play_youtube_video_or_music(query: str) -> dict:
        """Searches YouTube and opens it directly."""
        clean_q = query.strip()
        encoded = urllib.parse.quote_plus(clean_q)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        BrowserManager._launch_url_reliably(url)
        return {"status": "success", "message": f"Playing '{clean_q}' on YouTube."}
