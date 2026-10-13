import sys
import time
import threading

class BrainVisualizer:
    """Renders terminal animations, typewriter effects, and the animated Neural Brain with a glowing Yellow Sphere."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None

    def _animate(self, label: str):
        # Yellow sphere pulsating / rotating inside the neural brain
        frames = [
            (
                "\033[1;36m  .---.\033[0m   \033[1;33m( 🟡 )\033[0m   \033[1;36m.---.\033[0m\n"
                "\033[1;36m /     \\  \033[1;33m[  ●  ]\033[0m  /     \\\033[0m\n"
                "\033[1;36m|   \\   \\ \033[1;33m( ◈ )\033[0m /   /   |\033[0m\n"
                f"\033[1;33m [⚡ AGENT INITIALIZING: {label} ⚡]\033[0m"
            ),
            (
                "\033[1;36m  .---.\033[0m   \033[1;33m(  ●  )\033[0m   \033[1;36m.---.\033[0m\n"
                "\033[1;36m /     \\  \033[1;33m[ 🟡 ]\033[0m  /     \\\033[0m\n"
                "\033[1;36m|   \\   \\ \033[1;33m( ◉ )\033[0m /   /   |\033[0m\n"
                f"\033[1;33m [⚡ AGENT THINKING: {label} ⚡]\033[0m"
            ),
            (
                "\033[1;36m  .---.\033[0m   \033[1;33m( ◈ )\033[0m   \033[1;36m.---.\033[0m\n"
                "\033[1;36m /     \\  \033[1;33m[  ◉  ]\033[0m  /     \\\033[0m\n"
                "\033[1;36m|   \\   \\ \033[1;33m( 🟡 )\033[0m /   /   |\033[0m\n"
                f"\033[1;33m [⚡ AGENT EXECUTING: {label} ⚡]\033[0m"
            ),
            (
                "\033[1;36m  .---.\033[0m   \033[1;33m( ◉ )\033[0m   \033[1;36m.---.\033[0m\n"
                "\033[1;36m /     \\  \033[1;33m[ 🟡 ]\033[0m  /     \\\033[0m\n"
                "\033[1;36m|   \\   \\ \033[1;33m(  ●  )\033[0m /   /   |\033[0m\n"
                f"\033[1;33m [⚡ AGENT DISPATCHING: {label} ⚡]\033[0m"
            )
        ]

        idx = 0
        first_draw = True
        while not self._stop_event.is_set():
            frame = frames[idx % len(frames)]
            idx += 1

            if not first_draw:
                # Move cursor up 4 lines
                sys.stdout.write("\033[4A\r")
            else:
                first_draw = False

            sys.stdout.write(frame + "\n")
            sys.stdout.flush()
            time.sleep(0.18)

        # Clear animation lines upon stopping
        if not first_draw:
            sys.stdout.write("\033[4A\r\033[J")
            sys.stdout.flush()

    def start_agent_brain(self, label: str = "Neural Core"):
        """Starts animated brain visualization with pulsating yellow sphere."""
        self.stop_agent_brain()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, args=(label,), daemon=True)
        self._thread.start()

    def stop_agent_brain(self):
        """Stops animated brain visualization cleanly."""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=0.5)
            self._thread = None

    @staticmethod
    def moving_print(text: str, prefix: str = "", delay: float = 0.012, stop_check=None):
        """Prints text smoothly like an active sci-fi interface typewriter, with instant cancellation support."""
        if prefix:
            sys.stdout.write(prefix)
            sys.stdout.flush()
        for char in text:
            if stop_check and stop_check():
                break
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(delay)
        if not (stop_check and stop_check()):
            sys.stdout.write("\n")
            sys.stdout.flush()

visualizer = BrainVisualizer()


class StatusBar:
    """
    Real-time Terminal Status Bar for Project Ezra:
    - ⚡ THINKING: Smooth animated futuristic loading bar.
    - 🔊 SPEAKING: Glowing audio output waveform indicator.
    - 🎙️ LISTENING: High-speed real-time VU energy meter with instant mic handover.
    """

    def __init__(self):
        self._thinking_event = threading.Event()
        self._thinking_thread = None
        self._speaking_event = threading.Event()
        self._speaking_thread = None
        self._lock = threading.Lock()

    def start_thinking(self, label: str = "Reasoning with AI..."):
        """Starts animated futuristic loading bar while thinking."""
        self.stop_all()
        self._thinking_event.clear()

        def _think_loop():
            bars = [
                "|█░░░░░░░░░░░░░░░|",
                "|███░░░░░░░░░░░░░|",
                "|██████░░░░░░░░░░|",
                "|█████████░░░░░░░|",
                "|████████████░░░░|",
                "|███████████████░|",
                "|████████████████|",
                "|░███████████████|",
                "|░░░█████████████|",
                "|░░░░░░██████████|",
                "|░░░░░░░░░███████|",
                "|░░░░░░░░░░░░████|",
                "|░░░░░░░░░░░░░░░█|"
            ]
            idx = 0
            while not self._thinking_event.is_set():
                bar = bars[idx % len(bars)]
                sys.stdout.write(f"\r\033[1;33m[⚡ Thinking   {bar} ({label})]\033[0m\033[K")
                sys.stdout.flush()
                idx += 1
                time.sleep(0.08)

        self._thinking_thread = threading.Thread(target=_think_loop, daemon=True, name="ThinkingBar")
        self._thinking_thread.start()

    def stop_thinking(self):
        """Stops thinking animation and clears line."""
        if self._thinking_thread and self._thinking_thread.is_alive():
            self._thinking_event.set()
            self._thinking_thread.join(timeout=0.2)
            self._thinking_thread = None
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def start_speaking(self, phrase_snippet: str = ""):
        """Displays active speaking status bar."""
        self.stop_all()
        self._speaking_event.clear()

        def _speak_loop():
            waves = [
                "| ▃▅▇█▇▅▃ |",
                "| ▅▇█▇▅▃  |",
                "| ▇█▇▅▃  ▃|",
                "| █▇▅▃  ▃▅|",
                "| ▇▅▃  ▃▅▇|",
                "| ▅▃  ▃▅▇█|",
                "| ▃  ▃▅▇█▇|"
            ]
            idx = 0
            disp = phrase_snippet[:35] if phrase_snippet else "Ezra active"
            while not self._speaking_event.is_set():
                wave_str = waves[idx % len(waves)]
                sys.stdout.write(f"\r\033[1;35m[🔊 Speaking   {wave_str} ({disp}...)]\033[0m\033[K")
                sys.stdout.flush()
                idx += 1
                time.sleep(0.10)

        self._speaking_thread = threading.Thread(target=_speak_loop, daemon=True, name="SpeakingBar")
        self._speaking_thread.start()

    def stop_speaking(self):
        """Stops speaking indicator."""
        if self._speaking_thread and self._speaking_thread.is_alive():
            self._speaking_event.set()
            self._speaking_thread.join(timeout=0.2)
            self._speaking_thread = None
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def render_listening(self, level: int = 0, is_heard: bool = False):
        """Renders live mic status bar with instant responsiveness."""
        clamped = max(0, min(10, level))
        meter_bar = "█" * clamped + "░" * (10 - clamped)
        if is_heard:
            sys.stdout.write(f"\r\033[1;32m[🎙️ Heard You  |{meter_bar}| (Capturing voice...)]\033[0m\033[K")
        else:
            sys.stdout.write(f"\r\033[1;36m[🎙️ Mic Live   |{meter_bar}| (Speak freely)]\033[0m\033[K")
        sys.stdout.flush()

    def clear(self):
        self.stop_all()
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def stop_all(self):
        if self._thinking_thread and self._thinking_thread.is_alive():
            self._thinking_event.set()
            self._thinking_thread.join(timeout=0.2)
            self._thinking_thread = None
        if self._speaking_thread and self._speaking_thread.is_alive():
            self._speaking_event.set()
            self._speaking_thread.join(timeout=0.2)
            self._speaking_thread = None


status_bar = StatusBar()
