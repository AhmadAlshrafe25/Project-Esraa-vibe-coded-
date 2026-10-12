import os
import re
import time
import math
import struct
import wave
import uuid
import shutil
import json
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
    "huh", "huh.", "oh", "oh.", "so", "so.", "the"
}

class NativeSpeechRecognizer:
    """Intelligent Voice Activity Detection (VAD) with noise immunity, human voice gating, and ultra-fast Vosk STT."""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = 2.0  # Strict 2s timeout so Google STT never stalls
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

    def record_until_finished(self, max_wait_sec: float = 8.0, silence_threshold_sec: float = 0.55) -> str:
        """
        Dynamically records only genuine human speech with real-time streaming Vosk recognition:
        - Instant silence cut-off: defaults to 0.55s so Ezra responds near-instantly when user stops speaking.
        - Adaptive noise floor calibration: automatically normalizes to room acoustics and eliminates mic static/hiss.
        - Streams incoming audio directly to Vosk Kaldi recognizer in memory.
        - Maximum speech safety cutoff: caps continuous speech at 6.0s to prevent ever getting stuck!
        """
        self._ensure_mic_volume()
        self.last_streaming_transcription = ""
        wav_file = CACHE_DIR / f"mic_{uuid.uuid4().hex[:8]}.wav"

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

        try:
            proc = self._spawn_capture_process()
        except Exception as e:
            raise RuntimeError(f"Microphone recording failed: {e}")

        # 1. Warm-up & Calibration: Discard stream initialization surge and settle baseline
        calib_rms = []
        for _ in range(10):
            init_chunk = proc.stdout.read(self.chunk_size)
            if not init_chunk:
                break
            rms_val = self._calculate_rms(init_chunk)
            if 1000.0 < rms_val < 20000.0:
                calib_rms.append(rms_val)
                if len(calib_rms) >= 3:
                    break

        ambient_baseline = float(np.median(calib_rms)) if calib_rms else 7500.0
        if ambient_baseline < 1000.0:
            ambient_baseline = 7500.0

        # 640ms rolling pre-speech ring buffer
        pre_buffer_size = int(0.64 / self.chunk_duration)
        pre_buffer = deque(maxlen=pre_buffer_size)

        recorded_frames = []
        is_speaking = False
        consecutive_voice_chunks = 0
        speech_chunks_count = 0
        silence_chunks = 0
        max_silence_chunks = max(3, int(silence_threshold_sec / self.chunk_duration))

        start_time = time.time()
        speech_start_time = 0.0
        max_speech_sec = 6.0  # Hard ceiling: voice commands should never record longer than 6 seconds!

        try:
            while True:
                chunk = proc.stdout.read(self.chunk_size)
                if not chunk:
                    break

                rms = self._calculate_rms(chunk)

                # Skip clipping spikes (>32000) from noise floor tracking
                if rms < 32000.0:
                    if not is_speaking:
                        # Smooth continuous tracking of ambient room noise
                        ambient_baseline = 0.88 * ambient_baseline + 0.12 * rms
                    else:
                        # While speaking, noise floor only drifts if lower energy is observed
                        if rms < ambient_baseline:
                            ambient_baseline = 0.85 * ambient_baseline + 0.15 * rms

                # Dynamic speech threshold: requires voice energy clearly above ambient floor
                speech_threshold = max(ambient_baseline * 1.45, ambient_baseline + 3500.0)

                # Accurate dynamic audio level meter
                excess = max(0.0, rms - ambient_baseline)
                scale_span = max(speech_threshold - ambient_baseline, 3500.0)
                level = min(10, max(0, int((excess / scale_span) * 10)))
                meter_bar = "█" * level + "░" * (10 - level)

                if rms > speech_threshold:
                    consecutive_voice_chunks += 1

                    # Debounce: Require at least 2 consecutive chunks (160ms) of human vocal energy
                    if consecutive_voice_chunks >= 2 and not is_speaking:
                        is_speaking = True
                        speech_start_time = time.time()
                        buffered_list = list(pre_buffer)
                        recorded_frames.extend(buffered_list)
                        if vosk_rec:
                            for b_chunk in buffered_list:
                                vosk_rec.AcceptWaveform(b_chunk)

                    if is_speaking:
                        print(f"\r\033[1;32m[🎙️ Speaking |{meter_bar}|]\033[0m   ", end="", flush=True)
                        recorded_frames.append(chunk)
                        speech_chunks_count += 1
                        silence_chunks = 0
                        if vosk_rec:
                            if vosk_rec.AcceptWaveform(chunk):
                                # Kaldi acoustic model detected end of spoken sentence!
                                break

                        # Hard ceiling: if user has spoken for 6 seconds, cut off and process immediately!
                        if time.time() - speech_start_time > max_speech_sec:
                            break
                else:
                    consecutive_voice_chunks = 0
                    if is_speaking:
                        recorded_frames.append(chunk)
                        silence_chunks += 1
                        print(f"\r\033[1;33m[🎙️ Pausing |{meter_bar}|]\033[0m    ", end="", flush=True)
                        if vosk_rec:
                            vosk_rec.AcceptWaveform(chunk)
                        if silence_chunks >= max_silence_chunks:
                            # Natural end of spoken command (sub-second trigger)
                            break
                    else:
                        pre_buffer.append(chunk)
                        print(f"\r\033[1;35m[🎙️ Listening |{meter_bar}|]\033[0m  ", end="", flush=True)
                        if time.time() - start_time > max_wait_sec:
                            break

                # Global safety fallback
                if time.time() - start_time > 12.0:
                    break

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=0.2)
            except Exception:
                proc.kill()

        print("\r" + " " * 40 + "\r", end="", flush=True)

        # Noise Rejection Filter: If total speech was less than 4 chunks (<0.32s), discard as transient click/noise!
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

        # Biomarker / Voice Genetic Gate check:
        # Rejects random background voices, family/room chatter, and TV!
        from jarvis.voice.biometrics import voice_dna
        pcm_bytes = b"".join(recorded_frames)
        if voice_dna.is_enrolled() and spk_vector and len(spk_vector) >= 10:
            is_verified, score, reason = voice_dna.verify(spk_vector, pcm_data=pcm_bytes)
            if not is_verified:
                print(f"\r\033[1;31m[🛡️ Voice Gate: Ignored background speaker (Genetic match: {score:.1%}, required: {voice_dna.get_threshold():.0%})]\033[0m   \n")
                self.last_streaming_transcription = ""
                self.last_spk_vector = []
                return ""
            else:
                print(f"\r\033[1;32m[🧬 Voice Genetic Match: {score:.1%} | Verified {voice_dna.get_user_name()}]\033[0m   ")

        if recognized_text:
            self.last_streaming_transcription = recognized_text

        # Write clean WAV file for verification/fallback
        with wave.open(str(wav_file), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)

        return str(wav_file)

    def transcribe_audio_file(self, audio_path: str) -> str:
        """Transcribes audio using multi-tier low-latency engine (Streaming Vosk -> Offline Vosk file -> Google 2s timeout -> Gemini)."""
        if not audio_path and not self.last_streaming_transcription:
            return ""

        transcription = ""

        # 1. Tier 1: Instant Streaming Vosk Result (0ms - decoded concurrently as user spoke)
        if self.last_streaming_transcription:
            transcription = self.last_streaming_transcription
            self.last_streaming_transcription = ""

        # 2. Tier 2: Offline Vosk file pass (<50ms local inference)
        if not transcription and self.vosk_model and audio_path and os.path.exists(audio_path):
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

        # 3. Tier 3: High-speed Google Speech Recognition (strict 2s timeout)
        if not transcription and audio_path and os.path.exists(audio_path):
            try:
                with sr.AudioFile(audio_path) as source:
                    audio_data = self.recognizer.record(source)
                    text = self.recognizer.recognize_google(audio_data)
                    if text and text.strip():
                        transcription = text.strip()
            except Exception:
                pass

        # 4. Tier 4: Gemini 3.5 Flash Multimodal Audio (fallback if audio is complex)
        if not transcription and GEMINI_API_KEY and audio_path and os.path.exists(audio_path):
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
            except Exception:
                pass

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
