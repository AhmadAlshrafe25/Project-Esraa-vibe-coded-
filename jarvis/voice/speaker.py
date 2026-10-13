import os
import sys
import re
import time
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
import edge_tts
import requests
import urllib.parse
import pygame
from pathlib import Path
from config.settings import CACHE_DIR

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
    """Delivers silky smooth, natural human neural voice with instant responsiveness and zero robotic fallbacks."""

    def __init__(self, voice: str = "en-GB-SoniaNeural"):
        self.voice = voice  # Smooth British neural female voice (Sonia)
        self.fallback_voice = "en-US-JennyNeural"
        self.is_muted: bool = False
        self.is_speaking: bool = False
        self.is_interrupted: bool = False
        self.robotic_mode: bool = os.getenv("ROBOTIC_VOICE", "false").lower() in ("true", "1", "yes")
        self._active_proc = None

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

    def stop(self):
        """Immediately cuts off and silences Ezra's speech output."""
        self.is_interrupted = True
        self.is_speaking = False
        try:
            from jarvis.ui.visuals import status_bar
            status_bar.stop_speaking()
        except Exception:
            pass
        if HAS_PYGAME_MIXER:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        if self._active_proc:
            try:
                self._active_proc.terminate()
            except Exception:
                pass
            self._active_proc = None

    def _play_file_with_interrupt(self, audio_path: str, text: str = "", prefix: str = "", live_print: bool = True) -> bool:
        """Plays audio file with deliberate keyboard barge-in monitoring (Enter / Space / Esc).
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
                self.is_speaking = False
                return True

        # 1. Print message text cleanly if requested
        if live_print and text:
            clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
            print(f"{clean_p}{text}", flush=True)

        # 2. Start speaking status bar waveform
        from jarvis.ui.visuals import status_bar
        status_bar.start_speaking(text)

        # 3. Setup non-blocking keyboard listener with flushed buffer
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
            self.is_speaking = False
            status_bar.stop_speaking()
            # Drain any trailing bytes from multi-byte key/escape sequences (e.g. CSI u ^[[101;10u)
            if fd is not None:
                try:
                    while select.select([sys.stdin], [], [], 0)[0]:
                        os.read(fd, 1024)
                except Exception:
                    pass
            # Restore terminal attributes cleanly
            if fd is not None and old_settings is not None:
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
        # Cache identical phrases by MD5 so repeated phrases play with 0ms network latency
        cache_key = hashlib.md5(f"{voice_name}_{text}".encode("utf-8")).hexdigest()[:12]
        out_path = CACHE_DIR / f"smooth_{cache_key}.mp3"
        if out_path.exists() and out_path.stat().st_size > 500:
            return str(out_path)

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate="+6%",
            pitch="+0Hz"
        )
        await communicate.save(str(out_path))
        return str(out_path)

    def _generate_google_tts(self, text: str) -> str:
        """Neural British female voice fallback via Google TTS (smooth, non-robotic)."""
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

    def _split_sentences(self, text: str) -> list:
        """
        Splits text into spoken sentence chunks with numbered-list & abbreviation protection:
        - Prevents breaking '1. Step one' at '1.'
        - Prevents breaking decimals '3.14'
        - Prevents breaking abbreviations ('e.g.', 'i.e.', 'etc.', 'Mr.')
        - Handles English (. ? !) and Arabic (؟ .)
        """
        if not text:
            return []
        
        # Protect numbered list markers: '1. ', '2. ', '١. '
        t = re.sub(r"(\b\d+)\.(\s+)", r"\1__DOT__\2", text)
        t = re.sub(r"([\u0660-\u0669]+)\.(\s+)", r"\1__DOT__\2", t)
        
        # Protect abbreviations
        t = re.sub(r"\b(e\.g|i\.e|etc|mr|ms|mrs|dr|vs)\.", r"\1__DOT__", t, flags=re.IGNORECASE)
        
        # Split on sentence boundaries: . ! ? or Arabic ؟ or newlines
        raw_parts = re.split(r"(?<=[.!?؟\n])\s+", t)
        
        sentences = []
        for part in raw_parts:
            restored = part.replace("__DOT__", ".").strip()
            if restored:
                sentences.append(restored)
        return sentences or [text.strip()]

    def _prepare_audio_file(self, text: str) -> str:
        """Synthesizes or retrieves cached audio for a single sentence."""
        clean_text = text.strip()[:400]
        has_arabic = bool(re.search(r"[\u0600-\u06FF]", clean_text))
        voices_to_try = ["ar-JO-SanaNeural", "ar-EG-SalmaNeural"] if has_arabic else [self.voice, self.fallback_voice]

        audio_file = ""
        for v in voices_to_try:
            try:
                target_v = "en-GB-RyanNeural" if (self.robotic_mode and not has_arabic) else v
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

        # Apply cybernetic robotic DSP vocoder filter if enabled
        if audio_file and self.robotic_mode:
            audio_file = self._apply_robotic_filter(audio_file)

        return audio_file

    def speak(self, text: str, prefix: str = "", live_print: bool = True) -> bool:
        """Speaks with smooth, human neural voice with instant sentence-by-sentence streaming
        and live barge-in interruption. Guarantees zero robotic voices.
        """
        if self.is_muted or not text or not text.strip():
            if live_print and text:
                clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
                print(f"{clean_p}{text.strip()}", flush=True)
            return True

        sentences = self._split_sentences(text.strip())
        if not sentences:
            return True

        if len(sentences) == 1:
            audio_file = self._prepare_audio_file(sentences[0])
            if audio_file and os.path.exists(audio_file):
                return self._play_file_with_interrupt(audio_file, text=sentences[0], prefix=prefix, live_print=live_print)
            elif live_print:
                clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
                print(f"{clean_p}{sentences[0]}", flush=True)
            return True

        # Multi-Sentence Streaming:
        # Print full response text once up front so user sees complete message immediately
        if live_print and text:
            clean_p = prefix if (not prefix or prefix.endswith(" ")) else (prefix + " ")
            print(f"{clean_p}{text.strip()}", flush=True)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        next_future = executor.submit(self._prepare_audio_file, sentences[0])

        for i, sentence in enumerate(sentences):
            if self.is_interrupted:
                break

            try:
                audio_file = next_future.result(timeout=10.0)
            except Exception:
                audio_file = ""

            # Launch prefetch of next sentence immediately
            if i + 1 < len(sentences) and not self.is_interrupted:
                next_future = executor.submit(self._prepare_audio_file, sentences[i + 1])

            if audio_file and os.path.exists(audio_file):
                completed = self._play_file_with_interrupt(audio_file, text=sentence, prefix="", live_print=False)
                if not completed:
                    self.stop()
                    executor.shutdown(wait=False, cancel_futures=True)
                    return False

        executor.shutdown(wait=False)
        self.is_speaking = False
        try:
            from jarvis.ui.visuals import status_bar
            status_bar.stop_speaking()
        except Exception:
            pass
        return not self.is_interrupted

voice_speaker = SmoothSpeaker()
