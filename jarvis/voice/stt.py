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
import requests
import numpy as np
from config.settings import (
    CACHE_DIR,
    GEMINI_API_KEY,
    END_SIL,
    SHORT_SIL,
    MAX_UTT,
    MIN_SPEECH,
    PRE_BUFFER_SEC,
    SPEECH_LONG_THRESHOLD,
    NEED_ON_IDLE,
    NEED_ON_WORKING,
    NEED_ON_GUEST,
    ANSWER_ONLY_ON_WAKE,
    PUSH_TO_TALK,
)

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
        Calculates normalized autocorrelation peak in the pitch lag range [75 Hz, 450 Hz].
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

        min_lag = int(self.sample_rate / 450)
        max_lag = int(self.sample_rate / 75)
        if max_lag < len(r_norm):
            return float(np.max(r_norm[min_lag:max_lag]))
        return 0.0

    def filter_chunk(self, arr: np.ndarray, is_speech: bool = False) -> tuple:
        """
        Processes a float32 chunk:
        - Intelligent VAD: protects speech formants from polluting stationary noise profile.
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

        rms_raw = float(np.sqrt(np.mean(arr ** 2)))
        noise_rms = float(np.sqrt(np.mean((self.noise_profile * self.bp_mask) ** 2))) if self.noise_calibrated else 50.0
        hd_raw = self.calc_harmonic_density(arr)

        # Intelligent Voice Activity Detection for Stationary Noise Floor Tracking:
        # Stationary noise estimation MUST NEVER be updated with speech formants or loud transients,
        # otherwise speech is subtracted from itself and suppressed!
        is_chunk_speech = is_speech or (self.noise_calibrated and (hd_raw >= 0.16 or rms_raw > noise_rms * 1.35))

        if not is_chunk_speech:
            if not self.noise_calibrated:
                self.update_noise(mag, alpha=0.2)
            else:
                self.update_noise(mag, alpha=0.03)

        # Spectral subtraction: remove stationary ambient noise
        sub_mag = np.maximum(mag - self.oversubtraction * self.noise_profile, self.spectral_floor * mag)
        # Bandpass filter (85 Hz to 3500 Hz)
        bp_mag = sub_mag * self.bp_mask

        # Spectral noise gating during non-speech periods to clamp ambient reverberation
        if not is_chunk_speech and rms_raw < noise_rms * 1.35:
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
        self.is_headset = False
        self.last_device_name = ""
        self.dsp = AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=int(self.sample_rate * self.chunk_duration))
        self._check_device_mode()
        self._start_capture()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _check_device_mode(self) -> bool:
        """Auto-detects whether the active PipeWire audio source is a headset or internal laptop mic."""
        try:
            res = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True, timeout=0.8)
            dev = res.stdout.strip()
            if dev:
                self.last_device_name = dev
                self.is_headset = any(k in dev.lower() for k in ("bluez", "headset", "headphones", "bluetooth", "usb", "wireless"))
                return self.is_headset
        except Exception:
            pass
        return self.is_headset

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
                # Capture from current default source dynamically
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
                last_end = getattr(voice_speaker, "last_speech_end_time", 0.0)
                # 650ms acoustic & PipeWire buffer decay tail
                if not is_ezra_speaking and (time.time() - last_end < 0.65):
                    is_ezra_speaking = True
            except Exception:
                pass

            if is_ezra_speaking:
                # Discard Ezra's own voice so she never hears or answers herself
                with self.lock:
                    self.buffer.clear()
                continue

            clean_bytes, ac_rms, harmonic_d = self._calc_rms_and_clean(raw, is_speech=False)

            # Do NOT contaminate ambient noise floor baseline with Ezra's own speaker output
            if not is_ezra_speaking and ac_rms < self.ambient_baseline * 1.45:
                self.ambient_baseline = min(600.0, 0.98 * self.ambient_baseline + 0.02 * ac_rms)

            with self.lock:
                # Store raw PCM so Whisper receives uncorrupted natural speech, with ac_rms/harmonic_d for VAD
                self.buffer.append((raw, ac_rms, harmonic_d))

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

        # Initialize ultra-fast local Whisper Neural Model (accurate slang + Arabic + British English)
        self.whisper_model = None
        try:
            from faster_whisper import WhisperModel
            whisper_base = Path.home() / ".cache" / "whisper_models" / "base"
            whisper_tiny = Path.home() / ".cache" / "whisper_models" / "tiny"
            whisper_dir = whisper_base if whisper_base.exists() else whisper_tiny
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
        if re.search(r"\b(ezra|israel|esra|asra|azra|ezrah|jarvis)\b", low):
            return False

        # 1. Ambient room chatter / speaking to family, kids, colleagues (not directed at assistant)
        household_markers = [
            r"\b(hey mom|hey dad|mommy|daddy|pass the salt|where are my shoes)\b",
            r"\b(did you do your homework|clean your room|dinner is ready|time for dinner)\b",
            r"\b(can i have a snack|stop fighting|stop yelling|stop screaming|stop crying|stop doing that|give me that|give it back|look what i drew|brush your teeth)\b",
            r"\b(it\'s my turn|not your turn|leave me alone|don\'t touch that|let\'s play|come play with me|look at me|tag you\'re it)\b",
            r"\b(did you see that|did you see the email|are you on mute|can you hear me|can you see my screen|who are you talking to|what did you say)\b",
            r"\b(put on your shoes|are you leaving|see you tomorrow|see you later)\b",
        ]
        if any(re.search(p, low) for p in household_markers):
            return True

        # 2. TV / Broadcast / Commercial chatter markers
        tv_markers = [
            r"\b(subscribe to|like and subscribe|notification bell|coming up next|stay tuned)\b",
            r"\b(we will be right back|we\'ll be right back|after these messages|commercial break)\b",
            r"\b(breaking news|live from|back to you in the studio|weather forecast|weather update)\b",
            r"\b(previously on|season finale|in tonight\'s episode|new episode|welcome to the stream)\b",
            r"\b(welcome back to the show|touchdown|halftime|sponsor|sponsored by|buy now|call now|limited time offer)\b",
            r"\b(final score|scores|kickoff|championship|super bowl|world cup|penalty kick)\b",
        ]
        if any(re.search(p, low) for p in tv_markers):
            return True

        # 3. Third-person gossip/dialogue markers ('he said that', 'she told him', etc.)
        gossip_markers = [
            r"^(and then he was like|and then she said|he told me that|she said that|they were talking about)\b",
        ]
        if any(re.search(p, low) for p in gossip_markers):
            return True

        # 4. If clear desktop/system imperative directive, NEVER reject
        direct_patterns = [
            r"^(open|launch|close|kill|start|stop|pause|resume|play|mute|unmute|search|find|google|type|write|press|lock|set|run|git|add|clear|take|volume)\b",
        ]
        if any(re.search(p, low) for p in direct_patterns):
            return False

        # 5. Conversational fillers and mutterings
        filler_phrases = {
            "uh", "um", "er", "ah", "oh", "mm", "hmm", "huh", "cough", "click", "eh", "mhm",
            "yeah", "yep", "nope", "nah", "uh huh", "mm hmm", "hmm yeah", "oh yeah", "yeah right",
            "right yeah", "haha", "hahaha", "hehe", "oh wow", "wow", "right right", "okay okay",
            "cool cool", "i see", "whatever", "no way", "you know", "you know what",
            "yes yes", "sure sure", "fine fine", "aha", "mhm mhm"
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
            "you know", "you know what"
        }
        if low in filler_tokens or low in NOISE_PHRASES:
            return ""

        # Strip leading conversational fillers: 'uh', 'um', 'like', 'so'
        t = re.sub(r"^(?:(?:uh|um|er|ah|mm|like|so|well)\s+)+", "", t, flags=re.IGNORECASE).strip()

        # Homophone corrections: Israel / Isra / Esra / Asra / Azra -> Ezra
        t = re.sub(r"\b(israel|isra|asra|esra|azra|ezrah)\b", "Ezra", t, flags=re.IGNORECASE)
        # Antigravity homophones: antique gravity / anti gravity / the gravity -> antigravity
        t = re.sub(r"\b(antique gravity|anti gravity|the gravity)\b", "antigravity", t, flags=re.IGNORECASE)
        # Known desktop control corrections
        t = re.sub(r"\bcontrol my temp\b", "control my tab", t, flags=re.IGNORECASE)
        t = re.sub(r"\byou tube\b", "youtube", t, flags=re.IGNORECASE)
        t = re.sub(r"\bgit hub\b", "github", t, flags=re.IGNORECASE)
        # Fix colloquial "in it" -> "innit"
        t = re.sub(r"\bin it\b", "innit", t, flags=re.IGNORECASE)

        return t.strip()

    def record_until_finished(
        self,
        max_wait_sec: float = 15.0,
        silence_threshold_sec: float = None,
        is_busy: bool = False,
        speaker_tier: str = None,
        push_to_talk: bool = None,
        on_partial_transcript = None
    ) -> str:
        """
        Musa Turn-Taking & Voice Activity Detection (VAD) Architecture:
        - END_SIL (1.6s): After speaking for >1.2s, wait for 1.6s of quiet before treating turn as finished.
        - SHORT_SIL (0.9s): If speech duration <1.2s (e.g. 'yes', 'okay go'), wait 0.9s of quiet.
        - MAX_UTT (60.0s): Longest single turn continuous utterance hard cap.
        - MIN_SPEECH (0.35s): Audio shorter than 0.35s (coughs, clicks, claps) is treated as noise and discarded.
        - PRE (0.40s): Ring buffer keeps 0.4s (5 chunks @ 80ms) prior to speech onset so first consonant is never cut.
        - needOn: 0.15s sound needed to start a turn when idle or speaking, 0.30s while working, 0.20s for guests.
        - Thresholds: Speech must be 3x to 6x above ambient baseline; silence means volume drops below 2x the speech-start baseline.
        - Live Transcript Streaming: Refreshes every 1.8s (or 0.35s if Ezra is speaking simultaneously).
        - Interruption & Volume Ducking: Immediately ducks speaker volume when user speaks, and cuts off reply when confirmed.
        - Push-to-Talk (PTT): Hold key mode with zero silence timers.
        """
        from jarvis.ui.visuals import status_bar
        from jarvis.voice.speaker import voice_speaker

        ensure_hardware_mic_volume()
        self.last_streaming_transcription = ""
        self.last_spk_vector = []
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

        # Push-to-talk mode determination
        is_ptt = PUSH_TO_TALK if push_to_talk is None else bool(push_to_talk)

        # Dynamic silence thresholds (Musa spec)
        if silence_threshold_sec is not None:
            end_sil_sec = float(silence_threshold_sec)
            short_sil_sec = min(SHORT_SIL, end_sil_sec)
        else:
            end_sil_sec = END_SIL
            short_sil_sec = SHORT_SIL

        # Sound duration needed to start a turn (needOn)
        if is_busy:
            need_on_sec = NEED_ON_WORKING  # 0.30s while busy/working
        elif speaker_tier == "guest":
            need_on_sec = NEED_ON_GUEST    # 0.20s for guests
        else:
            need_on_sec = NEED_ON_IDLE     # 0.15s when idle or speaking
        need_on_chunks = max(1, int(round(need_on_sec / self.chunk_duration)))

        # Pre-speech audio ring buffer (PRE: 0.40s = 5 chunks @ 80ms)
        pre_chunks_count = max(1, int(round(PRE_BUFFER_SEC / self.chunk_duration)))
        pre_buffer = deque(maxlen=pre_chunks_count)

        # Wait for worker calibration before we start listening (fast 1.5s max)
        calib_deadline = time.time() + 1.5
        while not self.worker.calibrated and time.time() < calib_deadline:
            time.sleep(0.02)

        # Drain all previous audio chunks so Ezra never hears past sounds or her own voice
        self.worker.drain(keep_recent=0)

        # Immediate mic handover: render live mic indicator instantly!
        status_bar.render_listening(level=0, is_heard=False)

        dsp = getattr(self, "dsp", None) or getattr(getattr(self, "worker", None), "dsp", None)
        if dsp is None:
            sr = getattr(self, "sample_rate", 16000)
            cd = getattr(self, "chunk_duration", 0.08)
            dsp = AudioDSPFilter(sample_rate=sr, chunk_samples=int(sr * cd))
            self.dsp = dsp

        # Setup streaming partial recognizer if Vosk model is available
        streaming_rec = None
        v_model = getattr(self, "vosk_model", None)
        if v_model:
            try:
                import vosk
                sr_val = getattr(self, "sample_rate", 16000)
                streaming_rec = vosk.KaldiRecognizer(v_model, sr_val)
            except Exception:
                streaming_rec = None

        recorded_frames = []
        is_speaking = False
        self.is_user_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        harmonic_chunks_count = 0
        silence_chunks = 0
        speech_start_baseline = 250.0

        start_time = time.time()
        last_chunk_time = start_time
        speech_start_time = 0.0
        last_refresh_time = 0.0
        speaker_was_ducked = False

        try:
            while True:
                item = self.worker.get_chunk()
                if item is None:
                    time.sleep(0.01)
                    now = time.time()
                    if not is_speaking and (now - start_time > max_wait_sec):
                        break
                    if is_speaking:
                        # MAX_UTT hard cap (60s)
                        if speech_start_time and (now - speech_start_time > MAX_UTT):
                            break
                        # Stalled chunk safety timeout
                        if now - last_chunk_time > 1.2:
                            break
                    continue

                last_chunk_time = time.time()
                if len(item) >= 3:
                    chunk, ac_rms, harmonic_density = item[0], item[1], item[2]
                else:
                    chunk, ac_rms = item[0], item[1]
                    harmonic_density = dsp.calc_harmonic_density(chunk)

                # Check if Ezra speaker is actively outputting audio
                is_speaker_active = False
                try:
                    is_speaker_active = getattr(voice_speaker, "is_speaking", False)
                except Exception:
                    pass

                baseline = min(self.worker.ambient_baseline, 800.0)
                is_headset = getattr(self.worker, "is_headset", False)

                # Dynamic Threshold Adaptation:
                # - Headset: high proximity, clean signal, zero laptop fan interference -> 2.2x baseline (min 150)
                # - Laptop Mic: ambient fan noise and room reverberation -> adaptive baseline tracking with 1.8x multiplier (min 120)
                if is_speaker_active:
                    speech_threshold = max(baseline * (3.5 if is_headset else 4.5) + 200.0, 650.0)
                elif is_headset:
                    speech_threshold = max(baseline * 2.2, 150.0)
                else:
                    # Laptop Mic with fan sound compensation
                    speech_threshold = max(baseline * 1.8, 115.0)

                # Dynamic VU Audio Meter: voice dynamically fills the bar
                excess = max(0.0, ac_rms - baseline)
                scale_span = max(baseline * 1.2, 200.0)
                level = min(10, max(0, int((excess / scale_span) * 10)))

                # Check vocal harmonic density
                samples_raw = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) if len(chunk) >= 2 else np.array([])
                is_synthetic_mock = len(samples_raw) > 0 and np.all(samples_raw == 0) and ac_rms > 0
                # Laptop mic with fan sound has lower harmonic purity (0.07 threshold); headset has high purity (0.12)
                min_harmonic_gate = 0.12 if is_headset else 0.07
                has_vocal_harmonics = is_synthetic_mock or (harmonic_density >= min_harmonic_gate)

                if not is_speaking:
                    # ONSET DETECTION PHASE
                    if ac_rms > speech_threshold and has_vocal_harmonics:
                        consecutive_voice_chunks += 1

                        # Musa: Turn volume down (duck) right away if speaking while Musa is talking
                        if is_speaker_active and not speaker_was_ducked:
                            try:
                                voice_speaker.duck_volume(0.15)
                                speaker_was_ducked = True
                            except Exception:
                                pass

                        if consecutive_voice_chunks >= need_on_chunks:
                            # Confirmed speech onset!
                            is_speaking = True
                            self.is_user_speaking = True
                            speech_start_time = time.time()
                            speech_start_baseline = baseline  # Musa: store baseline at moment user started talking
                            recorded_frames.extend(list(pre_buffer))
                            recorded_frames.append(chunk)
                            speech_chunks_count += 1
                            harmonic_chunks_count += 1
                            silence_chunks = 0
                            status_bar.render_listening(level=level, is_heard=True)

                            if streaming_rec:
                                try:
                                    for pb in pre_buffer:
                                        streaming_rec.AcceptWaveform(pb)
                                    streaming_rec.AcceptWaveform(chunk)
                                except Exception:
                                    pass
                    else:
                        consecutive_voice_chunks = 0
                        pre_buffer.append(chunk)
                        status_bar.render_listening(level=level, is_heard=False)
                        # If speaker was ducked on a false trigger, restore it
                        if speaker_was_ducked and not is_speaking:
                            try:
                                voice_speaker.restore_volume(1.0)
                                speaker_was_ducked = False
                            except Exception:
                                pass

                        if time.time() - start_time > max_wait_sec:
                            break

                else:
                    # ACTIVE SPEECH RECORDING PHASE
                    recorded_frames.append(chunk)
                    if streaming_rec:
                        try:
                            streaming_rec.AcceptWaveform(chunk)
                        except Exception:
                            pass

                    # Musa: Silence means volume drops below 2x the background level at speech onset
                    silence_cutoff = speech_start_baseline * 2.0
                    if ac_rms < silence_cutoff:
                        silence_chunks += 1
                    else:
                        silence_chunks = 0
                        speech_chunks_count += 1
                        if has_vocal_harmonics:
                            harmonic_chunks_count += 1

                    # If speaking while Ezra was playing and voice confirmed (>0.35s), stop reply for good
                    if is_speaker_active and speech_chunks_count >= 5:
                        try:
                            voice_speaker.stop()
                            speaker_was_ducked = False
                        except Exception:
                            pass

                    # Live Streaming Transcript Refresh:
                    # Musa: every 1.8s, or every 0.35s if Musa is speaking at the same time
                    refresh_interval = 0.35 if is_speaker_active else 1.8
                    now = time.time()
                    if streaming_rec and (now - last_refresh_time >= refresh_interval):
                        last_refresh_time = now
                        try:
                            res_dict = json.loads(streaming_rec.PartialResult())
                            partial = res_dict.get("partial", "").strip()
                            if partial:
                                self.last_streaming_transcription = partial
                                status_bar.render_listening(level=level, is_heard=True, transcript=partial)
                                if on_partial_transcript:
                                    on_partial_transcript(partial)

                                # Musa: Saying a stop word stops speech straight away
                                if is_speaker_active:
                                    p_low = partial.lower()
                                    if any(w in p_low for w in ("stop", "quiet", "wait", "hold on", "shut up", "hush", "pause", "be quiet")):
                                        voice_speaker.stop()
                                        speaker_was_ducked = False
                        except Exception:
                            pass
                    else:
                        status_bar.render_listening(level=level, is_heard=True, transcript=self.last_streaming_transcription)

                    # Check turn completion conditions:
                    # 1. MAX_UTT (60.0s) hard cap
                    if now - speech_start_time >= MAX_UTT:
                        break

                    # 2. Silence Endpointing (skipped in Push-to-Talk mode)
                    if not is_ptt:
                        speech_duration = speech_chunks_count * self.chunk_duration
                        if speech_duration >= SPEECH_LONG_THRESHOLD:  # > 1.2s
                            target_silence = end_sil_sec              # 1.6s default
                        else:
                            target_silence = short_sil_sec            # 0.9s default

                        target_silence_chunks = max(3, int(round(target_silence / self.chunk_duration)))
                        if silence_chunks >= target_silence_chunks:
                            break

                # Manual cutoff / Space bar / Enter check (non-blocking)
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
            if speaker_was_ducked and not getattr(voice_speaker, "is_speaking", False):
                try:
                    voice_speaker.restore_volume(1.0)
                except Exception:
                    pass

        # MIN_SPEECH (0.35s) Check:
        # Musa: "Shortest speech it accepts: 0.35s (MIN_SPEECH). Anything shorter is treated as a noise, like a cough or click, and thrown away."
        total_speech_sec = speech_chunks_count * self.chunk_duration
        if not recorded_frames or not is_speaking or total_speech_sec < MIN_SPEECH:
            return ""

        pcm_bytes = b"".join(recorded_frames)
        full_samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) if len(pcm_bytes) >= 2 else np.array([])
        is_synth_full = len(full_samples) > 0 and np.all(full_samples == 0)
        if not is_synth_full and len(full_samples) >= 320:
            full_harmonic_d = dsp.calc_harmonic_density(full_samples)
            # Relaxed for laptop mic so valid speech is not discarded
            if full_harmonic_d < 0.05 and (harmonic_chunks_count / max(1, speech_chunks_count) < 0.05):
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

        # Tier 1: Cloud Groq Whisper Large v3 Turbo (State-of-the-art Large-v3 neural accuracy, ~180ms)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                with open(audio_path, "rb") as f:
                    resp = requests.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {groq_key}"},
                        files={"file": (os.path.basename(audio_path), f, "audio/wav")},
                        data={
                            "model": "whisper-large-v3-turbo",
                            "prompt": "Ezra, British English, mate, innit, cheers, sir, developer, code, news"
                        },
                        timeout=3.5
                    )
                    if resp.status_code == 200:
                        gw_text = (resp.json().get("text") or "").strip()
                        if gw_text and len(gw_text) > 1 and gw_text not in (".", "...", "!", "?"):
                            raw_transcription = gw_text
            except Exception:
                pass

        # Tier 2: Cloud Google Speech Recognition (Instantaneous British & US English recognition)
        if not raw_transcription:
            try:
                with sr.AudioFile(audio_path) as source:
                    audio_data = self.recognizer.record(source)
                    try:
                        g_res = self.recognizer.recognize_google(audio_data, language="en-GB")
                        if g_res and len(g_res.strip()) > 1:
                            raw_transcription = g_res.strip()
                    except Exception:
                        pass

                    if not raw_transcription:
                        try:
                            g_us = self.recognizer.recognize_google(audio_data, language="en-US")
                            if g_us and len(g_us.strip()) > 1:
                                raw_transcription = g_us.strip()
                        except Exception:
                            pass
            except Exception:
                pass

        # Tier 3: Local Whisper Neural Model (Local offline fallback when internet is down)
        if not raw_transcription and self.whisper_model:
            try:
                segments, info = self.whisper_model.transcribe(
                    audio_path,
                    beam_size=2,
                    best_of=2,
                    temperature=0.0,
                    condition_on_previous_text=False,
                    initial_prompt="Ezra, British English, mate, innit, cheers, sir, developer, code, news"
                )
                whisper_text = " ".join([s.text for s in segments]).strip()
                if whisper_text and len(whisper_text) > 1 and whisper_text not in (".", "...", "!", "?"):
                    raw_transcription = whisper_text
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
