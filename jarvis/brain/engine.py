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
    "inspect_screen, click_screen_element, prompt_antigravity, focus_app, type_message, dictate_text, press_key, press_hotkey, "
    "set_clipboard, get_clipboard, toggle_voice, set_voice_mode, get_weather, get_crypto_price, get_exchange_rate, search_wikipedia, get_network_info, "
    "get_tech_news, get_github_info, open_tab, close_tab, close_browser, search_web, search_portal, open_folder, play_youtube, launch_app, close_app, "
    "send_discord_message, take_screenshot, media_control, get_system_status, get_top_processes, set_volume, remember_fact, "
    "execute_shell_command, send_email, send_telegram, get_daily_briefing, send_desktop_notification, "
    "schedule_timer, git_status, git_publish, git_log_recent, git_pull, sync_gdrive, lock_screen, "
    "add_note, get_notes, clear_notes, add_todo, get_todos, clear_todos, get_recent_downloads, deep_research"
)

SYSTEM_PROMPT_TEMPLATE = f"""You are Ezra, an ultra-fast, loyal, witty British AI assistant (inspired by JARVIS).
Rules:
- Ultra-short & punchy: 1 sentence preferred, 2 max. Never bloat replies.
- Direct & sharp British wit.
- Multilingual & Slang: Seamlessly understand British English, modern slang, idioms, and Arabic (العربية). Reply in British English, or in natural Arabic if addressed in Arabic.
- Spoken input: Understand intended conversational meaning even with minor acoustic homophones.
- Execute actions immediately.
User Context: {{learned_context}}

Tools available:
{ALL_TOOLS_LIST}.

Format any tool calls as:
```tool_call
{{"tool": "tool_name", "args": {{...}}}}
```"""

def get_system_prompt(learned_context: str) -> str:
    """Loads system instructions from SOUL.md with dynamic context injection."""
    if SOUL_FILE.exists():
        try:
            soul_text = SOUL_FILE.read_text(encoding="utf-8").strip()
            tools_spec = (
                f"\n\nTools available:\n{ALL_TOOLS_LIST}.\n\n"
                "Format any tool calls strictly as:\n"
                "```tool_call\n"
                '{"tool": "tool_name", "args": {...}}\n'
                "```"
            )
            return f"{soul_text}\n\nLearned User Context:\n{learned_context}{tools_spec}"
        except Exception:
            pass
    return SYSTEM_PROMPT_TEMPLATE.format(learned_context=learned_context)

class BrainEngine:
    def __init__(self):
        self.gemini_key = GEMINI_API_KEY
        self.groq_key = GROQ_API_KEY

    def reload_keys(self):
        from config import settings
        import importlib
        importlib.reload(settings)
        self.gemini_key = settings.GEMINI_API_KEY
        self.groq_key = settings.GROQ_API_KEY

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
            elif tool_name == "type_message":
                text = args.get("text", "") or args.get("message", "") or user_context
                res = AppManager.type_message(text, args.get("press_enter", False))
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
                res = AppManager.focus_app(app_name)
            elif tool_name == "prompt_antigravity":
                prompt_txt = args.get("prompt") or args.get("text") or args.get("query") or user_context
                res = AppManager.prompt_antigravity(prompt_txt)
            elif tool_name == "type_message":
                msg_txt = args.get("text") or args.get("message") or ""
                press_enter = bool(args.get("press_enter", False) or args.get("enter", False))
                res = AppManager.type_message(msg_txt, press_enter=press_enter)
            elif tool_name == "dictate_text":
                msg_txt = args.get("text") or args.get("message") or ""
                press_enter = bool(args.get("press_enter", False))
                res = AppManager.dictate_text(msg_txt, press_enter=press_enter)
            elif tool_name == "press_key":
                key_name = args.get("key") or args.get("name") or "enter"
                res = AppManager.press_key(key_name)
            elif tool_name == "press_hotkey":
                keys_list = args.get("keys") or [args.get("key", "enter")]
                res = AppManager.press_hotkey(keys_list)
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
        """Instant conversational reflex: replies in <1ms without LLM thinking for routine interaction."""
        import random
        m = msg.strip().lower()
        # Clean punctuation
        m_clean = re.sub(r"[^\w\s]", "", m).strip()

        # Clean leading filler like 'ezra', 'israel', 'i said', 'so'
        m_intent = re.sub(r"^(ezra|israel|hey|hi|yo|so|and|i said)\s+", "", m_clean).strip()

        # Greetings
        if m_clean in ("hi", "hello", "hey", "hey ezra", "hello ezra", "hi ezra", "morning", "good morning") or m_intent in ("hi", "hello", "hey"):
            return random.choice([
                "Good day, sir. At your command.",
                "Right here, sir. How can I assist?",
                "Hello, sir. Standing by."
            ])

        # Status / liveness checks
        if m_clean in ("are you there", "you there", "ezra", "can you hear me", "you listening") or m_intent in ("are you there", "you there"):
            return random.choice([
                "Loud and clear, sir.",
                "Always, sir. Ready when you are.",
                "Right beside you, sir."
            ])

        # Acknowledgements
        if m_clean in ("thank you", "thanks", "thanks ezra", "thank you ezra", "cheers") or m_intent in ("thank you", "thanks"):
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

        if "how are you" in m_clean or "how r u" in m_clean or "how you doing" in m_clean or m_intent in ("how are you", "how are you doing", "how are things"):
            return "Operating at peak performance, sir. Ready for your instructions."

        # British slang & casual greetings
        if m_clean in ("wassup", "what's good", "whats good", "wagwan", "alright mate", "yo", "sup") or m_intent in ("wassup", "what's good", "whats good", "wagwan", "alright mate"):
            return random.choice([
                "All good on my end, mate. What's on your mind?",
                "Everything running smooth, sir. How can I help?",
                "Top shape, sir. What are we getting into?"
            ])

        # Arabic greetings
        if any(w in m for w in ("مرحبا", "أهلا", "اهلا", "سلام", "السلام عليكم", "صباح الخير", "مساء الخير", "هلا")):
            return random.choice([
                "أهلاً بك يا سيدي، في خدمتك دائماً.",
                "مرحباً بك، كيف يمكنني مساعدتك؟",
                "أهلاً وسهلاً، أنا في الاستماع."
            ])

        # Arabic status / liveness
        if any(w in m for w in ("سامعني", "أنت هنا", "انت هنا", "سامعتني", "موجودة", "وينك")):
            return random.choice([
                "نعم يا سيدي، أسمعك بكل وضوح.",
                "معك دائماً، تفضل بأوامرك.",
                "بجانبك يا سيدي، جاهزة لكل طلباتك."
            ])

        # Arabic acknowledgements
        if any(w in m for w in ("شكرا", "شكراً", "تسلم", "يعطيك العافية", "مشكورة")):
            return random.choice([
                "العفو يا سيدي، في خدمتك دائماً.",
                "بكل سرور يا سيدي.",
                "على الرحب والسعة دائماً."
            ])

        # Arabic condition
        if any(w in m for w in ("كيفك", "كيف حالك", "شو اخبارك", "شلونك")):
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

        # Build context from learned facts
        facts = memory_service.get_all_facts()
        facts_str = "\n".join([f"- {k}: {v}" for k, v in facts.items()]) or "No specific custom facts recorded yet."
        prompt = get_system_prompt(learned_context=facts_str)

        output = None
        # 1. Attempt Gemini (Free on Google AI Studio)
        if self.gemini_key:
            try:
                output = await self._call_gemini(user_message, prompt, speaker_tier=speaker_tier)
            except Exception as e:
                print(f"[Brain] Gemini error: {e}")

        # 2. Attempt Groq fallback
        if not output and self.groq_key:
            try:
                output = await self._call_groq(user_message, prompt, speaker_tier=speaker_tier)
            except Exception as e:
                print(f"[Brain] Groq error: {e}")

        # 3. Attempt Local Ollama fallback (100% Offline LLM on localhost:11434)
        if not output:
            try:
                output = await self._call_ollama(user_message, prompt, speaker_tier=speaker_tier)
            except Exception:
                pass

        # 4. Offline smart rule fallback
        if not output:
            output = await self._offline_smart_fallback(user_message)

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
            "gemini-3.5-flash",
            "gemini-3.7-flash",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-2.5-pro",
            "gemini-pro-latest"
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
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 200}
        }

        timeout = aiohttp.ClientTimeout(total=8.0, connect=3.0)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
                try:
                    async with session.post(url, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if "candidates" in data and data["candidates"]:
                                reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
                                return await self._process_tool_calls_in_text(reply_text, user_context=user_message, speaker_tier=speaker_tier)
                        elif resp.status in (404, 400, 503):
                            continue  # Try next model in candidate list
                except Exception:
                    continue
        raise Exception("All Gemini candidate models failed to respond.")

    async def _call_groq(self, user_message: str, system_prompt: str, speaker_tier: str = "verified") -> Dict[str, Any]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_key}"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.7
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
                if "choices" in data:
                    reply_text = data["choices"][0]["message"]["content"]
                    return await self._process_tool_calls_in_text(reply_text, user_context=user_message, speaker_tier=speaker_tier)
                else:
                    raise Exception(f"Groq API returned error: {data}")

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
        pattern = r"```tool_call\s*(.*?)\s*```"
        matches = re.findall(pattern, reply_text, re.DOTALL)
        
        tool_results = []
        for match in matches:
            try:
                call_data = json.loads(match.strip())
                res = await self.execute_tool(call_data["tool"], call_data.get("args", {}), user_context=user_context, speaker_tier=speaker_tier)
                tool_results.append({"tool": call_data["tool"], "result": json.loads(res)})
            except Exception as e:
                tool_results.append({"error": str(e)})

        clean_text = re.sub(pattern, "", reply_text).strip()
        tool_speech = None
        if tool_results:
            first_tool = tool_results[0].get("tool", "")
            first_res = tool_results[0].get("result", {})
            if isinstance(first_res, dict):
                if first_tool == "get_system_status":
                    tool_speech = f"Systems nominal, sir. CPU at {first_res.get('cpu_percent', '--')}, RAM at {first_res.get('ram_used_gb', '--')}, battery at {first_res.get('battery', 'OK')}."
                elif first_tool == "get_crypto_price" and "data" in first_res:
                    prices_str = ", ".join([f"{k.capitalize()} is at {v.get('price', '')}" for k, v in first_res["data"].items()])
                    tool_speech = f"Live market figures: {prices_str}."
                elif first_tool == "get_network_info" and "network" in first_res:
                    net = first_res.get("network", {})
                    tool_speech = f"Public IP is {net.get('public_ip', '--')}, Wi-Fi is {net.get('wifi_ssid', '--')}, latency {net.get('ping_latency', '--')}."
                elif first_tool == "get_tech_news" and "articles" in first_res:
                    titles = "; ".join([a.get('title', '') for a in first_res["articles"][:3]])
                    tool_speech = f"Top headlines right now: {titles}."
                elif first_tool == "get_github_info":
                    if "recent_repos" in first_res:
                        repos = ", ".join(first_res["recent_repos"][:4])
                        tool_speech = f"User {first_res.get('username')} has {first_res.get('public_repos_count')} repos, including {repos}."
                    elif "description" in first_res:
                        tool_speech = f"Repo {first_res.get('repo_name')} ({first_res.get('stars')} stars): {first_res.get('description')}."
                elif first_tool == "git_status":
                    clean_state = "working tree clean" if first_res.get("is_clean") else f"{first_res.get('modified_files_count')} uncommitted files"
                    tool_speech = f"On branch {first_res.get('branch', 'main')}: {clean_state}."
                elif first_tool == "git_log_recent":
                    tool_speech = f"Recent commits: {first_res.get('summary', '')}."
                elif "summary" in first_res:
                    tool_speech = first_res["summary"]
                elif "extract" in first_res:
                    tool_speech = first_res["extract"]
                elif "message" in first_res and not clean_text:
                    tool_speech = first_res["message"]

        if tool_speech:
            if not clean_text:
                clean_text = tool_speech
            elif any(first_tool.startswith(prefix) for prefix in ["get_", "search_", "inspect_"]):
                clean_text = f"{clean_text} {tool_speech}"
        elif not clean_text and tool_results:
            clean_text = f"Directive for {tool_results[0].get('tool', 'command')} completed, sir."

        # SPEECH GATE PROTOCOL:
        # Prevent claiming an action succeeded if the tool failed or threw an error.
        if tool_results:
            first_tool = tool_results[0].get("tool", "")
            first_res = tool_results[0].get("result", {})
            first_err = tool_results[0].get("error", "")
            
            is_error = bool(first_err) or (isinstance(first_res, dict) and first_res.get("status") == "error")
            if is_error:
                err_detail = first_err or (first_res.get("message") if isinstance(first_res, dict) else "execution failed")
                clean_text = f"Action for {first_tool} could not be completed, sir. Reason: {err_detail}."

        return {
            "speech_text": clean_text,
            "full_reply": reply_text,
            "tool_calls": tool_results
        }

    async def _offline_smart_fallback(self, user_message: str) -> Dict[str, Any]:
        msg = user_message.lower().strip()
        has_ar = bool(re.search(r"[\u0600-\u06FF]", msg))

        # 0. Antigravity Prompt Bridge (Direct Neural Voice Bridge to Antigravity IDE)
        m_antigrav = (
            re.search(
                r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:can you\s+)?(?:please\s+)?(?:write|type|send|give|paste|submit|run)\s+(?:this\s+)?(?:prompt\s+)?(?:to|in|into|for)\s+(?:anti-?gravity|antique gravity|gravity)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"^(?:(?:hi|hey|yo)\s+)?(?:ezra\s*,?\s*)?(?:tell|ask|prompt)\s+(?:anti-?gravity|antique gravity|gravity)\s+(?:to\s+)?(?:write|make|do|fix|generate)?\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
            or re.search(
                r"^(?:يا\s*عزرا\s*)?(?:اكتبي|ابعتي|ارسلي|سجلي|قولي|اطرحي)\s*(?:هذا\s*)?(?:البرومبت\s*)?(?:لـ|إلى|الى|ل)\s*(?:antigravity|انتي\s*جرافيتي|انتيجرافيتي|جرافيتي)\s*:?\s*(.+)$",
                msg,
                re.IGNORECASE
            )
        )
        if m_antigrav:
            prompt_payload = m_antigrav.group(1).strip().strip("\"'").strip()
            res = AppManager.prompt_antigravity(prompt_payload)
            speech = f"تم إرسال الأمر إلى Antigravity يا سيدي: '{prompt_payload[:40]}'." if has_ar else f"Prompt dispatched to Antigravity, sir: '{prompt_payload[:45]}'."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "prompt_antigravity", "result": res}]
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

        # Press Enter / Hit Enter (Standalone key press)
        if any(w in msg for w in ("press enter", "hit enter", "send enter", "اضغطي انتر", "انتر")):
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

        # 10. Close Desktop Application
        m_close_app = re.search(r"(?:close|kill|exit|quit|سكر|اغلق)\s+(discord|terminal|files|vlc|code|vscode|calculator|spotify|obs|antigravity)", msg)
        if m_close_app:
            app_to_kill = m_close_app.group(1)
            res = AppManager.close_app(app_to_kill)
            speech = f"تم إغلاق {app_to_kill} يا سيدي." if has_ar else f"Closed {app_to_kill}, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "close_app", "result": res}]
            }

        # 11. Launch Desktop Application
        m_launch_app = re.search(r"(?:open|launch|start|شغل|افتح)\s+(discord|terminal|files|vlc|code|vscode|calculator|spotify|obs|settings|brave|firefox|chrome)", msg)
        if m_launch_app:
            app_to_open = m_launch_app.group(1)
            res = AppManager.launch_app(app_to_open)
            speech = f"جاري تشغيل {app_to_open} يا سيدي." if has_ar else f"Launching {app_to_open} for you, sir."
            return {
                "speech_text": speech,
                "tool_calls": [{"tool": "launch_app", "result": res}]
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
        if "movie" in msg or "watch" in msg or "youtube" in msg:
            clean_q = re.sub(r"(open|watch|play|movie|video|on youtube)", "", msg).strip() or "trending movies"
            res = BrowserManager.play_youtube_video_or_music(clean_q)
            return {
                "speech_text": f"Right away, sir. Pulling up {clean_q} on YouTube.",
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
