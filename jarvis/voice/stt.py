import os
import time
import math
import struct
import wave
import uuid
import subprocess
from collections import deque
from pathlib import Path
import speech_recognition as sr
from config.settings import CACHE_DIR, GEMINI_API_KEY

class NativeSpeechRecognizer:
    """Smart Voice Activity Detection (VAD) with rolling pre-speech buffer, adaptive energy tracking, and dual-engine STT."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.chunk_duration = 0.08  # 80ms chunks
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        self._ensure_mic_volume()

    def _ensure_mic_volume(self):
        """Ensures system microphone capture volume is at 100% so speech is crisp and never faint."""
        try:
            subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "100%"], capture_output=True)
            subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"], capture_output=True)
        except Exception:
            pass

    def _calculate_rms(self, pcm_data: bytes) -> float:
        """Calculates RMS energy of 16-bit PCM chunk."""
        if not pcm_data or len(pcm_data) < 2:
            return 0.0
        count = len(pcm_data) // 2
        try:
            samples = struct.unpack(f"<{count}h", pcm_data[:count * 2])
            sum_squares = sum(s * s for s in samples)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0.0

    def record_until_finished(self, max_wait_sec: float = 14.0, silence_threshold_sec: float = 1.8) -> str:
        """
        Dynamically records from microphone:
        - 800ms rolling ring buffer ensures the start of words ('Ezra', 'Hey') are never clipped.
        - Adaptive noise tracker prevents the mic from deafening if the user speaks immediately.
        - 1.8s natural pause threshold gives user breathing room to speak comfortably.
        """
        self._ensure_mic_volume()
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

        cmd = [
            "arecord",
            "-D", "default",
            "-f", "S16_LE",
            "-r", str(self.sample_rate),
            "-c", "1",
            "-t", "raw",
            "-q"
        ]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            raise RuntimeError(f"Microphone recording failed: {e}")

        # 800ms rolling pre-speech ring buffer (10 chunks)
        pre_buffer_size = int(0.8 / self.chunk_duration)
        pre_buffer = deque(maxlen=pre_buffer_size)

        recorded_frames = []
        is_speaking = False
        silence_chunks = 0
        max_silence_chunks = int(silence_threshold_sec / self.chunk_duration)

        ambient_baseline = 350.0
        start_time = time.time()
        max_total_sec = 45.0

        try:
            while True:
                chunk = proc.stdout.read(self.chunk_size)
                if not chunk:
                    break

                rms = self._calculate_rms(chunk)

                # Dynamically update ambient baseline ONLY on quiet chunks (never on user voice!)
                if rms < 650.0:
                    ambient_baseline = 0.95 * ambient_baseline + 0.05 * rms

                # Speech threshold dynamically tuned above ambient noise (capped so mic is never deaf)
                speech_threshold = min(max(ambient_baseline * 1.25, 550.0), 900.0)

                # Visual audio level meter
                level = min(10, int(rms / (speech_threshold * 1.5) * 10))
                meter_bar = "█" * level + "░" * (10 - level)

                if rms > speech_threshold:
                    if not is_speaking:
                        is_speaking = True
                        # Include full 800ms pre-buffer so initial words are completely intact
                        recorded_frames.extend(list(pre_buffer))
                    print(f"\r\033[1;32m[🎙️ Speaking |{meter_bar}|]\033[0m   ", end="", flush=True)
                    recorded_frames.append(chunk)
                    silence_chunks = 0
                else:
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        print(f"\r\033[1;33m[🎙️ Pausing |{meter_bar}|]\033[0m    ", end="", flush=True)
                        if silence_chunks >= max_silence_chunks:
                            # User naturally finished speaking their thought
                            break
                    else:
                        pre_buffer.append(chunk)
                        print(f"\r\033[1;35m[🎙️ Listening |{meter_bar}|]\033[0m  ", end="", flush=True)
                        if time.time() - start_time > max_wait_sec:
                            break

                if time.time() - start_time > max_total_sec:
                    break

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=0.2)
            except Exception:
                proc.kill()

        print("\r" + " " * 40 + "\r", end="", flush=True)

        if not recorded_frames or not is_speaking:
            return ""

        # Write clean WAV file
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(recorded_frames))

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using dual-engine approach (Google STT + Gemini Multimodal Audio)."""
        if not audio_path or not os.path.exists(audio_path):
            return ""

        # 1. Primary: High-speed Google Speech Recognition
        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)
                if text and text.strip():
                    return text.strip()
        except Exception:
            pass

        # 2. Secondary: Gemini 3.5 Flash Multimodal Audio
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
                        "Transcribe the spoken audio accurately into text. Return ONLY the transcription text, no preamble or quotes."
                    ]
                )
                if resp and resp.text:
                    clean = resp.text.strip().strip('"').strip("'")
                    if clean and not clean.lower().startswith("thank you for watching"):
                        return clean
            except Exception as e:
                print(f"\n[STT Error]: {e}")

        return ""

stt_engine = NativeSpeechRecognizer()
