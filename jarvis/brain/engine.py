import os
import json
import re
import asyncio
from typing import Dict, Any, List, Optional
import aiohttp
from config.settings import GEMINI_API_KEY, GROQ_API_KEY
from jarvis.actions.browser import BrowserManager
from jarvis.actions.apps import AppManager
from jarvis.actions.system import SystemManager
from jarvis.actions.vision import screen_vision
from jarvis.actions.apis import api_manager
from jarvis.voice.speaker import voice_speaker
from jarvis.comms.messaging import CommsManager
from jarvis.agents.subagents import ResearchSubAgent
from jarvis.memory import memory_service
from config.settings import PROJECT_ROOT

SOUL_FILE = PROJECT_ROOT / "SOUL.md"

ALL_TOOLS_LIST = (
    "inspect_screen, click_screen_element, point_at, move_mouse, click_mouse, double_click, right_click, drag_mouse, "
    "prompt_antigravity, prompt_app, focus_app, type_message, type_text, dictate_text, press_key, press_hotkey, "
    "set_clipboard, get_clipboard, toggle_voice, set_voice_mode, get_weather, get_crypto_price, get_exchange_rate, search_wikipedia, get_network_info, "
    "get_tech_news, get_github_info, open_tab, close_tab, close_browser, search_web, search_portal, open_folder, play_youtube, launch_app, close_app, "
    "send_discord_message, take_screenshot, media_control, get_system_status, get_top_processes, set_volume, remember_fact, "
    "execute_shell_command, send_email, send_telegram, get_daily_briefing, send_desktop_notification, "
    "schedule_timer, git_status, git_publish, git_log_recent, git_pull, sync_gdrive, lock_screen, "
    "add_note, get_notes, clear_notes, add_todo, get_todos, clear_todos, get_recent_downloads, deep_research"
)

TOOLS_SPECIFICATION = f"""
### REAL-TIME SYSTEM & DESKTOP TOOLS SPECIFICATION:
You have direct, real-time control over the user's Linux computer (Arch Linux / Pop!_OS).
Whenever the user commands or asks for an action, task, or information, you MUST immediately output one or more ```tool_call blocks.

Supported Tools and Exact Arguments:
- `type_text`: Types arbitrary text, words, code, or shell commands into any window or terminal, with optional automatic Enter.
  Args: {{"text": "<text to type>", "press_enter": true|false, "app_name": "<optional app name, e.g. terminal>"}}
  Example: {{"tool": "type_text", "args": {{"text": "brave", "press_enter": true, "app_name": "terminal"}}}}

- `move_mouse`: Moves the mouse cursor to absolute screen coordinates (x, y).
  Args: {{"x": 500, "y": 300}}
  Example: {{"tool": "move_mouse", "args": {{"x": 680, "y": 380}}}}

- `point_at`: Points the mouse cursor at screen coordinates (x, y) or visually finds and points at a described screen element.
  Args: {{"x": 500, "y": 300}} or {{"target": "<visual element or description>"}}
  Example: {{"tool": "point_at", "args": {{"target": "search bar"}}}}

- `click_mouse`: Clicks mouse button ('left', 'right', 'middle', 'double') at current or specified position.
  Args: {{"button": "left"|"right"|"middle", "clicks": 1|2, "x": <optional int>, "y": <optional int>}}
  Example: {{"tool": "click_mouse", "args": {{"button": "left"}}}}

- `double_click`: Double clicks left mouse button at current or specified coordinates.
  Args: {{"x": <optional int>, "y": <optional int>}}

- `right_click`: Right clicks (context menu) at current or specified coordinates.
  Args: {{"x": <optional int>, "y": <optional int>}}

- `drag_mouse`: Drags mouse cursor from current or starting coordinates to target coordinates.
  Args: {{"to_x": <int>, "to_y": <int>, "from_x": <optional int>, "from_y": <optional int>}}

- `prompt_antigravity`: Direct bridge to Antigravity IDE. Focuses the Antigravity window, types the prompt into the active chat prompt input, and presses Enter to run it.
  Args: {{"prompt": "<exact prompt text to submit to Antigravity>"}}
  Example: {{"tool": "prompt_antigravity", "args": {{"prompt": "write a python function to parse json files"}}}}

- `prompt_app`: Universal bridge to ANY desktop application (Discord, Terminal, VS Code, Browser, Notes, etc.). Focuses the app, types the text, and presses Enter.
  Args: {{"app_name": "<discord|terminal|code|obsidian|...>", "text": "<text to type/send>", "press_enter": true}}
  Example: {{"tool": "prompt_app", "args": {{"app_name": "terminal", "text": "brave", "press_enter": true}}}}

- `execute_shell_command`: Runs ANY Linux bash shell command on the laptop and retrieves stdout/stderr.
  Args: {{"command": "<bash command>"}}
  Example: {{"tool": "execute_shell_command", "args": {{"command": "git pull origin main"}}}}

- `type_message`: Types or pastes text into the currently active desktop window, optionally pressing Enter.
  Args: {{"text": "<text>", "press_enter": true|false}}
  Example: {{"tool": "type_message", "args": {{"text": "npm run build", "press_enter": true}}}}

- `focus_app`: Brings an application window to the foreground.
  Args: {{"app_name": "<name of app>"}}
  Example: {{"tool": "focus_app", "args": {{"app_name": "terminal"}}}}

- `launch_app`: Launches or opens any desktop application or Flatpak.
  Args: {{"app_name": "<name of app>"}}
  Example: {{"tool": "launch_app", "args": {{"app_name": "spotify"}}}}

- `close_app`: Terminates or closes a running application.
  Args: {{"app_name": "<name of app>"}}
  Example: {{"tool": "close_app", "args": {{"app_name": "steam"}}}}

- `press_key`: Presses a single keyboard key (e.g. 'enter', 'esc', 'tab', 'backspace', 'space', 'up', 'down').
  Args: {{"key": "<key name>"}}
  Example: {{"tool": "press_key", "args": {{"key": "enter"}}}}

- `press_hotkey`: Presses a key combination.
  Args: {{"keys": ["ctrl", "c"]}}
  Example: {{"tool": "press_hotkey", "args": {{"keys": ["alt", "tab"]}}}}

- `open_tab`: Opens a URL in the web browser.
  Args: {{"url": "<url>"}}
  Example: {{"tool": "open_tab", "args": {{"url": "https://github.com"}}}}

- `close_tab`: Closes the current browser tab.
  Args: {{}}

- `search_web`: Searches the web on Google, YouTube, or Wikipedia.
  Args: {{"query": "<query>", "engine": "google"|"youtube"|"wikipedia"}}
  Example: {{"tool": "search_web", "args": {{"query": "how to setup docker", "engine": "google"}}}}

- `play_youtube`: Starts playback of a song or video on YouTube.
  Args: {{"query": "<song or video name>"}}
  Example: {{"tool": "play_youtube", "args": {{"query": "hans zimmer interstellar"}}}}

- `media_control`: Controls system media (play, pause, next, previous, stop).
  Args: {{"action": "play"|"pause"|"next"|"previous"|"stop"}}

- `set_volume`: Sets master audio volume percentage.
  Args: {{"percent": 0..100}}
  Example: {{"tool": "set_volume", "args": {{"percent": 75}}}}

- `inspect_screen`: Analyzes screen display with vision/OCR.
  Args: {{"instruction": "<what to look for>"}}

- `click_screen_element`: Clicks on a visual UI element on screen.
  Args: {{"description": "<button or text to click>"}}

- `set_clipboard`: Copies text to the system clipboard.
  Args: {{"text": "<content>"}}

- `get_clipboard`: Reads system clipboard text.
  Args: {{}}

- `take_screenshot`: Captures a screenshot of the entire screen.
  Args: {{}}

- `get_system_status`: Retrieves CPU, RAM, disk, battery, and uptime.
  Args: {{}}

- `get_top_processes`: Lists top RAM/CPU hogging processes.
  Args: {{"limit": 3}}

- `lock_screen`: Locks the computer screen.
  Args: {{}}

- `git_status`: Inspects repository status.
  Args: {{}}

- `git_publish`: Stages, commits, and pushes changes.
  Args: {{"commit_message": "<message>"}}

- `git_pull`: Pulls remote changes.
  Args: {{}}

- `git_log_recent`: Lists recent commits.
  Args: {{"limit": 3}}

- `add_note` / `get_notes` / `clear_notes`: Voice scratchpad notes.
  Args: {{"note": "<text>"}}

- `add_todo` / `get_todos` / `clear_todos`: Task list.
  Args: {{"task": "<text>"}}

- `deep_research`: Autonomous multi-source research report.
  Args: {{"query": "<topic>"}}

- `schedule_timer`: Sets a background voice timer.
  Args: {{"seconds": 60, "note": "<reminder>"}}

Format your tool call strictly as:
```tool_call
{{"tool": "tool_name", "args": {{...}}}}
```
Always provide a concise 1-sentence verbal acknowledgement along with the tool call.
"""

SYSTEM_PROMPT_TEMPLATE = f"""You are Ezra, an ultra-fast, loyal, witty British AI assistant (inspired by JARVIS).
Rules:
- Radical Semantic Intent Understanding: Never require or expect fixed command structures, exact keywords, or rigid grammar. The user speaks naturally, conversationally, in slang, with indirect hints, questions, or mixed Arabic/English. Comprehend the core desire behind their words and choose the best tool(s) to fulfill it immediately.
- Action-First Mandate: Whenever the user's statement implies or requests an action, desktop task, or system inspection, EXECUTE IT IMMEDIATELY with the appropriate tool call. Never lecture, hesitate, or explain how to do it manually.
- Ultra-short & punchy: 1 sentence spoken acknowledgement preferred, 2 max. Direct & sharp British wit.
- Multilingual & Slang: Seamlessly understand British English, modern slang, idioms, and natural Arabic (العربية - Levantine/Jordanian/Gulf/Standard). Reply in British English, or in natural Arabic if addressed in Arabic.
- Spoken input: Understand intended conversational meaning even with minor acoustic homophones or transcription noise.
User Context: {{learned_context}}

{TOOLS_SPECIFICATION}"""

def get_system_prompt(learned_context: str) -> str:
    """Loads system instructions from SOUL.md with dynamic context and full tool specifications."""
    if SOUL_FILE.exists():
        try:
            soul_text = SOUL_FILE.read_text(encoding="utf-8").strip()
            return f"{soul_text}\n\nLearned User Context:\n{learned_context}\n\n{TOOLS_SPECIFICATION}"
        except Exception:
            pass
    return SYSTEM_PROMPT_TEMPLATE.format(learned_context=learned_context)

class BrainEngine:
    def __init__(self):
        self.reload_keys()

    def reload_keys(self):
        from config import settings
        import importlib
        importlib.reload(settings)
        raw_gemini = getattr(settings, "GEMINI_API_KEY", "") or ""
        # Multi-key rotation: supports comma-separated keys (e.g. GEMINI_API_KEY=key1,key2,key3)
        self.gemini_keys = [k.strip() for k in raw_gemini.split(",") if k.strip()]
        self.gemini_key = self.gemini_keys[0] if self.gemini_keys else ""
        self.groq_key = getattr(settings, "GROQ_API_KEY", "") or ""

    async def execute_tool(self, tool_name: str, args: Dict[str, Any], user_context: str = "", speaker_tier: str = "verified") -> str:
        """Executes system or desktop action with biometric permission gating."""
        try:
            # Biometric access gate: verify permissions for current speaker tier
            from jarvis.voice.biometrics import voice_dna
            permitted, reason = voice_dna.is_action_permitted(tool_name, speaker_tier)
            if not permitted:
                return json.dumps({"status": "error", "message": reason})

            if tool_name == "inspect_screen":
                vision_analysis = screen_vision.analyze_screen(args.get("instruction", "Describe what is on screen"))
                res = {"status": "success", "message": vision_analysis, "screen_vision": vision_analysis}
            elif tool_name == "click_screen_element":
                res = screen_vision.locate_and_click(args.get("description", ""))
            elif tool_name in ("type_message", "type_text"):
                msg_txt = args.get("text") or args.get("message") or args.get("command") or user_context
                press_enter = bool(args.get("press_enter", False) or args.get("enter", False))
                app_target = args.get("app_name") or args.get("app") or None
                in_term = args.get("in_terminal")
                res = AppManager.type_text(msg_txt, press_enter=press_enter, app_name=app_target, in_terminal=in_term)
            elif tool_name == "move_mouse":
                res = AppManager.move_mouse(int(args.get("x", 0)), int(args.get("y", 0)))
            elif tool_name == "point_at":
                x = args.get("x")
                y = args.get("y")
                tgt = args.get("target") or args.get("element") or args.get("description")
                res = AppManager.point_at(x=int(x) if x is not None else None, y=int(y) if y is not None else None, target=tgt)
            elif tool_name == "click_mouse":
                x = args.get("x")
                y = args.get("y")
                btn = args.get("button", "left")
                clicks = int(args.get("clicks", 1))
                res = AppManager.click_mouse(x=int(x) if x is not None else None, y=int(y) if y is not None else None, button=btn, clicks=clicks)
            elif tool_name == "double_click":
                x = args.get("x")
                y = args.get("y")
                res = AppManager.double_click(x=int(x) if x is not None else None, y=int(y) if y is not None else None)
            elif tool_name == "right_click":
                x = args.get("x")
                y = args.get("y")
                res = AppManager.right_click(x=int(x) if x is not None else None, y=int(y) if y is not None else None)
            elif tool_name == "drag_mouse":
                to_x = int(args.get("to_x", 0))
                to_y = int(args.get("to_y", 0))
                from_x = args.get("from_x")
                from_y = args.get("from_y")
                btn = args.get("button", "left")
                res = AppManager.drag_mouse(to_x, to_y, from_x=int(from_x) if from_x is not None else None, from_y=int(from_y) if from_y is not None else None, button=btn)
            elif tool_name == "dictate_text":
                text = args.get("text", "") or args.get("message", "") or user_context
                res = AppManager.dictate_text(text, args.get("press_enter", False))
            elif tool_name == "press_key":
                res = AppManager.press_key(args.get("key", "enter"))
            elif tool_name == "press_hotkey":
                res = AppManager.press_hotkey(args.get("keys", []))
            elif tool_name == "toggle_voice":
                enabled = bool(args.get("enabled", True))
                voice_speaker.set_muted(not enabled)
                status_str = "unmuted and will speak aloud" if enabled else "muted in silent text mode"
                res = {"status": "success", "message": f"My voice is now {status_str}, sir."}
            elif tool_name == "get_weather":
                city = args.get("city", "") or args.get("location", "")
                res = api_manager.get_weather(city)
            elif tool_name == "get_crypto_price":
                res = api_manager.get_crypto_price(args.get("coins", "bitcoin,ethereum"), args.get("currency", "usd"))
            elif tool_name == "get_exchange_rate":
                res = api_manager.get_exchange_rate(args.get("base_currency", "USD"), args.get("target_currency", "EUR"))
            elif tool_name == "search_wikipedia":
                query = args.get("query", "") or args.get("q", "") or args.get("topic", "") or user_context
                res = api_manager.search_wikipedia(query)
            elif tool_name == "get_network_info":
                res = api_manager.get_network_info()
            elif tool_name == "get_tech_news":
                res = api_manager.get_tech_news(int(args.get("limit", 5)))
            elif tool_name == "get_github_info":
                res = api_manager.get_github_info(args.get("username", "AhmadAlshrafe25"), args.get("repo", ""))
            elif tool_name == "open_tab":
                url = args.get("url", "") or args.get("link", "")
                res = BrowserManager.open_url(url)
            elif tool_name == "close_tab":
                res = BrowserManager.close_tab()
            elif tool_name == "close_browser":
                res = BrowserManager.close_browser(args.get("browser_name", ""))
            elif tool_name == "search_web":
                query = args.get("query") or args.get("q") or args.get("search") or args.get("search_query") or args.get("keyword") or user_context.strip()
                res = BrowserManager.search_web(query, args.get("engine", "google"))
            elif tool_name == "play_youtube":
                query = args.get("query", "") or args.get("q", "") or args.get("song", "") or args.get("video", "") or user_context.strip()
                res = BrowserManager.play_youtube_video_or_music(query)
            elif tool_name == "launch_app":
                app_name = args.get("app_name") or args.get("app") or args.get("name") or args.get("application") or ""
                res = AppManager.launch_app(app_name)
            elif tool_name == "focus_app":
                app_name = args.get("app_name") or args.get("app") or args.get("name") or ""
                pick_other = bool(args.get("pick_other", False) or "other" in app_name.lower())
                res = AppManager.focus_app(app_name, pick_other=pick_other)
            elif tool_name == "prompt_antigravity":
                prompt_txt = args.get("prompt") or args.get("text") or args.get("query") or user_context
                res = AppManager.prompt_antigravity(prompt_txt)
            elif tool_name == "prompt_app":
                app_target = args.get("app_name") or args.get("app") or args.get("application") or "antigravity"
                prompt_txt = args.get("prompt") or args.get("text") or args.get("query") or user_context
                press_enter = bool(args.get("press_enter", True))
                res = AppManager.prompt_app(app_target, prompt_txt, press_enter=press_enter)
            elif tool_name == "set_clipboard":
                clip_txt = args.get("text") or args.get("content") or ""
                res = AppManager.copy_to_clipboard(clip_txt)
            elif tool_name == "get_clipboard":
                res = AppManager.read_clipboard()
            elif tool_name == "close_app":
                app_name = args.get("app_name") or args.get("app") or args.get("name") or args.get("application") or ""
                res = AppManager.close_app(app_name)
            elif tool_name == "send_discord_message":
                res = AppManager.send_discord_message(args.get("message", ""))
            elif tool_name == "take_screenshot":
                res = AppManager.take_screenshot()
            elif tool_name == "media_control":
                res = SystemManager.media_control(args.get("action", "play-pause"))
            elif tool_name == "play_media":
                res = AppManager.play_media_file(args.get("media_path", ""))
            elif tool_name == "get_system_status":
                res = SystemManager.get_system_status()
            elif tool_name == "set_volume":
                res = SystemManager.set_volume(int(args.get("percent", 50)))
            elif tool_name == "remember_fact":
                memory_service.remember_fact(args.get("topic", "general"), args.get("content", ""))
                res = {"status": "success", "message": f"Learned fact about {args.get('topic')}"}
            elif tool_name == "execute_shell_command":
                res = SystemManager.execute_shell_command(args.get("command", ""))
            elif tool_name == "send_email":
                res = CommsManager.send_email(args.get("to_email"), args.get("subject"), args.get("body"))
            elif tool_name == "send_telegram":
                res = await CommsManager.send_telegram_message(args.get("text"))
            elif tool_name == "get_daily_briefing":
                res = api_manager.get_daily_briefing(args.get("city", "Amman"))
            elif tool_name == "send_desktop_notification":
                res = SystemManager.send_desktop_notification(
                    args.get("title", "Project Ezra"),
                    args.get("message", ""),
                    args.get("urgency", "normal")
                )
            elif tool_name == "schedule_timer":
                res = SystemManager.schedule_timer(
                    int(args.get("seconds", 60)),
                    args.get("note", "Timer finished")
                )
            elif tool_name == "git_status":
                res = SystemManager.git_status(args.get("repo_dir"))
            elif tool_name == "git_publish":
                res = SystemManager.git_publish(
                    args.get("commit_message", ""),
                    args.get("repo_dir")
                )
            elif tool_name == "git_log_recent":
                res = SystemManager.git_log_recent(
                    int(args.get("limit", 3)),
                    args.get("repo_dir")
                )
            elif tool_name == "git_pull":
                res = SystemManager.git_pull(args.get("repo_dir"))
            elif tool_name == "sync_gdrive":
                res = SystemManager.sync_gdrive()
            elif tool_name == "get_top_processes":
                res = SystemManager.get_top_processes(int(args.get("limit", 3)))
            elif tool_name == "lock_screen":
                res = SystemManager.lock_screen()
            elif tool_name == "add_note":
                res = SystemManager.add_note(args.get("note", ""))
            elif tool_name == "get_notes":
                res = SystemManager.get_notes(int(args.get("limit", 5)))
            elif tool_name == "clear_notes":
                res = SystemManager.clear_notes()
            elif tool_name == "add_todo":
                res = SystemManager.add_todo(args.get("task", ""))
            elif tool_name == "get_todos":
                res = SystemManager.get_todos()
            elif tool_name == "clear_todos":
                res = SystemManager.clear_todos()
            elif tool_name == "get_recent_downloads":
                res = SystemManager.get_recent_downloads(int(args.get("limit", 5)))
            elif tool_name == "search_portal":
                res = BrowserManager.search_portal(args.get("portal", "google"), args.get("query", ""))
            elif tool_name == "open_folder":
                res = BrowserManager.open_folder(args.get("folder_name", "downloads"))
            elif tool_name == "deep_research":
                q = args.get("query", "") or args.get("topic", "") or user_context
                res = await ResearchSubAgent.deep_research(q)
            elif tool_name == "set_voice_mode":
                mode = args.get("mode", "robotic").lower()
                is_robot = "robot" in mode or "synth" in mode
                voice_speaker.set_robotic_mode(is_robot)
                m_str = "cybernetic robotic mode" if is_robot else "natural neural voice"
                res = {"status": "success", "message": f"Voice switched to {m_str}, sir."}
            else:
                res = {"status": "error", "message": f"Unknown tool: {tool_name}"}
            return json.dumps(res)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    def _quick_conversational_reflex(self, msg: str) -> Optional[str]:
        """Instant conversational reflex: replies in <1ms ONLY for pure, standalone greetings without commands."""
        import random
        m = msg.strip().lower()
        # Clean punctuation
        m_clean = re.sub(r"[^\w\s]", "", m).strip()
        words = m_clean.split()
        
        # If the message has more than 4 words, it's likely a full sentence or command -> send to LLM brain!
        if len(words) > 4:
            return None

        # Check if there are any action indicator cues in the utterance
        action_cues = (
            "open", "launch", "close", "kill", "write", "type", "run", "execute",
            "prompt", "send", "tell", "press", "click", "search", "lock", "volume",
            "timer", "git", "note", "todo", "play", "check", "see", "show", "what", "how",
            "افتح", "شغل", "اغلق", "سكر", "اكتبي", "نفذي", "اضغطي", "ابعتي", "ارسلي", "شوفي", "شو", "كيف", "بدي"
        )
        if any(c in words for c in action_cues):
            return None

        # Clean leading filler like 'ezra', 'israel', 'i said', 'so'
        m_intent = re.sub(r"^(ezra|israel|hey|hi|yo|so|and|i said)\s+", "", m_clean).strip()

        # Greetings (pure standalone)
        if m_clean in ("hi", "hello", "hey", "hey ezra", "hello ezra", "hi ezra", "morning", "good morning") or m_intent in ("hi", "hello", "hey", "morning", "good morning"):
            return random.choice([
                "Good day, sir. At your command.",
                "Right here, sir. How can I assist?",
                "Hello, sir. Standing by."
            ])

        # Status / liveness checks
        if m_clean in ("are you there", "you there", "ezra", "can you hear me", "you listening") or m_intent in ("are you there", "you there", "can you hear me", "you listening"):
            return random.choice([
                "Loud and clear, sir.",
                "Always, sir. Ready when you are.",
                "Right beside you, sir."
            ])

        # Acknowledgements
        if m_clean in ("thank you", "thanks", "thanks ezra", "thank you ezra", "cheers") or m_intent in ("thank you", "thanks", "cheers"):
            return random.choice([
                "My absolute pleasure, sir.",
                "Anytime, sir.",
                "Quite happy to help."
            ])

        if m_clean in ("okay", "ok", "cool", "nice", "great", "alright", "perfect"):
            return random.choice([
                "Splendid.",
                "Understood, sir.",
                "Standing by."
            ])

        if m_clean in ("how are you", "how r u", "how you doing", "how are things") or m_intent in ("how are you", "how are you doing", "how are things"):
            return "Operating at peak performance, sir. Ready for your instructions."

        # British slang & casual greetings
        if m_clean in ("wassup", "what's good", "whats good", "wagwan", "alright mate", "yo", "sup") or m_intent in ("wassup", "what's good", "whats good", "wagwan", "alright mate", "sup"):
            return random.choice([
                "All good on my end, mate. What's on your mind?",
                "Everything running smooth, sir. How can I help?",
                "Top shape, sir. What are we getting into?"
            ])

        # Arabic greetings (standalone exact match or with عزرا only)
        if m_clean in ("مرحبا", "أهلا", "اهلا", "سلام", "السلام عليكم", "صباح الخير", "مساء الخير", "هلا", "مرحبا عزرا", "اهلا عزرا", "هلا عزرا") or m_intent in ("مرحبا", "أهلا", "اهلا", "سلام", "السلام عليكم", "صباح الخير", "مساء الخير", "هلا"):
            return random.choice([
                "أهلاً بك يا سيدي، في خدمتك دائماً.",
                "مرحباً بك، كيف يمكنني مساعدتك؟",
                "أهلاً وسهلاً، أنا في الاستماع."
            ])

        # Arabic status / liveness
        if m_clean in ("سامعني", "أنت هنا", "انت هنا", "سامعتني", "موجودة", "وينك", "سامعني عزرا", "انت هنا عزرا") or m_intent in ("سامعني", "أنت هنا", "انت هنا", "سامعتني", "موجودة", "وينك"):
            return random.choice([
                "نعم يا سيدي، أسمعك بكل وضوح.",
                "معك دائماً، تفضل بأوامرك.",
                "بجانبك يا سيدي، جاهزة لكل طلباتك."
            ])

        # Arabic acknowledgements
        if m_clean in ("شكرا", "شكراً", "تسلم", "يعطيك العافية", "مشكورة", "شكرا عزرا") or m_intent in ("شكرا", "شكراً", "تسلم", "يعطيك العافية", "مشكورة"):
            return random.choice([
                "العفو يا سيدي، في خدمتك دائماً.",
                "بكل سرور يا سيدي.",
                "على الرحب والسعة دائماً."
            ])

        # Arabic condition
        if m_clean in ("كيفك", "كيف حالك", "شو اخبارك", "شلونك", "كيفك عزرا") or m_intent in ("كيفك", "كيف حالك", "شو اخبارك", "شلونك"):
            return "بأفضل حال والحمد لله يا سيدي، جاهزة ومستعدة لكل أوامرك."

        return None

    async def think(self, user_message: str, speaker_tier: str = "verified") -> Dict[str, Any]:
        """Main LLM reasoning loop with instant reflexes, biometric access gate, and fast fallback."""
        self.reload_keys()

        # Save user query to persistent memory
        memory_service.save_message("user", user_message)

        # 0. Instant Reflex Path (<1ms latency for natural conversational banter!)
        quick_reply = self._quick_conversational_reflex(user_message)
        if quick_reply:
            memory_service.save_message("ezra", quick_reply, [])
            return {"speech_text": quick_reply, "tool_calls": []}

        # 1. ACTION-FIRST FAST PATH (<5ms latency, 100% Zero-Cloud, Zero-Quota)
        # "If she can do it without AI that's great; if she needs AI let her use it."
        # If the user is issuing a clear desktop, volume, media, app, or system directive,
        # execute it locally and immediately!
        direct_action = await self._try_direct_action(user_message)
        if direct_action:
            reply_speech = direct_action.get("speech_text", "")
            memory_service.save_message("ezra", reply_speech, direct_action.get("tool_calls", []))
            asyncio.create_task(memory_service.auto_learn_from_interaction(user_message, reply_speech))
            return direct_action

        # Build context from learned facts
        facts = memory_service.get_all_facts()
        facts_str = "\n".join([f"- {k}: {v}" for k, v in facts.items()]) or "No specific custom facts recorded yet."
        prompt = get_system_prompt(learned_context=facts_str)

        output = None
        # Priority 1: Groq (14,400 free requests per day, ~250ms voice speed)
        if self.groq_key:
            try:
                output = await self._call_groq(user_message, prompt, speaker_tier=speaker_tier)
            except Exception:
                pass

        # Priority 2: Gemini with Multi-Key Rotation (Free on Google AI Studio)
        if not output and self.gemini_keys:
            try:
                output = await self._call_gemini(user_message, prompt, speaker_tier=speaker_tier)
            except Exception:
                pass

        # Priority 3: Local Ollama daemon (100% Offline LLM on localhost:11434)
        if not output:
            try:
                output = await self._call_ollama(user_message, prompt, speaker_tier=speaker_tier)
            except Exception:
                pass

        # Priority 4: Offline smart rule fallback
        if not output:
            output = await self._offline_smart_fallback(user_message)

        # 5. Smart Intent Guard: If LLM generated text but missed tool calls for a clear command, execute it!
        if output and not output.get("tool_calls"):
            msg_lower = user_message.lower().strip()
            action_indicators = (
                "open", "launch", "close", "kill", "write", "type", "run", "execute",
                "prompt", "send", "tell", "press", "click", "search", "lock", "volume",
                "timer", "git", "note", "todo", "افتح", "شغل", "اغلق", "سكر", "اكتبي", "نفذي", "اضغطي"
            )
            if any(ind in msg_lower for ind in action_indicators):
                fallback_output = await self._offline_smart_fallback(user_message)
                if fallback_output and fallback_output.get("tool_calls"):
                    output["tool_calls"] = fallback_output["tool_calls"]
                    if not output.get("speech_text") or any(neg in output.get("speech_text", "").lower() for neg in ("cannot", "can't", "unable", "sorry")):
                        output["speech_text"] = fallback_output.get("speech_text", output.get("speech_text"))

        # Save Ezra reply to memory
        reply_speech = output.get("speech_text", "")
        memory_service.save_message("ezra", reply_speech, output.get("tool_calls", []))

        # Continuously adapt and learn from interaction in background
        asyncio.create_task(memory_service.auto_learn_from_interaction(user_message, reply_speech))
        return output

    async def _call_gemini(self, user_message: str, system_prompt: str, speaker_tier: str = "verified") -> Dict[str, Any]:
        candidate_models = [
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-3.5-flash",
            "gemini-3.8-flash-lite-tts",
            "gemini-3.8-flash-tts",
            "gemini-robotics-er-2-preview",
            "gemini-3.5-transcribe"
        ]
        
        recent = memory_service.get_recent_history(8)
        # Build strictly alternating history (user -> model -> user -> model)
        sanitized_history = []
        last_role = None
        for h in recent[:-1]:  # Exclude current message
            role = "user" if h["sender"] == "user" else "model"
            msg_txt = (h.get("message") or "").strip()
            if not msg_txt:
                continue
            if role != last_role:
                sanitized_history.append({"role": role, "parts": [{"text": msg_txt}]})
                last_role = role

        # Multi-turn rules for Gemini API:
        # 1. If last history message is 'user', remove it so new turn is 'user'
        if sanitized_history and sanitized_history[-1]["role"] == "user":
            sanitized_history.pop()

        # 2. Conversation must start with 'user'
        if sanitized_history and sanitized_history[0]["role"] == "model":
            sanitized_history.pop(0)

        contents = sanitized_history + [
            {"role": "user", "parts": [{"text": user_message.strip()}]}
        ]
        
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
        }

        req_timeout = aiohttp.ClientTimeout(total=4.0, connect=1.5)
        async with aiohttp.ClientSession() as session:
            for api_key in self.gemini_keys:
                for model_name in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    try:
                        async with session.post(url, json=payload, timeout=req_timeout) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if "candidates" in data and data["candidates"]:
                                    cand = data["candidates"][0]
                                    parts = cand.get("content", {}).get("parts", [])
                                    reply_text = "".join([p.get("text", "") for p in parts if p.get("text")]).strip()
                                    if reply_text:
                                        return await self._process_tool_calls_in_text(reply_text, user_context=user_message, speaker_tier=speaker_tier)
                            elif resp.status == 429:
                                break  # Daily quota reached for this key; rotate immediately to next key!
                            elif resp.status in (404, 400, 500, 503):
                                continue
                    except Exception:
                        continue
        raise Exception("All Gemini candidate models failed to respond.")

    async def _call_groq(self, user_message: str, system_prompt: str, speaker_tier: str = "verified") -> Dict[str, Any]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_key}"}
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        async with aiohttp.ClientSession() as session:
            for model in models:
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.5,
                    "max_tokens": 800
                }
                try:
                    async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=4.5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "choices" in data and data["choices"]:
                                reply_text = data["choices"][0]["message"]["content"]
                                return await self._process_tool_calls_in_text(reply_text, user_context=user_message, speaker_tier=speaker_tier)
                except Exception:
                    continue
        raise Exception("Groq failed to respond.")

    async def _call_ollama(self, user_message: str, system_prompt: str, speaker_tier: str = "verified") -> Dict[str, Any]:
        """Calls local Ollama daemon (100% offline LLM) at http://127.0.0.1:11434 with fast timeout."""
        ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.2")

        payload = {
            "model": model,
            "prompt": f"{system_prompt}\n\nUser: {user_message}\n\nEzra:",
            "stream": False,
            "options": {
                "temperature": 0.5,
                "num_predict": 120
            }
        }
        timeout = aiohttp.ClientTimeout(total=4.0, connect=1.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{ollama_host}/api/generate", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    reply_text = data.get("response", "").strip()
                    if reply_text:
                        return await self._process_tool_calls_in_text(reply_text, user_context=user_message, speaker_tier=speaker_tier)
        raise Exception("Ollama daemon did not return valid response.")

    async def _process_tool_calls_in_text(self, reply_text: str, user_context: str = "", speaker_tier: str = "verified") -> Dict[str, Any]:
        all_calls = []
        seen = set()

        def add_call(obj):
            if isinstance(obj, dict) and "tool" in obj:
                key = (obj.get("tool"), json.dumps(obj.get("args", {}), sort_keys=True))
                if key not in seen:
                    seen.add(key)
                    all_calls.append(obj)

        def find_json_objects(text: str):
            results = []
            i = 0
            n = len(text)
            while i < n:
                if text[i] == '{':
                    start = i
                    depth = 0
                    in_string = False
                    escape = False
                    for j in range(start, n):
                        char = text[j]
                        if in_string:
                            if escape:
                                escape = False
                            elif char == '\\':
                                escape = True
                            elif char == '"':
                                in_string = False
                        else:
                            if char == '"':
                                in_string = True
                            elif char == '{':
                                depth += 1
                            elif char == '}':
                                depth -= 1
                                if depth == 0:
                                    candidate = text[start:j+1]
                                    try:
                                        obj = json.loads(candidate)
                                        if isinstance(obj, dict) and 'tool' in obj:
                                            results.append(obj)
                                            i = j
                                    except Exception:
                                        pass
                                    break
                i += 1
            return results

        # 1. Parse markdown code blocks (```tool_call, ```json, or generic ```)
        code_blocks = re.findall(r'```(?:tool_call|json)?\s*([\s\S]*?)\s*```', reply_text)
        for block in code_blocks:
            b_str = block.strip()
            try:
                parsed = json.loads(b_str)
                if isinstance(parsed, dict):
                    add_call(parsed)
                    continue
                elif isinstance(parsed, list):
                    for item in parsed:
                        add_call(item)
                    continue
            except Exception:
                pass

            for obj in find_json_objects(b_str):
                add_call(obj)

        # 2. Parse inline tool JSON objects anywhere in text
        for obj in find_json_objects(reply_text):
            add_call(obj)

        tool_results = []
        for call_data in all_calls:
            try:
                res = await self.execute_tool(call_data["tool"], call_data.get("args", {}), user_context=user_context, speaker_tier=speaker_tier)
                tool_results.append({"tool": call_data["tool"], "result": json.loads(res)})
            except Exception as e:
                tool_results.append({"tool": call_data.get("tool", "unknown"), "error": str(e)})

        # Clean raw JSON and code blocks from speech text
        clean_text = re.sub(r'```(?:tool_call|json)?[\s\S]*?```', '', reply_text)
        while True:
            m = re.search(r'\{\s*"tool"\s*:', clean_text)
            if not m:
                break
            start = m.start()
            depth = 0
            end = -1
            for i in range(start, len(clean_text)):
                if clean_text[i] == '{':
                    depth += 1
                elif clean_text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end != -1:
                clean_text = clean_text[:start] + clean_text[end:]
            else:
                break
        clean_text = clean_text.strip()

        tool_speech_items = []
        for tr in tool_results:
            t_name = tr.get("tool", "")
            t_res = tr.get("result", {})
            if isinstance(t_res, dict):
                if t_name == "get_system_status":
                    tool_speech_items.append(f"Systems nominal, sir. CPU at {t_res.get('cpu_percent', '--')}, RAM at {t_res.get('ram_used_gb', '--')}, battery at {t_res.get('battery', 'OK')}.")
                elif t_name == "get_top_processes" and "summary" in t_res:
                    tool_speech_items.append(f"Top processes are {t_res.get('summary')}.")
                elif t_name == "get_crypto_price" and "data" in t_res:
                    prices_str = ", ".join([f"{k.capitalize()} is at {v.get('price', '')}" for k, v in t_res["data"].items()])
                    tool_speech_items.append(f"Live market figures: {prices_str}.")
                elif t_name == "get_network_info" and "network" in t_res:
                    net = t_res.get("network", {})
                    tool_speech_items.append(f"Public IP is {net.get('public_ip', '--')}, Wi-Fi is {net.get('wifi_ssid', '--')}, latency {net.get('ping_latency', '--')}.")
                elif t_name == "get_tech_news" and "articles" in t_res:
                    titles = "; ".join([a.get('title', '') for a in t_res["articles"][:3]])
                    tool_speech_items.append(f"Top headlines right now: {titles}.")
                elif t_name == "get_github_info":
                    if "recent_repos" in t_res:
                        repos = ", ".join(t_res["recent_repos"][:4])
                        tool_speech_items.append(f"User {t_res.get('username')} has {t_res.get('public_repos_count')} repos, including {repos}.")
                    elif "description" in t_res:
                        tool_speech_items.append(f"Repo {t_res.get('repo_name')} ({t_res.get('stars')} stars): {t_res.get('description')}.")
                elif t_name == "git_status":
                    clean_state = "working tree clean" if t_res.get("is_clean") else f"{t_res.get('modified_files_count')} uncommitted files"
                    tool_speech_items.append(f"On branch {t_res.get('branch', 'main')}: {clean_state}.")
                elif t_name == "git_log_recent":
                    tool_speech_items.append(f"Recent commits: {t_res.get('summary', '')}.")
                elif t_name == "execute_shell_command" and "output" in t_res:
                    out = t_res.get("output", "").strip()[:100]
                    tool_speech_items.append(f"Command output: {out}" if out else "Command executed successfully.")
                elif t_name in ("prompt_antigravity", "prompt_app", "type_message", "type_text", "move_mouse", "point_at", "click_mouse", "double_click", "right_click", "drag_mouse", "focus_app") and "message" in t_res and not clean_text:
                    tool_speech_items.append(t_res["message"])
                elif "summary" in t_res:
                    tool_speech_items.append(t_res["summary"])
                elif "extract" in t_res:
                    tool_speech_items.append(t_res["extract"])
                elif "message" in t_res and not clean_text:
                    tool_speech_items.append(t_res["message"])

        tool_speech = " ".join(tool_speech_items).strip() if tool_speech_items else None
        if tool_speech:
            if not clean_text:
                clean_text = tool_speech
            elif any(tr.get("tool", "").startswith(prefix) for tr in tool_results for prefix in ["get_", "search_", "inspect_"]):
                clean_text = f"{clean_text} {tool_speech}".strip()
        elif not clean_text and tool_results:
            tools_done = [tr.get("tool", "directive") for tr in tool_results if "error" not in tr]
            if tools_done:
                clean_text = f"Actions for {', '.join(tools_done)} completed, sir."
            else:
                clean_text = "Directives completed, sir."

        # SPEECH GATE PROTOCOL:
        # Prevent claiming an action succeeded if any tool failed or threw an error.
        errors = []
        for tr in tool_results:
            t_name = tr.get("tool", "action")
            t_err = tr.get("error", "")
            t_res = tr.get("result", {})
            if t_err:
                errors.append(f"{t_name}: {t_err}")
            elif isinstance(t_res, dict) and t_res.get("status") == "error":
                errors.append(f"{t_name}: {t_res.get('message', 'execution failed')}")

        if errors and not clean_text:
            clean_text = f"Could not complete all directives, sir. Reason: {'; '.join(errors)}."
        elif errors and clean_text:
            clean_text = f"{clean_text} (Note: {'; '.join(errors)})"

        return {
            "speech_text": clean_text,
            "full_reply": reply_text,
            "tool_calls": tool_results
        }

    async def _try_direct_action(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Action-First Fast Path:
        "If she can do it without AI that's great; if she needs AI let her use it."
        Directly executes local desktop/system/media commands in <5ms without querying cloud AI.
        Returns response dict if handled, or None if cognitive AI reasoning is needed.
        """
        msg = user_message.lower().strip()
        # Pure information-seeking questions require generative AI reasoning
        question_starters = ("what is ", "what are ", "who is ", "who was ", "why is ", "why are ", "why do ", "how does ", "explain ", "summarize ", "write me ")
        if any(msg.startswith(qs) for qs in question_starters) and not any(k in msg for k in ("hogging", "memory", "ram", "status", "battery")):
            return None

        # Check if the universal semantic action planner resolves actions
        return await self._parse_and_execute_semantic_actions(user_message)

    async def _parse_and_execute_semantic_actions(self, user_message: str) -> Optional[Dict[str, Any]]:
        raw_msg = user_message.strip()
        msg = raw_msg.lower()
        has_ar = bool(re.search(r"[\u0600-\u06FF]", msg))

        # Clean conversational preambles repeatedly
        clean_text = msg
        while True:
            prev = clean_text
            clean_text = re.sub(r'^(?:all\s+right|alright|okay|ok|hey|hi|hello|yo)\s*,?\s*', '', clean_text)
            clean_text = re.sub(r'^(?:ezra|israel|esra|asra|azra|يا\s*عزرا|اسمعي\s*عزرا|عزرا)\s*,?\s*', '', clean_text)
            clean_text = re.sub(r'^(?:can\s+you\s+like|can\s+you|could\s+you|would\s+you|please|like|just|go\s+ahead\s+and|ممكن|لو\s*سمحتي|بالله\s*عليكي|اعملي|بدي\s*منك)\s*', '', clean_text)
            clean_text = clean_text.strip()
            if clean_text == prev:
                break

        # Clean conversational postambles
        while True:
            prev = clean_text
            clean_text = re.sub(r'\s*(?:while\s+we\s+talk|while\s+i\s+talk|while\s+we\s+chat|in\s+the\s+background|for\s+me|please|right\s+now|لو\s*سمحتي|بالله\s*عليكي)$', '', clean_text).strip()
            if clean_text == prev:
                break

        # Smart compound request splitting
        ACTION_VERBS = (
            r'(?:open|launch|start|run|close|kill|exit|quit|focus|switch\s+to|go\s+to|bring\s+up|'
            r'type|write|dictate|pipe|point|move\s+(?:the\s+)?(?:mouse|cursor)|click|double\s+click|right\s+click|drag|'
            r'press\s+(?:key|enter|escape|esc|tab|backspace|space)|hit\s+enter|send\s+enter|'
            r'take\s+screenshot|capture\s+screen|lock\s+screen|suspend|sleep|'
            r'mute|unmute|lower\s+(?:the\s+)?(?:sound|volume)|turn\s+down|turn\s+up|set\s+(?:the\s+)?(?:sound|volume)|'
            r'pause\s+music|resume\s+music|stop\s+music|next\s+(?:song|track)|skip\s+song|'
            r'search|google|prompt|tell|ask|'
            r'روحي\s+على|ركزي\s+على|افتح|شغل|اغلق|سكر|اكتبي|اطبعي|اشري|حرك|انقري|اضغطي|دبل\s+كليك|رايت\s+كليك|'
            r'اسحب|اضغطي\s+انتر|صور|اقفل|اكتم|علي\s+الصوت|وطي\s+الصوت|ابحث)'
        )

        raw_splits = re.split(r'(?:[;,]|\s+(?:and\s+then|then|after\s+that|afterwards|ثم|بعدين|وبعدين|وكمان)\s+)', clean_text)
        parts = []
        for chunk in raw_splits:
            chunk = chunk.strip()
            if not chunk:
                continue
            sub_pattern = rf'\s+(?:and\s+(?:also\s+)?|also\s+|plus\s+|&\s+|و\s*كمان\s+|و\s*)(?={ACTION_VERBS}\b)'
            sub_chunks = re.split(sub_pattern, chunk)
            merged = []
            i = 0
            while i < len(sub_chunks):
                current = sub_chunks[i].strip()
                if not current:
                    i += 1
                    continue
                if i + 1 < len(sub_chunks):
                    nxt = sub_chunks[i+1].strip()
                    is_type = any(current.startswith(w) for w in ('type', 'write', 'dictate', 'pipe', 'اكتبي', 'اطبعي')) or 'terminal' in current
                    is_enter = any(e in nxt for e in ('hit enter', 'press enter', 'send enter', 'اضغطي انتر', 'انتر'))
                    if is_type and is_enter:
                        merged.append(f'{current} {nxt}')
                        i += 2
                        continue
                merged.append(current)
                i += 1
            parts.extend(merged)

        if not parts:
            parts = [clean_text]

        detected_actions = []

        for p in parts:
            # 1. Volume & Audio Levels (e.g. "lower the sound to 50%", "make volume 30%", "sound at 70")
            m_vol = (
                re.search(r'(?:lower|reduce|turn\s+down|turn\s+up|set|put|make|وطي|اخفض|علي|ارفع|حط|خلي)?\s*(?:the\s+)?(?:sound|volume|audio|الصوت)\s*(?:to|at|on|لـ?|على)?\s*(\d+)\s*%?', p)
                or re.search(r'(?:sound|volume|الصوت)\s*(\d+)\s*%?', p)
            )
            if m_vol:
                pct = max(0, min(100, int(m_vol.group(1))))
                detected_actions.append(("set_volume", {"percent": pct}, f"Volume set to {pct}%"))
                continue

            if any(w in p for w in ("volume up", "louder", "turn it up", "علي الصوت", "ارفع الصوت")):
                detected_actions.append(("set_volume", {"percent": 85}, "Turned the volume up"))
                continue

            if any(w in p for w in ("volume down", "quieter", "turn it down", "وطي الصوت", "اخفض الصوت")):
                detected_actions.append(("set_volume", {"percent": 35}, "Turned the volume down"))
                continue

            if any(w in p for w in ("mute volume", "mute sound", "mute pc", "mute laptop", "mute", "اكتم الصوت", "ميوت")):
                detected_actions.append(("set_volume", {"percent": 0}, "Master audio muted"))
                continue

            # 2. Antigravity Prompt Bridge
            if any(w in p for w in ("antigravity", "anti-gravity", "antique gravity", "انتي جرافيتي", "انتيجرافيتي")):
                p_text = re.sub(r'^(?:write\s+(?:this\s+)?prompt\s+to|prompt|tell|ask|اكتبي\s+لـ|ابعتي\s+لـ|ارسلي\s+لـ)\s*(?:anti-?gravity|انتي\s*جرافيتي)?\s*(?:to|that|with|انه|انو)?\s*:?\s*', '', p).strip()
                if not p_text:
                    p_text = raw_msg
                detected_actions.append(("prompt_antigravity", {"prompt": p_text}, f"Prompting Antigravity"))
                continue

            # 3. Application Prompting Bridge ("prompt discord <text>", "tell <app> to <text>")
            m_bridge = re.search(r'^(?:tell|ask|prompt|write\s+to|type\s+into)\s+([a-zA-Z0-9_\-\.\+]+)\s*:?\s*(.+)$', p)
            if m_bridge:
                t_app = m_bridge.group(1).strip()
                t_txt = m_bridge.group(2).strip()
                if t_app not in ("the", "this", "my", "me", "screen", "youtube", "weather"):
                    detected_actions.append(("prompt_app", {"app_name": t_app, "text": t_txt, "press_enter": True}, f"Sent to {t_app}"))
                    continue

            # 4. YouTube & Media Playback
            is_music = (
                any(w in p for w in ("leave her johnny", "shanty", "soundtrack", "song", "music", "youtube", "track", "أغنية", "اغنية", "شغل", "يوتيوب", "watch", "video", "trailer", "movie"))
                or p.startswith("play ") or p.startswith("listen to ") or p.startswith("put on ") or p.startswith("watch ")
                or ("everything great about" in p)
            )
            if is_music:
                clean_s = re.sub(r'^(?:can\s+you\s+)?(?:play|start|listen\s+to|put\s+on|stream|watch|open|search\s+(?:for\s+)?|شغل|حط|افتح)\s*(?:the\s+)?(?:song|music|video|track|movie|أغنية|اغنية)?\s*', '', p, flags=re.IGNORECASE).strip()
                clean_s = re.sub(r'\s*(?:on\s+youtube|from\s+youtube|in\s+youtube|باليوتيوب|على\s+اليوتيوب)$', '', clean_s, flags=re.IGNORECASE).strip()
                if clean_s:
                    detected_actions.append(("play_youtube", {"query": clean_s}, f"Starting \"{clean_s}\" on YouTube"))
                    continue

            # 5. Media Controls
            if any(w in p for w in ("pause music", "pause song", "stop music", "وقف الموسيقى", "ايقاف مؤقت")):
                detected_actions.append(("media_control", {"action": "pause"}, "Paused playback"))
                continue
            if any(w in p for w in ("resume music", "continue music", "استئناف الموسيقى")):
                detected_actions.append(("media_control", {"action": "play"}, "Resumed playback"))
                continue
            if any(w in p for w in ("next song", "next track", "skip song", "الاغنية التالية")):
                detected_actions.append(("media_control", {"action": "next"}, "Skipped track"))
                continue

            # 6. Terminal & Window Switching / Focus
            if any(w in p for w in ("other terminal", "another terminal", "الترمينال الثاني", "الترمينال التاني")):
                detected_actions.append(("focus_app", {"app_name": "terminal", "pick_other": True}, "Switched to other terminal"))
                continue

            m_win_focus = re.search(r'^(?:go\s+to|switch\s+to|focus|bring\s+up|روحي\s+على|ركزي\s+على)\s+(?:the\s+|a\s+|my\s+)?([a-zA-Z0-9_\-\.\+]+)(?:\s+(?:terminal|window|app|application))?$', p)
            if m_win_focus:
                f_target = m_win_focus.group(1).strip()
                if f_target not in ("the", "this", "my", "other", "another", "screen", "youtube", "weather"):
                    if "terminal" in p:
                        f_target = "terminal"
                    detected_actions.append(("focus_app", {"app_name": f_target}, f"Focused {f_target}"))
                    continue

            # 7. Terminal Typing / Command Execution in Terminal:
            p_norm = re.sub(r'\bpipe\b', 'type', p)
            is_term_req = any(w in p_norm for w in ("terminal", "kitty", "konsole", "alacritty", "ترمينال", "الترمينال"))
            wants_enter = any(w in p_norm for w in ("hit enter", "press enter", "with enter", "send enter", "and enter", "then enter", "انتر", "واضغطي انتر", "ثم اضغطي انتر", "مع انتر"))

            # Pattern A: (type|write) <text> in (the|my)? terminal ...
            m_t_term = re.search(r'(?:type|write|اكتبي|اطبعي)\s+(?:the\s+command\s+(?:to\s+)?)?(.+?)\s+(?:in|into|on|بالـ|بـ)\s*(?:the\s+|my\s+)?(?:kitty\s+|alacritty\s+)?terminal(?:\s+that\s+i(?:\'m|\s+am)\s+looking\s+at(?:\s+right\s+now)?)?(?:\s+(?:and\s+|with\s+|then\s+)?(?:hit|press|send)?\s*enter|\s+مع\s+انتر|\s+واضغطي\s+انتر|\s+ثم\s+اضغطي\s+انتر|\s+and)?$', p_norm)
            if not m_t_term:
                # Pattern B: (go to|open) ... terminal ... (and\s+)?(type|write) <text> ...
                m_t_term = re.search(r'(?:go\s+to|open(?:\s+up)?|switch\s+to|روحي\s+على)\s+(?:the\s+|a\s+|my\s+)?(?:kitty\s+|alacritty\s+)?terminal.*?(?:type|write|اكتبي|اطبعي)\s+(?:the\s+command\s+(?:to\s+)?)?(.+?)(?:\s+(?:and\s+|with\s+|then\s+)?(?:hit|press|send)?\s*enter|\s+مع\s+انتر|\s+واضغطي\s+انتر|\s+ثم\s+اضغطي\s+انتر|\s+and)?$', p_norm)
            if not m_t_term and is_term_req and any(k in p_norm for k in ("type ", "write ", "اكتبي ", "اطبعي ")):
                # Pattern C: general typing with terminal mentioned anywhere
                m_t_term = re.search(r'(?:type|write|اكتبي|اطبعي)\s+(?:the\s+command\s+(?:to\s+)?)?(.+?)(?:\s+(?:and\s+|with\s+|then\s+)?(?:hit|press|send)?\s*enter|\s+مع\s+انتر|\s+واضغطي\s+انتر|\s+ثم\s+اضغطي\s+انتر)?$', p_norm)

            if m_t_term and is_term_req:
                text_payload = m_t_term.group(1).strip()
                text_payload = re.sub(r'(?:\s+(?:and\s+|with\s+|then\s+)?(?:hit|press|send)?\s*enter|\s+مع\s+انتر|\s+و?اضغطي\s+انتر|\s+ثم\s+اضغطي\s+انتر|\s+انتر)$', '', text_payload, flags=re.IGNORECASE).strip()
                text_payload = re.sub(r'^(?:the\s+command\s+(?:to\s+)?)?(?:open|launch|start)\s+([a-zA-Z0-9_\-\.\+]+)$', r'\1', text_payload).strip()
                text_payload = re.sub(r'\s+(?:in|into|on)\s+(?:the\s+|my\s+)?terminal.*$', '', text_payload).strip()
                text_payload = re.sub(r'\s+(?:بالترمينال|في\s+الترمينال).*$', '', text_payload).strip()
                text_payload = text_payload.strip("\"'").strip()
                if text_payload:
                    detected_actions.append(("focus_app", {"app_name": "terminal"}, "Focused terminal"))
                    detected_actions.append(("type_text", {"text": text_payload, "press_enter": wants_enter, "in_terminal": True}, f"Typed '{text_payload}' in terminal{' and hit Enter' if wants_enter else ''}"))
                    continue

            # 8. General Window Live Typing (not necessarily terminal)
            if p_norm.startswith("type ") or p_norm.startswith("write ") or p_norm.startswith("dictate ") or p_norm.startswith("اكتبي ") or p_norm.startswith("اطبعي "):
                m_t_gen = re.search(r'^(?:type|write|dictate|اكتبي|اطبعي)\s+(?:the\s+command\s+(?:to\s+)?)?(.+?)(?:\s+(?:and\s+|with\s+|then\s+)?(?:hit|press|send)?\s*enter|\s+مع\s+انتر|\s+و?اضغطي\s+انتر|\s+ثم\s+اضغطي\s+انتر|\s+انتر)?$', p_norm)
                if m_t_gen:
                    t_gen = m_t_gen.group(1).strip()
                    t_gen = re.sub(r'(?:\s+(?:and\s+|with\s+|then\s+)?(?:hit|press|send)?\s*enter|\s+مع\s+انتر|\s+و?اضغطي\s+انتر|\s+ثم\s+اضغطي\s+انتر|\s+انتر)$', '', t_gen, flags=re.IGNORECASE).strip()
                    t_gen = re.sub(r'^(?:the\s+command\s+(?:to\s+)?)?(?:open|launch|start)\s+([a-zA-Z0-9_\-\.\+]+)$', r'\1', t_gen).strip()
                    t_gen = t_gen.strip("\"'").strip()
                    if t_gen:
                        detected_actions.append(("type_text", {"text": t_gen, "press_enter": wants_enter}, f"Typed '{t_gen}'{' and pressed Enter' if wants_enter else ''}"))
                        continue

            # 9. Mouse Movement & Coordinates Pointing
            m_mouse_xy = re.search(r'(?:point|move\s+(?:the\s+)?(?:mouse|cursor))\s+(?:at|to)?\s*(\d+)\s*[,x\s]\s*(\d+)', p)
            if m_mouse_xy:
                mx = int(m_mouse_xy.group(1))
                my = int(m_mouse_xy.group(2))
                detected_actions.append(("move_mouse", {"x": mx, "y": my}, f"Moved mouse to ({mx}, {my})"))
                continue

            # Relative Mouse Movement: "move mouse right 100", "move cursor down 50"
            m_mouse_rel = re.search(r'(?:move\s+(?:the\s+)?(?:mouse|cursor))\s+(right|left|up|down|يمين|يسار|شمال|فوق|تحت)(?:\s+by)?\s*(\d+)?', p)
            if m_mouse_rel:
                m_dir = m_mouse_rel.group(1)
                dist = int(m_mouse_rel.group(2) or 60)
                dx, dy = 0, 0
                if m_dir in ("right", "يمين"):
                    dx = dist
                elif m_dir in ("left", "يسار", "شمال"):
                    dx = -dist
                elif m_dir in ("down", "تحت"):
                    dy = dist
                elif m_dir in ("up", "فوق"):
                    dy = -dist
                detected_actions.append(("move_mouse_relative", {"dx": dx, "dy": dy}, f"Moved mouse {m_dir} by {dist}px"))
                continue

            # Visual Element Pointing: "point at the search bar", "point at the close button", "اشري على المتصفح"
            m_point_tgt = re.search(r'^(?:point\s+(?:at|to)|اشري\s+على|اشري\s+ع)\s+(.+)$', p)
            if m_point_tgt:
                pt_desc = m_point_tgt.group(1).strip()
                if pt_desc and not any(w in pt_desc for w in ("out", "this", "that")):
                    detected_actions.append(("point_at", {"target": pt_desc}, f"Pointed mouse at '{pt_desc}'"))
                    continue

            # 10. Mouse Clicks & Double-Clicks & Right-Clicks
            m_dclick = re.search(r'^(?:double\s+click|دبل\s+كليك)(?:\s+(?:there|here|اضغطي))?(?:\s+(?:at\s*)?(\d+)\s*[,x\s]\s*(\d+))?$', p)
            if m_dclick:
                dc_x = int(m_dclick.group(1)) if m_dclick.group(1) else None
                dc_y = int(m_dclick.group(2)) if m_dclick.group(2) else None
                detected_actions.append(("double_click", {"x": dc_x, "y": dc_y}, "Double clicked"))
                continue

            m_rclick = re.search(r'^(?:right\s+click|context\s+menu|رايت\s+كليك)(?:\s+(?:there|here))?(?:\s+(?:at\s*)?(\d+)\s*[,x\s]\s*(\d+))?$', p)
            if m_rclick:
                rc_x = int(m_rclick.group(1)) if m_rclick.group(1) else None
                rc_y = int(m_rclick.group(2)) if m_rclick.group(2) else None
                detected_actions.append(("right_click", {"x": rc_x, "y": rc_y}, "Right clicked"))
                continue

            m_click = re.search(r'^(?:left\s+click|click|انقري|اضغطي\s+بالماوس)(?:\s+(?:there|here|هنا|هناك))?(?:\s+(?:at\s*)?(\d+)\s*[,x\s]\s*(\d+))?$', p)
            if m_click:
                c_x = int(m_click.group(1)) if m_click.group(1) else None
                c_y = int(m_click.group(2)) if m_click.group(2) else None
                detected_actions.append(("click_mouse", {"x": c_x, "y": c_y, "button": "left"}, "Clicked mouse"))
                continue

            m_click_elem = re.search(r'^(?:click\s+(?:on|the)|اضغطي\s+على)\s+(.+)$', p)
            if m_click_elem:
                cl_desc = m_click_elem.group(1).strip()
                if cl_desc and cl_desc not in ("there", "here", "it"):
                    detected_actions.append(("click_screen_element", {"description": cl_desc}, f"Clicked '{cl_desc}'"))
                    continue

            # 11. Mouse Dragging
            m_drag = re.search(r'drag(?:\s+(?:the\s+)?mouse)?(?:\s+from\s+(\d+)\s*[,x\s]\s*(\d+))?\s+to\s+(\d+)\s*[,x\s]\s*(\d+)', p)
            if m_drag:
                fx = int(m_drag.group(1)) if m_drag.group(1) else None
                fy = int(m_drag.group(2)) if m_drag.group(2) else None
                tx = int(m_drag.group(3))
                ty = int(m_drag.group(4))
                detected_actions.append(("drag_mouse", {"to_x": tx, "to_y": ty, "from_x": fx, "from_y": fy}, f"Dragged mouse to ({tx}, {ty})"))
                continue

            # 12. Standalone Key Presses
            if p in ("press enter", "hit enter", "send enter", "اضغطي انتر", "انتر", "now press enter", "just hit enter"):
                detected_actions.append(("press_key", {"key": "enter"}, "Pressed Enter"))
                continue
            if p in ("press escape", "press esc", "اضغطي escape", "اضغطي esc"):
                detected_actions.append(("press_key", {"key": "esc"}, "Pressed Escape"))
                continue
            if p in ("press tab", "اضغطي tab"):
                detected_actions.append(("press_key", {"key": "tab"}, "Pressed Tab"))
                continue
            if p in ("press backspace", "اضغطي backspace"):
                detected_actions.append(("press_key", {"key": "backspace"}, "Pressed Backspace"))
                continue
            if p in ("press space", "اضغطي مسافة"):
                detected_actions.append(("press_key", {"key": "space"}, "Pressed Space"))
                continue

            # 13. Launch Application
            m_launch = re.search(r'^(?:open(?:\s+up)?|launch|start|run|شغل|افتح)\s+(?:a\s+|an\s+|the\s+)?(?:application|app|برنامج|تطبيق)?\s*([a-zA-Z0-9_\-\.\+]+)(?:\s+(?:terminal|browser|editor|window|app|application))?$', p)
            if m_launch:
                app_t = m_launch.group(1).strip()
                if app_t not in ("the", "this", "tab", "browser", "folder", "downloads", "documents", "youtube"):
                    detected_actions.append(("launch_app", {"app_name": app_t}, f"Launching {app_t}"))
                    continue

            # 14. Close Application
            m_close = re.search(r'^(?:close|kill|exit|quit|terminate|سكر|اغلق)\s+(?:application|app|برنامج|تطبيق)?\s*([a-zA-Z0-9_\-\.\+]+)$', p)
            if m_close:
                app_t = m_close.group(1).strip()
                if app_t not in ("the", "this", "tab", "browser", "window"):
                    detected_actions.append(("close_app", {"app_name": app_t}, f"Closed {app_t}"))
                    continue

            # 15. Browser Tabs
            if any(w in p for w in ("close tab", "close the tab", "سكر التاب", "اغلق التاب")):
                detected_actions.append(("close_tab", {}, "Closed browser tab"))
                continue
            if any(w in p for w in ("close browser", "سكر المتصفح", "اغلق المتصفح")):
                detected_actions.append(("close_browser", {}, "Closed browser"))
                continue
            if any(w in p for w in ("open tab", "new tab", "افتح تاب")):
                detected_actions.append(("open_tab", {"url": "https://google.com"}, "Opened new tab"))
                continue

            # 16. Screenshot
            if any(w in p for w in ("screenshot", "take a screenshot", "capture screen", "صور الشاشة", "لقطة شاشة")):
                detected_actions.append(("take_screenshot", {}, "Captured screenshot"))
                continue

            # 17. Lock / Suspend
            if any(w in p for w in ("lock screen", "lock pc", "lock computer", "قفل الشاشة")):
                detected_actions.append(("lock_screen", {}, "Locked screen"))
                continue
            if any(w in p for w in ("suspend", "sleep pc", "sleep computer", "وضع السكون")):
                detected_actions.append(("execute_shell_command", {"command": "systemctl suspend"}, "Suspended computer"))
                continue

            # 18. System Status & Resources
            if (
                any(w in p for w in ("top process", "top processes", "hogging", "ماخذ رام", "العمليات", "resource hog", "memory hog", "cpu hog"))
                or bool(re.search(r'(?:hogging|eating|using|taking\s+up|consuming)\s+(?:the\s+|my\s+)?(?:ram|memory|cpu|resources)', p))
            ):
                detected_actions.append(("get_top_processes", {"limit": 3}, "Checked top processes"))
                continue
            if (
                p in ("system status", "status", "check status", "system health", "diagnostics", "ram usage", "battery", "cpu", "memory", "ram", "فحص النظام", "حالة النظام")
                or bool(re.search(r'^(?:get|check|show|tell\s+me|what\s+is|display|فحص|شوف|شيك|اعطيني)?\s*(?:the\s+)?(?:system\s+status|system\s+health|system\s+vitals|diagnostics|ram\s+usage|cpu\s+usage|battery\s+(?:level|status|percent)?|memory\s+usage|حالة\s+النظام)', p))
            ):
                detected_actions.append(("get_system_status", {}, "Checked system vitals"))
                continue

            # 19. Web Search
            m_search = re.search(r'^(?:search\s+(?:the\s+web\s+)?for|google\s+for|search|google|ابحث\s+عن)\s+(.+)$', p)
            if m_search:
                q_s = m_search.group(1).strip()
                detected_actions.append(("search_web", {"query": q_s, "engine": "google"}, f"Searching Google for '{q_s}'"))
                continue


        # If one or more semantic actions were detected, execute all of them!
        if detected_actions:
            executed_tools = []
            speech_summaries = []
            for tool_name, args, desc in detected_actions:
                try:
                    res_raw = await self.execute_tool(tool_name, args, user_context=user_message)
                    res_obj = json.loads(res_raw)
                    executed_tools.append({"tool": tool_name, "result": res_obj})
                    if isinstance(res_obj, dict) and tool_name == "get_top_processes" and res_obj.get("summary"):
                        speech_summaries.append(f"Top processes are {res_obj['summary']}")
                    elif isinstance(res_obj, dict) and tool_name == "get_system_status" and res_obj.get("status") == "success":
                        speech_summaries.append(f"CPU at {res_obj.get('cpu_percent', '--')}, RAM at {res_obj.get('ram_used_gb', '--')}, battery at {res_obj.get('battery', '--')}")
                    else:
                        speech_summaries.append(desc)
                except Exception as e:
                    executed_tools.append({"tool": tool_name, "error": str(e)})

            if speech_summaries:
                joined_desc = " and ".join(speech_summaries)
                reply_speech = f"{joined_desc} for you, sir." if not has_ar else f"تم تنفيذ: {joined_desc} يا سيدي."
            else:
                reply_speech = "All actions completed, sir."

            return {
                "speech_text": reply_speech,
                "tool_calls": executed_tools
            }

        return None

    async def _offline_smart_fallback(self, user_message: str) -> Dict[str, Any]:
        raw_msg = user_message.strip()
        msg = raw_msg.lower()
        has_ar = bool(re.search(r"[\u0600-\u06FF]", msg))

        # Check semantic actions first
        direct_res = await self._parse_and_execute_semantic_actions(user_message)
        if direct_res:
            return direct_res
        m_antigrav = (
            re.search(
                r"(?:write|type|send|give|paste|submit|run)\s+(?:this|a|an|the)?\s*(?:prompt\s+)?(?:to|in|into|for)\s+(?:anti-?gravity|antique gravity|gravity)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"(?:tell|ask|prompt)\s+(?:anti-?gravity|antique gravity|gravity)\s+(?:to\s+)?(?:write|make|do|fix|generate)?\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"(?:اكتبي|ابعتي|ارسلي|سجلي|قولي|اطرحي|ابعثي)\s*(?:هذا|هاد|الـ)?\s*(?:برومبت|البرومبت)?\s*(?:لـ?|إلى|الى)?\s*(?:antigravity|انتي\s*جرافيتي|انتيجرافيتي|جرافيتي|للانتي\s*جرافيتي|لانتي\s*جرافيتي)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"(?:antigravity|انتي\s*جرافيتي|انتيجرافيتي|جرافيتي).*?(?:يصلح|يعدل|يكتب|يعمل|fix|solve|generate|optimize|refactor)\s*(.+)$",
                msg,
                re.IGNORECASE
            )
        )
        if m_antigrav:
            prompt_payload = m_antigrav.group(1).strip().strip("\"'").strip()
            prompt_payload = re.sub(r"^(?:to|that says|saying|about|انه|انو)\s+", "", prompt_payload, flags=re.IGNORECASE).strip()
            res = AppManager.prompt_antigravity(prompt_payload)
            speech = f"تم إرسال الأمر إلى Antigravity يا سيدي: '{prompt_payload[:40]}'." if has_ar else f"Prompt dispatched to Antigravity, sir: '{prompt_payload[:45]}'."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "prompt_antigravity", "result": res}]
            }

        # Universal App Prompt Bridge: "tell discord [text]", "write to [app] [text]", "send to [app] [text]"
        m_app_bridge = (
            re.search(
                r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:write|type|send|give|paste|submit|run)\s+(?:this|a|an|the)?\s*(?:prompt\s+)?(?:to|in|into|for)\s+([a-zA-Z0-9_\-\.\+]+)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:tell|ask)\s+([a-zA-Z0-9_\-\.\+]+)\s+(?:to\s+)?(?:write|make|do|fix|generate)?\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"^(?:يا\s*عزرا\s*)?(?:اكتبي|ابعتي|ارسلي|سجلي|قولي|اطرحي)\s*(?:هذا|هاد|الـ)?\s*(?:برومبت|البرومبت)?\s*(?:لـ|إلى|الى|ل)\s*([a-zA-Z0-9_\-\.\+]+)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
        )
        if m_app_bridge:
            target_app = m_app_bridge.group(1).strip()
            if target_app not in ("the", "this", "my", "me", "him", "her", "them", "us", "it", "screen", "web", "youtube", "weather", "news"):
                prompt_payload = m_app_bridge.group(2).strip().strip("\"'").strip()
                prompt_payload = re.sub(r"^(?:to|that says|saying|about)\s+", "", prompt_payload, flags=re.IGNORECASE).strip()
                res = AppManager.prompt_app(target_app, prompt_payload, press_enter=True)
                speech = f"تم إرسال الأمر إلى {target_app} يا سيدي." if has_ar else f"Dispatched to {target_app}, sir."
                return {
                    "speech_text": speech,
                    "tool_calls": [{"tool": "prompt_app", "result": res}]
                }

        # Universal Shell Command Execution: "run command [cmd]", "execute [cmd]", "run in terminal [cmd]", "نفذي أمر [cmd]"
        m_shell = (
            re.search(
                r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:run|execute)\s+(?:the\s+)?(?:shell\s+|bash\s+|terminal\s+)?command\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:run|execute)\s+in\s+(?:terminal|bash|shell)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"^(?:يا\s*عزرا\s*)?(?:نفذي|شغلي)\s*(?:أمر|امر|بالترمينال|بالباش)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
        )
        if m_shell:
            shell_cmd = m_shell.group(1).strip().strip("\"'").strip()
            res = SystemManager.execute_shell_command(shell_cmd)
            out_preview = res.get("output", "")[:120].strip()
            speech = f"تم تنفيذ الأمر يا سيدي: {out_preview}" if has_ar else f"Command executed, sir. {out_preview}"
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "execute_shell_command", "result": res}]
            }

        # Live Typing & Dictation into Active Window (with optional Enter)
        if msg.startswith("type ") or msg.startswith("dictate ") or msg.startswith("write ") or msg.startswith("اكتبي ") or msg.startswith("اطبعي "):
            hit_enter = any(w in msg for w in ("and press enter", "and hit enter", "مع انتر", "واضغطي انتر", "ثم اضغطي انتر"))
            text_to_type = re.sub(r"^(?:type|dictate|write|اكتبي|اطبعي)\s*(?:this|out|for me|the following)?\s*:?\s*", "", user_message, flags=re.IGNORECASE).strip()
            text_to_type = re.sub(r"\s+(?:and\s+(?:press|hit)\s+enter|مع\s+انتر|واضغطي\s+انتر|ثم\s+اضغطي\s+انتر)$", "", text_to_type, flags=re.IGNORECASE).strip()
            if text_to_type:
                res = AppManager.type_message(text_to_type, press_enter=hit_enter)
                speech = f"كتبت النص{' وضغطت Enter' if hit_enter else ''} يا سيدي." if has_ar else f"Typed '{text_to_type[:40]}' for you{' and pressed Enter' if hit_enter else ''}, sir."
                return {
                    "speech_text": speech,
                    "tool_calls": [{"tool": "type_message", "result": res}]
                }

        # Press Enter / Hit Enter (Standalone key press ONLY when not a typing command)
        has_typing_intent = any(w in msg for w in ("type", "write", "dictate", "pipe", "اكتبي", "اطبعي", "terminal", "ترمينال"))
        if not has_typing_intent and any(w in msg for w in ("press enter", "hit enter", "send enter", "اضغطي انتر", "انتر")):
            res = AppManager.press_key("enter")
            speech = "تم ضغط مفتاح Enter يا سيدي." if has_ar else "Pressed Enter, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "press_key", "result": res}]
            }

        # Press Escape / Backspace / Tab
        m_key = re.search(r"press\s+(escape|esc|backspace|tab|space|up|down|left|right)", msg)
        if m_key:
            k = m_key.group(1)
            res = AppManager.press_key(k)
            return {
                "speech_text": f"Pressed {k}, sir.",
                "tool_calls": [{"tool": "press_key", "result": res}]
            }

        # Focus application window
        m_focus = re.search(r"(?:focus|switch to|bring up|ركزي على|روحي على)\s+(antigravity|discord|terminal|files|vlc|code|vscode|calculator|spotify|obs|chrome|firefox|brave)", msg)
        if m_focus:
            app_to_focus = m_focus.group(1)
            res = AppManager.focus_app(app_to_focus)
            speech = f"تم الانتقال إلى {app_to_focus} يا سيدي." if has_ar else f"Switched to {app_to_focus}, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "focus_app", "result": res}]
            }

        # Clipboard management
        if any(w in msg for w in ("what is on my clipboard", "what's on my clipboard", "read clipboard", "get clipboard", "شو في بالحافظة", "محتوى الحافظة")):
            res = AppManager.read_clipboard()
            clip_val = res.get("clipboard", "")
            if clip_val:
                speech = f"حفظت في الحافظة: '{clip_val[:50]}'" if has_ar else f"Clipboard contains: '{clip_val[:50]}'."
            else:
                speech = "الحافظة فارغة يا سيدي." if has_ar else "Clipboard is currently empty, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "get_clipboard", "result": res}]
            }

        m_copy = re.search(r"(?:copy\s+(?:this\s+)?(?:to\s+clipboard)?|انسخي\s*(?:للحافظة)?)\s*:?\s*(.+)", msg)
        if m_copy and not any(w in msg for w in ("file", "folder", "repo")):
            text_to_copy = m_copy.group(1).strip()
            res = AppManager.copy_to_clipboard(text_to_copy)
            speech = f"تم نسخ النص إلى الحافظة يا سيدي." if has_ar else f"Copied to clipboard, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "set_clipboard", "result": res}]
            }

        # 1. Executive Daily Briefing
        if "brief" in msg or "موجز" in msg or "morning" in msg:
            res = api_manager.get_daily_briefing()
            return {
                "speech_text": res.get("summary", "Executive briefing compiled."),
                "tool_calls": [{"tool": "get_daily_briefing", "result": res}]
            }

        # 2. Git Automation
        if "git status" in msg or "حالة الجت" in msg or "branch status" in msg:
            res = SystemManager.git_status()
            clean_state = "working tree clean" if res.get("is_clean") else f"{res.get('modified_files_count')} uncommitted files"
            return {
                "speech_text": f"Git repository is on branch {res.get('branch', 'main')}. {clean_state}.",
                "tool_calls": [{"tool": "git_status", "result": res}]
            }

        if "git publish" in msg or "publish repo" in msg or "publish changes" in msg or "انشر" in msg:
            res = SystemManager.git_publish()
            return {
                "speech_text": res.get("message", "Git publish executed."),
                "tool_calls": [{"tool": "git_publish", "result": res}]
            }

        if "recent commit" in msg or "git log" in msg:
            res = SystemManager.git_log_recent(limit=3)
            return {
                "speech_text": f"Recent commits: {res.get('summary', 'none')}.",
                "tool_calls": [{"tool": "git_log_recent", "result": res}]
            }

        if "git pull" in msg or "pull repo" in msg or "pull changes" in msg or "اسحب التغييرات" in msg:
            res = SystemManager.git_pull()
            return {
                "speech_text": res.get("message", "Git pull complete."),
                "tool_calls": [{"tool": "git_pull", "result": res}]
            }

        # 3. Google Drive Dual-Laptop Sync
        if "sync" in msg or "gdrive" in msg or "مزامنة" in msg or "sync data" in msg or "sync memory" in msg:
            res = SystemManager.sync_gdrive()
            return {
                "speech_text": res.get("message", "Cloud memory sync complete."),
                "tool_calls": [{"tool": "sync_gdrive", "result": res}]
            }

        # 4. Top System Processes (RAM / CPU Monitor)
        if any(w in msg for w in ("top process", "top processes", "process hogs", "what is using my ram", "ram usage", "شو اللي ماخذ رام", "العمليات")):
            res = SystemManager.get_top_processes(limit=3)
            speech = f"Top processes by memory: {res.get('summary', 'none')}."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "get_top_processes", "result": res}]
            }

        # 5. Lock Screen
        if any(w in msg for w in ("lock screen", "lock the screen", "lock computer", "lock pc", "قفل الشاشة", "اقفل الشاشة")):
            res = SystemManager.lock_screen()
            speech = "تم قفل الشاشة يا سيدي." if has_ar else "Locking desktop session now, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "lock_screen", "result": res}]
            }

        # 6. Voice Scratchpad / Notes
        if any(w in msg for w in ("take a note", "save note", "record note", "سجل ملاحظة", "اكتب ملاحظة")):
            note_text = re.sub(r"^(?:take a note|save note|record note|سجل ملاحظة|اكتب ملاحظة)\s*:?\s*", "", user_message, flags=re.IGNORECASE).strip()
            if note_text:
                res = SystemManager.add_note(note_text)
                speech = f"حفظت الملاحظة: {note_text}" if has_ar else f"Noted: '{note_text}', sir."
                return {
                    "speech_text": speech,
                    "tool_calls": [{"tool": "add_note", "result": res}]
                }

        if any(w in msg for w in ("read my notes", "what are my notes", "show notes", "اقرأ الملاحظات", "شو ملاحظاتي")):
            res = SystemManager.get_notes(limit=3)
            return {
                "speech_text": res.get("summary", "No notes found."),
                "tool_calls": [{"tool": "get_notes", "result": res}]
            }

        if any(w in msg for w in ("clear notes", "delete notes", "امسح الملاحظات")):
            res = SystemManager.clear_notes()
            speech = "تم مسح جميع الملاحظات." if has_ar else "Cleared all notes, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "clear_notes", "result": res}]
            }

        # 7. Interactive Tasks & Todos
        if any(w in msg for w in ("add todo", "add task", "remind me to", "أضف مهمة", "سجل مهمة")):
            task_text = re.sub(r"^(?:add todo|add task|remind me to|أضف مهمة|سجل مهمة)\s*:?\s*", "", user_message, flags=re.IGNORECASE).strip()
            if task_text:
                res = SystemManager.add_todo(task_text)
                speech = f"تمت إضافة المهمة: {task_text}" if has_ar else f"Added task: '{task_text}', sir."
                return {
                    "speech_text": speech,
                    "tool_calls": [{"tool": "add_todo", "result": res}]
                }

        if any(w in msg for w in ("what are my todos", "read my tasks", "show todos", "show tasks", "اقرأ المهام", "شو مهامي")):
            res = SystemManager.get_todos()
            return {
                "speech_text": res.get("summary", "No pending tasks."),
                "tool_calls": [{"tool": "get_todos", "result": res}]
            }

        if any(w in msg for w in ("clear todos", "clear tasks", "امسح المهام")):
            res = SystemManager.clear_todos()
            speech = "تم مسح قائمة المهام." if has_ar else "Cleared all tasks, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "clear_todos", "result": res}]
            }

        # 8. Recent Downloads
        if any(w in msg for w in ("recent downloads", "what did i download", "آخر التحميلات", "شو حملت")):
            res = SystemManager.get_recent_downloads(limit=4)
            speech = f"Recent downloads: {res.get('summary', 'none')}."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "get_recent_downloads", "result": res}]
            }

        # 9. Open Folders (Downloads, Documents, Pictures, Project)
        m_folder = re.search(r"(?:open|show)\s+(downloads|documents|pictures|project|code|ezra)\s*(?:folder)?", msg)
        if m_folder:
            f_name = m_folder.group(1)
            res = BrowserManager.open_folder(f_name)
            return {
                "speech_text": f"Opening your {f_name} folder, sir.",
                "tool_calls": [{"tool": "open_folder", "result": res}]
            }

        # 10. Developer Portal Search (Arch Linux Wiki, GitHub, Stack Overflow, Reddit)
        m_portal = re.search(r"search\s+(arch\s*wiki|github|stack\s*overflow|reddit)\s+(?:for\s+)?(.+)", msg)
        if m_portal:
            portal_target = m_portal.group(1).replace(" ", "")
            query_term = m_portal.group(2).strip()
            res = BrowserManager.search_portal(portal_target, query_term)
            return {
                "speech_text": f"Searching {portal_target} for {query_term}, sir.",
                "tool_calls": [{"tool": "search_portal", "result": res}]
            }

        # 3. Background Timers
        m_timer = re.search(r"(?:set|start)?\s*(?:a\s*)?timer\s*(?:for)?\s*(\d+)\s*(sec|second|seconds|min|minute|minutes)", msg) or re.search(r"مؤقت\s*(?:لمدة)?\s*(\d+)\s*(ثانية|دقيقة)", msg)
        if m_timer:
            val = int(m_timer.group(1))
            unit = m_timer.group(2)
            seconds = val * 60 if any(u in unit for u in ("min", "minute", "دقيقة")) else val
            res = SystemManager.schedule_timer(seconds, note=f"Timer for {val} {unit}")
            return {
                "speech_text": res.get("message", f"Timer set for {val} {unit}."),
                "tool_calls": [{"tool": "schedule_timer", "result": res}]
            }

        # 4. Compound Directive: Stop playback AND close browser tab
        if any(s in msg for s in ("stop", "pause", "توقف", "وقف")) and any(t in msg for t in ("tab", "close", "سكر", "اغلق")):
            res_media = SystemManager.media_control("pause")
            res_tab = BrowserManager.close_tab()
            speech = "تم إيقاف الأغنية وإغلاق التبويب يا سيدي." if has_ar else "Stopped playback and closed the tab, sir."
            return {
                "speech_text": speech,
                "tool_calls": [
                    {"tool": "media_control", "result": res_media},
                    {"tool": "close_tab", "result": res_tab}
                ]
            }

        # 5. Media Control: Stop / Pause playback
        if (
            any(w in msg for w in (
                "stop the song", "stop song", "stop the music", "stop music", "pause the song",
                "pause music", "pause song", "stop playing", "pause playback", "stop playback"
            ))
            or ("stop" in msg and any(m in msg for m in ("song", "music", "track", "audio", "video", "youtube")))
            or ("pause" in msg and any(m in msg for m in ("song", "music", "track", "audio", "video", "youtube")))
            or any(w in msg for w in ("وقف الأغنية", "وقف الموسيقى", "وقف الغنية", "وقف الفيديو", "توقف عن التشغيل"))
            or msg in ("pause", "stop", "وقف", "توقف")
        ):
            res = SystemManager.media_control("pause")
            speech = "حاضر يا سيدي، تم إيقاف التشغيل." if has_ar else "Playback paused, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "media_control", "result": res}]
            }

        # 6. Media Control: Resume / Play playback
        if (
            any(w in msg for w in (
                "resume the song", "resume song", "resume music", "play song", "continue music",
                "continue song", "unpause", "keep playing"
            ))
            or any(w in msg for w in ("شغل الأغنية", "شغل الموسيقى", "كمل الأغنية", "تابع التشغيل"))
            or msg in ("resume", "play", "unpause", "شغل")
        ):
            res = SystemManager.media_control("play")
            speech = "تم استئناف التشغيل يا سيدي." if has_ar else "Resuming playback, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "media_control", "result": res}]
            }

        # 7. Media Control: Next / Previous Track
        if any(w in msg for w in ("next song", "next track", "skip song", "skip track", "الأغنية التالية", "التالي")):
            res = SystemManager.media_control("next")
            speech = "الأغنية التالية، يا سيدي." if has_ar else "Skipping to the next track, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "media_control", "result": res}]
            }

        if any(w in msg for w in ("previous song", "previous track", "last song", "الأغنية السابقة", "السابق")):
            res = SystemManager.media_control("previous")
            speech = "الأغنية السابقة، يا سيدي." if has_ar else "Playing previous track, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "media_control", "result": res}]
            }

        # 8. Close Active Tab
        if (
            any(w in msg for w in ("close the tab", "close tab", "close this tab", "kill tab", "exit tab"))
            or any(w in msg for w in ("سكر التاب", "اغلق التبويب", "سكر التبويب", "اغلق الصفحة"))
        ):
            res = BrowserManager.close_tab()
            speech = "تم إغلاق التبويب يا سيدي." if has_ar else "Closed the active tab, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "close_tab", "result": res}]
            }

        # 9. Close Browser Session
        if any(w in msg for w in (
            "close chrome", "close google chrome", "close browser", "close the browser",
            "close brave", "close firefox", "close youtube", "سكر الكروم", "سكر المتصفح"
        )):
            res = BrowserManager.close_browser()
            speech = "تم إغلاق المتصفح يا سيدي." if has_ar else "Closed the browser session, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "close_browser", "result": res}]
            }

        # 10. Close ANY Desktop Application
        m_close_app = re.search(r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:close|kill|exit|quit|terminate|سكر|اغلق)\s+(?:application|app|برنامج|تطبيق)?\s*([a-zA-Z0-9_\-\.\+]+)$", msg, re.IGNORECASE)
        if m_close_app:
            app_to_kill = m_close_app.group(1).strip()
            if app_to_kill not in ("the", "this", "tab", "window", "browser", "music", "song", "all", "audio"):
                res = AppManager.close_app(app_to_kill)
                speech = f"تم إغلاق {app_to_kill} يا سيدي." if has_ar else f"Closed {app_to_kill}, sir."
                return {
                    "speech_text": speech,
                    "tool_calls": [{"tool": "close_app", "result": res}]
                }

        # 11. Launch ANY Desktop Application or Website
        m_launch_app = re.search(r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:open|launch|start|run|شغل|افتح)\s+(?:application|app|برنامج|تطبيق)?\s*([a-zA-Z0-9_\-\.\+]+)$", msg, re.IGNORECASE)
        if m_launch_app:
            target_to_open = m_launch_app.group(1).strip()
            if any(target_to_open.endswith(ext) for ext in (".com", ".org", ".net", ".io", ".dev", ".ai", ".co")):
                res = BrowserManager.open_url(target_to_open)
                return {
                    "speech_text": f"Opening {target_to_open} for you, sir.",
                    "tool_calls": [{"tool": "open_tab", "result": res}]
                }
            elif target_to_open in ("youtube", "google", "github", "reddit", "twitter", "twitch", "netflix", "chatgpt"):
                res = BrowserManager.open_url(f"https://{target_to_open}.com")
                return {
                    "speech_text": f"Opening {target_to_open} in your browser, sir.",
                    "tool_calls": [{"tool": "open_tab", "result": res}]
                }
            elif target_to_open not in ("the", "this", "tab", "browser", "folder", "downloads", "documents", "pictures", "notes", "todos", "project"):
                res = AppManager.launch_app(target_to_open)
                speech = f"جاري تشغيل {target_to_open} يا سيدي." if has_ar else f"Launching {target_to_open} for you, sir."
                return {
                    "speech_text": speech,
                    "tool_calls": [{"tool": "launch_app", "result": res}]
                }

        # General Web Search / Google Search
        m_web_search = re.search(
            r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:search\s+(?:the\s+web\s+|google\s+)?(?:for\s+)?|google\s+|ابحث\s+(?:في\s+قوقل\s+)?عن\s+)(.+)$",
            msg,
            re.IGNORECASE
        )
        if m_web_search and not any(w in msg for w in ("arch wiki", "github", "stack overflow", "reddit", "youtube")):
            query_str = m_web_search.group(1).strip()
            res = BrowserManager.search_web(query_str, engine="google")
            speech = f"جاري البحث عن {query_str} يا سيدي." if has_ar else f"Searching Google for '{query_str}', sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "search_web", "result": res}]
            }

        # Visual Screen Click
        m_click = re.search(
            r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:click\s+(?:on\s+)?|اضغطي\s+على\s+)(.+)$",
            msg,
            re.IGNORECASE
        )
        if m_click and not any(w in msg for w in ("mouse", "trackpad", "screen", "enter")):
            click_target = m_click.group(1).strip()
            res = screen_vision.locate_and_click(click_target)
            return {
                "speech_text": res.get("message", f"Clicked on {click_target}."),
                "tool_calls": [{"tool": "click_screen_element", "result": res}]
            }

        # System Power Management (Reboot, Suspend, Poweroff)
        if any(w in msg for w in ("reboot computer", "restart computer", "restart pc", "reboot pc", "إعادة تشغيل الكمبيوتر", "إعادة تشغيل الجهاز")):
            res = SystemManager.execute_shell_command("systemctl reboot || reboot")
            speech = "جاري إعادة تشغيل الجهاز يا سيدي." if has_ar else "Rebooting computer now, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "execute_shell_command", "result": res}]
            }

        if any(w in msg for w in ("suspend computer", "sleep computer", "put pc to sleep", "وضع السكون")):
            res = SystemManager.execute_shell_command("systemctl suspend")
            speech = "تم تفعيل وضع السكون يا سيدي." if has_ar else "Suspending desktop session, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "execute_shell_command", "result": res}]
            }

        if any(w in msg for w in ("shutdown computer", "power off computer", "turn off pc", "إطفاء الجهاز", "إيقاف تشغيل الكمبيوتر")):
            res = SystemManager.execute_shell_command("systemctl poweroff || poweroff")
            speech = "جاري إيقاف تشغيل الجهاز يا سيدي." if has_ar else "Shutting down computer, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "execute_shell_command", "result": res}]
            }

        # 12. Volume Controls
        if any(w in msg for w in ("volume up", "louder", "turn it up", "علي الصوت", "ارفع الصوت")):
            res = SystemManager.set_volume(85)
            speech = "تم رفع مستوى الصوت يا سيدي." if has_ar else "Turned the volume up, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "set_volume", "result": res}]
            }

        if any(w in msg for w in ("volume down", "quieter", "turn it down", "وطي الصوت", "اخفض الصوت")):
            res = SystemManager.set_volume(35)
            speech = "تم خفض مستوى الصوت يا سيدي." if has_ar else "Turned the volume down, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "set_volume", "result": res}]
            }

        if any(w in msg for w in ("mute volume", "mute sound", "mute pc", "mute laptop", "اكتم الصوت")):
            res = SystemManager.set_volume(0)
            speech = "تم كتم صوت النظام يا سيدي." if has_ar else "Master audio muted, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "set_volume", "result": res}]
            }

        m_vol = re.search(r"(?:set\s+)?volume\s+(?:to\s+)?(\d+)", msg) or re.search(r"الصوت\s+(?:على\s+)?(\d+)", msg)
        if m_vol:
            pct = int(m_vol.group(1))
            res = SystemManager.set_volume(pct)
            return {
                "speech_text": f"Volume set to {pct}%, sir.",
                "tool_calls": [{"tool": "set_volume", "result": res}]
            }

        # 13. Screen Screenshot
        if any(w in msg for w in ("take a screenshot", "take screenshot", "screenshot", "capture screen", "صور الشاشة", "لقطة شاشة", "سكرين شوت")):
            res = AppManager.take_screenshot()
            speech = "تم التقاط صورة للشاشة وحفظها يا سيدي." if has_ar else "Screenshot captured and saved, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "take_screenshot", "result": res}]
            }

        # 14. Top Tech News
        if any(w in msg for w in ("tech news", "hacker news", "technology news", "اخبار التقنية", "أخبار التكنولوجيا")):
            res = api_manager.get_tech_news(limit=3)
            articles = res.get("articles", [])
            if articles:
                titles = ". ".join([a.get("title", "") for a in articles if a.get("title")])
                speech = f"Top tech headlines: {titles}."
            else:
                speech = "Could not fetch top tech news at the moment, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "get_tech_news", "result": res}]
            }

        # 15. Autonomous Web & Knowledge Research
        if msg.startswith("research ") or msg.startswith("deep research ") or msg.startswith("ابحث عن "):
            clean_q = re.sub(r"^(research|deep research|ابحث عن)\s*", "", user_message, flags=re.IGNORECASE).strip()
            res = await ResearchSubAgent.deep_research(clean_q)
            return {
                "speech_text": res.get("summary", f"Research on {clean_q} completed."),
                "tool_calls": [{"tool": "deep_research", "result": res}]
            }

        # 16. YouTube / Media Playback
        if any(w in msg for w in ("movie", "watch", "youtube", "play", "listen to", "put on", "stream")):
            clean_q = re.sub(r"^(?:can\s+you\s+)?(?:open|watch|play|listen\s+to|stream|search\s+for)?\s*", "", msg, flags=re.IGNORECASE).strip()
            clean_q = re.sub(r"\s*(?:on\s+youtube|from\s+youtube|in\s+youtube)$", "", clean_q, flags=re.IGNORECASE).strip() or "trending videos"
            res = BrowserManager.play_youtube_video_or_music(clean_q)
            return {
                "speech_text": f"Starting \"{clean_q}\" on YouTube for you, sir.",
                "tool_calls": [{"tool": "play_youtube", "result": res}]
            }

        # 17. System Health & Hardware Diagnostics
        if "status" in msg or "diagnostics" in msg or "system" in msg or "مواصفات" in msg:
            res = SystemManager.get_system_status()
            return {
                "speech_text": f"Systems operational. CPU load is at {res['cpu_percent']}, and memory usage is {res['ram_used_gb']}.",
                "tool_calls": [{"tool": "get_system_status", "result": res}]
            }

        # 18. Voice Mute / Unmute
        if "mute" in msg or "be quiet" in msg or "silent" in msg or "shh" in msg or "stop talking" in msg:
            voice_speaker.set_muted(True)
            return {
                "speech_text": "Understood. Voice muted. I am operating in silent text mode.",
                "tool_calls": [{"tool": "toggle_voice", "result": {"status": "success", "message": "Voice muted"}}]
            }

        if "unmute" in msg or "speak up" in msg or "voice on" in msg or "talk to me" in msg:
            voice_speaker.set_muted(False)
            return {
                "speech_text": "Voice restored, sir. Ready and listening.",
                "tool_calls": [{"tool": "toggle_voice", "result": {"status": "success", "message": "Voice unmuted"}}]
            }

        # 19. Cybernetic Robot vs Silky Neural Voice Switching
        if any(w in msg for w in ("robot voice", "robotic voice", "robot mode", "صوت روبوت", "صوت آلي")):
            voice_speaker.set_robotic_mode(True)
            return {
                "speech_text": "Robotic cybernetic synthesis module activated, sir.",
                "tool_calls": [{"tool": "set_voice_mode", "result": {"mode": "robotic"}}]
            }

        if any(w in msg for w in ("neural voice", "normal voice", "smooth voice", "human voice", "صوت طبيعي", "صوت عادي")):
            voice_speaker.set_robotic_mode(False)
            return {
                "speech_text": "Silky neural voice restored, sir.",
                "tool_calls": [{"tool": "set_voice_mode", "result": {"mode": "neural"}}]
            }


        # 21. Live Weather
        if "weather" in msg or "temperature" in msg or "طقس" in msg or "حرارة" in msg:
            city_match = re.search(r"in ([a-zA-Z\s]+)", msg)
            city = city_match.group(1).strip() if city_match else ""
            res = api_manager.get_weather(city)
            summary = res.get("summary", "Could not retrieve weather details.")
            return {
                "speech_text": summary,
                "tool_calls": [{"tool": "get_weather", "result": res}]
            }

        # 22. Live Crypto Prices
        if "crypto" in msg or "bitcoin" in msg or "btc" in msg or "ethereum" in msg:
            res = api_manager.get_crypto_price()
            data = res.get("data", {})
            btc_p = data.get("bitcoin", {}).get("price", "unknown")
            eth_p = data.get("ethereum", {}).get("price", "unknown")
            return {
                "speech_text": f"Bitcoin is at {btc_p}, and Ethereum is at {eth_p}.",
                "tool_calls": [{"tool": "get_crypto_price", "result": res}]
            }

        # 23. Network Info
        if "network" in msg or "wifi" in msg or "ip" in msg:
            res = api_manager.get_network_info()
            net = res.get("network", {})
            return {
                "speech_text": f"Public IP is {net.get('public_ip')}, Wi-Fi is {net.get('wifi_ssid')}, and ping latency is {net.get('ping_latency')}.",
                "tool_calls": [{"tool": "get_network_info", "result": res}]
            }

        # 24. Screen OCR & Vision Inspection
        if "screen" in msg or "look" in msg:
            analysis = screen_vision.analyze_screen(user_message)
            return {
                "speech_text": analysis,
                "tool_calls": [{"tool": "inspect_screen", "result": {"message": analysis}}]
            }

        # 25. Open Google / Browser Tab
        if "open" in msg and ("google" in msg or "chrome" in msg or "tab" in msg):
            res = BrowserManager.open_url("https://google.com")
            return {
                "speech_text": "Opening a new browser tab for you now.",
                "tool_calls": [{"tool": "open_tab", "result": res}]
            }

        # 26. Capabilities / Help / What Can You Do
        if any(w in msg for w in (
            "what can you do", "what can she do", "what do you do", "capabilities",
            "what are your skills", "help me", "commands", "شو بتعرفي تعملي", "شو بتعملي", "ما هي قدراتك"
        )):
            speech = (
                "أنا مساعدتك الشخصية عزرا يا سيدي. يمكنني التحكم في تشغيل الموسيقى والوسائط، إغلاق وفتح التبويبات والتطبيقات، التقاط صور للشاشة، ضبط مستوى الصوت، مراقبة موارد النظام، إعداد المؤقتات، إجراء أبحاث الويب، متابعة أسعار العملات والطقس، وأتمتة Git والمزامنة مع تيليجرام. لتفعيل التفكير الحواري الكامل، يمكنك إضافة مفتاح Google AI Studio المجاني في ملف الإعدادات."
                if has_ar
                else "I control media playback, close and open browser tabs, launch and kill applications, take screenshots, adjust master audio, monitor system health, set background timers, conduct deep web research, track crypto and weather, automate Git workflows, and sync with Telegram. Adding a free Gemini key in your config unlocks full open-ended conversational reasoning."
            )
            return {
                "speech_text": speech,
                "tool_calls": []
            }

        # 27. Encyclopedic / Definition Lookups (Wikipedia / DuckDuckGo)
        m_wiki = re.search(r"^(?:who is|what is|tell me about|define|من هو|من هي|ما هو|ما هي|عرف)\s+(.+)", msg)
        if m_wiki:
            topic = m_wiki.group(1).strip()
            topic = re.sub(r"[?!.,]+$", "", topic)
            res = api_manager.search_instant_answer(topic)
            answer = res.get("answer") or res.get("extract") or ""
            if answer:
                summary = answer[:260] + ("..." if len(answer) > 260 else "")
                return {
                    "speech_text": summary,
                    "tool_calls": [{"tool": "search_wikipedia", "result": res}]
                }

        # 28. Intelligent Fallback (Try quick instant search if multi-word query)
        if len(msg.split()) >= 2 and not any(w in msg for w in ("hello", "hey", "hi", "test")):
            try:
                res = api_manager.search_instant_answer(user_message)
                answer = res.get("answer") or res.get("extract") or ""
                if answer:
                    summary = answer[:260] + ("..." if len(answer) > 260 else "")
                    return {
                        "speech_text": summary,
                        "tool_calls": [{"tool": "search_wikipedia", "result": res}]
                    }
            except Exception:
                pass

        fallback_speech = (
            "في خدمتك يا سيدي. يمكنك أمري بالتحكم في الموسيقى، إغلاق التبويبات، فتح التطبيقات، فحص النظام، أو إجراء أبحاث الويب."
            if has_ar
            else "At your command, sir. You can instruct me to control media, close tabs, launch apps, adjust audio, run web research, or check system status."
        )
        return {
            "speech_text": fallback_speech,
            "tool_calls": []
        }

brain_service = BrainEngine()
