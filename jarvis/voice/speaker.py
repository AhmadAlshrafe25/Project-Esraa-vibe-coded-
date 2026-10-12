import os
import time
import uuid
import asyncio
import edge_tts
import requests
import urllib.parse
import pygame
from pathlib import Path
import pyttsx3
from config.settings import CACHE_DIR

# Initialize lightweight audio mixer
try:
    pygame.mixer.pre_init(24000, -16, 2, 512)
    pygame.mixer.init()
except Exception:
    try:
        pygame.mixer.init()
    except Exception as e:
        print(f"[Mixer Init] {e}")

class SmoothSpeaker:
    """Delivers silky smooth, natural human neural voice with zero robotic artifacts."""

    def __init__(self, voice: str = "en-GB-SoniaNeural"):
        self.voice = voice  # Smooth British neural female voice (Sonia)
        self.fallback_voice = "en-US-JennyNeural"
        self._offline_engine = None
        self.is_muted: bool = False

    def set_muted(self, muted: bool):
        """Sets mute state. When True, Ezra outputs purely text without speaking aloud."""
        self.is_muted = bool(muted)

    def toggle_mute(self) -> bool:
        """Toggles between voice speech and silent mode."""
        self.is_muted = not self.is_muted
        return self.is_muted

    def _init_offline(self):
        if not self._offline_engine:
            self._offline_engine = pyttsx3.init()
            self._offline_engine.setProperty('voice', 'en-gb+f3')
            self._offline_engine.setProperty('rate', 175)

    def _play_file(self, audio_path: str):
        try:
            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.02)
        except Exception as e:
            print(f"[Playback Error] {e}")

    async def _generate_edge_speech(self, text: str, voice_name: str) -> str:
        out_path = CACHE_DIR / f"smooth_{uuid.uuid4().hex[:6]}.mp3"
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate="+5%",
            pitch="+0Hz"
        )
        await communicate.save(str(out_path))
        return str(out_path)

    def speak(self, text: str):
        """Speaks with smooth, human neural voice directly through laptop speakers."""
        if self.is_muted or not text or not text.strip():
            return

        clean_text = text.strip()[:400]

        # 1. Primary: Silky Smooth Neural Voice via Edge-TTS
        for v in [self.voice, self.fallback_voice]:
            try:
                loop = asyncio.new_event_loop()
                audio_file = loop.run_until_complete(
                    asyncio.wait_for(self._generate_edge_speech(clean_text, v), timeout=3.0)
                )
                loop.close()
                if audio_file and os.path.exists(audio_file):
                    self._play_file(audio_file)
                    return
            except Exception:
                continue

        # 2. Secondary smooth fallback (Google TTS)
        try:
            encoded_text = urllib.parse.quote(clean_text[:250])
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_text}&tl=en-GB&client=tw-ob"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.0)
            if resp.status_code == 200:
                audio_path = CACHE_DIR / f"tts_{uuid.uuid4().hex[:6]}.mp3"
                audio_path.write_bytes(resp.content)
                self._play_file(str(audio_path))
                return
        except Exception:
            pass

        # 3. Offline fallback
        try:
            self._init_offline()
            self._offline_engine.say(clean_text)
            self._offline_engine.runAndWait()
        except Exception as e:
            print(f"[TTS Fallback Error] {e}")

voice_speaker = SmoothSpeaker()
