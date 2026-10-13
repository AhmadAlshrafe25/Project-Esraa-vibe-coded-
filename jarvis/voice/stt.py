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

class AudioStreamWorker:
    """
    Persistent microphone capture worker.
    Keeps `parec` (or fallback `arecord`) running continuously in a background daemon thread.
    - Zero subprocess spawning overhead during conversation turns.
    - Discards the 1.5s Linux PipeWire/ALSA hardware DC offset & AGC volume surge ONCE during startup.
    - Continuously tracks ambient noise baseline (~6500-7500 RMS) smoothly in steady-state.
    - Drains audio buffer while Ezra speaks aloud to prevent self-interruption and feedback loops.
    """

    def __init__(self, sample_rate: int = 16000, chunk_duration: float = 0.08):
        self.sample_rate = sample_rate
        self.chunk_duration = chunk_duration
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        self.running = True
        self.buffer = deque(maxlen=150)
        self.lock = threading.Lock()
        self.ambient_baseline = 7500.0
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

    def _calc_rms(self, pcm_data: bytes) -> float:
        if not pcm_data or len(pcm_data) < 2:
            return 0.0
        count = len(pcm_data) // 2
        try:
            samples = struct.unpack(f"<{count}h", pcm_data[:count * 2])
            sum_squares = sum(s * s for s in samples)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0.0

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
        # 1. Warm-up & Calibration: Discard initial 1.5 seconds of DC offset and AGC surge
        warm_samples = []
        for _ in range(18):
            if not self.running:
                return
            data = self._read_exact(self.chunk_size)
            if not data:
                break
            rms = self._calc_rms(data)
            if 1000.0 < rms < 20000.0:
                warm_samples.append(rms)

        if warm_samples:
            self.ambient_baseline = float(np.median(warm_samples))
        if self.ambient_baseline < 1000.0:
            self.ambient_baseline = 7500.0

        self.calibrated = True

        # 2. Continuous Capture Loop
        while self.running:
            data = self._read_exact(self.chunk_size)
            if not data:
                break

            # Check if Ezra is speaking aloud through laptop speakers
            is_ezra_speaking = False
            try:
                from jarvis.voice.speaker import voice_speaker
                is_ezra_speaking = getattr(voice_speaker, "is_speaking", False)
            except Exception:
                pass

            rms = self._calc_rms(data)

            # If Ezra is speaking aloud, drain buffer so laptop mic doesn't hear her
            if is_ezra_speaking:
                with self.lock:
                    self.buffer.clear()
                continue

            # Update ambient noise baseline continuously (only on steady audio <30000)
            if rms < 30000.0:
                self.ambient_baseline = 0.96 * self.ambient_baseline + 0.04 * rms

            with self.lock:
                self.buffer.append((data, rms))

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
    """Intelligent Voice Activity Detection (VAD) with persistent capture worker and ultra-fast Vosk STT."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = 2.0
        self.sample_rate = 16000
        self.chunk_duration = 0.08  # 80ms chunks
        self.chunk_size = int(self.sample_rate * self.chunk_duration * 2)  # 2560 bytes
        self._ensure_mic_volume()
        self.last_streaming_transcription = ""

        # Initialize ultra-fast offline Vosk model (<5ms streaming decoding)
        self.vosk_model = None
        self.spk_model = None
        self.last_spk_vector = []
        try:
            import vosk
            vosk.SetLogLevel(-1)
            vosk_path = Path.home() / ".cache" / "vosk" / "vosk-model-small-en-us-0.15"
            spk_path = Path.home() / ".cache" / "vosk" / "vosk-model-spk-0.4"
            if vosk_path.exists():
                self.vosk_model = vosk.Model(str(vosk_path))
            else:
                self.vosk_model = vosk.Model(lang="en-us")

            if spk_path.exists():
                self.spk_model = vosk.SpkModel(str(spk_path))
        except Exception:
            self.vosk_model = None
            self.spk_model = None

        # Persistent stream worker: keeps capture device open continuously
        self.worker = AudioStreamWorker(sample_rate=self.sample_rate, chunk_duration=self.chunk_duration)

    def _ensure_mic_volume(self):
        """Sets microphone to balanced 60% capture volume so speech is clear without clipping or excessive background hiss."""
        try:
            subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "60%"], capture_output=True)
            subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"], capture_output=True)
        except Exception:
            pass

    def record_until_finished(self, max_wait_sec: float = 8.0, silence_threshold_sec: float = 0.50) -> str:
        """
        Dynamically records only genuine human speech with real-time streaming Vosk recognition:
        - Persistent audio stream: zero startup transient or DC pop!
        - Instant silence cut-off: 0.50s trigger when user stops speaking.
        - Streams incoming audio directly into Vosk Kaldi recognizer concurrently.
        - Maximum speech safety cutoff: caps continuous speech at 6.0s.
        """
        self._ensure_mic_volume()
        self.last_streaming_transcription = ""
        self.last_spk_vector = []
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

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
        is_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        silence_chunks = 0
        max_silence_chunks = max(3, int(silence_threshold_sec / self.chunk_duration))

        start_time = time.time()
        speech_start_time = 0.0
        max_speech_sec = 6.0

        try:
            while True:
                item = self.worker.get_chunk()
                if item is None:
                    time.sleep(0.015)
                    if not is_speaking and (time.time() - start_time > max_wait_sec):
                        break
                    continue

                chunk, rms = item
                baseline = self.worker.ambient_baseline
                speech_threshold = max(baseline * 1.55, baseline + 4000.0)

                # Dynamic audio level meter
                excess = max(0.0, rms - baseline)
                scale_span = max(speech_threshold - baseline, 4000.0)
                level = min(10, max(0, int((excess / scale_span) * 10)))
                meter_bar = "█" * level + "░" * (10 - level)

                if rms > speech_threshold:
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
                                # Kaldi detected natural sentence end
                                break

                        if time.time() - speech_start_time > max_speech_sec:
                            break
                else:
                    consecutive_voice_chunks = 0
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        print(f"\r\033[1;33m[🎙 Pausing   |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        if vosk_rec:
                            vosk_rec.AcceptWaveform(chunk)
                        if silence_chunks >= max_silence_chunks:
                            # Sub-second silence trigger
                            break
                    else:
                        pre_buffer.append(chunk)
                        print(f"\r\033[1;36m[🎙 Listening |{meter_bar}|]\033[0m\033[K", end="", flush=True)
                        if time.time() - start_time > max_wait_sec:
                            break

                if time.time() - start_time > 12.0:
                    break

        finally:
            print("\r\033[K", end="", flush=True)

        # Noise Rejection Filter: If user spoke less than 4 chunks (<0.32s), discard as transient click/noise
        if not recorded_frames or not is_speaking or speech_chunks_count < 4:
            return ""

        # Extract near-instant in-memory streaming transcription & speaker vector from Vosk (<5ms)
        recognized_text = ""
        spk_vector = []
        if vosk_rec:
            try:
                final_res = json.loads(vosk_rec.FinalResult())
                recognized_text = final_res.get("text", "").strip()
                spk_vector = final_res.get("spk", [])
                self.last_spk_vector = spk_vector
            except Exception:
                pass

        # If Vosk heard no words, it was not human speech
        if not recognized_text:
            return ""

        # Biomarker / Voice Genetic Gate check:
        # Rejects random background voices, family/room chatter, and TV!
        from jarvis.voice.biometrics import voice_dna
        pcm_bytes = b"".join(recorded_frames)
        if voice_dna.is_enrolled() and spk_vector and len(spk_vector) >= 10:
            is_verified, score, reason = voice_dna.verify(spk_vector, pcm_data=pcm_bytes)
            if not is_verified:
                print(f"\r\033[1;31m[🛡️ Voice Gate: Ignored background speaker (Genetic match: {score:.1%}, required: {voice_dna.get_threshold():.0%})]\033[0m\n")
                self.last_streaming_transcription = ""
                self.last_spk_vector = []
                return ""
            else:
                print(f"\r\033[1;32m[🧬 Voice Genetic Match: {score:.1%} | Verified {voice_dna.get_user_name()}]\033[0m\n")

        self.last_streaming_transcription = recognized_text

        # Write clean WAV file for verification/fallback/enrollment
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using ultra-fast local Vosk engine (<5ms)."""
        # Tier 1: Instant Streaming Vosk Result (0ms - decoded concurrently while user spoke)
        if self.last_streaming_transcription:
            transcription = self.last_streaming_transcription
            self.last_streaming_transcription = ""
            return transcription

        if not audio_path or not os.path.exists(audio_path):
            return ""

        transcription = ""

        # Tier 2: Offline Vosk file pass (<50ms local inference)
        if self.vosk_model:
            try:
                import vosk
                from jarvis.voice.biometrics import voice_dna
                with wave.open(audio_path, "rb") as wf:
                    if self.spk_model:
                        rec = vosk.KaldiRecognizer(self.vosk_model, wf.getframerate(), self.spk_model)
                    else:
                        rec = vosk.KaldiRecognizer(self.vosk_model, wf.getframerate())
                    while True:
                        data = wf.readframes(4000)
                        if not data:
                            break
                        rec.AcceptWaveform(data)
                    file_res = json.loads(rec.FinalResult())
                    text = file_res.get("text", "").strip()
                    spk = file_res.get("spk", [])
                    if voice_dna.is_enrolled() and spk and len(spk) >= 10:
                        is_ok, score, _ = voice_dna.verify(spk)
                        if not is_ok:
                            print(f"\r\033[1;31m[🛡️ Voice Gate: Ignored background speaker (match: {score:.1%})]\033[0m\n")
                            return ""
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
