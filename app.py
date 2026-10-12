import sys
import os
import time
import asyncio
from jarvis.brain.engine import brain_service
from jarvis.voice.speaker import voice_speaker
from jarvis.voice.stt import stt_engine
from jarvis.memory import memory_service

BANNER = """
\033[1;36m
  ╔═══════════════════════════════════════════════════════════════╗
  ║                 PROJECT ESRAA // DESKTOP CORE                ║
  ║         Witty Autonomous Assistant • Sarcastic & Crisp        ║
  ╚═══════════════════════════════════════════════════════════════╝
\033[0m
"""

def print_banner():
    print(BANNER)
    print("\033[1;32m[+] Engine Status:\033[0m Gemini 3.5 Flash Online")
    print("\033[1;32m[+] Voice:\033[0m Crisp British Female (Played Directly via Hardware Speakers)")
    print("\033[1;32m[+] Input Modes:\033[0m Voice (Hardware Mic) or Direct Text Prompt")
    print("\033[1;33m[!] Press ENTER to speak via Mic, or type your directive directly!\033[0m")
    print("-" * 65 + "\n")

async def process_user_input(text: str):
    if not text or not text.strip():
        return
    
    print(f"\n\033[1;34m[You]:\033[0m {text}")
    print("\033[1;35m[Esraa Thinking...]\033[0m")
    
    response = await brain_service.think(text)
    reply_speech = response.get("speech_text", "")
    tools = response.get("tool_calls", [])
    
    if tools:
        for t in tools:
            if "tool" in t:
                print(f"\033[1;33m[System Executed Tool]:\033[0m {t['tool']}")

    print(f"\033[1;36m[Esraa]:\033[0m {reply_speech}")
    
    # Speak reply out loud through hardware speakers
    voice_speaker.speak(reply_speech)

def main():
    print_banner()

    # Initial witty greeting
    initial_greet = "All systems online, sir. Do try not to blow up the workshop today. What can I do for you?"
    print(f"\033[1;36m[Esraa]:\033[0m {initial_greet}\n")
    voice_speaker.speak(initial_greet)

    while True:
        try:
            user_choice = input("\033[1;37m[Press ENTER for Mic, or type command, 'exit' to quit] > \033[0m").strip()
            
            if user_choice.lower() in ("exit", "quit", "q"):
                farewell = "Powering down. Try to stay out of trouble without me, sir."
                print(f"\n\033[1;36m[Esraa]:\033[0m {farewell}\n")
                voice_speaker.speak(farewell)
                break

            # If user pressed ENTER with empty text, trigger microphone recording
            if not user_choice:
                print("\n\033[1;31m[🎙️ LISTENING...] Speak into your microphone now (4 seconds)...\033[0m")
                audio_file = stt_engine.record_mic_audio(duration_sec=4)
                print("\033[1;33m[Transcribing voice...]\033[0m")
                transcription = stt_engine.transcribe_audio_file(audio_file)
                if not transcription:
                    print("\033[1;31m[!] Didn't catch that. Could you repeat, sir?\033[0m")
                    continue
                asyncio.run(process_user_input(transcription))
            else:
                asyncio.run(process_user_input(user_choice))

        except KeyboardInterrupt:
            print("\nShutting down Project Esraa.")
            break
        except Exception as e:
            print(f"\n[Error]: {e}")

if __name__ == "__main__":
    main()
