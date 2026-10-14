# Project Ezra

> **"All systems operational and ready, sir."**  
> An autonomous, ultra-efficient, 100% free AI desktop companion.

---

## ⚡ Vision & Architecture
Project Ezra delivers a production-grade, local, conversational companion without recurring cloud costs:
- **Streaming Neural Voice (<250ms TTS):** In-memory 24kHz British neural voice synthesis with native PipeWire/Pygame audio.
- **Hands-Free Conversation Engine:** Wake word (`"Ezra"`), intelligent conversational dwell window, and instant sleep commands (`"go to sleep"`, `"stop listening"`).
- **Vocal Genetic Biometrics (3 Tiers):** Pure NumPy 48-dimensional spectral timbre embeddings + F0 pitch tracker. Gated action access:
  - **Tier 1 (Verified Master):** Full desktop automation, terminal, messaging, git.
  - **Tier 2 (Unsure):** Challenge with secret passphrase (`"protocol zero"`).
  - **Tier 3 (Guest):** Safe conversational banter and read-only queries only.
- **Executive Morning Briefing (`/brief`):** Spoken and visual digest of Amman weather, system metrics, git repository cleanliness, and top tech news.
- **Git Developer Voice Workflow:** Voice & CLI commands to inspect status (`/git status`), review history (`/git log`), and stage/commit/push (`/git publish`).
- **Autonomous Deep Web Research:** Zero-cost multi-source DuckDuckGo web scraping and executive synthesis.
- **Offline Resilience:** Seamless fallback cascade: Gemini 2.0 Flash → Groq Llama 3.3 → Local Ollama → Smart OS Reflexes.
- **Two-Way Telegram Remote Control:** Free mobile companion via long-polling (status, live desktop screenshots, broadcast speech, remote shell).

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone git@github.com:AhmadAlshrafe25/Project-Ezra-vibe-coded-.git
cd Project-Ezra-vibe-coded-
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure Free Keys (`.env`)
```env
GEMINI_API_KEY=your_free_key_from_aistudio.google.com
DEFAULT_CITY=Amman
```

### 3. Launch Ezra
```bash
./run_ezra.sh
# Or: ./venv/bin/python3 app.py
```

### 4. Enable Instant Laptop Auto-Activation (Arch Linux & Pop!_OS)
To have Ezra activate the exact second you open your laptop lid or wake from sleep on either laptop:
```bash
./install_autostart_daemon.sh
```
This automatically configures:
- **Systemd User Service**: Starts Ezra in the background upon boot and login.
- **Hardware Lid & Wake Monitor**: Uses D-Bus `login1` and kernel ACPI to detect physical lid opening and resume from sleep in under 5 milliseconds.
- **Dual-Distro Parity**: Seamlessly supported on both **Arch Linux** (KDE Plasma 6 Wayland) and **Pop!_OS** (GNOME / COSMIC Wayland/X11).

---

## 📱 Two-Way Telegram Remote Link Setup (100% Free)

You can remotely check system health, take desktop screenshots, and talk to Ezra from anywhere via your phone:

1. **Create your Bot on Telegram:**
   - Open Telegram and search for `@BotFather`.
   - Send `/newbot`.
   - Choose a name (e.g., `Ezra Desktop Companion`) and username (e.g., `my_ezra_desktop_bot`).
   - Copy the **HTTP API Bot Token** provided by BotFather.

2. **Add Token to `.env`:**
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz
   ```

3. **Get Your Personal Chat ID:**
   - Open your new bot on Telegram and tap **Start** (or send `/start`).
   - The bot will reply with your Chat ID, or Ezra's console will display it.
   - Add it to `.env`:
     ```env
     TELEGRAM_CHAT_ID=your_chat_id
     ```

4. **Remote Commands:**
   - `/status` — Live CPU load, RAM usage, battery, and git dirty status.
   - `/snap` — Captures and uploads a live desktop screenshot.
   - `/brief` — Generates and delivers the Executive Morning Briefing.
   - `/say <text>` — Speaks phrase through PC speakers.
   - `/run <cmd>` — Runs terminal command on your PC.
   - Any message — Conversational query processed by Ezra's brain.

---

## 🎙️ Biometrics & Voice Commands

| Voice / CLI Command | Action |
|:---|:---|
| `"Ezra"` / `"عزرا"` | Wakes Ezra into active 3-minute dwell state |
| `"اسكت"` / `"go to sleep"` | Puts Ezra to sleep immediately |
| `/enroll` / `/calibrate` | Calibrates your vocal genetic code (F0 + timbre) |
| `/brief` / `"morning brief"` | Compiles & announces executive morning briefing |
| `/git status` / `"git status"` | Reports current git branch & modified files |
| `/git publish` / `"publish changes"` | Stages all files, creates commit, and pushes to GitHub |
| `"timer for 5 minutes"` | Spawns non-blocking background alert & toast |
| `"research <topic>"` | Crawls DuckDuckGo & synthesizes executive brief |
| `/mute` / `/unmute` | Toggles between silent typewriter and spoken voice |
| `/threshold 0.35` | Adjusts vocal biometric sensitivity |

---

## 📜 Roadmap & Milestones
- [x] High-Speed Speech Recognition & Phonetic Filterbank
- [x] Sentence-Streaming British Neural Voice (~250ms latency)
- [x] Multi-Turn Hands-Free Dwell State & Arabic Wake Words
- [x] 3-Tier Vocal Genetic Security Architecture & Action Gate
- [x] Speech Gate (Anti-Hallucination Action Verification)
- [x] Executive Morning Briefing with Linux Desktop Toasts
- [x] Git Voice Developer Workflow (`git_status`, `git_publish`)
- [x] Non-Blocking Background Timers & Linux Notifications
- [x] Autonomous Zero-Cost Deep Web Research Agent
- [x] Local Offline LLM Mode (Ollama Fallback)
- [x] Two-Way Telegram Remote Control Daemon
