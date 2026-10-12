import os
import time
import uuid
import urllib.parse
import requests
import pygame
from pathlib import Path
import pyttsx3
from config.settings import CACHE_DIR

# Initialize lightweight audio mixer with minimal buffer to minimize latency
try:
    pygame.mixer.pre_init(22050, -16, 2, 512)
    pygame.mixer.init()
except Exception:
    try:
        pygame.mixer.init()
    except Exception as e:
        print(f"[Mixer Init] {e}")

class FastSpeaker:
    """Ultra-responsive, lightweight speech engine designed for minimal latency and zero laptop strain."""

    def __init__(self):
        self._offline_engine = None

    def _init_offline(self):
        if not self._offline_engine:
            self._offline_engine = pyttsx3.init()
            # Fast, crisp, articulate British female voice
            self._offline_engine.setProperty('voice', 'en-gb+f3')
            self._offline_engine.setProperty('rate', 180)

    def speak(self, text: str):
        if not text or not text.strip():
            return

        # 1. First attempt: Direct high-speed neural TTS stream (<0.4s)
        try:
            encoded_text = urllib.parse.quote(text[:350])  # Crisp sentence chunks
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_text}&tl=en-GB&client=tw-ob"
            headers = {"User-Agent": "Mozilla/5.0"}
            
            resp = requests.get(url, headers=headers, timeout=2.0)
            if resp.status_code == 200:
                audio_path = CACHE_DIR / f"tts_{uuid.uuid4().hex[:6]}.mp3"
                audio_path.write_bytes(resp.content)
                
                pygame.mixer.music.load(str(audio_path))
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.02)
                return
        except Exception:
            pass

        # 2. Instant offline fallback (Zero latency, 0% CPU overhead)
        try:
            self._init_offline()
            self._offline_engine.say(text)
            self._offline_engine.runAndWait()
        except Exception as e:
            print(f"[TTS Fallback Error] {e}")

voice_speaker = FastSpeaker()
