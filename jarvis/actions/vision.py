import os
import glob
import time
import subprocess
from pathlib import Path
from PIL import Image

if "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

try:
    import pyautogui
except Exception:
    pyautogui = None

from config.settings import CACHE_DIR, GEMINI_API_KEY

class ScreenVision:
    """Provides Ezra with real-time visual perception of your desktop screen."""

    @staticmethod
    def capture_screen() -> str:
        """Captures a full-resolution screenshot using COSMIC Wayland native screenshot tool or fallbacks."""
        # 1. Native Pop!_OS COSMIC desktop screenshot
        try:
            res = subprocess.run(
                ["cosmic-screenshot", "--interactive=false", "--notify=false", f"--save-dir={CACHE_DIR}"],
                capture_output=True,
                text=True,
                timeout=4.0
            )
            output_path = res.stdout.strip()
            if output_path and os.path.exists(output_path):
                return output_path
            
            # Check recently created screenshots in cache dir
            shots = sorted(glob.glob(str(CACHE_DIR / "Screenshot_*.png")), key=os.path.getmtime)
            if shots and (time.time() - os.path.getmtime(shots[-1])) < 5:
                return shots[-1]
        except Exception:
            pass

        # 2. PyAutoGUI screenshot fallback
        try:
            out_file = CACHE_DIR / f"ezra_screen_{int(time.time())}.png"
            shot = pyautogui.screenshot()
            shot.save(str(out_file))
            return str(out_file)
        except Exception as e:
            raise RuntimeError(f"Could not capture screen: {e}")

    @staticmethod
    def analyze_screen(instruction: str = "Describe what is currently visible on the screen.") -> str:
        """Takes a screenshot and sends it to Gemini 3.5 Flash Vision for visual analysis."""
        if not GEMINI_API_KEY:
            return "Gemini API key is required to analyze the screen visually."

        screenshot_path = ScreenVision.capture_screen()
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
        screenshot_path = ScreenVision.capture_screen()
        if not screenshot_path:
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
                    screen_w, screen_h = pyautogui.size()
                    click_x = int(screen_w * data["x"] / 1000)
                    click_y = int(screen_h * data["y"] / 1000)
                    pyautogui.click(click_x, click_y)
                    return {
                        "status": "success",
                        "message": f"Clicked on '{element_description}' at ({click_x}, {click_y})."
                    }

            return {"status": "warning", "message": f"Could not visually locate '{element_description}'."}
        except Exception as e:
            return {"status": "error", "message": f"Visual click failed: {e}"}

screen_vision = ScreenVision()
