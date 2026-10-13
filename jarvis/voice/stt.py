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
    "thank you.", "thank you", "thanks.", "thanks", "you", "you.",
    "thank you for watching.", "thank you for watching", "thanks for watching",
    "bye.", "bye", "goodbye", "mm", "mm-hmm", "uh", "um", "ah",
    "cough", "laughter", "applause", "music", "[music]", "(music)",
    "huh", "huh.", "oh", "oh.", "so", "so.", "the",
    "<noise>", "[noise]", "(noise)", "noise", "<silence>", "[silence]", "silence"
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
    """Intelligent Voice Activity Detection (VAD) with adaptive noise immunity and ultra-fast Vosk STT."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = 2.0
        self.sample_rate = 16000
        self.chunk_duration = 0.08  # 80ms chunks
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        ensure_hardware_mic_volume()
        self.last_streaming_transcription = ""

        # Initialize ultra-fast offline Vosk model (<5ms streaming decoding)
        self.vosk_model = None
        self.spk_model = None
        self.last_spk_vector = []
        try:
            import vosk
            vosk.SetLogLevel(-1)
            model_giant = Path.home() / ".cache" / "vosk" / "vosk-model-en-us-0.22"
            model_lgraph = Path.home() / ".cache" / "vosk" / "vosk-model-en-us-0.22-lgraph"
            model_small = Path.home() / ".cache" / "vosk" / "vosk-model-small-en-us-0.15"
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
                    self.vosk_model = vosk.Model(lang="en-us")

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

    def record_until_finished(self, max_wait_sec: float = 8.0, silence_threshold_sec: float = 1.6) -> str:
        """
        Dynamically records only genuine human speech with real-time streaming Vosk recognition:
        - True adaptive noise floor: perfectly calibrated to room acoustics (~6500-7500 RMS).
        - Speech threshold: requires vocal energy clearly above steady noise floor.
        - Streams incoming audio directly into Vosk Kaldi recognizer concurrently.
        - Generous silence endpointing: waits for user to truly finish speaking.
        - Idle timeout only starts AFTER worker is calibrated and delivering chunks.
        """
        ensure_hardware_mic_volume()
        self.last_streaming_transcription = ""
        self.last_spk_vector = []
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

        # Wait for worker calibration before we start — don't burn idle timer during warmup
        calib_deadline = time.time() + 8.0
        while not self.worker.calibrated and time.time() < calib_deadline:
            time.sleep(0.05)

        # Drain stale chunks from before listening began (keep 4 chunks = 320ms for pre-buffer)
        self.worker.drain(keep_recent=4)

        vosk_rec = None
        if self.vosk_model:
            try:
                import vosk
                if self.spk_model:
                    vosk_rec = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate, self.spk_model)
                else:
                    vosk_rec = vosk.KaldiRecognizer(self.vosk_model, self.sample_rate)
            except Exception:
                vosk_rec = None

        pre_buffer = deque(maxlen=5)  # 400ms pre-speech ring buffer
        recorded_frames = []
        recognized_segments = []
        is_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        silence_chunks = 0
        max_silence_chunks = max(5, int(silence_threshold_sec / self.chunk_duration))

        # Idle timer starts NOW (after calibration), not when the function was called
        start_time = time.time()
        speech_start_time = 0.0
        max_speech_sec = 30.0  # Allow long utterances — user talks at their own pace

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
                # Speech threshold: adaptive delta above real room acoustics (sensitive & reliable)
                speech_threshold = max(baseline * 1.35, baseline + 250.0)

                # Dynamic audio level meter: scale dynamically so speaking always lights up the bar
                excess = max(0.0, ac_rms - baseline)
                scale_span = max(speech_threshold * 2.0, 1500.0)
                level = min(10, max(0, int((excess / scale_span) * 10)))
                meter_bar = "█" * level + "░" * (10 - level)

                if ac_rms > speech_threshold:
                    consecutive_voice_chunks += 1
                    if consecutive_voice_chunks >= 2 and not is_speaking:
                        is_speaking = True
                        speech_start_time = time.time()
                        buffered_list = list(pre_buffer)
                        recorded_frames.extend(buffered_list)
                        if vosk_rec:
                            for b_chunk in buffered_list:
                                vosk_rec.AcceptWaveform(b_chunk)

                    if is_speaking:
                        print(f"\r\033[1;32m[🎙 Speaking  |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        recorded_frames.append(chunk)
                        speech_chunks_count += 1
                        silence_chunks = 0
                        if vosk_rec:
                            if vosk_rec.AcceptWaveform(chunk):
                                try:
                                    res = json.loads(vosk_rec.Result())
                                    txt = res.get("text", "").strip()
                                    if txt:
                                        recognized_segments.append(txt)
                                except Exception:
                                    pass

                        if time.time() - speech_start_time > max_speech_sec:
                            break
                else:
                    consecutive_voice_chunks = 0
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        print(f"\r\033[1;33m[🎙 Pausing   |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        if vosk_rec:
                            if vosk_rec.AcceptWaveform(chunk):
                                try:
                                    res = json.loads(vosk_rec.Result())
                                    txt = res.get("text", "").strip()
                                    if txt:
                                        recognized_segments.append(txt)
                                except Exception:
                                    pass
                        if silence_chunks >= max_silence_chunks:
                            # Natural end of complete utterance
                            break
                    else:
                        pre_buffer.append(chunk)
                        print(f"\r\033[1;36m[🎙 Listening |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        if time.time() - start_time > max_wait_sec:
                            break

        finally:
            print("\r\033[K", end="", flush=True)

        # Noise Rejection Filter: If user spoke less than 3 chunks (<0.24s), discard as transient noise
        if not recorded_frames or not is_speaking or speech_chunks_count < 3:
            return ""

        # Extract remaining transcription from Vosk
        if vosk_rec:
            try:
                final_res = json.loads(vosk_rec.FinalResult())
                txt = final_res.get("text", "").strip()
                if txt:
                    recognized_segments.append(txt)
            except Exception:
                pass

        recognized_text = " ".join(recognized_segments).strip()
        self.last_streaming_transcription = recognized_text

        # Write clean WAV file for verification/cloud recognition
        pcm_bytes = b"".join(recorded_frames)
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """
        Transcribes audio using high-accuracy open-vocabulary Google STT,
        with ultra-fast local Vosk as instantaneous fallback.
        """
        if not audio_path or not os.path.exists(audio_path):
            return ""

        transcription = ""

        # Tier 1: Cloud Google Speech Recognition (vast vocabulary, highly resilient to accents)
        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self.recognizer.record(source)
                google_text = self.recognizer.recognize_google(audio_data, language="en-US")
                if google_text and len(google_text.strip()) > 1:
                    transcription = google_text.strip()
                    self.last_streaming_transcription = ""
                    return transcription
        except sr.UnknownValueError:
            pass
        except Exception:
            pass

        # Tier 2: Instant Streaming Vosk Result (<5ms)
        if self.last_streaming_transcription:
            transcription = self.last_streaming_transcription
            self.last_streaming_transcription = ""
            return transcription

        # Tier 3: Offline Vosk file pass (<50ms local inference)
        if self.vosk_model:
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
                        transcription = text
            except Exception:
                pass

        if not transcription:
            return ""

        # Filter out noise hallucinations, timestamps, fragments
        clean_lower = transcription.lower().strip()
        if (
            clean_lower in NOISE_PHRASES
            or len(clean_lower) <= 2
            or bool(re.match(r"^[\d\s:\.\-_/]+$", clean_lower))
        ):
            return ""

        return transcription

stt_engine = NativeSpeechRecognizer()
