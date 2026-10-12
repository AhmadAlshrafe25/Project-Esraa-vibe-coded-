import os
import time
import math
import struct
import wave
import uuid
import subprocess
from pathlib import Path
import speech_recognition as sr
from config.settings import CACHE_DIR, GEMINI_API_KEY

class NativeSpeechRecognizer:
    """Smart Voice Activity Detection (VAD) that dynamically waits until the user finishes speaking."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.chunk_duration = 0.1  # 100ms per frame
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 3200 bytes for 16-bit mono

    def _calculate_rms(self, pcm_data: bytes) -> float:
        """Calculates RMS (energy volume) of raw 16-bit PCM chunk."""
        if not pcm_data or len(pcm_data) < 2:
            return 0.0
        count = len(pcm_data) // 2
        try:
            samples = struct.unpack(f"<{count}h", pcm_data[:count * 2])
            sum_squares = sum(s * s for s in samples)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0.0

    def record_until_finished(self, max_wait_sec: float = 8.0, silence_threshold_sec: float = 1.0) -> str:
        """
        Dynamically records from microphone:
        - Waits for speech to start (up to max_wait_sec).
        - Keeps recording as long as the user speaks.
        - Only stops when user has stopped talking for silence_threshold_sec.
        """
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

        frames = []
        is_speaking = False
        silence_chunks = 0
        max_silence_chunks = int(silence_threshold_sec / self.chunk_duration)
        ambient_energy = 500.0
        calibration_chunks = []

        start_time = time.time()
        max_total_sec = 45.0  # safety cutoff

        try:
            while True:
                chunk = proc.stdout.read(self.chunk_size)
                if not chunk:
                    break

                rms = self._calculate_rms(chunk)

                # Calibrate ambient noise for first 0.3s
                if len(calibration_chunks) < 3:
                    calibration_chunks.append(rms)
                    if len(calibration_chunks) == 3:
                        ambient_energy = max(sum(calibration_chunks) / 3.0, 300.0)
                    continue

                threshold = ambient_energy * 1.5 + 400.0

                if rms > threshold:
                    if not is_speaking:
                        is_speaking = True
                        print("\r\033[1;32m[🎙️ User speaking...]\033[0m            ", end="", flush=True)
                    frames.append(chunk)
                    silence_chunks = 0
                else:
                    if is_speaking:
                        frames.append(chunk)
                        silence_chunks += 1
                        if silence_chunks >= max_silence_chunks:
                            # User stopped talking!
                            break
                    else:
                        # Waiting for speech to begin
                        if time.time() - start_time > max_wait_sec:
                            break

                if time.time() - start_time > max_total_sec:
                    break

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=0.5)
            except Exception:
                proc.kill()

        if not frames or not is_speaking:
            return ""

        # Save to valid WAV file
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(frames))

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using Gemini Audio (crisp & smart) or Google STT fallback."""
        if not audio_path or not os.path.exists(audio_path):
            return ""

        # 1. Primary: Gemini Multimodal Audio (ultra intelligent transcription)
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
                        "Transcribe the spoken words accurately and concisely. Return ONLY the transcription text, with no extra commentary."
                    ]
                )
                if resp and resp.text:
                    clean = resp.text.strip().strip('"').strip("'")
                    return clean
            except Exception as e:
                print(f"\n[STT] Gemini transcription error: {e}")

        # 2. Free Google Speech Recognition fallback
        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self.recognizer.record(source)
                return self.recognizer.recognize_google(audio_data)
        except Exception:
            return ""

stt_engine = NativeSpeechRecognizer()
