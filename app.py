import sys
import os
import time
import asyncio
from jarvis.brain.engine import brain_service
from jarvis.voice.speaker import voice_speaker
from jarvis.voice.stt import stt_engine
from jarvis.memory import memory_service
from jarvis.ui.visuals import visualizer

BANNER = """\033[1;36m
  ╔═══════════════════════════════════════════════════════════════╗
  ║                  PROJECT EZRA // DESKTOP CORE                 ║
  ║      Continuous Conversation Mode • Ultra Low Latency         ║
  ╚═══════════════════════════════════════════════════════════════╝\033[0m"""

def print_banner():
    voice_status = "\033[1;31mMuted (Silent Mode)\033[0m" if voice_speaker.is_muted else "\033[1;32mActive (Silky Neural)\033[0m"
    print(BANNER)
    print("\033[1;32m[+] Engine:\033[0m Gemini 3.5 Flash (Vision & Real-Time APIs)")
    print(f"\033[1;32m[+] Voice:\033[0m {voice_status}")
    print("\033[1;32m[+] Memory:\033[0m Google Drive Two-Way Synchronizer Active")
    print("\033[1;33m[!] Press ENTER once to activate Hands-Free Conversation!\033[0m")
    print("\033[1;33m[!] Commands: Type directly, or use /mute, /unmute, or speak 'be quiet' / 'talk to me'.\033[0m")
    print("-" * 65 + "\n")

async def handle_turn(text: str) -> bool:
    """Processes a user turn with animated brain sphere and typewriter speech output."""
    clean = text.lower().strip()
    if clean in ("stop", "pause", "exit", "quit", "goodbye", "bye", "cancel"):
        farewell = "Understood. Pausing conversation loop, sir."
        visualizer.moving_print(farewell, prefix="\n\033[1;36m[Ezra]:\033[0m ")
        voice_speaker.speak(farewell)
        return False

    print(f"\n\033[1;34m[You]:\033[0m {text}\n")
    
    # Start animated brain with glowing yellow sphere
    visualizer.start_agent_brain("Ezra Neural Core")
    response = await brain_service.think(text)
    visualizer.stop_agent_brain()

    reply_speech = response.get("speech_text", "")
    tools = response.get("tool_calls", [])

    if tools:
        for t in tools:
            if "tool" in t:
                print(f"\033[1;33m[Action Executed]:\033[0m {t['tool']}")

    # Moving typewriter print
    prefix = "\033[1;35m[Ezra (Silent)]:\033[0m " if voice_speaker.is_muted else "\033[1;36m[Ezra]:\033[0m "
    visualizer.moving_print(reply_speech, prefix=prefix, delay=0.015)
    voice_speaker.speak(reply_speech)
    return True

def continuous_conversation_loop():
    """Continuous conversation loop: dynamically listens until you finish speaking, replies, and immediately resumes listening!"""
    print("\n\033[1;32m[⚡ CONTINUOUS CONVERSATION ACTIVE]\033[0m Speak freely! (Say 'stop', 'bye', or press Ctrl+C to pause)\n")
    
    silence_count = 0
    while True:
        try:
            audio_file = stt_engine.record_until_finished(max_wait_sec=12.0, silence_threshold_sec=1.2)
            
            if not audio_file:
                silence_count += 1
                if silence_count >= 8:
                    print("\r\033[1;33m[Paused due to inactivity. Press ENTER to talk again.]\033[0m\n")
                    break
                continue

            silence_count = 0
            print("\r\033[1;33m[⚡ Processing audio...]\033[0m          ", end="", flush=True)
            transcription = stt_engine.transcribe_audio_file(audio_file)
            print("\r" + " " * 35 + "\r", end="", flush=True)
            
            if not transcription or not transcription.strip():
                continue

            should_continue = asyncio.run(handle_turn(transcription))
            if not should_continue:
                break

            time.sleep(0.2)

        except KeyboardInterrupt:
            print("\n\033[1;33m[Conversation paused. Press ENTER to resume.]\033[0m\n")
            break
        except Exception as e:
            print(f"\n[Error in loop]: {e}\n")
            break

def main():
    # 1. Take memory from Google Drive on startup
    from jarvis.gdrive_sync import gdrive_sync
    gdrive_sync.pull_from_drive()

    print_banner()
    initial_greet = "Systems operational, sir. How can I assist you today?"
    prefix = "\033[1;35m[Ezra (Silent)]:\033[0m " if voice_speaker.is_muted else "\033[1;36m[Ezra]:\033[0m "
    visualizer.moving_print(initial_greet, prefix=prefix)
    voice_speaker.speak(initial_greet)

    while True:
        try:
            prompt_str = f"\033[1;37m[{'MUTED' if voice_speaker.is_muted else 'VOICE'} | ENTER for Conversation, type command, 'exit'] > \033[0m"
            user_choice = input(prompt_str).strip()
            
            if user_choice.lower() in ("exit", "quit", "q"):
                print("Powering down. Goodbye, sir.")
                gdrive_sync.push_to_drive()
                break

            if user_choice.lower() in ("/mute", "mute"):
                voice_speaker.set_muted(True)
                print("\033[1;33m[Ezra Voice: Muted (Silent Mode Active)]\033[0m\n")
                continue

            if user_choice.lower() in ("/unmute", "unmute"):
                voice_speaker.set_muted(False)
                print("\033[1;32m[Ezra Voice: Active (Silky Neural Voice Enabled)]\033[0m\n")
                voice_speaker.speak("Voice restored, sir.")
                continue

            if user_choice.lower() == "/voice":
                is_muted = voice_speaker.toggle_mute()
                status = "Muted (Silent Mode)" if is_muted else "Active"
                print(f"\033[1;33m[Ezra Voice: {status}]\033[0m\n")
                continue

            if not user_choice:
                # Trigger continuous multi-turn hands-free conversation
                continuous_conversation_loop()
            else:
                asyncio.run(handle_turn(user_choice))

        except KeyboardInterrupt:
            print("\nShutting down Project Ezra.")
            gdrive_sync.push_to_drive()
            break
        except Exception as e:
            print(f"[Error]: {e}")

if __name__ == "__main__":
    main()
