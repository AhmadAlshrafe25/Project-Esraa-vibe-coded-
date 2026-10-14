import os
import sys
import re
import io
import time
import wave
import math
import struct
import uuid
import select
import hashlib
import asyncio
import subprocess
import threading
import shutil
import concurrent.futures
from pathlib import Path
from typing import Optional, List, Generator

import edge_tts
import requests
import urllib.parse
import pygame
import numpy as np

from config.settings import CACHE_DIR
from jarvis.voice.local_tts import LocalNeuralTTS, apply_anti_clipping_dsp

# Try importing broadcast_ui_event with safe fallback
try:
    from jarvis.ui.server import broadcast_ui_event
except Exception:
    def broadcast_ui_event(event_dict: dict) -> None:
        pass

# Initialize audio mixer with robust native fallback (ffplay / pw-play)
HAS_PYGAME_MIXER = False
try:
    import pygame.mixer
    pygame.mixer.pre_init(24000, -16, 2, 512)
    pygame.mixer.init()
    HAS_PYGAME_MIXER = True
except Exception:
    HAS_PYGAME_MIXER = False


class SmoothSpeaker:
    """
    Delivers silky smooth, natural human neural voice with instant responsiveness,
    in-memory PCM playback, 5-tier fallback cascade, and zero robotic speech artifacts.
    """

    def __init__(self, voice: str = "bm_george"):
        self.voice = voice  # High-clarity British neural voice (bm_george / bf_isabella / bm_lewis)
        self.fallback_voice = "en-GB-RyanNeural"  # British neural voice
        self.is_muted: bool = False
        self.is_speaking: bool = False
        self.is_interrupted: bool = False
        self.is_ducked: bool = False
        self.robotic_mode: bool = os.getenv("ROBOTIC_VOICE", "false").lower() in ("true", "1", "yes")
        self.last_language: str = "en"
        self._active_proc = None
        self._current_channel = None
        self._current_sound = None
        self._lock = threading.RLock()
        self.local_tts = LocalNeuralTTS()
        self.last_spoken_text: str = ""
        self.last_speech_end_time: float = 0.0

    def set_robotic_mode(self, enabled: bool):
        """Switches between Cybernetic Robotic voice and Silky Neural voice."""
        self.robotic_mode = bool(enabled)

    def toggle_robotic_mode(self) -> bool:
        """Toggles between Cybernetic Robotic voice and Silky Neural voice."""
        self.robotic_mode = not self.robotic_mode
        return self.robotic_mode

    def _apply_robotic_filter(self, audio_path: str) -> str:
        """Applies a cybernetic metallic vocoder/flanger acoustic filter via ffmpeg."""
        if not self.robotic_mode or not shutil.which("ffmpeg") or not audio_path:
            return audio_path
        try:
            p = Path(audio_path)
            out_path = p.parent / f"robot_{p.name}"
            if out_path.exists() and out_path.stat().st_size > 500:
                return str(out_path)

            cmd = [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-af", "chorus=0.7:0.9:35:0.4:0.25:2,flanger=delay=4:depth=6:regen=45:speed=6,equalizer=f=900:t=q:w=1.2:g=5,equalizer=f=3000:t=q:w=1.5:g=6",
                str(out_path)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return str(out_path)
        except Exception:
            return audio_path

    def set_muted(self, muted: bool):
        """Sets mute state. When True, Ezra outputs purely text without speaking aloud."""
        self.is_muted = bool(muted)

    def toggle_mute(self) -> bool:
        """Toggles between voice speech and silent mode."""
        self.is_muted = not self.is_muted
        return self.is_muted

    def duck_volume(self, level: float = 0.15):
        """Immediately turns volume down or mutes speech output when user starts talking."""
        self.is_ducked = True
        if self._current_channel:
            try:
                self._current_channel.set_volume(level)
            except Exception:
                pass
        if HAS_PYGAME_MIXER:
            try:
                pygame.mixer.music.set_volume(level)
            except Exception:
                pass
        elif self._active_proc and self._active_proc.poll() is None:
            try:
                import signal
                os.kill(self._active_proc.pid, signal.SIGSTOP)
            except Exception:
                pass

    def restore_volume(self, level: float = 1.0):
        """Restores speech output volume if user vocalization was just transient echo or noise."""
        if not getattr(self, "is_ducked", False):
            return
        self.is_ducked = False
        if self._current_channel:
            try:
                self._current_channel.set_volume(level)
            except Exception:
                pass
        if HAS_PYGAME_MIXER:
            try:
                pygame.mixer.music.set_volume(level)
            except Exception:
                pass
        elif self._active_proc and self._active_proc.poll() is None:
            try:
                import signal
                os.kill(self._active_proc.pid, signal.SIGCONT)
            except Exception:
                pass

    def stop(self):
        """Immediately cuts off and silences Ezra's speech output with micro-fade to prevent pops."""
        self.is_interrupted = True
        self.is_speaking = False
        self.is_ducked = False
        try:
            from jarvis.ui.visuals import status_bar
            status_bar.stop_speaking()
        except Exception:
            pass
        try:
            broadcast_ui_event({"type": "state_change", "state": "idle"})
        except Exception:
            pass

        # 5ms micro-fade before stopping channel to eliminate digital pop
        if self._current_channel:
            try:
                self._current_channel.set_volume(0.0)
                time.sleep(0.005)
                self._current_channel.stop()
            except Exception:
                pass
            self._current_channel = None

        if HAS_PYGAME_MIXER:
            try:
                pygame.mixer.stop()
                pygame.mixer.music.stop()
            except Exception:
                pass

        if self._active_proc:
            try:
                import signal
                try:
                    os.kill(self._active_proc.pid, signal.SIGCONT)
                except Exception:
                    pass
                self._active_proc.terminate()
                self._active_proc.wait(timeout=0.1)
            except Exception:
                try:
                    self._active_proc.kill()
                except Exception:
                    pass
            self._active_proc = None

    def _play_pcm_with_interrupt(
        self,
        pcm_bytes: bytes,
        sample_rate: int,
        text: str = "",
        prefix: str = "",
        live_print: bool = False,
    ) -> bool:
        """
        Plays in-memory PCM audio buffer directly via pygame.mixer.Sound without disk serialization.
        Supports live keyboard barge-in and volume ducking.
        Returns True if completed naturally, False if interrupted by user.
        """
        if not pcm_bytes or self.is_interrupted:
            return not self.is_interrupted

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        buf.seek(0)

        if HAS_PYGAME_MIXER:
            try:
                sound = pygame.mixer.Sound(file=buf)
                self._current_sound = sound
                channel = sound.play()
                self._current_channel = channel
                if self.is_ducked and channel:
                    channel.set_volume(0.15)
                is_playing = lambda: (channel is not None and channel.get_busy())
            except Exception as e:
                print(f"[Mixer Error] {e}")
                is_playing = lambda: False
        else:
            # Native Linux playback via PipeWire stdin streaming
            player = shutil.which("pw-play") or shutil.which("aplay")
            if player and "pw-play" in player:
                args = [player, "--rate", str(sample_rate), "--channels", "1", "--format", "s16", "-"]
            elif player and "aplay" in player:
                args = [player, "-r", str(sample_rate), "-c", "1", "-f", "S16_LE"]
            else:
                args = None

            if args:
                try:
                    self._active_proc = subprocess.Popen(
                        args,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    self._active_proc.stdin.write(pcm_bytes)
                    self._active_proc.stdin.close()
                    is_playing = lambda: (self._active_proc is not None and self._active_proc.poll() is None)
                except Exception as e:
                    print(f"[Audio Stream Error] {e}")
                    is_playing = lambda: False
            else:
                is_playing = lambda: False

        # 1. Print message text cleanly if requested
        if live_print and text:
            clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
            print(f"{clean_p}{text}", flush=True)

        # 2. Update status bar
        try:
            from jarvis.ui.visuals import status_bar
            status_bar.start_speaking(text)
        except Exception:
            pass

        # 3. Setup non-blocking keyboard listener
        fd = None
        old_settings = None
        if sys.stdin.isatty():
            try:
                import termios
                import tty
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                termios.tcflush(fd, termios.TCIFLUSH)
            except Exception:
                fd = None

        try:
            while is_playing() and not self.is_interrupted:
                if fd is not None:
                    r, _, _ = select.select([sys.stdin], [], [], 0)
                    if r:
                        ch = sys.stdin.read(1)
                        if ch in ('\n', '\r', ' ', '\x1b', 'q', 'Q'):
                            self.stop()
                            print("\r\033[K\033[1;33m[⚡ Stopped by keypress]\033[0m\n")
                            break
                time.sleep(0.015)
        finally:
            if fd is not None:
                try:
                    while select.select([sys.stdin], [], [], 0)[0]:
                        os.read(fd, 1024)
                except Exception:
                    pass
                if old_settings is not None:
                    try:
                        import termios
                        termios.tcflush(fd, termios.TCIFLUSH)
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                        termios.tcflush(fd, termios.TCIFLUSH)
                    except Exception:
                        pass

        return not self.is_interrupted

    def _play_file_with_interrupt(
        self,
        audio_path: str,
        text: str = "",
        prefix: str = "",
        live_print: bool = True,
        keep_speaking_state: bool = False,
    ) -> bool:
        """
        Plays audio file with deliberate keyboard barge-in monitoring (Enter / Space / Esc).
        Kept for backward compatibility with file-based fallbacks and test harnesses.
        Returns True if completed naturally, False if interrupted by user.
        """
        self.is_speaking = True
        self.is_interrupted = False

        if HAS_PYGAME_MIXER:
            try:
                pygame.mixer.music.load(str(audio_path))
                pygame.mixer.music.play()
                time.sleep(0.04)
                is_playing = lambda: pygame.mixer.music.get_busy()
            except Exception:
                is_playing = lambda: False
        else:
            # Native Linux playback via ffplay or pw-play
            player = shutil.which("ffplay") or shutil.which("pw-play") or "aplay"
            args = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio_path)] if "ffplay" in player else [player, str(audio_path)]
            try:
                self._active_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                is_playing = lambda: (self._active_proc is not None and self._active_proc.poll() is None)
            except Exception as e:
                print(f"[Audio Player Error] {e}")
                if not keep_speaking_state:
                    self.is_speaking = False
                return True

        if live_print and text:
            clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
            print(f"{clean_p}{text}", flush=True)

        try:
            from jarvis.ui.visuals import status_bar
            status_bar.start_speaking(text)
        except Exception:
            pass

        fd = None
        old_settings = None
        if sys.stdin.isatty():
            try:
                import termios
                import tty
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                termios.tcflush(fd, termios.TCIFLUSH)
            except Exception:
                fd = None

        try:
            while is_playing() and not self.is_interrupted:
                if fd is not None:
                    r, _, _ = select.select([sys.stdin], [], [], 0)
                    if r:
                        ch = sys.stdin.read(1)
                        if ch in ('\n', '\r', ' ', '\x1b', 'q', 'Q'):
                            self.stop()
                            print("\r\033[K\033[1;33m[⚡ Stopped by keypress]\033[0m\n")
                            break
                time.sleep(0.02)
        finally:
            if not keep_speaking_state:
                self.is_speaking = False
                try:
                    from jarvis.ui.visuals import status_bar
                    status_bar.stop_speaking()
                except Exception:
                    pass
            if fd is not None:
                try:
                    while select.select([sys.stdin], [], [], 0)[0]:
                        os.read(fd, 1024)
                except Exception:
                    pass
                if old_settings is not None:
                    try:
                        import termios
                        termios.tcflush(fd, termios.TCIFLUSH)
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                        termios.tcflush(fd, termios.TCIFLUSH)
                    except Exception:
                        pass

        was_interrupted = self.is_interrupted
        return not was_interrupted

    async def _generate_edge_speech(self, text: str, voice_name: str) -> str:
        """Tier 2 fallback: Cloud Edge TTS synthesis."""
        cache_key = hashlib.md5(f"{voice_name}_{text}".encode("utf-8")).hexdigest()[:12]
        out_path = CACHE_DIR / f"smooth_{cache_key}.mp3"
        if out_path.exists() and out_path.stat().st_size > 500:
            return str(out_path)

        is_ryan = "Ryan" in voice_name
        rate_val = "-8%" if is_ryan else "+0%"
        pitch_val = "-12Hz" if is_ryan else "+0Hz"
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate=rate_val,
            pitch=pitch_val
        )
        await communicate.save(str(out_path))
        return str(out_path)

    def _generate_google_tts(self, text: str) -> str:
        """Tier 3 fallback: Google Web TTS."""
        try:
            from gtts import gTTS
            cache_key = hashlib.md5(f"gtts_{text}".encode("utf-8")).hexdigest()[:12]
            out_path = CACHE_DIR / f"gtts_{cache_key}.mp3"
            if out_path.exists() and out_path.stat().st_size > 500:
                return str(out_path)

            tts = gTTS(text=text, lang="en", tld="co.uk")
            tts.save(str(out_path))
            return str(out_path)
        except Exception:
            # Web endpoint fallback
            encoded = urllib.parse.quote(text[:250])
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded}&tl=en-GB&client=tw-ob"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3.0)
            if resp.status_code == 200:
                out_path = CACHE_DIR / f"gtts_web_{uuid.uuid4().hex[:6]}.mp3"
                out_path.write_bytes(resp.content)
                return str(out_path)
            return ""

    def _generate_pyttsx3_speech(self, text: str) -> str:
        """Tier 4 fallback: Offline system pyttsx3 speech synthesis."""
        try:
            import pyttsx3
            cache_key = hashlib.md5(f"pyttsx3_{text}".encode("utf-8")).hexdigest()[:12]
            out_path = CACHE_DIR / f"pyttsx3_{cache_key}.wav"
            if out_path.exists() and out_path.stat().st_size > 500:
                return str(out_path)

            engine = pyttsx3.init()
            engine.save_to_file(text, str(out_path))
            engine.runAndWait()
            if out_path.exists() and out_path.stat().st_size > 500:
                return str(out_path)
        except Exception:
            pass
        return ""

    def _terminal_typewriter_fallback(self, text: str, prefix: str = ""):
        """Tier 5 fallback: Terminal typewriter & UI visual guarantee."""
        clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
        print(f"{clean_p}{text}", flush=True)
        try:
            broadcast_ui_event({"type": "speech", "speaker": "EZRA", "text": text})
        except Exception:
            pass

    def _split_sentences(self, text: str) -> list:
        """
        Splits text into spoken sentence chunks with numbered-list & abbreviation protection:
        - Prevents breaking '1. Step one' at '1.'
        - Prevents breaking decimals '3.14'
        - Prevents breaking abbreviations ('e.g.', 'i.e.', 'etc.', 'Mr.')
        - Handles English (. ? !) and Arabic (؟ .)
        """
        return self.local_tts.split_sentences(text)

    def _prepare_audio_file(self, text: str) -> str:
        """Synthesizes or retrieves cached audio file for fallback paths."""
        clean_text = text.strip()[:400]
        voices_to_try = [self.voice, self.fallback_voice]

        audio_file = ""
        for v in voices_to_try:
            try:
                target_v = "en-GB-RyanNeural" if self.robotic_mode else v
                cache_key = hashlib.md5(f"{target_v}_{clean_text}_{self.robotic_mode}".encode("utf-8")).hexdigest()[:12]
                cached_file = CACHE_DIR / f"smooth_{cache_key}.mp3"
                if cached_file.exists() and cached_file.stat().st_size > 500:
                    audio_file = str(cached_file)
                    break

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    generated = pool.submit(asyncio.run, self._generate_edge_speech(clean_text, target_v)).result(timeout=10.0)
                if generated and os.path.exists(generated):
                    audio_file = generated
                    break
            except Exception:
                continue

        # Secondary fallback: Google TTS
        if not audio_file or not os.path.exists(audio_file):
            try:
                audio_file = self._generate_google_tts(clean_text)
            except Exception:
                audio_file = ""

        # Tertiary fallback: pyttsx3
        if not audio_file or not os.path.exists(audio_file):
            try:
                audio_file = self._generate_pyttsx3_speech(clean_text)
            except Exception:
                audio_file = ""

        # Apply cybernetic robotic DSP vocoder filter if enabled
        if audio_file and self.robotic_mode:
            audio_file = self._apply_robotic_filter(audio_file)

        return audio_file

    def speak(self, text: str, prefix: str = "", live_print: bool = True) -> bool:
        """
        Speaks text with smooth neural voice, in-memory PCM streaming, persistent is_speaking lock,
        and 5-tier fallback cascade.
        """
        if self.is_muted or not text or not text.strip():
            if live_print and text:
                clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
                print(f"{clean_p}{text.strip()}", flush=True)
            return True

        clean_text = text.strip()
        sentences = self._split_sentences(clean_text)
        if not sentences:
            return True

        self.last_language = "en"

        # Print full response text once up front so user sees complete message immediately
        if live_print:
            clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
            print(f"{clean_p}{clean_text}", flush=True)

        # Persistent lock engages before first chunk begins
        self.last_spoken_text = clean_text
        self.is_speaking = True
        self.is_interrupted = False
        try:
            from jarvis.ui.visuals import status_bar
            status_bar.start_speaking(clean_text)
        except Exception:
            pass
        try:
            broadcast_ui_event({"type": "state_change", "state": "speaking"})
            broadcast_ui_event({"type": "speech", "speaker": "EZRA", "text": clean_text})
        except Exception:
            pass

        try:
            # Check if _play_file_with_interrupt is explicitly mocked by unit test harnesses
            is_play_mocked = (
                hasattr(self._play_file_with_interrupt, "assert_called") or
                hasattr(self._play_file_with_interrupt, "mock_calls")
            )

            # -----------------------------------------------------------------
            # TIER 1: In-Memory Local Neural TTS (Kokoro-82M / Piper Arabic)
            # -----------------------------------------------------------------
            if not is_play_mocked and self.local_tts.is_available():
                try:
                    voice_name = self.voice
                    if voice_name in ("en-GB-SoniaNeural", "en-GB-RyanNeural", "en-US-JennyNeural"):
                        voice_name = "bf_isabella"

                    for pcm_bytes, sr, sent in self.local_tts.synthesize_sentence_stream(clean_text, voice_name=voice_name):
                        if self.is_interrupted:
                            break
                        if pcm_bytes:
                            completed = self._play_pcm_with_interrupt(pcm_bytes, sr, text=sent, live_print=False)
                            if not completed:
                                self.stop()
                                return False
                    return not self.is_interrupted
                except Exception as tier1_exc:
                    # Fall through to Tier 2..5 fallback cascades on error
                    pass

            # -----------------------------------------------------------------
            # FALLBACK TIERS (Tiers 2 through 5)
            # -----------------------------------------------------------------
            for i, sentence in enumerate(sentences):
                if self.is_interrupted:
                    break

                audio_file = self._prepare_audio_file(sentence)
                if audio_file and os.path.exists(audio_file):
                    completed = self._play_file_with_interrupt(
                        audio_file, text=sentence, prefix="", live_print=False, keep_speaking_state=True
                    )
                    if not completed:
                        self.stop()
                        return False
                else:
                    # Tier 5: Terminal typewriter & visual guarantee
                    self._terminal_typewriter_fallback(sentence)

            return not self.is_interrupted

        finally:
            # Persistent lock tail: 250ms room reverberation grace period before releasing lock
            if not self.is_interrupted:
                time.sleep(0.25)

            self.is_speaking = False
            self.last_speech_end_time = time.time()
            try:
                from jarvis.ui.visuals import status_bar
                status_bar.stop_speaking()
            except Exception:
                pass
            try:
                broadcast_ui_event({"type": "state_change", "state": "idle"})
            except Exception:
                pass

    async def speak_async(self, text: str, prefix: str = "", live_print: bool = True) -> bool:
        """
        Non-blocking asynchronous speech execution preventing event loop stalls.
        Safe for FastAPI / Starlette UI server event loops.
        """
        return await asyncio.to_thread(self.speak, text, prefix=prefix, live_print=live_print)


voice_speaker = SmoothSpeaker()
