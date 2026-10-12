import sys
import uvicorn
from config.settings import HOST, PORT

def main():
    print("=" * 60)
    print("  PROJECT ESRAA // AUTONOMOUS NEURAL DESKTOP ASSISTANT")
    print("=" * 60)
    print(f"  [+] Initializing Core Modules...")
    print(f"  [+] Voice Engine: British Female Neural (Sonia / Edge-TTS)")
    print(f"  [+] Web HUD Dashboard: http://{HOST}:{PORT}")
    print("=" * 60)
    uvicorn.run("jarvis.server:app", host=HOST, port=PORT, reload=True)

if __name__ == "__main__":
    main()
