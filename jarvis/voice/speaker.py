import os
import sys
import time
import math
import struct
import uuid
import select
import asyncio
import subprocess
import threading
import edge_tts
import requests
import urllib.parse
import pygame
from pathlib import Path
import pyttsx3
from config.settings import CACHE_DIR

# Initialize lightweight audio mixer
try:
    pygame.mixer.pre_init(24000, -16, 2, 512)
    pygame.mixer.init()
except Exception:
    try:
        pygame.mixer.init()
    except Exception as e:
        print(f"[Mixer Init] {e}")

class SmoothSpeaker:
    """Delivers silky smooth, natural human neural voice with full-duplex interruption (barge-in) support."""

    def __init__(self, voice: str = "en-GB-SoniaNeural"):
        self.voice = voice  # Smooth British neural female voice (Sonia)
        self.fallback_voice = "en-US-JennyNeural"
        self._offline_engine = None
        self.is_muted: bool = False
        self.is_speaking: bool = False
        self.is_interrupted: bool = False

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
            pygame.mixer.music.stop()
        except Exception:
            pass

    def _init_offline(self):
        if not self._offline_engine:
            self._offline_engine = pyttsx3.init()
            self._offline_engine.setProperty('voice', 'en-gb+f3')
            self._offline_engine.setProperty('rate', 175)

    def _play_file_with_interrupt(self, audio_path: str, text: str = "", prefix: str = "", live_print: bool = True) -> bool:
        """Plays audio file with active full-duplex barge-in monitoring (keyboard tap or microphone speech).
        Returns True if completed naturally, False if interrupted by user.
        """
        self.is_speaking = True
        self.is_interrupted = False

        try:
            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.play()
        except Exception as e:
            print(f"[Playback Load Error] {e}")
            self.is_speaking = False
            return True

        # 1. Start live synchronized typewriter in background thread
        print_thread = None
        if live_print and text:
            from jarvis.ui.visuals import visualizer
            print_thread = threading.Thread(
                target=visualizer.moving_print,
                args=(text,),
                kwargs={"prefix": prefix, "delay": 0.015, "stop_check": lambda: self.is_interrupted},
                daemon=True
            )
            print_thread.start()

        # 2. Setup non-blocking keyboard listener
        fd = None
        old_settings = None
        if sys.stdin.isatty():
            try:
                import termios
                import tty
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                tty.setcbreak(fd)
            except Exception:
                fd = None

        # 3. Setup microphone barge-in process
        mic_proc = None
        try:
            mic_proc = subprocess.Popen(
                ["arecord", "-D", "default", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "raw", "-q"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            mic_proc = None

        calibration = []
        baseline_bleed = 1000.0
        consecutive_voice_chunks = 0
        start_time = time.time()

        try:
            while pygame.mixer.music.get_busy() and not self.is_interrupted:
                # A. Check Keyboard Tap (instant cut-off on Enter / Space / any key)
                if fd is not None:
                    r, _, _ = select.select([sys.stdin], [], [], 0)
                    if r:
                        sys.stdin.read(1)
                        self.stop()
                        print("\r\033[K\033[1;33m[⚡ CUT OFF by keypress — Ezra stopped talking]\033[0m\n")
                        break

                # B. Check Microphone Voice Interruption
                if mic_proc and mic_proc.stdout:
                    try:
                        chunk = mic_proc.stdout.read(2560)
                        if chunk and len(chunk) >= 2:
                            count = len(chunk) // 2
                            samples = struct.unpack(f"<{count}h", chunk[:count * 2])
                            rms = math.sqrt(sum(s * s for s in samples) / count)

                            elapsed = time.time() - start_time
                            if elapsed < 0.25:
                                calibration.append(rms)
                                if len(calibration) >= 3:
                                    baseline_bleed = sum(calibration) / len(calibration)
                            else:
                                if baseline_bleed < 2500:
                                    voice_threshold = max(baseline_bleed * 1.5, 3800.0)
                                else:
                                    voice_threshold = max(baseline_bleed * 1.35, 27000.0)

                                if rms > voice_threshold:
                                    consecutive_voice_chunks += 1
                                    if consecutive_voice_chunks >= 2:  # ~160ms of continuous human voice
                                        self.stop()
                                        print("\r\033[K\033[1;33m[⚡ CUT OFF by your voice — Listening to you!]\033[0m\n")
                                        break
                                else:
                                    consecutive_voice_chunks = 0
                    except Exception:
                        pass

                time.sleep(0.015)

        finally:
            # Restore terminal attributes cleanly
            if fd is not None and old_settings is not None:
                try:
                    import termios
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass

            # Terminate mic process cleanly
            if mic_proc:
                mic_proc.terminate()
                try:
                    mic_proc.wait(timeout=0.2)
                except Exception:
                    mic_proc.kill()

        was_interrupted = self.is_interrupted
        self.is_speaking = False

        if print_thread and print_thread.is_alive():
            print_thread.join(timeout=0.2)

        return not was_interrupted

    async def _generate_edge_speech(self, text: str, voice_name: str) -> str:
        out_path = CACHE_DIR / f"smooth_{uuid.uuid4().hex[:6]}.mp3"
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice_name,
            rate="+5%",
            pitch="+0Hz"
        )
        await communicate.save(str(out_path))
        return str(out_path)

    def speak(self, text: str, prefix: str = "", live_print: bool = True) -> bool:
        """Speaks with smooth human neural voice with instant interruption (barge-in) support.
        Returns True if speech completed normally, False if interrupted by the user.
        """
        if self.is_muted or not text or not text.strip():
            if live_print and text:
                from jarvis.ui.visuals import visualizer
                visualizer.moving_print(text, prefix=prefix)
            return True

        clean_text = text.strip()[:400]

        # 1. Primary: Silky Smooth Neural Voice via Edge-TTS
        for v in [self.voice, self.fallback_voice]:
            try:
                loop = asyncio.new_event_loop()
                audio_file = loop.run_until_complete(
                    asyncio.wait_for(self._generate_edge_speech(clean_text, v), timeout=3.0)
                )
                loop.close()
                if audio_file and os.path.exists(audio_file):
                    return self._play_file_with_interrupt(audio_file, text=clean_text, prefix=prefix, live_print=live_print)
            except Exception:
                continue

        # 2. Secondary smooth fallback (Google TTS)
        try:
            encoded_text = urllib.parse.quote(clean_text[:250])
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_text}&tl=en-GB&client=tw-ob"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.0)
            if resp.status_code == 200:
                audio_path = CACHE_DIR / f"tts_{uuid.uuid4().hex[:6]}.mp3"
                audio_path.write_bytes(resp.content)
                return self._play_file_with_interrupt(str(audio_path), text=clean_text, prefix=prefix, live_print=live_print)
        except Exception:
            pass

        # 3. Offline fallback
        try:
            if live_print and clean_text:
                from jarvis.ui.visuals import visualizer
                visualizer.moving_print(clean_text, prefix=prefix)
            self._init_offline()
            self._offline_engine.say(clean_text)
            self._offline_engine.runAndWait()
            return True
        except Exception as e:
            print(f"[TTS Fallback Error] {e}")
            return True

voice_speaker = SmoothSpeaker()
