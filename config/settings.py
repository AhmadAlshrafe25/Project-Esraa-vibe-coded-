import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# LLM & External Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Amman")

# Voice Settings (Default: Sonia British neural female voice)
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "en-GB-SoniaNeural")
VOICE_RATE = os.getenv("VOICE_RATE", "+0%")
VOICE_PITCH = os.getenv("VOICE_PITCH", "+0Hz")
VOICE_MUTED = os.getenv("VOICE_MUTED", "False").lower() in ("true", "1", "yes")
ROBOTIC_VOICE = os.getenv("ROBOTIC_VOICE", "False").lower() in ("true", "1", "yes")

# Musa Turn-Taking & Silence Endpointing Specification
END_SIL = float(os.getenv("END_SIL", "2.4"))                      # 2.4s pause after >1.2s speech before Ezra takes turn
SHORT_SIL = float(os.getenv("SHORT_SIL", "1.8"))                  # 1.8s pause after short replies before Ezra takes turn
MAX_UTT = float(os.getenv("MAX_UTT", "60.0"))                     # 60s max continuous utterance hard cap
MIN_SPEECH = float(os.getenv("MIN_SPEECH", "0.35"))               # 0.35s minimum speech accepted; shorter discarded as noise
PRE_BUFFER_SEC = float(os.getenv("PRE_BUFFER_SEC", "0.40"))       # 0.40s pre-speech ring buffer so opening consonant is never cut
SPEECH_LONG_THRESHOLD = float(os.getenv("SPEECH_LONG_THRESHOLD", "1.2")) # 1.2s speech threshold split
NEED_ON_IDLE = float(os.getenv("NEED_ON_IDLE", "0.15"))           # 0.15s sound needed to start a turn when idle or speaking
NEED_ON_WORKING = float(os.getenv("NEED_ON_WORKING", "0.30"))     # 0.30s sound needed while working so own sounds don't trigger
NEED_ON_GUEST = float(os.getenv("NEED_ON_GUEST", "0.20"))         # 0.20s sound needed for guests
ANSWER_ONLY_ON_WAKE = os.getenv("ANSWER_ONLY_ON_WAKE", "False").lower() in ("true", "1", "yes") # Answer only when wake word used
PUSH_TO_TALK = os.getenv("PUSH_TO_TALK", "False").lower() in ("true", "1", "yes")               # Push to talk mode (hold key)

# Application & Media
DEFAULT_BROWSER = os.getenv("DEFAULT_BROWSER", "")
DEFAULT_MEDIA_PLAYER = os.getenv("DEFAULT_MEDIA_PLAYER", "vlc")

# Comms (Telegram & Email)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")

# Server config
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# Directories
STATIC_DIR = PROJECT_ROOT / "jarvis" / "static"
CACHE_DIR = PROJECT_ROOT / "cache"
LOGS_DIR = PROJECT_ROOT / "logs"

CACHE_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
