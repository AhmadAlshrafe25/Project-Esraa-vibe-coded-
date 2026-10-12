import os
import time
import uuid
import pygame
from pathlib import Path
from gtts import gTTS
import pyttsx3
from config.settings import CACHE_DIR

# Initialize pygame mixer once
try:
    pygame.mixer.init()
except Exception as e:
    print(f"[Audio Mixer Init] {e}")

class VoiceSpeaker:
    """Crisp, 100% free female voice speaker that plays audio directly through local speakers."""
    
    def __init__(self):
        self.tld = "co.uk"  # British accent English
        self._offline_engine = None

    def _get_offline_engine(self):
        if not self._offline_engine:
            self._offline_engine = pyttsx3.init()
            # Set female voice if available in system
            voices = self._offline_engine.getProperty('voices')
            for v in voices:
                if "female" in v.name.lower() or "girl" in v.name.lower():
                    self._offline_engine.setProperty('voice', v.id)
                    break
            self._offline_engine.setProperty('rate', 170)
        return self._offline_engine

    def speak(self, text: str):
        """Generates speech and immediately plays it out loud on your local machine."""
        if not text or not text.strip():
            return
            
        print(f"\n[Project Esraa Speaking]: \"{text}\"\n")
        
        # 1. Try crisp British female voice (gTTS with co.uk top-level domain)
        try:
            mp3_path = CACHE_DIR / f"speech_{uuid.uuid4().hex[:8]}.mp3"
            tts = gTTS(text=text, lang="en", tld=self.tld, slow=False)
            tts.save(str(mp3_path))
            
            # Play through local machine speakers using pygame
            pygame.mixer.music.load(str(mp3_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            return
        except Exception as e:
            print(f"[Voice Online Fallback]: {e}")

        # 2. Offline fallback (pyttsx3 local system voice)
        try:
            eng = self._get_offline_engine()
            eng.say(text)
            eng.runAndWait()
        except Exception as e:
            print(f"[Voice Offline Fallback]: {e}")

voice_speaker = VoiceSpeaker()
