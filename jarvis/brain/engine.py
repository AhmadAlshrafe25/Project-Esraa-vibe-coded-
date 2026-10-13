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
from jarvis.memory import memory_service

SYSTEM_PROMPT_TEMPLATE = """You are Ezra, an ultra-fast, loyal, witty British AI assistant (inspired by JARVIS).
Rules:
- Ultra-short & punchy: 1 sentence preferred, 2 max. Never bloat replies.
- Direct & sharp British wit.
- Spoken input: Understand intended conversational meaning even with minor acoustic homophones.
- Execute actions immediately.
User Context: {learned_context}

Tools available:
inspect_screen, click_screen_element, type_message, dictate_text, press_key, press_hotkey, toggle_voice, get_weather, get_crypto_price, get_exchange_rate, search_wikipedia, get_network_info, get_tech_news, get_github_info, open_tab, search_web, play_youtube, launch_app, close_app, send_discord_message, take_screenshot, media_control, get_system_status, set_volume, remember_fact, execute_shell_command, send_email, send_telegram.

Format any tool calls as:
```tool_call
{{"tool": "tool_name", "args": {{...}}}}
```"""

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

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Executes system or desktop action."""
        try:
            if tool_name == "inspect_screen":
                vision_analysis = screen_vision.analyze_screen(args.get("instruction", "Describe what is on screen"))
                res = {"status": "success", "message": vision_analysis, "screen_vision": vision_analysis}
            elif tool_name == "click_screen_element":
                res = screen_vision.locate_and_click(args.get("description", ""))
            elif tool_name == "type_message":
                res = AppManager.type_message(args.get("text", ""), args.get("press_enter", False))
            elif tool_name == "dictate_text":
                res = AppManager.dictate_text(args.get("text", ""), args.get("press_enter", False))
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
                res = api_manager.get_weather(args.get("city", ""))
            elif tool_name == "get_crypto_price":
                res = api_manager.get_crypto_price(args.get("coins", "bitcoin,ethereum"), args.get("currency", "usd"))
            elif tool_name == "get_exchange_rate":
                res = api_manager.get_exchange_rate(args.get("base_currency", "USD"), args.get("target_currency", "EUR"))
            elif tool_name == "search_wikipedia":
                res = api_manager.search_wikipedia(args.get("query", ""))
            elif tool_name == "get_network_info":
                res = api_manager.get_network_info()
            elif tool_name == "get_tech_news":
                res = api_manager.get_tech_news(int(args.get("limit", 5)))
            elif tool_name == "get_github_info":
                res = api_manager.get_github_info(args.get("username", "AhmadAlshrafe25"), args.get("repo", ""))
            elif tool_name == "open_tab":
                res = BrowserManager.open_url(args.get("url", ""))
            elif tool_name == "search_web":
                res = BrowserManager.search_web(args.get("query", ""), args.get("engine", "google"))
            elif tool_name == "play_youtube":
                res = BrowserManager.play_youtube_video_or_music(args.get("query", ""))
            elif tool_name == "launch_app":
                res = AppManager.launch_app(args.get("app_name", ""))
            elif tool_name == "close_app":
                res = AppManager.close_app(args.get("app_name", ""))
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

        # Greetings
        if m_clean in ("hi", "hello", "hey", "hey ezra", "hello ezra", "hi ezra", "morning", "good morning"):
            return random.choice([
                "Good day, sir. At your command.",
                "Right here, sir. How can I assist?",
                "Hello, sir. Standing by."
            ])

        # Status / liveness checks
        if m_clean in ("are you there", "you there", "ezra", "can you hear me", "you listening"):
            return random.choice([
                "Loud and clear, sir.",
                "Always, sir. Ready when you are.",
                "Right beside you, sir."
            ])

        # Acknowledgements
        if m_clean in ("thank you", "thanks", "thanks ezra", "thank you ezra", "cheers"):
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

        if m_clean in ("how are you", "how are you doing", "how are things"):
            return "Operating at peak performance, sir. Ready for your instructions."

        return None

    async def think(self, user_message: str) -> Dict[str, Any]:
        """Main LLM reasoning loop with instant reflexes and fast fallback."""
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
        prompt = SYSTEM_PROMPT_TEMPLATE.format(learned_context=facts_str)

        output = None
        # 1. Attempt Gemini (Free on Google AI Studio)
        if self.gemini_key:
            try:
                output = await self._call_gemini(user_message, prompt)
            except Exception as e:
                print(f"[Brain] Gemini error: {e}")

        # 2. Attempt Groq fallback
        if not output and self.groq_key:
            try:
                output = await self._call_groq(user_message, prompt)
            except Exception as e:
                print(f"[Brain] Groq error: {e}")

        # 3. Offline rule fallback
        if not output:
            output = await self._offline_smart_fallback(user_message)

        # Save Ezra reply to memory
        reply_speech = output.get("speech_text", "")
        memory_service.save_message("ezra", reply_speech, output.get("tool_calls", []))

        # Continuously adapt and learn from interaction in background
        asyncio.create_task(memory_service.auto_learn_from_interaction(user_message, reply_speech))
        return output

    async def _call_gemini(self, user_message: str, system_prompt: str) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={self.gemini_key}"
        
        recent = memory_service.get_recent_history(6)
        formatted_history = []
        for h in recent[:-1]:  # Exclude current message
            role = "user" if h["sender"] == "user" else "model"
            formatted_history.append({"role": role, "parts": [{"text": h["message"]}]})

        contents = formatted_history + [
            {"role": "user", "parts": [{"text": system_prompt + "\n\nUser: " + user_message}]}
        ]
        
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 85}
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if "candidates" in data:
                    reply_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    return await self._process_tool_calls_in_text(reply_text)
                else:
                    raise Exception(f"Gemini API returned error: {data}")

    async def _call_groq(self, user_message: str, system_prompt: str) -> Dict[str, Any]:
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
                    return await self._process_tool_calls_in_text(reply_text)
                else:
                    raise Exception(f"Groq API returned error: {data}")

    async def _process_tool_calls_in_text(self, reply_text: str) -> Dict[str, Any]:
        pattern = r"```tool_call\s*(.*?)\s*```"
        matches = re.findall(pattern, reply_text, re.DOTALL)
        
        tool_results = []
        for match in matches:
            try:
                call_data = json.loads(match.strip())
                res = await self.execute_tool(call_data["tool"], call_data.get("args", {}))
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

        return {
            "speech_text": clean_text,
            "full_reply": reply_text,
            "tool_calls": tool_results
        }

    async def _offline_smart_fallback(self, user_message: str) -> Dict[str, Any]:
        msg = user_message.lower().strip()
        
        if "movie" in msg or "watch" in msg or "youtube" in msg:
            clean_q = re.sub(r"(open|watch|play|movie|video|on youtube)", "", msg).strip() or "trending movies"
            res = BrowserManager.play_youtube_video_or_music(clean_q)
            return {
                "speech_text": f"Right away, sir. Pulling up {clean_q} on YouTube.",
                "tool_calls": [{"tool": "play_youtube", "result": res}]
            }
        
        if "status" in msg or "diagnostics" in msg or "system" in msg:
            res = SystemManager.get_system_status()
            return {
                "speech_text": f"Systems operational. CPU load is at {res['cpu_percent']}, and memory usage is {res['ram_used_gb']}.",
                "tool_calls": [{"tool": "get_system_status", "result": res}]
            }

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

        if msg.startswith("type ") or msg.startswith("dictate ") or msg.startswith("write "):
            text_to_type = re.sub(r"^(type|dictate|write)\s*(this|out|for me|the following)?\s*:?\s*", "", user_message, flags=re.IGNORECASE).strip()
            res = AppManager.type_message(text_to_type, press_enter=False)
            return {
                "speech_text": f"Typed '{text_to_type[:40]}' for you, sir.",
                "tool_calls": [{"tool": "type_message", "result": res}]
            }

        if "weather" in msg or "temperature" in msg:
            city_match = re.search(r"in ([a-zA-Z\s]+)", msg)
            city = city_match.group(1).strip() if city_match else ""
            res = api_manager.get_weather(city)
            summary = res.get("summary", "Could not retrieve weather details.")
            return {
                "speech_text": summary,
                "tool_calls": [{"tool": "get_weather", "result": res}]
            }

        if "crypto" in msg or "bitcoin" in msg or "btc" in msg or "ethereum" in msg:
            res = api_manager.get_crypto_price()
            data = res.get("data", {})
            btc_p = data.get("bitcoin", {}).get("price", "unknown")
            eth_p = data.get("ethereum", {}).get("price", "unknown")
            return {
                "speech_text": f"Bitcoin is at {btc_p}, and Ethereum is at {eth_p}.",
                "tool_calls": [{"tool": "get_crypto_price", "result": res}]
            }

        if "network" in msg or "wifi" in msg or "ip" in msg:
            res = api_manager.get_network_info()
            net = res.get("network", {})
            return {
                "speech_text": f"Public IP is {net.get('public_ip')}, Wi-Fi is {net.get('wifi_ssid')}, and ping latency is {net.get('ping_latency')}.",
                "tool_calls": [{"tool": "get_network_info", "result": res}]
            }

        if "screen" in msg or "look" in msg:
            analysis = screen_vision.analyze_screen(user_message)
            return {
                "speech_text": analysis,
                "tool_calls": [{"tool": "inspect_screen", "result": {"message": analysis}}]
            }

        if "open" in msg and ("google" in msg or "chrome" in msg or "tab" in msg):
            res = BrowserManager.open_url("https://google.com")
            return {
                "speech_text": "Opening a new browser tab for you now.",
                "tool_calls": [{"tool": "open_tab", "result": res}]
            }

        return {
            "speech_text": "Online and standing by. I am listening.",
            "tool_calls": []
        }

brain_service = BrainEngine()
