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

from jarvis.voice.local_tts import LocalNeuralTTS

class VoiceEngine:
    def __init__(self, voice: str = DEFAULT_VOICE, rate: str = VOICE_RATE, pitch: str = VOICE_PITCH):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self._local_tts = LocalNeuralTTS()

    def set_voice(self, voice_key_or_name: str):
        if voice_key_or_name in FEMALE_VOICES:
            self.voice = FEMALE_VOICES[voice_key_or_name]
        else:
            self.voice = voice_key_or_name

    async def generate_speech_file(self, text: str, output_path: str = None) -> str:
        """Generates an audio file with local neural female voice (Kokoro/Piper) with fallback."""
        if not output_path:
            ext = ".wav"
            filename = f"tts_{uuid.uuid4().hex[:8]}{ext}"
            output_path = str(CACHE_DIR / filename)

        # Tier 1: Local Neural TTS (Kokoro-82M / Piper Arabic - 100% offline)
        try:
            pcm_bytes, sr = await asyncio.to_thread(self._local_tts.synthesize_to_pcm, text)
            if pcm_bytes:
                import io, wave
                with wave.open(output_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    wf.writeframes(pcm_bytes)
                return output_path
        except Exception:
            pass

        # Tier 2: Edge-TTS fallback
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch
            )
            await communicate.save(output_path)
            return output_path
        except Exception:
            pass

        return output_path

    async def speak_text_bytes(self, text: str) -> bytes:
        """Returns raw audio bytes directly for web streaming or playback."""
        # Tier 1: Local Neural TTS
        try:
            pcm_bytes, sr = await asyncio.to_thread(self._local_tts.synthesize_to_pcm, text)
            if pcm_bytes:
                import io, wave
                buf = io.BytesIO()
                with wave.open(buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sr)
                    wf.writeframes(pcm_bytes)
                return buf.getvalue()
        except Exception:
            pass

        # Tier 2: Edge-TTS fallback
        try:
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
        except Exception:
            return b""

# Singleton instance
voice_service = VoiceEngine()
