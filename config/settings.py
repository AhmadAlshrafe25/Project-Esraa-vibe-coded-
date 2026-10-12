import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# LLM Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Voice Settings (Default: Sonia British neural female voice)
DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "en-GB-SoniaNeural")
VOICE_RATE = os.getenv("VOICE_RATE", "+0%")
VOICE_PITCH = os.getenv("VOICE_PITCH", "+0Hz")

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
