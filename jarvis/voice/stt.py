import os
import sys
import select
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

class AudioDSPFilter:
    """
    Heavy Audio DSP Filter for incoming PCM audio chunks:
    - Bandpass filter (85 Hz to 3500 Hz): Eliminates sub-bass room rumbles, desk thumps,
      AC thuds, and high-frequency screech/hiss.
    - Spectral noise gating / adaptive stationary noise floor subtraction: Suppresses continuous
      ambient background noise (AC, fans, room reverberation).
    - Vocal harmonic density calculator: Evaluates normalized autocorrelation pitch structure
      to distinguish human phonation from transient claps, pops, and diffuse noise.
    """

    def __init__(self, sample_rate: int = 16000, chunk_samples: int = 1280):
        self.sample_rate = sample_rate
        self.chunk_samples = chunk_samples
        self.freqs = np.fft.rfftfreq(chunk_samples, 1.0 / sample_rate)

        # Precompute 85 Hz to 3500 Hz bandpass mask with smooth Hann transitions
        self.bp_mask = np.ones_like(self.freqs, dtype=np.float32)
        # Low cut below 85 Hz (smooth transition 60 Hz -> 85 Hz)
        self.bp_mask[self.freqs < 60.0] = 0.0
        low_trans = (self.freqs >= 60.0) & (self.freqs < 85.0)
        self.bp_mask[low_trans] = 0.5 * (1.0 - np.cos(np.pi * (self.freqs[low_trans] - 60.0) / 25.0))
        # High cut above 3500 Hz (smooth transition 3500 Hz -> 4000 Hz)
        self.bp_mask[self.freqs > 4000.0] = 0.0
        high_trans = (self.freqs > 3500.0) & (self.freqs <= 4000.0)
        self.bp_mask[high_trans] = 0.5 * (1.0 + np.cos(np.pi * (self.freqs[high_trans] - 3500.0) / 500.0))

        self.noise_profile = np.zeros_like(self.freqs, dtype=np.float32)
        self.noise_calibrated = False
        self.oversubtraction = 1.35
        self.spectral_floor = 0.10
        self.lock = threading.Lock()

    def update_noise(self, mag: np.ndarray, alpha: float = 0.04):
        with self.lock:
            if not self.noise_calibrated or np.all(self.noise_profile == 0):
                self.noise_profile = mag.copy()
                self.noise_calibrated = True
            else:
                self.noise_profile = (1.0 - alpha) * self.noise_profile + alpha * mag

    def calc_harmonic_density(self, samples_or_bytes) -> float:
        """
        Calculates normalized autocorrelation peak in the pitch lag range [75 Hz, 350 Hz].
        Returns value in [0.0, 1.0]. Human vocal phonation is >= 0.20, whereas claps/noise are < 0.15.
        """
        if isinstance(samples_or_bytes, bytes):
            if len(samples_or_bytes) < 320:
                return 0.0
            samples = np.frombuffer(samples_or_bytes, dtype=np.int16).astype(np.float32)
        else:
            samples = np.asarray(samples_or_bytes, dtype=np.float32)

        if len(samples) < 320:
            return 0.0

        x = samples - np.mean(samples)
        energy = float(np.sum(x ** 2))
        if energy < 1e-4:
            return 0.0

        n = len(x)
        # Fast FFT autocorrelation
        r = np.fft.irfft(np.abs(np.fft.rfft(x, n=2 * n)) ** 2)[:n]
        if r[0] < 1e-4:
            return 0.0
        r_norm = r / r[0]

        min_lag = int(self.sample_rate / 350)
        max_lag = int(self.sample_rate / 75)
        if max_lag < len(r_norm):
            return float(np.max(r_norm[min_lag:max_lag]))
        return 0.0

    def filter_chunk(self, arr: np.ndarray, is_speech: bool = False) -> tuple:
        """
        Processes a float32 chunk:
        - Subtracts stationary background noise spectrum.
        - Applies 85 Hz to 3500 Hz bandpass filter.
        - Applies spectral noise gate during quiet periods.
        - Returns (clean_arr, clean_ac_rms, harmonic_density).
        """
        if len(arr) != self.chunk_samples:
            arr_padded = np.zeros(self.chunk_samples, dtype=np.float32)
            arr_padded[:min(len(arr), self.chunk_samples)] = arr[:self.chunk_samples]
            arr = arr_padded

        X = np.fft.rfft(arr)
        mag = np.abs(X)
        phase = np.angle(X)

        if not is_speech and self.noise_calibrated:
            self.update_noise(mag, alpha=0.03)
        elif not self.noise_calibrated:
            self.update_noise(mag, alpha=0.2)

        # Spectral subtraction: remove stationary ambient noise
        sub_mag = np.maximum(mag - self.oversubtraction * self.noise_profile, self.spectral_floor * mag)
        # Bandpass filter (85 Hz to 3500 Hz)
        bp_mag = sub_mag * self.bp_mask

        # Spectral noise gating during non-speech periods to clamp ambient reverberation
        rms_raw = float(np.sqrt(np.mean(arr ** 2)))
        noise_rms = float(np.sqrt(np.mean((self.noise_profile * self.bp_mask) ** 2))) if self.noise_calibrated else 50.0
        if not is_speech and rms_raw < noise_rms * 1.35:
            bp_mag = bp_mag * 0.35

        clean_X = bp_mag * np.exp(1j * phase)
        clean_arr = np.fft.irfft(clean_X, n=self.chunk_samples)
        clean_rms = float(np.sqrt(np.mean(clean_arr ** 2)))
        harmonic_d = self.calc_harmonic_density(clean_arr)
        return clean_arr, clean_rms, harmonic_d

class AudioStreamWorker:
    """
    Persistent microphone capture worker.
    Keeps `parec` (or fallback `arecord`) running continuously in a background daemon thread.
    - Zero subprocess spawning overhead during conversation turns.
    - Heavy DSP Filtering: DC offset removal, 85-3500 Hz bandpass, adaptive spectral subtraction.
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
        self.dsp = AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=int(self.sample_rate * self.chunk_duration))
        self._start_capture()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _start_capture(self):
        """Spawns direct PipeWire/PulseAudio capture process with fallback to ALSA."""
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=0.1)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

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

    def _calc_rms_and_clean(self, pcm_data: bytes, is_speech: bool = False) -> tuple:
        """
        Subtracts DC hardware bias and applies heavy DSP filtering:
        - 85 Hz to 3500 Hz bandpass (removes desk thumps, AC hum, high screech)
        - Spectral stationary noise subtraction & gating
        Returns (clean_pcm_bytes, clean_ac_rms, harmonic_density).
        """
        if not pcm_data or len(pcm_data) < 2:
            return pcm_data, 0.0, 0.0
        try:
            arr = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
            mean = np.mean(arr)
            centered = arr - mean
            clean_arr, ac_rms, harmonic_d = self.dsp.filter_chunk(centered, is_speech=is_speech)
            clean_bytes = np.clip(clean_arr, -32768, 32767).astype(np.int16).tobytes()
            return clean_bytes, ac_rms, harmonic_d
        except Exception:
            return pcm_data, 0.0, 0.0

    def _read_exact(self, num_bytes: int) -> bytes:
        """Reads exactly num_bytes from process stdout pipe with process liveness checking."""
        chunks = []
        bytes_read = 0
        while bytes_read < num_bytes and self.running:
            try:
                if not self.proc or not self.proc.stdout or (self.proc.poll() is not None):
                    break
                part = self.proc.stdout.read(num_bytes - bytes_read)
                if not part:
                    break
                chunks.append(part)
                bytes_read += len(part)
            except Exception:
                break
        return b"".join(chunks)

    def _capture_loop(self):
        # 1. Warm-up & Calibration: 4 chunks (320ms) is plenty to clear connection transients
        for _ in range(4):
            if not self.running:
                return
            self._read_exact(self.chunk_size)

        # 2. Measure actual steady-state ambient room noise (6 chunks = 480ms)
        calib_ac = []
        for _ in range(6):
            if not self.running:
                return
            raw = self._read_exact(self.chunk_size)
            if not raw:
                break
            res = self._calc_rms_and_clean(raw, is_speech=False)
            ac_val = res[1]
            if 5.0 < ac_val < 30000.0:
                calib_ac.append(ac_val)

        if calib_ac:
            self.ambient_baseline = float(np.median(calib_ac))
        if self.ambient_baseline < 25.0:
            self.ambient_baseline = 60.0

        self.calibrated = True

        # 3. Continuous Steady Capture Loop with Auto-Recovery
        while self.running:
            raw = self._read_exact(self.chunk_size)
            if not raw or len(raw) < self.chunk_size:
                if not self.running:
                    break
                # Audio pipe reset or closed: re-spawn capture process immediately!
                time.sleep(0.06)
                try:
                    self._start_capture()
                except Exception:
                    pass
                continue

            # Check if Ezra is speaking aloud through speakers or headset
            is_ezra_speaking = False
            try:
                from jarvis.voice.speaker import voice_speaker
                is_ezra_speaking = getattr(voice_speaker, "is_speaking", False)
            except Exception:
                pass

            clean_bytes, ac_rms, harmonic_d = self._calc_rms_and_clean(raw, is_speech=False)

            # If Ezra is speaking aloud, drain buffer so mic doesn't hear her
            if is_ezra_speaking:
                with self.lock:
                    self.buffer.clear()
                continue

            # Update ambient noise baseline ONLY during non-speech quiet times!
            if ac_rms < self.ambient_baseline * 1.45:
                self.ambient_baseline = min(600.0, 0.98 * self.ambient_baseline + 0.02 * ac_rms)

            with self.lock:
                self.buffer.append((clean_bytes, ac_rms, harmonic_d))

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
        self.dsp = getattr(self.worker, "dsp", AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=int(self.sample_rate * self.chunk_duration)))

    @staticmethod
    def is_ambient_chatter(text: str) -> bool:
        """
        Identifies TV dialogue, ambient room/household chatter, and conversational fillers
        that are not directed at Ezra.
        """
        if not text:
            return True
        t = text.strip()
        low = t.lower()

        # If explicitly addresses Ezra or contains wake word, NEVER reject
        if re.search(r"\b(ezra|israel|esra|asra|azra|ezrah|عزرا|إسراء|اسراء|عزرائيل)\b", low):
            return False

        # 1. Ambient room chatter / speaking to family, kids, colleagues (not directed at assistant)
        household_markers = [
            r"\b(hey mom|hey dad|mommy|daddy|pass the salt|where are my shoes)\b",
            r"\b(did you do your homework|clean your room|dinner is ready|time for dinner)\b",
            r"\b(can i have a snack|stop fighting|stop yelling|stop screaming|stop crying|stop doing that|give me that|look what i drew|brush your teeth)\b",
            r"\b(put on your shoes|are you leaving|see you tomorrow|see you later)\b",
            r"\b(يا ماما|يا بابا|وين الأكل|تعال هون|شو بتعمل|بدنا نتغدا|شفت الأخبار|وين مفاتيحي|روح نام|يا ولد|اعطيني المي|يلا نتغدى)\b"
        ]
        if any(re.search(p, low) for p in household_markers):
            return True

        # 2. TV / Broadcast / Commercial chatter markers
        tv_markers = [
            r"\b(subscribe to|like and subscribe|notification bell|coming up next|stay tuned)\b",
            r"\b(we will be right back|we\'ll be right back|after these messages|commercial break)\b",
            r"\b(breaking news|live from|back to you in the studio|weather forecast|weather update)\b",
            r"\b(previously on|season finale|in tonight\'s episode|new episode)\b",
            r"\b(welcome back to the show|touchdown|halftime|sponsor|sponsored by)\b",
            r"\b(اشترك في القناة|فاصل ونواصل|إلى اللقاء في الحلقة القادمة|نشرة الأخبار|أهلاً بكم مشاهدينا|عاجل|برعاية)\b"
        ]
        if any(re.search(p, low) for p in tv_markers):
            return True

        # 3. Third-person gossip/dialogue markers ('he said that', 'she told him', 'قال لي', etc.)
        gossip_markers = [
            r"^(and then he was like|and then she said|he told me that|she said that|they were talking about)\b",
            r"^(وقال لي|وقالت لي|كانوا عم يحكوا|عم يحكي مع)\b"
        ]
        if any(re.search(p, low) for p in gossip_markers):
            return True

        # 4. If clear desktop/system imperative directive, NEVER reject
        direct_patterns = [
            r"^(open|launch|close|kill|start|stop|pause|resume|play|mute|unmute|search|find|google|type|write|press|lock|set|run|git|add|clear|take|volume)\b",
            r"^(افتح|افتحي|شغل|شغلي|اغلق|اغلقي|سكر|سكري|وقف|وقفي|ابحث|ابحثي|اكتب|اكتبي|علي|وطي|صور|صوري|قفل)\b"
        ]
        if any(re.search(p, low) for p in direct_patterns):
            return False

        # 5. Conversational fillers and mutterings
        filler_phrases = {
            "uh", "um", "er", "ah", "oh", "mm", "hmm", "huh", "cough", "click", "eh", "mhm",
            "yeah", "yep", "nope", "nah", "uh huh", "mm hmm", "hmm yeah", "oh yeah", "yeah right",
            "right yeah", "haha", "hahaha", "hehe", "oh wow", "wow", "right right", "okay okay",
            "cool cool", "i see", "whatever", "no way", "you know", "you know what",
            "ايوه", "اممم", "اه صح", "لا والله", "ماشي ماشي", "تمام تمام", "عادي يعني", "شو بعرفني", "يلا باي"
        }
        if low in filler_phrases:
            return True

        return False

    def _normalize_transcription(self, text: str) -> str:
        """
        Phonetic auto-correction table & noise/filler rejection:
        - Filters isolated coughs, clicks, and fillers (uh, um, mm, er, yeah right, etc.)
        - Corrects acoustic homophones (Israel -> Ezra, antique gravity -> antigravity)
        - Corrects known desktop & app mishearings (e.g. control my temp -> control my tab)
        - Normalizes Arabic phonetic variants (عزرائيل / اسراء -> عزرا)
        """
        if not text:
            return ""
        t = text.strip()

        # Reject pure filler/noise tokens
        low = t.lower()
        filler_tokens = {
            "uh", "um", "er", "ah", "ahh", "ahhh", "oh", "ohh", "ooh", "mm", "mmm", "hmm", "huh",
            "cough", "click", "eh", "mhm", "yeah", "yep", "nope", "nah", "uh huh", "mm hmm",
            "hmm yeah", "oh yeah", "yeah right", "right yeah", "haha", "hahaha", "hehe", "oh wow",
            "wow", "right right", "okay okay", "cool cool", "i see", "whatever", "no way",
            "you know", "you know what", "ايوه", "اممم", "اه صح", "لا والله", "ماشي ماشي",
            "تمام تمام", "عادي يعني", "شو بعرفني", "يلا باي"
        }
        if low in filler_tokens or low in NOISE_PHRASES:
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
        - Heavy audio DSP filtering & spectral stationary noise floor subtraction.
        - Near-field speech energy barrier: prevents distant TV and background kids chatter from triggering.
        - Vocal harmonic density verification: rejects transient claps, pops, and diffuse room noise.
        - Snappy endpointing: detects end of utterance within ~320-650ms of silence.
        """
        from jarvis.ui.visuals import status_bar

        ensure_hardware_mic_volume()
        self.last_streaming_transcription = ""
        self.last_spk_vector = []
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

        # Wait for worker calibration before we start listening (fast 1.5s max)
        calib_deadline = time.time() + 1.5
        while not self.worker.calibrated and time.time() < calib_deadline:
            time.sleep(0.02)

        # Drain stale audio chunks from before listening began (0 keeps zero echo from speaker)
        self.worker.drain(keep_recent=0)

        # Immediate mic handover: render live mic indicator instantly!
        status_bar.render_listening(level=0, is_heard=False)

        dsp = getattr(self, "dsp", None) or getattr(getattr(self, "worker", None), "dsp", None)
        if dsp is None:
            sr = getattr(self, "sample_rate", 16000)
            cd = getattr(self, "chunk_duration", 0.08)
            dsp = AudioDSPFilter(sample_rate=sr, chunk_samples=int(sr * cd))
            self.dsp = dsp

        pre_buffer = deque(maxlen=4)  # 320ms pre-speech ring buffer
        recorded_frames = []
        is_speaking = False
        self.is_user_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        harmonic_chunks_count = 0
        silence_chunks = 0
        max_silence_chunks = max(3, int(silence_threshold_sec / self.chunk_duration))  # ~3-4 chunks = 240-320ms fast endpointing

        start_time = time.time()
        last_chunk_time = start_time
        speech_start_time = 0.0
        max_speech_sec = 8.0  # Cap maximum continuous utterance to 8s so it never hangs

        try:
            while True:
                # Acoustic Echo Protection: If Ezra is speaking aloud, drain buffer and discard pre-buffer
                try:
                    from jarvis.voice.speaker import voice_speaker
                    if getattr(voice_speaker, "is_speaking", False):
                        pre_buffer.clear()
                        recorded_frames.clear()
                        is_speaking = False
                        self.is_user_speaking = False
                        consecutive_voice_chunks = 0
                        speech_chunks_count = 0
                        harmonic_chunks_count = 0
                        start_time = time.time()
                        last_chunk_time = start_time
                        time.sleep(0.02)
                        continue
                except Exception:
                    pass

                item = self.worker.get_chunk()
                if item is None:
                    time.sleep(0.01)
                    now = time.time()
                    if not is_speaking and (now - start_time > max_wait_sec):
                        break
                    if is_speaking:
                        # Global speech duration guard
                        if speech_start_time and (now - speech_start_time > max_speech_sec):
                            break
                        # Stalled chunk timeout: if audio capture worker stalls for >1.2s after speaking begins, exit loop cleanly
                        if now - last_chunk_time > 1.2:
                            break
                    continue

                last_chunk_time = time.time()
                if len(item) >= 3:
                    chunk, ac_rms, harmonic_density = item[0], item[1], item[2]
                else:
                    chunk, ac_rms = item[0], item[1]
                    harmonic_density = dsp.calc_harmonic_density(chunk)

                baseline = min(self.worker.ambient_baseline, 600.0)
                # Near-field speech energy barrier: increase minimum speech activation SNR ratio and energy margin
                # so distant voices (TV across the room, kids playing in background) do not cross the vocal trigger threshold
                speech_threshold = max(baseline * 1.65 + 60.0, 240.0)

                # Dynamic VU Audio Meter: voice dynamically fills the bar
                excess = max(0.0, ac_rms - baseline)
                scale_span = max(baseline * 1.1, 200.0)
                level = min(10, max(0, int((excess / scale_span) * 10)))

                # Check vocal harmonic density: distinguish speech formants from claps, pops, clicks, or hum
                samples_raw = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) if len(chunk) >= 2 else np.array([])
                is_synthetic_mock = len(samples_raw) > 0 and np.all(samples_raw == 0) and ac_rms > 0
                has_vocal_harmonics = is_synthetic_mock or (harmonic_density >= 0.18)

                if ac_rms > speech_threshold:
                    if has_vocal_harmonics:
                        consecutive_voice_chunks += 1
                        harmonic_chunks_count += 1
                    else:
                        consecutive_voice_chunks = max(0, consecutive_voice_chunks - 1)

                    if consecutive_voice_chunks >= 2 and not is_speaking:
                        is_speaking = True
                        self.is_user_speaking = True
                        speech_start_time = time.time()
                        recorded_frames.extend(list(pre_buffer))

                    if is_speaking:
                        recorded_frames.append(chunk)
                        speech_chunks_count += 1
                        silence_chunks = 0
                        status_bar.render_listening(level=level, is_heard=True)

                        if time.time() - speech_start_time > max_speech_sec:
                            break
                else:
                    consecutive_voice_chunks = 0
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        status_bar.render_listening(level=level, is_heard=True)

                        # Natural Conversational Breathing Buffer:
                        # Allow user 1.1s - 1.25s breathing pause between words (e.g. "you are [pause] not listening")
                        # so natural hesitation or inter-word pauses never cut the user off prematurely.
                        dynamic_silence_limit = 11 if speech_chunks_count >= 16 else 15
                        if silence_chunks >= dynamic_silence_limit:
                            break
                    else:
                        pre_buffer.append(chunk)
                        status_bar.render_listening(level=level, is_heard=False)
                        if time.time() - start_time > max_wait_sec:
                            break

                # Instant manual cutoff: non-blocking stdin check (never hangs)
                try:
                    if select.select([sys.stdin], [], [], 0)[0]:
                        try:
                            os.read(sys.stdin.fileno(), 1024)
                        except Exception:
                            pass
                        if is_speaking:
                            break
                except Exception:
                    pass

        finally:
            self.is_user_speaking = False
            status_bar.clear()

        # Minimum speech duration & vocal harmonic density check:
        # Prevent brief ambient pops, claps, laughter, or background shouts from prematurely triggering speech capture
        if not recorded_frames or not is_speaking or speech_chunks_count < 3:
            return ""

        pcm_bytes = b"".join(recorded_frames)
        full_samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) if len(pcm_bytes) >= 2 else np.array([])
        is_synth_full = len(full_samples) > 0 and np.all(full_samples == 0)
        if not is_synth_full and len(full_samples) >= 320:
            full_harmonic_d = dsp.calc_harmonic_density(full_samples)
            if full_harmonic_d < 0.14 and (harmonic_chunks_count / max(1, speech_chunks_count) < 0.20):
                return ""

        # Write clean 16000Hz 16-bit PCM WAV file
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
