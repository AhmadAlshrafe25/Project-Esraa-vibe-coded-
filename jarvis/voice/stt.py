import os
import subprocess
import shutil
import uuid
from pathlib import Path
import speech_recognition as sr
from config.settings import CACHE_DIR, GEMINI_API_KEY

class NativeSpeechRecognizer:
    """Captures microphone audio directly using Linux audio subsystem and transcribes it for free."""
    
    def __init__(self):
        self.recognizer = sr.Recognizer()

    def record_mic_audio(self, duration_sec: int = 4) -> str:
        """Records from hardware microphone to a WAV file using system arecord."""
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"
        
        # arecord: Linux ALSA / PulseAudio native recorder
        cmd = [
            "arecord",
            "-D", "default",
            "-d", str(duration_sec),
            "-f", "cd",
            "-t", "wav",
            "-q",
            str(wav_file)
        ]
        
        try:
            subprocess.run(cmd, check=True)
            return str(wav_file)
        except Exception as e:
            # Fallback to parec / sox if arecord fails
            raise RuntimeError(f"Microphone capture error: {e}")

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using free Google Speech Recognition or Gemini Audio."""
        # 1. Try Gemini 2.0 / 3.5 Flash Multimodal Audio (Best accuracy)
        if GEMINI_API_KEY:
            try:
                import google.genai as genai
                client = genai.Client(api_key=GEMINI_API_KEY)
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                
                resp = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=[
                        genai.types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                        "Transcribe the spoken words accurately and concisely. Return only the transcription without comments or quotes."
                    ]
                )
                if resp and resp.text:
                    return resp.text.strip()
            except Exception as e:
                print(f"[STT] Gemini audio transcription error: {e}")

        # 2. Free Google Speech Recognition fallback (No key required)
        with sr.AudioFile(audio_path) as source:
            audio_data = self.recognizer.record(source)
            try:
                text = self.recognizer.recognize_google(audio_data)
                return text
            except sr.UnknownValueError:
                return ""
            except Exception as e:
                print(f"[STT] Google STT fallback error: {e}")
                return ""

stt_engine = NativeSpeechRecognizer()
