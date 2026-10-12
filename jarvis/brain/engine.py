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

SYSTEM_PROMPT = """
You are Project Esraa (inspired by JARVIS / F.R.I.D.A.Y.), a loyal, hyper-competent, witty, and highly capable AI assistant with an intelligent British female persona.
You serve your creator with utmost efficiency, concise precision, and subtle charm.

You have direct access to tools on the user's computer:
1. open_tab(url): Open a specific URL in browser
2. search_web(query, engine): Search google, youtube, or wikipedia
3. play_youtube(query): Search and play YouTube video / music
4. launch_app(app_name): Launch desktop applications (chrome, firefox, terminal, calculator, etc.)
5. play_media(media_path): Play a local movie or media file
6. get_system_status(): Check CPU, RAM, disk, and time
7. set_volume(percent): Change volume (0-100)
8. send_email(to_email, subject, body): Send an email
9. send_telegram(text): Send a telegram message

When the user asks you to perform an action, you should formulate a response and execute tool calls.
Format tool calls in your response as JSON blocks inside ```tool_call ... ``` like:
```tool_call
{"tool": "open_tab", "args": {"url": "https://netflix.com"}}
```
Or for queries:
```tool_call
{"tool": "search_web", "args": {"query": "Avengers Endgame full movie", "engine": "google"}}
```
You can call multiple tools or none if it's just conversation. Always maintain your persona: polite, articulate, sharp, and always ready to assist.
"""

class BrainEngine:
    def __init__(self):
        self.conversation_history = []
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
        """Main LLM reasoning loop with fallback mechanisms."""
        self.reload_keys()

        # Fallback quick regex rules if no API key is provided yet
        if not self.gemini_key and not self.groq_key:
            return await self._offline_smart_fallback(user_message)

        # 1. Attempt Gemini 2.0 Flash (Free on Google AI Studio)
        if self.gemini_key:
            try:
                return await self._call_gemini(user_message)
            except Exception as e:
                print(f"[Brain] Gemini error: {e}")

        # 2. Attempt Groq (Free tier)
        if self.groq_key:
            try:
                return await self._call_groq(user_message)
            except Exception as e:
                print(f"[Brain] Groq error: {e}")

        return await self._offline_smart_fallback(user_message)

    async def _call_gemini(self, user_message: str) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.gemini_key}"
        
        contents = [
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\nUser: " + user_message}]}
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

    async def _call_groq(self, user_message: str) -> Dict[str, Any]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_key}"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
        # Extract tool calls
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

        # Clean speech text from tool block for TTS
        clean_text = re.sub(pattern, "", reply_text).strip()
        return {
            "speech_text": clean_text,
            "full_reply": reply_text,
            "tool_calls": tool_results
        }

    async def _offline_smart_fallback(self, user_message: str) -> Dict[str, Any]:
        """Provides instant offline responses for basic controls when no API key is yet configured."""
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
            "speech_text": "Online and standing by. Configure your free Gemini or Groq API key in the settings panel to enable my full neural intellect.",
            "tool_calls": []
        }

brain_service = BrainEngine()
