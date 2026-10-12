import sys
import os
import subprocess
import time
import threading
import uvicorn
from config.settings import HOST, PORT

def start_backend():
    uvicorn.run("jarvis.server:app", host=HOST, port=PORT, log_level="warning")

def launch_desktop_window():
    """Launches Project Esraa in a clean dedicated desktop window."""
    url = f"http://{HOST}:{PORT}"
    
    # 1. Chrome / Chromium App Mode (standalone app window)
    for browser in ["google-chrome", "chromium-browser", "chromium"]:
        if os.system(f"which {browser} >/dev/null 2>&1") == 0:
            print(f"[+] Launching via {browser} Native App Mode...")
            subprocess.Popen([browser, f"--app={url}", "--window-size=1280,820", "--class=ProjectEsraa"])
            return

    # 2. Firefox standalone application window
    if os.system("which firefox >/dev/null 2>&1") == 0:
        print("[+] Launching via Firefox Desktop Window...")
        subprocess.Popen(["firefox", "--new-window", url])
        return

    # 3. Default opener
    subprocess.Popen(["xdg-open", url])

def main():
    print("=" * 65)
    print("  PROJECT ESRAA // DESKTOP NEURAL APPLICATION")
    print("=" * 65)
    print(f"  [+] Voice: British Female Neural Engine")
    print(f"  [+] Brain: Gemini 2.0 Flash Initialized")
    print(f"  [+] Storage: Local SQLite & Memory System Loaded")
    print(f"  [+] Launching Desktop Interface...")
    print("=" * 65)

    backend_thread = threading.Thread(target=start_backend, daemon=True)
    backend_thread.start()

    # Launch desktop window on the user's graphical display
    launch_desktop_window()

if __name__ == "__main__":
    main()
