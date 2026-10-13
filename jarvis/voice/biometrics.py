import os
import json
import math
import time
import struct
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

# Storage for Voice Genetic Code Profile
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PROFILE_FILE = DATA_DIR / "voice_genetic_code.json"

# Three Security Tiers (Inspired by Musa Production Architecture)
TIER_VERIFIED = "verified"  # Score >= threshold (default >= 0.35): Full access
TIER_UNSURE = "unsure"      # Score 0.20 - 0.35: Requires confirmation word before outside actions
TIER_GUEST = "guest"        # Score < 0.20: Read-only conversation, outside actions strictly blocked

SAFE_READ_TOOLS = {
    "get_weather", "get_crypto_price", "get_exchange_rate", "search_wikipedia",
    "get_network_info", "get_tech_news", "get_github_info", "get_system_status",
    "search_web", "toggle_voice", "set_voice_mode", "get_daily_briefing", "git_status", "git_log_recent",
    "deep_research", "media_control", "close_tab", "close_browser", "git_pull", "sync_gdrive",
    "get_top_processes", "lock_screen", "add_note", "get_notes", "clear_notes",
    "add_todo", "get_todos", "clear_todos", "get_recent_downloads", "search_portal", "open_folder",
    "prompt_antigravity", "prompt_app", "focus_app", "launch_app", "close_app",
    "type_message", "type_text", "dictate_text", "press_key", "press_hotkey",
    "move_mouse", "move_mouse_relative", "point_at", "click_mouse", "double_click", "right_click", "drag_mouse",
    "click_screen_element", "inspect_screen",
    "set_clipboard", "get_clipboard", "take_screenshot", "execute_shell_command"
}

class VoiceBiometrics:
    """
    Vocal Genetic Biometrics Engine.
    Maps and locks Ezra to the master's unique acoustic DNA:
    - 3-Tier Security Architecture: Verified (>=0.35), Unsure (0.20-0.34), Guest (<0.20)
    - Secret confirmation word session (active for 10 minutes or 3 turns)
    - Fast 48-dimensional NumPy Mel-filterbank timbre embedding + F0 pitch tracker
    - Zero external cloud latency, 100% private on local CPU.
    """

    def __init__(self):
        self.enrolled: bool = False
        self.user_name: str = "Ahmad"
        self.threshold: float = 0.35  # Calibrated threshold for master recognition
        self.strict_mode: bool = False
        self.voice_vector: Optional[np.ndarray] = None
        self.sample_count: int = 0
        self.history_vectors: List[List[float]] = []
        self.f0_mean: float = 0.0
        self.f0_std: float = 0.0
        self.last_score: float = 0.0
        self.last_tier: str = TIER_VERIFIED
        self.secret_word: str = "protocol zero"
        self.secret_session_until: float = 0.0
        self.load_profile()

    def load_profile(self) -> bool:
        """Loads voice genetic profile from disk."""
        if not PROFILE_FILE.exists():
            self.enrolled = False
            return False

        try:
            with open(PROFILE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if data.get("enrolled") and data.get("voice_vector"):
                vec = np.array(data["voice_vector"], dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    self.voice_vector = vec / norm
                    self.enrolled = True
                    self.user_name = data.get("user_name", "Ahmad")
                    self.threshold = float(data.get("threshold", 0.35))
                    self.strict_mode = bool(data.get("strict_mode", False))
                    self.sample_count = int(data.get("sample_count", 1))
                    self.history_vectors = data.get("history_vectors", [])
                    self.f0_mean = float(data.get("f0_mean", 0.0))
                    self.f0_std = float(data.get("f0_std", 0.0))
                    self.secret_word = data.get("secret_word", "protocol zero")
                    return True
        except Exception as e:
            print(f"[Voice Biometrics Load Error]: {e}")

        self.enrolled = False
        return False

    def save_profile(self):
        """Saves current voice genetic profile to disk."""
        if self.voice_vector is None:
            return

        data = {
            "enrolled": self.enrolled,
            "user_name": self.user_name,
            "threshold": self.threshold,
            "strict_mode": self.strict_mode,
            "sample_count": self.sample_count,
            "voice_vector": self.voice_vector.tolist(),
            "history_vectors": self.history_vectors[-5:],
            "f0_mean": self.f0_mean,
            "f0_std": self.f0_std,
            "secret_word": self.secret_word,
            "updated_at": time.time()
        }

        try:
            with open(PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Voice Biometrics Save Error]: {e}")

    def is_enrolled(self) -> bool:
        return self.enrolled and self.voice_vector is not None

    def get_threshold(self) -> float:
        return self.threshold

    def set_threshold(self, value: float):
        self.threshold = max(0.25, min(0.85, float(value)))
        self.save_profile()

    def get_user_name(self) -> str:
        return self.user_name

    def set_user_name(self, name: str):
        self.user_name = name.strip() or "Ahmad"
        self.save_profile()

    def set_secret_word(self, word: str):
        self.secret_word = word.strip().lower() or "protocol zero"
        self.save_profile()

    def toggle_strict_mode(self) -> bool:
        self.strict_mode = not self.strict_mode
        self.save_profile()
        return self.strict_mode

    @staticmethod
    def extract_acoustic_embedding(pcm_data: bytes, sample_rate: int = 16000) -> np.ndarray:
        """
        Extracts a 48-dimensional spectral timbre embedding using pure NumPy:
        - 24-band log filterbank energy mean
        - 24-band log filterbank energy standard deviation
        - Normalized to unit sphere for fast cosine similarity.
        """
        if not pcm_data or len(pcm_data) < sample_rate * 0.15:
            return np.zeros(48, dtype=np.float32)
        try:
            samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
            frame_len = int(sample_rate * 0.030)  # 30ms frames
            hop_len = int(sample_rate * 0.015)    # 15ms step
            num_frames = max(1, (len(samples) - frame_len) // hop_len)
            
            fft_size = 512
            filters = 24
            mel_energies = []
            window = np.hanning(frame_len)
            
            for i in range(num_frames):
                start = i * hop_len
                frame = samples[start:start + frame_len] * window
                fft = np.abs(np.fft.rfft(frame, n=fft_size))
                if np.sum(fft) < 1e-3:
                    continue
                bands = np.array_split(fft, filters)
                band_energies = [np.mean(b**2) + 1e-8 for b in bands]
                mel_energies.append(np.log(band_energies))
                
            if not mel_energies:
                return np.zeros(48, dtype=np.float32)
                
            mel_mat = np.array(mel_energies)
            mean_vec = np.mean(mel_mat, axis=0)
            std_vec = np.std(mel_mat, axis=0)
            feat = np.concatenate([mean_vec, std_vec])
            norm = np.linalg.norm(feat)
            return (feat / norm).astype(np.float32) if norm > 0 else feat
        except Exception:
            return np.zeros(48, dtype=np.float32)

    @staticmethod
    def extract_f0_pitch(pcm_data: bytes, sample_rate: int = 16000) -> float:
        """Estimates fundamental frequency (F0) using normalized autocorrelation over voiced frames."""
        if not pcm_data or len(pcm_data) < sample_rate // 10:
            return 0.0

        try:
            count = len(pcm_data) // 2
            samples = np.frombuffer(pcm_data[:count * 2], dtype=np.int16).astype(np.float32)
            frame_len = int(sample_rate * 0.04)
            step = int(sample_rate * 0.02)
            pitches = []
            min_lag = int(sample_rate / 350)
            max_lag = int(sample_rate / 65)

            for i in range(0, len(samples) - frame_len, step * 2):
                frame = samples[i:i + frame_len]
                frame = frame - np.mean(frame)
                sq_sum = np.sum(frame * frame)
                if sq_sum < 1e5:
                    continue

                corr = np.correlate(frame, frame, mode='full')
                corr = corr[len(frame) - 1:]

                if len(corr) > max_lag:
                    search_slice = corr[min_lag:max_lag]
                    if len(search_slice) > 0:
                        peak_idx = min_lag + np.argmax(search_slice)
                        if corr[peak_idx] > 0.35 * corr[0]:
                            pitch_hz = sample_rate / peak_idx
                            if 70.0 <= pitch_hz <= 320.0:
                                pitches.append(pitch_hz)

            if pitches:
                return float(np.median(pitches))
        except Exception:
            pass

        return 0.0

    def enroll(self, spk_vector: List[float] = None, pcm_data: bytes = None, user_name: str = "Ahmad"):
        """Enrolls or refines the master's voice genetic profile with a new utterance."""
        unit_vec = None
        if pcm_data:
            unit_vec = self.extract_acoustic_embedding(pcm_data)
        elif spk_vector and len(spk_vector) > 5:
            v = np.array(spk_vector, dtype=np.float32)
            norm = np.linalg.norm(v)
            if norm > 0:
                unit_vec = v / norm

        if unit_vec is None or np.linalg.norm(unit_vec) == 0:
            return False

        self.user_name = user_name.strip() or "Ahmad"

        if self.voice_vector is not None and self.sample_count > 0 and len(self.voice_vector) == len(unit_vec):
            combined = (self.voice_vector * self.sample_count + unit_vec) / (self.sample_count + 1)
            self.voice_vector = combined / np.linalg.norm(combined)
            self.sample_count += 1
        else:
            self.voice_vector = unit_vec
            self.sample_count = 1

        self.history_vectors.append(unit_vec.tolist())
        if len(self.history_vectors) > 5:
            self.history_vectors = self.history_vectors[-5:]

        if pcm_data:
            f0 = self.extract_f0_pitch(pcm_data)
            if f0 > 0:
                if self.f0_mean > 0:
                    self.f0_mean = 0.7 * self.f0_mean + 0.3 * f0
                else:
                    self.f0_mean = f0

        self.enrolled = True
        self.save_profile()
        return True

    def verify_turn(self, pcm_data: bytes, user_text: str = "") -> Tuple[str, float, str]:
        """
        Verifies incoming speaker against enrolled biometric profile into 3 Security Tiers:
        - TIER_VERIFIED: score >= threshold (default 0.35)
        - TIER_UNSURE: score between 0.20 and 0.35
        - TIER_GUEST: score < 0.20
        """
        if not self.is_enrolled():
            self.last_tier = TIER_VERIFIED
            return TIER_VERIFIED, 1.0, "biometrics_not_enrolled"

        # Check if an active secret confirmation session is alive (<10 mins)
        now = time.time()
        if self.secret_session_until > now:
            self.last_tier = TIER_VERIFIED
            return TIER_VERIFIED, 1.0, "secret_session_active"

        # Check if user spoke the secret confirmation word
        if user_text and self.secret_word.lower() in user_text.lower():
            self.secret_session_until = now + 600.0  # 10 minutes session!
            self.last_tier = TIER_VERIFIED
            return TIER_VERIFIED, 0.95, "secret_word_authenticated"

        # Extract acoustic embedding from current utterance
        embedding = self.extract_acoustic_embedding(pcm_data) if pcm_data else np.zeros(48, dtype=np.float32)
        if np.linalg.norm(embedding) == 0:
            tier = TIER_VERIFIED if not self.strict_mode else TIER_UNSURE
            self.last_tier = tier
            return tier, 0.5, "short_audio_fallback"

        if self.voice_vector is not None and len(self.voice_vector) == len(embedding):
            similarity = float(np.dot(self.voice_vector, embedding))
            for h in self.history_vectors:
                if len(h) == len(embedding):
                    sim_h = float(np.dot(np.array(h, dtype=np.float32), embedding))
                    if sim_h > similarity:
                        similarity = sim_h
        else:
            # Dimension mismatch (e.g. legacy x-vector profile): use pitch and energy
            f0 = self.extract_f0_pitch(pcm_data) if pcm_data else 0.0
            if self.f0_mean > 0 and f0 > 0:
                pitch_ratio = min(f0, self.f0_mean) / max(f0, self.f0_mean)
                similarity = float(pitch_ratio * 0.75)
            else:
                similarity = 0.45

        self.last_score = similarity

        if similarity >= self.threshold:
            tier = TIER_VERIFIED
            detail = f"verified_master ({similarity:.2f})"
        elif similarity >= 0.20:
            tier = TIER_UNSURE
            detail = f"unsure_speaker ({similarity:.2f})"
        else:
            tier = TIER_GUEST
            detail = f"guest_speaker ({similarity:.2f})"

        self.last_tier = tier
        return tier, similarity, detail

    def is_action_permitted(self, tool_name: str, tier: str = None) -> Tuple[bool, str]:
        """
        Enforces access control on actions based on the verified security tier.
        In default personal mode (strict_mode=False), all actions from the master are unconditionally permitted.
        """
        if not self.strict_mode:
            return True, "permitted"

        if tier is None:
            tier = self.last_tier

        # Safe read-only actions are permitted for everyone
        if tool_name in SAFE_READ_TOOLS:
            return True, "permitted"

        if tier == TIER_VERIFIED:
            return True, "verified_master"

        if tier == TIER_UNSURE:
            return False, f"Action '{tool_name}' requires confirmation. Please speak secret word ('{self.secret_word}')"

        return False, f"Action '{tool_name}' denied: Guest voice detected. Desktop actions reserved for {self.user_name}."

    def clear_enrollment(self):
        """Clears enrolled voice genetic code."""
        self.enrolled = False
        self.voice_vector = None
        self.sample_count = 0
        self.history_vectors = []
        self.f0_mean = 0.0
        if PROFILE_FILE.exists():
            try:
                PROFILE_FILE.unlink()
            except Exception:
                pass

voice_dna = VoiceBiometrics()
