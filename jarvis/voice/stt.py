import os
import re
import time
import math
import struct
import wave
import uuid
import shutil
import json
import threading
import subprocess
from collections import deque
from pathlib import Path
import speech_recognition as sr
import numpy as np
from config.settings import CACHE_DIR, GEMINI_API_KEY

NOISE_PHRASES = {
    "<noise>", "[noise]", "(noise)", "noise", "<silence>", "[silence]", "silence",
    "[music]", "(music)", "music", "[applause]", "applause"
}

def ensure_hardware_mic_volume():
    """Do NOT touch user microphone volume. User has total control over their input level."""
    pass

class AudioStreamWorker:
    """
    Persistent microphone capture worker.
    Keeps `parec` (or fallback `arecord`) running continuously in a background daemon thread.
    - Zero subprocess spawning overhead during conversation turns.
    - High-Pass DC Offset Removal: Eliminates hardware DC bias completely.
    - Adaptive Noise Floor Tracker: Accurately follows real ambient room acoustics.
    - Drains audio buffer while Ezra speaks aloud to prevent self-interruption.
    """

    def __init__(self, sample_rate: int = 16000, chunk_duration: float = 0.08):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        self.running = True
        self.buffer = deque(maxlen=150)
        self.lock = threading.Lock()
        self.ambient_baseline = 250.0
        self.calibrated = False
        self.proc = None
        self._start_capture()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _start_capture(self):
        """Spawns direct PipeWire/PulseAudio capture process with fallback to ALSA."""
        if shutil.which("parec"):
            try:
                self.proc = subprocess.Popen(
                    ["parec", "--rate=16000", "--channels=1", "--format=s16le", "--raw"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass

        self.proc = subprocess.Popen(
            ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

    def _calc_rms_and_clean(self, pcm_data: bytes) -> tuple:
        """
        Subtracts DC hardware bias and calculates true AC acoustic energy (standard deviation).
        Returns (clean_pcm_bytes, ac_rms).
        """
        if not pcm_data or len(pcm_data) < 2:
            return pcm_data, 0.0
        try:
            arr = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
            mean = np.mean(arr)
            centered = arr - mean
            ac_rms = float(np.sqrt(np.mean(centered ** 2)))
            clean_bytes = np.clip(centered, -32768, 32767).astype(np.int16).tobytes()
            return clean_bytes, ac_rms
        except Exception:
            return pcm_data, 0.0

    def _read_exact(self, num_bytes: int) -> bytes:
        """Reads exactly num_bytes from process stdout pipe."""
        chunks = []
        bytes_read = 0
        while bytes_read < num_bytes and self.running:
            try:
                part = self.proc.stdout.read(num_bytes - bytes_read)
                if not part:
                    break
                chunks.append(part)
                bytes_read += len(part)
            except Exception:
                break
        return b"".join(chunks)

    def _capture_loop(self):
        # 1. Warm-up & Calibration: Discard initial 2.0s (25 chunks) of hardware connection transient
        for _ in range(25):
            if not self.running:
                return
            self._read_exact(self.chunk_size)

        # 2. Measure actual steady-state ambient room noise
        calib_ac = []
        for _ in range(12):
            if not self.running:
                return
            raw = self._read_exact(self.chunk_size)
            if not raw:
                break
            _, ac_val = self._calc_rms_and_clean(raw)
            if 10.0 < ac_val < 30000.0:
                calib_ac.append(ac_val)

        if calib_ac:
            self.ambient_baseline = float(np.median(calib_ac))
        if self.ambient_baseline < 50.0:
            self.ambient_baseline = 200.0

        self.calibrated = True

        # 3. Continuous Steady Capture Loop
        while self.running:
            raw = self._read_exact(self.chunk_size)
            if not raw:
                break

            # Check if Ezra is speaking aloud through laptop speakers
            is_ezra_speaking = False
            try:
                from jarvis.voice.speaker import voice_speaker
                is_ezra_speaking = getattr(voice_speaker, "is_speaking", False)
            except Exception:
                pass

            clean_bytes, ac_rms = self._calc_rms_and_clean(raw)

            # If Ezra is speaking aloud, drain buffer so laptop mic doesn't hear her
            if is_ezra_speaking:
                with self.lock:
                    self.buffer.clear()
                continue

            # Update ambient noise baseline continuously (ignoring clipping speech >25000)
            if ac_rms < 25000.0:
                self.ambient_baseline = 0.96 * self.ambient_baseline + 0.04 * ac_rms

            with self.lock:
                self.buffer.append((clean_bytes, ac_rms))

    def get_chunk(self):
        """Pulls oldest available chunk from buffer."""
        with self.lock:
            if self.buffer:
                return self.buffer.popleft()
        return None

    def drain(self, keep_recent: int = 4):
        """Discards older chunks, keeping at most keep_recent chunks as pre-speech buffer."""
        with self.lock:
            while len(self.buffer) > keep_recent:
                self.buffer.popleft()

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=0.2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


class NativeSpeechRecognizer:
    """Intelligent Voice Activity Detection (VAD) with adaptive noise immunity, Whisper neural STT, and Google cloud fallback."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = 8.0
        self.sample_rate = 16000
        self.chunk_duration = 0.08  # 80ms chunks
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        ensure_hardware_mic_volume()
        self.last_streaming_transcription = ""

        # Initialize ultra-fast local Whisper Neural Model (<460ms decoding, slang + Arabic + British English)
        self.whisper_model = None
        try:
            from faster_whisper import WhisperModel
            whisper_dir = Path.home() / ".cache" / "whisper_models" / "tiny"
            if whisper_dir.exists():
                self.whisper_model = WhisperModel(str(whisper_dir), device="cpu", compute_type="int8", cpu_threads=4)
        except Exception:
            self.whisper_model = None

        # Initialize offline Vosk model as secondary local fallback
        self.vosk_model = None
        self.spk_model = None
        self.last_spk_vector = []
        try:
            import vosk
            vosk.SetLogLevel(-1)
            model_giant = Path.home() / ".cache" / "vosk" / "vosk-model-en-us-0.22"
            model_lgraph = Path.home() / ".cache" / "vosk" / "vosk-model-en-us-0.22-lgraph"
            model_small = Path.home() / ".cache" / "vosk" / "vosk-model-small-en-us-0.15"
            spk_path = Path.home() / ".cache" / "vosk" / "vosk-model-spk-0.4"
            if model_giant.exists():
                vosk_path = model_giant
            elif model_lgraph.exists():
                vosk_path = model_lgraph
            else:
                vosk_path = model_small

            # Cleanly suppress Kaldi C++ node check stderr warnings
            old_err = None
            try:
                old_err = os.dup(2)
                devnull = os.open(os.devnull, os.O_WRONLY)
                os.dup2(devnull, 2)
                os.close(devnull)
            except Exception:
                pass

            try:
                if vosk_path.exists():
                    self.vosk_model = vosk.Model(str(vosk_path))
                else:
                    self.vosk_model = None

                if spk_path.exists():
                    self.spk_model = vosk.SpkModel(str(spk_path))
            finally:
                if old_err is not None:
                    try:
                        os.dup2(old_err, 2)
                        os.close(old_err)
                    except Exception:
                        pass
        except Exception:
            self.vosk_model = None
            self.spk_model = None

        # Persistent stream worker: keeps capture device open continuously
        self.worker = AudioStreamWorker(sample_rate=self.sample_rate, chunk_duration=self.chunk_duration)

    def _normalize_transcription(self, text: str) -> str:
        """
        Phonetic auto-correction table & noise/filler rejection:
        - Filters isolated coughs, clicks, and fillers (uh, um, mm, er)
        - Corrects acoustic homophones (Israel -> Ezra, antique gravity -> antigravity)
        - Corrects known desktop & app mishearings (e.g. control my temp -> control my tab)
        - Normalizes Arabic phonetic variants (عزرائيل / اسراء -> عزرا)
        """
        if not text:
            return ""
        t = text.strip()

        # Reject pure filler/noise tokens
        low = t.lower()
        if low in ("uh", "um", "er", "ah", "mm", "mmm", "hmm", "huh", "cough", "click") or low in NOISE_PHRASES:
            return ""

        # Strip leading conversational fillers: 'uh', 'um', 'like', 'so'
        t = re.sub(r"^(?:(?:uh|um|er|ah|mm|like|so|well)\s+)+", "", t, flags=re.IGNORECASE).strip()

        # Homophone corrections: Israel / Isra / Esra / Asra / Azra -> Ezra
        t = re.sub(r"\b(israel|isra|asra|esra|azra|ezrah)\b", "Ezra", t, flags=re.IGNORECASE)
        # Antigravity homophones: antique gravity / anti gravity / the gravity -> antigravity
        t = re.sub(r"\b(antique gravity|anti gravity|the gravity)\b", "antigravity", t, flags=re.IGNORECASE)
        # Arabic phonetic Ezra:
        t = re.sub(r"\b(عزرة|إسراء|اسراء|اسرا|عزرائيل|ابو عزرا|يا عزرا)\b", "عزرا", t)
        # Known desktop control corrections
        t = re.sub(r"\bcontrol my temp\b", "control my tab", t, flags=re.IGNORECASE)
        t = re.sub(r"\byou tube\b", "youtube", t, flags=re.IGNORECASE)
        t = re.sub(r"\bgit hub\b", "github", t, flags=re.IGNORECASE)
        # Fix colloquial "in it" -> "innit"
        t = re.sub(r"\bin it\b", "innit", t, flags=re.IGNORECASE)

        return t.strip()

    def record_until_finished(self, max_wait_sec: float = 15.0, silence_threshold_sec: float = 0.65) -> str:
        """
        Dynamically records human speech with responsive VU metering and snappy silence endpointing:
        - True adaptive noise floor calibrated to room acoustics.
        - Dynamic VU meter: voice energy lights up the bar (████████░░).
        - Snappy endpointing: detects end of utterance within ~650ms of silence.
        - Noise immunity: isolated room ticks do not reset silence countdown.
        """
        ensure_hardware_mic_volume()
        self.last_streaming_transcription = ""
        self.last_spk_vector = []
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

        # Wait for worker calibration before we start listening
        calib_deadline = time.time() + 6.0
        while not self.worker.calibrated and time.time() < calib_deadline:
            time.sleep(0.05)

        # Drain stale audio chunks from before listening began (keep 3 chunks = 240ms pre-buffer)
        self.worker.drain(keep_recent=3)

        pre_buffer = deque(maxlen=4)  # 320ms pre-speech ring buffer
        recorded_frames = []
        is_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        silence_chunks = 0
        max_silence_chunks = max(6, int(silence_threshold_sec / self.chunk_duration))  # ~8 chunks = 640ms

        start_time = time.time()
        speech_start_time = 0.0
        max_speech_sec = 15.0  # Cap maximum continuous utterance to 15s so it never hangs

        try:
            while True:
                item = self.worker.get_chunk()
                if item is None:
                    time.sleep(0.015)
                    if not is_speaking and (time.time() - start_time > max_wait_sec):
                        break
                    continue

                chunk, ac_rms = item
                baseline = self.worker.ambient_baseline
                # Sensitive vocal threshold cleanly above room acoustics
                speech_threshold = max(baseline * 1.25, baseline + 130.0)

                # Dynamic VU Audio Meter: voice dynamically fills the bar
                excess = max(0.0, ac_rms - baseline)
                scale_span = max(baseline * 1.1, 350.0)
                level = min(10, max(0, int((excess / scale_span) * 10)))
                meter_bar = "█" * level + "░" * (10 - level)

                if ac_rms > speech_threshold:
                    consecutive_voice_chunks += 1
                    if consecutive_voice_chunks >= 2 and not is_speaking:
                        is_speaking = True
                        speech_start_time = time.time()
                        recorded_frames.extend(list(pre_buffer))

                    if is_speaking:
                        recorded_frames.append(chunk)
                        speech_chunks_count += 1
                        # Voice confirmed: gently decrement silence accumulator rather than wiping out
                        if consecutive_voice_chunks >= 2:
                            silence_chunks = max(0, silence_chunks - 2)
                        print(f"\r\033[1;32m[🎙 Heard You   |{meter_bar}|]\033[0m\033[K", end="", flush=True)

                        if time.time() - speech_start_time > max_speech_sec:
                            break
                else:
                    consecutive_voice_chunks = 0
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        print(f"\r\033[1;32m[🎙 Heard You   |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        if silence_chunks >= max_silence_chunks:
                            # User naturally finished their sentence!
                            break
                    else:
                        pre_buffer.append(chunk)
                        print(f"\r\033[1;36m[🎙 Listening   |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        if time.time() - start_time > max_wait_sec:
                            break

        finally:
            print("\r\033[K", end="", flush=True)

        # Noise Rejection Filter: If user spoke less than 2 chunks (<0.16s), discard
        if not recorded_frames or not is_speaking or speech_chunks_count < 2:
            return ""

        # Write clean 16000Hz 16-bit PCM WAV file
        pcm_bytes = b"".join(recorded_frames)
        self.last_pcm_bytes = pcm_bytes
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)

        return str(wav_file)

    def get_last_pcm(self) -> bytes:
        """Returns raw PCM byte buffer of the most recent recorded turn."""
        return getattr(self, "last_pcm_bytes", b"")

    def transcribe_audio_file(self, audio_path: str) -> str:
        """
        Ultra-low-latency, multi-lingual transcription:
        1. Local Whisper Neural Model (<460ms on CPU, fluent British English, Slang & Arabic).
        2. Google Cloud Speech Recognition fallback.
        3. Offline Vosk Kaldi fallback.
        """
        if not audio_path or not os.path.exists(audio_path):
            return ""

        raw_transcription = ""

        # Tier 1: Local Whisper Neural Model (<460ms, accurate British English, modern slang & Arabic)
        if self.whisper_model:
            try:
                segments, info = self.whisper_model.transcribe(
                    audio_path,
                    beam_size=1,
                    initial_prompt="Ezra, British English, innit, mate, Arabic العربية"
                )
                whisper_text = " ".join([s.text for s in segments]).strip()
                if whisper_text and len(whisper_text) > 1:
                    raw_transcription = whisper_text
            except Exception:
                pass

        # Tier 2: Cloud Google Speech Recognition Fallback (English / Arabic)
        if not raw_transcription:
            try:
                with sr.AudioFile(audio_path) as source:
                    audio_data = self.recognizer.record(source)
                    # Try English (British/Slang)
                    try:
                        g_en = self.recognizer.recognize_google(audio_data, language="en-GB")
                        if g_en and len(g_en.strip()) > 1:
                            raw_transcription = g_en.strip()
                    except Exception:
                        pass
                    # If English didn't match, try Arabic
                    if not raw_transcription:
                        try:
                            g_ar = self.recognizer.recognize_google(audio_data, language="ar-SA")
                            if g_ar and len(g_ar.strip()) > 1:
                                raw_transcription = g_ar.strip()
                        except Exception:
                            pass
            except Exception:
                pass

        # Tier 3: Offline Vosk file pass fallback
        if not raw_transcription and self.vosk_model:
            try:
                import vosk
                with wave.open(audio_path, "rb") as wf:
                    rec = vosk.KaldiRecognizer(self.vosk_model, wf.getframerate())
                    while True:
                        data = wf.readframes(4000)
                        if not data:
                            break
                        rec.AcceptWaveform(data)
                    file_res = json.loads(rec.FinalResult())
                    text = file_res.get("text", "").strip()
                    if text:
                        raw_transcription = text
            except Exception:
                pass

        if not raw_transcription:
            return ""

        # Phonetic normalization (e.g. Israel -> Ezra, Arabic phonetics -> عزرا, in it -> innit)
        normalized = self._normalize_transcription(raw_transcription)

        # Filter out noise hallucinations, timestamps, fragments
        clean_lower = normalized.lower().strip()
        if (
            clean_lower in NOISE_PHRASES
            or len(clean_lower) <= 1
            or bool(re.match(r"^[\d\s:\.\-_/]+$", clean_lower))
        ):
            return ""

        return normalized

stt_engine = NativeSpeechRecognizer()
