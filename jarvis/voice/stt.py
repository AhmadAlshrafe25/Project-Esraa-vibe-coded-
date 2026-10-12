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
    """Smart Voice Activity Detection (VAD) with rolling pre-speech buffer and live audio meter."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.chunk_duration = 0.08  # 80ms chunks for rapid response
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes for 16-bit mono
        self._ensure_mic_volume()

    def _ensure_mic_volume(self):
        """Ensures system microphone capture volume is at least 80% so speech is clear."""
        try:
            subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "85%"], capture_output=True)
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

    def record_until_finished(self, max_wait_sec: float = 12.0, silence_threshold_sec: float = 1.2) -> str:
        """
        Dynamically records from microphone:
        - Maintains a rolling pre-speech ring buffer so beginning of words are NEVER missed.
        - Shows a live audio meter so user sees their mic working in real time.
        - Continues recording until the user naturally finishes speaking.
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

        # Rolling buffer holds 0.4s of pre-speech audio
        pre_buffer_size = int(0.4 / self.chunk_duration)
        pre_buffer = deque(maxlen=pre_buffer_size)

        recorded_frames = []
        is_speaking = False
        silence_chunks = 0
        max_silence_chunks = int(silence_threshold_sec / self.chunk_duration)
        
        # Adaptive ambient energy
        ambient_baseline = 400.0
        calibration = []
        start_time = time.time()
        max_total_sec = 40.0

        try:
            while True:
                chunk = proc.stdout.read(self.chunk_size)
                if not chunk:
                    break

                rms = self._calculate_rms(chunk)

                # Calibrate first 0.24s (3 chunks)
                if len(calibration) < 3:
                    calibration.append(rms)
                    if len(calibration) == 3:
                        ambient_baseline = sum(calibration) / 3.0
                    continue

                # Speech threshold dynamically tuned above ambient noise
                threshold = max(ambient_baseline * 1.3, 500.0)

                # Visual meter (bars)
                level = min(10, int(rms / (threshold * 1.5) * 10))
                meter_bar = "█" * level + "░" * (10 - level)

                if rms > threshold:
                    if not is_speaking:
                        is_speaking = True
                        # Include pre-speech buffer so initial syllables are intact!
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
                            # User finished their thought
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
                proc.wait(timeout=0.3)
            except Exception:
                proc.kill()

        print("\r" + " " * 40 + "\r", end="", flush=True)

        if not recorded_frames or not is_speaking:
            return ""

        # Write valid WAV file
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(recorded_frames))

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using Gemini Multimodal Audio or Google STT fallback."""
        if not audio_path or not os.path.exists(audio_path):
            return ""

        # 1. Primary: Gemini 3.5 Flash Multimodal Audio
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
                    return clean
            except Exception as e:
                print(f"\n[STT Gemini fallback to Google]: {e}")

        # 2. Free Google Speech Recognition fallback
        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self.recognizer.record(source)
                return self.recognizer.recognize_google(audio_data)
        except Exception:
            return ""

stt_engine = NativeSpeechRecognizer()
