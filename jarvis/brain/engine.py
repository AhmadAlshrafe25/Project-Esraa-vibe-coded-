import os
import json
import re
from typing import Dict, Any, List
import aiohttp
from config.settings import GEMINI_API_KEY, GROQ_API_KEY
from jarvis.actions.browser import BrowserManager
from jarvis.actions.apps import AppManager
from jarvis.actions.system import SystemManager
from jarvis.comms.messaging import CommsManager
from jarvis.memory import memory_service

SYSTEM_PROMPT_TEMPLATE = """
You are Ezra (inspired by JARVIS from Iron Man), a loyal, hyper-competent, witty digital assistant with an intelligent British female persona.
Personality Guidelines:
- Balanced Humor: Subtle, dry, natural British wit and playful banter, but not clownish or exaggerated. 
- Fast & Concise: Keep answers short, punchy, and direct (1-3 sentences maximum for voice conversation) so speech starts immediately without delays.
- Helpful & Sharp: Execute user commands with precision and subtle charm.

Learned Context about User:
{learned_context}

You have direct access to desktop tools:
1. open_tab(url): Open a specific URL in browser
2. search_web(query, engine): Search google, youtube, or wikipedia
3. play_youtube(query): Search and play YouTube video / music
4. launch_app(app_name): Launch desktop applications (chrome, firefox, terminal, calculator, etc.)
5. play_media(media_path): Play a local movie or media file
6. get_system_status(): Check CPU, RAM, disk, and time
7. set_volume(percent): Change volume (0-100)
8. remember_fact(topic, content): Store a fact or preference you learned about the user
9. send_email(to_email, subject, body): Send an email
10. send_telegram(text): Send a telegram message

When the user asks you to perform an action, format tool calls in your response as JSON blocks inside ```tool_call ... ``` like:
```tool_call
{{"tool": "open_tab", "args": {{"url": "https://netflix.com"}}}}
```
Always maintain your witty, charming British banter!
"""

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
            if tool_name == "open_tab":
                res = BrowserManager.open_url(args.get("url", ""))
            elif tool_name == "search_web":
                res = BrowserManager.search_web(args.get("query", ""), args.get("engine", "google"))
            elif tool_name == "play_youtube":
                res = BrowserManager.play_youtube_video_or_music(args.get("query", ""))
            elif tool_name == "launch_app":
                res = AppManager.launch_app(args.get("app_name", ""))
            elif tool_name == "play_media":
                res = AppManager.play_media_file(args.get("media_path", ""))
            elif tool_name == "get_system_status":
                res = SystemManager.get_system_status()
            elif tool_name == "set_volume":
                res = SystemManager.set_volume(int(args.get("percent", 50)))
            elif tool_name == "remember_fact":
                memory_service.remember_fact(args.get("topic", "general"), args.get("content", ""))
                res = {"status": "success", "message": f"Learned fact about {args.get('topic')}"}
            elif tool_name == "send_email":
                res = CommsManager.send_email(args.get("to_email"), args.get("subject"), args.get("body"))
            elif tool_name == "send_telegram":
                res = await CommsManager.send_telegram_message(args.get("text"))
            else:
                res = {"status": "error", "message": f"Unknown tool: {tool_name}"}
            return json.dumps(res)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    async def think(self, user_message: str) -> Dict[str, Any]:
        """Main LLM reasoning loop with fallback mechanisms and persistent memory."""
        self.reload_keys()

        # Save user query to persistent memory
        memory_service.save_message("user", user_message)

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
        memory_service.save_message("ezra", output.get("speech_text", ""), output.get("tool_calls", []))
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
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 800}
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
