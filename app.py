import sys
import os
import time
import asyncio
from jarvis.brain.engine import brain_service
from jarvis.voice.speaker import voice_speaker
from jarvis.voice.stt import stt_engine
from jarvis.memory import memory_service

BANNER = """\033[1;36m
  ╔═══════════════════════════════════════════════════════════════╗
  ║                  PROJECT EZRA // DESKTOP CORE                 ║
  ║      Continuous Conversation Mode • Ultra Low Latency         ║
  ╚═══════════════════════════════════════════════════════════════╝\033[0m"""

def print_banner():
    print(BANNER)
    print("\033[1;32m[+] Engine:\033[0m Gemini 3.5 Flash (Optimized for speed & minimal resource usage)")
    print("\033[1;32m[+] Voice:\033[0m Fast Crisp British Female (Zero-lag)")
    print("\033[1;33m[!] Press ENTER once to activate Continuous Conversation Mode!\033[0m")
    print("\033[1;33m[!] Speak naturally back and forth. Say 'stop', 'bye', or press Ctrl+C to pause.\033[0m")
    print("-" * 65 + "\n")

async def handle_turn(text: str) -> bool:
    """Processes a user turn. Returns False if user requested to exit/pause."""
    clean = text.lower().strip()
    if clean in ("stop", "pause", "exit", "quit", "goodbye", "bye", "cancel"):
        farewell = "Understood. Pausing conversation loop, sir."
        print(f"\n\033[1;36m[Ezra]:\033[0m {farewell}\n")
        voice_speaker.speak(farewell)
        return False

    print(f"\n\033[1;34m[You]:\033[0m {text}")
    response = await brain_service.think(text)
    reply_speech = response.get("speech_text", "")
    tools = response.get("tool_calls", [])

    if tools:
        for t in tools:
            if "tool" in t:
                print(f"\033[1;33m[Action Executed]:\033[0m {t['tool']}")

    print(f"\033[1;36m[Ezra]:\033[0m {reply_speech}")
    voice_speaker.speak(reply_speech)
    return True

def continuous_conversation_loop():
    """Continuous conversation loop: listens, replies, and immediately listens for your next response!"""
    print("\n\033[1;32m[⚡ CONTINUOUS CONVERSATION ACTIVE]\033[0m Speak freely! (Say 'stop' or press Ctrl+C to pause)\n")
    
    silence_count = 0
    while True:
        try:
            print("\033[1;35m[🎙️ Listening...]\033[0m")
            audio_file = stt_engine.record_mic_audio(duration_sec=3)
            transcription = stt_engine.transcribe_audio_file(audio_file)
            
            if not transcription or not transcription.strip():
                silence_count += 1
                if silence_count >= 4:
                    print("\033[1;33m[Paused due to silence. Press ENTER to speak again.]\033[0m")
                    break
                continue

            silence_count = 0
            should_continue = asyncio.run(handle_turn(transcription))
            if not should_continue:
                break

            # Short pause before next listen
            time.sleep(0.3)

        except KeyboardInterrupt:
            print("\n\033[1;33m[Conversation paused. Press ENTER to resume.]\033[0m\n")
            break
        except Exception as e:
            print(f"[Error in loop]: {e}")
            break

def main():
    print_banner()
    initial_greet = "Systems operational, sir. How can I assist you today?"
    print(f"\033[1;36m[Ezra]:\033[0m {initial_greet}\n")
    voice_speaker.speak(initial_greet)

    while True:
        try:
            user_choice = input("\033[1;37m[Press ENTER to start Conversation, or type directly, 'exit' to quit] > \033[0m").strip()
            
            if user_choice.lower() in ("exit", "quit", "q"):
                print("Powering down. Goodbye, sir.")
                break

            if not user_choice:
                # Trigger continuous multi-turn hands-free conversation
                continuous_conversation_loop()
            else:
                asyncio.run(handle_turn(user_choice))

        except KeyboardInterrupt:
            print("\nShutting down Project Ezra.")
            break
        except Exception as e:
            print(f"[Error]: {e}")

if __name__ == "__main__":
    main()
