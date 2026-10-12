import asyncio
import os
import uuid
from pathlib import Path
import edge_tts
from config.settings import DEFAULT_VOICE, VOICE_RATE, VOICE_PITCH, CACHE_DIR

# Available high quality female voices (Free neural voices)
FEMALE_VOICES = {
    "british": "en-GB-SoniaNeural",       # Polite, intelligent, British JARVIS style
    "american_aria": "en-US-AriaNeural",  # Expressive, crisp American female
    "american_jenny": "en-US-JennyNeural",# Friendly, conversational
    "arabic_salma": "ar-EG-SalmaNeural",  # Egyptian Arabic female
    "arabic_zariyah": "ar-SA-ZariyahNeural" # Saudi Arabic female
}

class VoiceEngine:
    def __init__(self, voice: str = DEFAULT_VOICE, rate: str = VOICE_RATE, pitch: str = VOICE_PITCH):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def set_voice(self, voice_key_or_name: str):
        if voice_key_or_name in FEMALE_VOICES:
            self.voice = FEMALE_VOICES[voice_key_or_name]
        else:
            self.voice = voice_key_or_name

    async def generate_speech_file(self, text: str, output_path: str = None) -> str:
        """Generates an MP3 file with neural female voice without needing any API key."""
        if not output_path:
            filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
            output_path = str(CACHE_DIR / filename)

        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch
        )
        await communicate.save(output_path)
        return output_path

    async def speak_text_bytes(self, text: str) -> bytes:
        """Returns the raw MP3 audio bytes directly for web streaming."""
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch
        )
        audio_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.extend(chunk["data"])
        return bytes(audio_data)

# Singleton instance
voice_service = VoiceEngine()
