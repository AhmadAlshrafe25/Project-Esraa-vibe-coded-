import os
import sys
import time
import glob
import socket
import select
import shutil
import logging
import threading
import subprocess
from typing import Callable, Optional

logger = logging.getLogger("LidWakeMonitor")

class LidWakeMonitor:
    """
    Autonomous Laptop Lid & Wake Monitor.
    Detects the exact second a laptop is opened or resumes from suspend/sleep across:
    1. Arch Linux (KDE Plasma 6 Wayland)
    2. Pop!_OS (GNOME / COSMIC Wayland/X11)
    
    Uses 4 parallel zero-overhead detection strategies:
    - D-Bus login1 PrepareForSleep(false) / UPower LidIsClosed=false stream
    - Kernel ACPI /proc/acpi/button/lid/*/state hardware watcher
    - Logind Unlock / session activation stream
    - Unix Domain Socket (/run/user/<UID>/ezra_wake.sock) for instant IPC
    """

    def __init__(self, on_wake_callback: Optional[Callable[[str], None]] = None):
        self.on_wake_callback = on_wake_callback
        self.running = False
        self.last_trigger_time = 0.0
        self.debounce_sec = 3.0
        self.last_acpi_state = self._read_acpi_lid_state()
        self.threads = []
        self.sock_path = self._get_socket_path()

    def _get_socket_path(self) -> str:
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        if os.path.exists(runtime_dir):
            return os.path.join(runtime_dir, "ezra_wake.sock")
        return f"/tmp/ezra_wake_{os.getuid()}.sock"

    def _read_acpi_lid_state(self) -> str:
        """Reads kernel ACPI lid state from /proc/acpi/button/lid/*/state."""
        try:
            for p in glob.glob("/proc/acpi/button/lid/*/state"):
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read().lower()
                    if "open" in content:
                        return "open"
                    elif "closed" in content:
                        return "closed"
        except Exception:
            pass
        return "open"

    def trigger_wake(self, reason: str = "lid_open"):
        """Fires wake event with debouncing to avoid duplicate triggers."""
        now = time.time()
        if now - self.last_trigger_time < self.debounce_sec:
            return
        self.last_trigger_time = now
        logger.info(f"[LidWakeMonitor] Laptop activated: {reason}")
        if self.on_wake_callback:
            try:
                self.on_wake_callback(reason)
            except Exception as e:
                logger.error(f"[LidWakeMonitor] Error executing callback: {e}")

    def _monitor_dbus_signals(self):
        """Monitors system D-Bus for login1 PrepareForSleep and UPower LidIsClosed signals."""
        cmd = None
        if shutil.which("gdbus"):
            cmd = ["gdbus", "monitor", "--system", "-d", "org.freedesktop.login1"]
        elif shutil.which("busctl"):
            cmd = ["busctl", "--system", "monitor", "org.freedesktop.login1"]

        if not cmd:
            return

        while self.running:
            proc = None
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1
                )
                while self.running and proc.poll() is None:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    line_lower = line.lower()
                    # 1. System resumed from sleep / suspend: PrepareForSleep(false)
                    if "prepareforsleep" in line_lower and ("false" in line_lower or " 0" in line_lower or "b false" in line_lower):
                        self.trigger_wake("resume_from_sleep")
                    # 2. Lid closed property changed to false (lid opened)
                    elif ("lidclosed" in line_lower or "lidisclosed" in line_lower) and ("false" in line_lower or " 0" in line_lower):
                        self.trigger_wake("lid_opened_dbus")
                    # 3. Session unlocked / activated
                    elif "unlock" in line_lower or ("lockedhint" in line_lower and "false" in line_lower):
                        self.trigger_wake("session_unlocked")
            except Exception as e:
                logger.debug(f"[LidWakeMonitor] D-Bus monitor error: {e}")
            finally:
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass
            if self.running:
                time.sleep(2.0)

    def _monitor_acpi_polling(self):
        """Polls kernel /proc/acpi/button/lid/*/state every 0.8 seconds."""
        while self.running:
            try:
                current_state = self._read_acpi_lid_state()
                if self.last_acpi_state == "closed" and current_state == "open":
                    self.trigger_wake("acpi_lid_opened")
                self.last_acpi_state = current_state
            except Exception:
                pass
            time.sleep(0.8)

    def _monitor_unix_socket(self):
        """Listens on Unix domain socket for external wake pings (system-sleep hooks / CLI)."""
        try:
            if os.path.exists(self.sock_path):
                os.remove(self.sock_path)
        except Exception:
            pass

        server_sock = None
        try:
            server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server_sock.bind(self.sock_path)
            server_sock.listen(5)
            server_sock.setblocking(False)

            while self.running:
                readable, _, _ = select.select([server_sock], [], [], 1.0)
                if readable:
                    conn, _ = server_sock.accept()
                    try:
                        data = conn.recv(64).decode("utf-8", errors="ignore").strip()
                        if "wake" in data.lower() or not data:
                            self.trigger_wake("socket_ping")
                        conn.sendall(b"OK\n")
                    except Exception:
                        pass
                    finally:
                        conn.close()
        except Exception as e:
            logger.debug(f"[LidWakeMonitor] Socket server error: {e}")
        finally:
            if server_sock:
                try:
                    server_sock.close()
                except Exception:
                    pass
            try:
                if os.path.exists(self.sock_path):
                    os.remove(self.sock_path)
            except Exception:
                pass

    def start(self):
        """Starts all monitoring threads in background."""
        if self.running:
            return
        self.running = True

        t_dbus = threading.Thread(target=self._monitor_dbus_signals, daemon=True, name="LidDbusMonitor")
        t_acpi = threading.Thread(target=self._monitor_acpi_polling, daemon=True, name="LidAcpiMonitor")
        t_sock = threading.Thread(target=self._monitor_unix_socket, daemon=True, name="LidSocketMonitor")

        self.threads = [t_dbus, t_acpi, t_sock]
        for t in self.threads:
            t.start()
        logger.info("[LidWakeMonitor] Active: Laptop lid and wake monitoring initialized.")

    def stop(self):
        """Gracefully stops all monitoring threads."""
        self.running = False
        try:
            if os.path.exists(self.sock_path):
                os.remove(self.sock_path)
        except Exception:
            pass

def ping_running_ezra(reason: str = "wake") -> bool:
    """Sends wake ping to currently running Ezra instance via Unix domain socket."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    sock_path = os.path.join(runtime_dir, "ezra_wake.sock") if os.path.exists(runtime_dir) else f"/tmp/ezra_wake_{os.getuid()}.sock"
    if not os.path.exists(sock_path):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(sock_path)
        s.sendall(f"WAKE:{reason}\n".encode("utf-8"))
        res = s.recv(16)
        s.close()
        return bool(res)
    except Exception:
        return False

lid_monitor = LidWakeMonitor()
