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
    """Launches Project Esraa in native standalone desktop window mode."""
    url = f"http://{HOST}:{PORT}"
    time.sleep(1.2)  # Give uvicorn a moment to bind

    # 1. Try PyWebView if available
    try:
        import webview
        print("[+] Launching native PyWebView HUD Window...")
        webview.create_window(
            title="PROJECT ESRAA // AUTONOMOUS HUD",
            url=url,
            width=1280,
            height=820,
            resizable=True,
            frameless=False,
            easy_drag=True
        )
        webview.start()
        return
    except ImportError:
        pass
    except Exception as e:
        print(f"[!] PyWebView failed: {e}")

    # 2. Try Chrome / Chromium App Mode (frameless native window)
    for browser in ["google-chrome", "chromium-browser", "chromium"]:
        if os.system(f"which {browser} >/dev/null 2>&1") == 0:
            print(f"[+] Launching via {browser} Native App Mode...")
            subprocess.run([browser, f"--app={url}", "--window-size=1280,820"])
            return

    # 3. Firefox native window
    if os.system("which firefox >/dev/null 2>&1") == 0:
        print("[+] Launching via Firefox Native Window...")
        subprocess.run(["firefox", "--new-window", url])
        return

    # 4. Fallback default desktop opener
    subprocess.run(["xdg-open", url])

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
