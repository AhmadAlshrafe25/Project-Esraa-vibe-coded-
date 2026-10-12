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
    def moving_print(text: str, prefix: str = "", delay: float = 0.012):
        """Prints text smoothly like an active sci-fi interface typewriter."""
        if prefix:
            sys.stdout.write(prefix)
            sys.stdout.flush()
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(delay)
        sys.stdout.write("\n")
        sys.stdout.flush()

visualizer = BrainVisualizer()
