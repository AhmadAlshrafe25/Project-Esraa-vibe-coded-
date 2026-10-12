import webbrowser
import urllib.parse
import subprocess
import shutil

class BrowserManager:
    """Manages browser tabs, video searches, web navigation."""

    @staticmethod
    def open_url(url: str) -> dict:
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        webbrowser.open_new_tab(url)
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
        webbrowser.open_new_tab(url)
        return {"status": "success", "message": f"Searching {engine} for '{query}'."}

    @staticmethod
    def play_youtube_video_or_music(query: str) -> dict:
        """Searches YouTube and opens it directly."""
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
        webbrowser.open_new_tab(url)
        return {"status": "success", "message": f"Playing '{query}' on YouTube."}
