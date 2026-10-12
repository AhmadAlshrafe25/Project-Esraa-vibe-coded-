import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import STATIC_DIR, CACHE_DIR
from jarvis.brain.engine import brain_service
from jarvis.voice.tts import voice_service
from jarvis.actions.system import SystemManager

app = FastAPI(title="Project Esraa AI Assistant")

# Serve cache folder for dynamic speech files
app.mount("/cache", StaticFiles(directory=str(CACHE_DIR)), name="cache")

class CommandRequest(BaseModel):
    command: str

class SettingsRequest(BaseModel):
    gemini_key: str = ""
    groq_key: str = ""
    voice: str = ""

@app.get("/", response_class=HTMLResponse)
async def serve_hud():
    index_file = STATIC_DIR / "index.html"
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

@app.get("/api/telemetry")
async def get_telemetry():
    return SystemManager.get_system_status()

@app.post("/api/command")
async def process_command(req: CommandRequest):
    # 1. LLM / Brain thinking & tool execution
    brain_output = await brain_service.think(req.command)
    speech_text = brain_output.get("speech_text", "")
    
    # 2. Neural Voice (Edge-TTS Female British / Aria voice)
    audio_url = None
    if speech_text:
        try:
            audio_path = await voice_service.generate_speech_file(speech_text)
            audio_filename = Path(audio_path).name
            audio_url = f"/cache/{audio_filename}"
        except Exception as e:
            print(f"[TTS Error] {e}")

    return {
        "reply": speech_text,
        "tools": brain_output.get("tool_calls", []),
        "audio_url": audio_url
    }

@app.post("/api/settings")
async def update_settings(req: SettingsRequest):
    env_file = Path(__file__).resolve().parent.parent / ".env"
    
    # Update running services
    if req.gemini_key:
        brain_service.gemini_key = req.gemini_key
    if req.groq_key:
        brain_service.groq_key = req.groq_key
    if req.voice:
        voice_service.set_voice(req.voice)

    # Persist in .env
    lines = []
    if env_file.exists():
        lines = env_file.read_text().splitlines()

    def set_kv(key, val):
        nonlocal lines
        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={val}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={val}")
        lines = new_lines

    if req.gemini_key:
        set_kv("GEMINI_API_KEY", req.gemini_key)
    if req.groq_key:
        set_kv("GROQ_API_KEY", req.groq_key)
    if req.voice:
        set_kv("DEFAULT_VOICE", req.voice)

    env_file.write_text("\n".join(lines) + "\n")
    return {"status": "success", "message": "Settings persisted"}
