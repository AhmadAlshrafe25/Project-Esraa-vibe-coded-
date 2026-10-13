import os
import glob
import time
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

import sys
import types

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

from config.settings import CACHE_DIR, GEMINI_API_KEY
from jarvis.actions.apps import capture_desktop_screenshot, mouse_controller

class ScreenVision:
    """Provides Ezra with real-time visual perception of your desktop screen."""

    @staticmethod
    def capture_screen() -> str:
        """Captures a full-resolution screenshot using multi-distro tools (spectacle, grim, cosmic, gnome, etc.)."""
        out_file = CACHE_DIR / f"ezra_screen_{int(time.time() * 1000)}.png"
        return capture_desktop_screenshot(str(out_file))

    @staticmethod
    def get_screen_dimensions(screenshot_path: Optional[str] = None) -> tuple[int, int]:
        """Gets screen width and height directly from screenshot or mouse controller."""
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                with Image.open(screenshot_path) as img:
                    return img.size
            except Exception:
                pass
        return (mouse_controller.screen_w, mouse_controller.screen_h)

    @staticmethod
    def analyze_screen(instruction: str = "Describe what is currently visible on the screen.") -> str:
        """Takes a screenshot and sends it to Gemini 3.5 Flash Vision for visual analysis."""
        if not GEMINI_API_KEY:
            return "Gemini API key is required to analyze the screen visually."

        try:
            screenshot_path = ScreenVision.capture_screen()
        except Exception as e:
            return f"Failed to capture desktop screenshot: {e}"

        if not screenshot_path or not os.path.exists(screenshot_path):
            return "Failed to capture desktop screenshot."

        try:
            import google.genai as genai
            client = genai.Client(api_key=GEMINI_API_KEY)

            with open(screenshot_path, "rb") as f:
                img_bytes = f.read()

            prompt = (
                f"You are Ezra, an AI assistant with direct vision of the user's computer screen.\n"
                f"User Directive: {instruction}\n"
                f"Analyze the screenshot carefully. Answer concisely, smartly, with subtle British wit. Focus directly on the UI elements, open apps, windows, or errors the user asked about."
            )

            resp = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    genai.types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    prompt
                ]
            )

            return resp.text.strip() if resp and resp.text else "Unable to interpret screen contents."
        except Exception as e:
            return f"Visual inspection error: {e}"

    @staticmethod
    def locate_and_click(element_description: str) -> dict:
        """Uses visual reasoning to locate an element on screen and click it."""
        try:
            screenshot_path = ScreenVision.capture_screen()
        except Exception as e:
            return {"status": "error", "message": f"Failed to capture screen: {e}"}

        if not screenshot_path or not os.path.exists(screenshot_path):
            return {"status": "error", "message": "Failed to capture screen."}

        try:
            import google.genai as genai
            import json
            import re

            client = genai.Client(api_key=GEMINI_API_KEY)
            with open(screenshot_path, "rb") as f:
                img_bytes = f.read()

            prompt = (
                f"Locate the UI element described as: '{element_description}'.\n"
                f"Return ONLY a JSON object with normalized coordinates from 0 to 1000:\n"
                f'{{"found": true, "x": 500, "y": 300}}\n'
                f"If not visible, return {{\"found\": false}}"
            )

            resp = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    genai.types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    prompt
                ]
            )

            match = re.search(r"\{.*\}", resp.text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("found"):
                    screen_w, screen_h = ScreenVision.get_screen_dimensions(screenshot_path)
                    click_x = int(screen_w * data["x"] / 1000)
                    click_y = int(screen_h * data["y"] / 1000)
                    mouse_controller.click(click_x, click_y)
                    return {
                        "status": "success",
                        "message": f"Clicked on '{element_description}' at ({click_x}, {click_y}).",
                        "x": click_x,
                        "y": click_y
                    }

            return {"status": "warning", "message": f"Could not visually locate '{element_description}'."}
        except Exception as e:
            return {"status": "error", "message": f"Visual click failed: {e}"}

    @staticmethod
    def locate_and_point(element_description: str) -> dict:
        """Uses visual reasoning to locate an element on screen and point the mouse cursor at it."""
        try:
            screenshot_path = ScreenVision.capture_screen()
        except Exception as e:
            return {"status": "error", "message": f"Failed to capture screen: {e}"}

        if not screenshot_path or not os.path.exists(screenshot_path):
            return {"status": "error", "message": "Failed to capture screen."}

        try:
            import google.genai as genai
            import json
            import re

            client = genai.Client(api_key=GEMINI_API_KEY)
            with open(screenshot_path, "rb") as f:
                img_bytes = f.read()

            prompt = (
                f"Locate the UI element described as: '{element_description}'.\n"
                f"Return ONLY a JSON object with normalized coordinates from 0 to 1000:\n"
                f'{{"found": true, "x": 500, "y": 300}}\n'
                f"If not visible, return {{\"found\": false}}"
            )

            resp = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    genai.types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    prompt
                ]
            )

            match = re.search(r"\{.*\}", resp.text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("found"):
                    screen_w, screen_h = ScreenVision.get_screen_dimensions(screenshot_path)
                    target_x = int(screen_w * data["x"] / 1000)
                    target_y = int(screen_h * data["y"] / 1000)
                    mouse_controller.move_to(target_x, target_y)
                    return {
                        "status": "success",
                        "message": f"Pointed mouse at '{element_description}' at ({target_x}, {target_y}).",
                        "x": target_x,
                        "y": target_y
                    }

            return {"status": "warning", "message": f"Could not visually locate '{element_description}'."}
        except Exception as e:
            return {"status": "error", "message": f"Visual pointing failed: {e}"}

screen_vision = ScreenVision()

