import os
import re
import time
import math
import struct
import wave
import uuid
import shutil
import subprocess
from collections import deque
from pathlib import Path
import speech_recognition as sr
from config.settings import CACHE_DIR, GEMINI_API_KEY

NOISE_PHRASES = {
    "thank you.", "thank you", "thanks.", "thanks", "you", "you.",
    "thank you for watching.", "thank you for watching", "thanks for watching",
    "bye.", "bye", "goodbye", "mm", "mm-hmm", "uh", "um", "ah",
    "cough", "laughter", "applause", "music", "[music]", "(music)"
}

class NativeSpeechRecognizer:
    """Intelligent Voice Activity Detection (VAD) with noise immunity, human voice gating, and dual-engine STT."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.chunk_duration = 0.08  # 80ms chunks
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        self._ensure_mic_volume()

    def _ensure_mic_volume(self):
        """Sets microphone to balanced 60% capture volume so speech is clear without clipping or excessive background hiss."""
        try:
            subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "60%"], capture_output=True)
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

    def _spawn_capture_process(self):
        """Spawns direct PipeWire/PulseAudio capture process with fallback to ALSA."""
        if shutil.which("parec"):
            try:
                return subprocess.Popen(
                    ["parec", "--rate=16000", "--channels=1", "--format=s16le", "--raw"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
            except Exception:
                pass

        return subprocess.Popen(
            ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

    def record_until_finished(self, max_wait_sec: float = 14.0, silence_threshold_sec: float = 1.8) -> str:
        """
        Dynamically records only genuine human speech:
        - Rejects random clicks, keyboard taps, fan noise, and breathing.
        - Requires consecutive vocal frames (160ms) before activating.
        - Discards sub-second noise spikes so Ezra is never confused by room artifacts.
        """
        self._ensure_mic_volume()
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

        try:
            proc = self._spawn_capture_process()
        except Exception as e:
            raise RuntimeError(f"Microphone recording failed: {e}")

        # 800ms rolling pre-speech ring buffer
        pre_buffer_size = int(0.8 / self.chunk_duration)
        pre_buffer = deque(maxlen=pre_buffer_size)

        recorded_frames = []
        is_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        silence_chunks = 0
        max_silence_chunks = int(silence_threshold_sec / self.chunk_duration)

        ambient_baseline = 400.0
        start_time = time.time()
        max_total_sec = 45.0

        try:
            while True:
                chunk = proc.stdout.read(self.chunk_size)
                if not chunk:
                    break

                rms = self._calculate_rms(chunk)

                # Track ambient baseline only on quiet chunks
                if rms < 800.0:
                    ambient_baseline = 0.95 * ambient_baseline + 0.05 * rms

                # Strict speech threshold (rejects room hum, keyboard taps, and breaths)
                speech_threshold = max(ambient_baseline * 2.0, 1600.0)

                # Audio level meter
                level = min(10, int(rms / (speech_threshold * 1.5) * 10))
                meter_bar = "█" * level + "░" * (10 - level)

                if rms > speech_threshold:
                    consecutive_voice_chunks += 1

                    # Debounce: Require at least 2 consecutive chunks (160ms) of human vocal energy
                    if consecutive_voice_chunks >= 2 and not is_speaking:
                        is_speaking = True
                        recorded_frames.extend(list(pre_buffer))

                    if is_speaking:
                        print(f"\r\033[1;32m[🎙️ Speaking |{meter_bar}|]\033[0m   ", end="", flush=True)
                        recorded_frames.append(chunk)
                        speech_chunks_count += 1
                        silence_chunks = 0
                else:
                    consecutive_voice_chunks = 0
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        print(f"\r\033[1;33m[🎙️ Pausing |{meter_bar}|]\033[0m    ", end="", flush=True)
                        if silence_chunks >= max_silence_chunks:
                            # Natural end of spoken command
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

        # Noise Rejection Filter: If total speech was less than 5 chunks (<0.4s), discard as transient click/noise!
        if not recorded_frames or not is_speaking or speech_chunks_count < 5:
            return ""

        # Write clean WAV file
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b"".join(recorded_frames))

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using dual-engine approach with noise hallucination filter."""
        if not audio_path or not os.path.exists(audio_path):
            return ""

        transcription = ""

        # 1. Primary: High-speed Google Speech Recognition
        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_google(audio_data)
                if text and text.strip():
                    transcription = text.strip()
        except Exception:
            pass

        # 2. Secondary: Gemini 3.5 Flash Multimodal Audio
        if not transcription and GEMINI_API_KEY:
            try:
                import google.genai as genai
                client = genai.Client(api_key=GEMINI_API_KEY)
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()

                resp = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=[
                        genai.types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                        "Transcribe the spoken audio accurately into text. If the audio is silent or only background noise, return nothing. Return ONLY the transcription text, no preamble or quotes."
                    ]
                )
                if resp and resp.text:
                    transcription = resp.text.strip().strip('"').strip("'")
            except Exception as e:
                print(f"\n[STT Error]: {e}")

        if not transcription:
            return ""

        # Filter out random background noise hallucinations, timestamps, and fragments
        clean_lower = transcription.lower().strip()
        if (
            clean_lower in NOISE_PHRASES
            or len(clean_lower) <= 2
            or bool(re.match(r"^[\d\s:\.\-_/]+$", clean_lower))
        ):
            return ""

        return transcription

stt_engine = NativeSpeechRecognizer()
