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
    from jarvis.voice.biometrics import voice_dna
    voice_status = "\033[1;31mMuted (Silent Mode)\033[0m" if voice_speaker.is_muted else "\033[1;32mActive (Silky Neural)\033[0m"
    gate_status = f"\033[1;32m🧬 Genetic Code Locked ({voice_dna.get_user_name()})\033[0m" if voice_dna.is_enrolled() else "\033[1;33m⚠️ Uncalibrated (Type /enroll)\033[0m"
    print(BANNER)
    print("\033[1;32m[+] Engine:\033[0m Gemini 3.5 Flash (Vision & Real-Time APIs)")
    print(f"\033[1;32m[+] Voice:\033[0m {voice_status}")
    print(f"\033[1;32m[+] Voice Gate:\033[0m {gate_status}")
    print("\033[1;32m[+] Memory:\033[0m Google Drive Two-Way Synchronizer Active")
    print("\033[1;33m[!] Press ENTER once to activate Hands-Free Conversation!\033[0m")
    print("\033[1;33m[!] Barge-In Enabled: Speak or tap ENTER/SPACE to cut Ezra off at any time!\033[0m")
    print("\033[1;33m[!] Commands: /enroll (calibrate voice), /voicegate, /threshold <num>, /mute, /unmute.\033[0m")
    print("-" * 65 + "\n")

async def handle_turn(text: str) -> dict:
    """Processes a user turn with animated brain sphere and synchronized typewriter speech with full barge-in cut-out."""
    clean = text.lower().strip()
    if clean in ("stop", "pause", "exit", "quit", "goodbye", "bye", "cancel"):
        farewell = "Understood. Pausing conversation loop, sir."
        voice_speaker.speak(farewell, prefix="\n\033[1;36m[Ezra]:\033[0m ", live_print=True)
        return {"should_continue": False, "was_interrupted": False}

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

    # Synchronized speech & live typewriter with instant interruption (barge-in)
    prefix = "\033[1;35m[Ezra (Silent)]:\033[0m " if voice_speaker.is_muted else "\033[1;36m[Ezra]:\033[0m "
    completed = voice_speaker.speak(reply_speech, prefix=prefix, live_print=True)
    return {"should_continue": True, "was_interrupted": not completed}

def run_voice_enrollment():
    """Interactive Voice Genetic Code Calibration."""
    from jarvis.voice.biometrics import voice_dna
    print("\n\033[1;36m╔═══════════════════════════════════════════════════════════════╗")
    print("║            🧬 EZRA VOCAL GENETIC CALIBRATION MODULE          ║")
    print("╚═══════════════════════════════════════════════════════════════╝\033[0m")
    print("\033[1;33m[!] When prompted, speak naturally for 3-5 seconds.\033[0m")
    print("\033[1;33m[!] Example: 'Ezra, calibrate my vocal biometrics as my genetic code.'\033[0m\n")
    
    voice_speaker.speak("Please speak clearly for a few seconds so I can sequence and lock into your unique voice genetic code, sir.")
    print("\033[1;32m[🎙️ Ready — Speak now!]\033[0m")
    
    audio_file = stt_engine.record_until_finished(max_wait_sec=10.0, silence_threshold_sec=1.2)
    if not audio_file or not stt_engine.last_spk_vector:
        print("\033[1;31m[-] Calibration incomplete: No vocal profile captured. Please speak a little louder.\033[0m\n")
        return

    try:
        import wave
        with wave.open(audio_file, "rb") as wf:
            pcm = wf.readframes(wf.getnframes())
        
        voice_dna.enroll(stt_engine.last_spk_vector, pcm_data=pcm, user_name="Beat")
        msg = f"Voice genetic code successfully locked in! Vocal profile calibrated. I will now strictly ignore all other voices around you."
        print(f"\n\033[1;32m[+] SUCCESS: Genetic profile locked for {voice_dna.get_user_name()} (F0: {voice_dna.f0_mean:.1f}Hz, Threshold: {voice_dna.get_threshold():.0%})\033[0m\n")
        voice_speaker.speak(msg)
    except Exception as e:
        print(f"\033[1;31m[-] Calibration error: {e}\033[0m\n")

def continuous_conversation_loop():
    """Continuous conversation loop: dynamically listens until you finish speaking, replies, and immediately resumes listening!"""
    print("\n\033[1;32m[⚡ CONTINUOUS CONVERSATION ACTIVE]\033[0m Speak freely! Tap ENTER/SPACE or speak to cut Ezra off anytime.\n")
    
    silence_count = 0
    while True:
        try:
            audio_file = stt_engine.record_until_finished(max_wait_sec=14.0, silence_threshold_sec=0.6)
            
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

            turn_res = asyncio.run(handle_turn(transcription))
            should_continue = turn_res.get("should_continue", True) if isinstance(turn_res, dict) else turn_res
            if not should_continue:
                break

            # If user cut Ezra off to speak, immediately record next speech without delay
            if isinstance(turn_res, dict) and turn_res.get("was_interrupted"):
                time.sleep(0.05)
            else:
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
    voice_speaker.speak(initial_greet, prefix=prefix, live_print=True)

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

            if user_choice.lower() in ("/enroll", "/calibrate", "/voiceprint"):
                run_voice_enrollment()
                continue

            if user_choice.lower().startswith("/threshold"):
                parts = user_choice.split()
                if len(parts) > 1:
                    try:
                        from jarvis.voice.biometrics import voice_dna
                        new_t = float(parts[1])
                        voice_dna.set_threshold(new_t)
                        print(f"\033[1;32m[Voice Genetic Gate threshold set to {voice_dna.get_threshold():.0%}]\033[0m\n")
                    except ValueError:
                        print("Usage: /threshold 0.58\n")
                else:
                    from jarvis.voice.biometrics import voice_dna
                    print(f"[Current Voice Genetic Gate threshold: {voice_dna.get_threshold():.0%}]\n")
                continue

            if user_choice.lower() in ("/voicegate", "/strict"):
                from jarvis.voice.biometrics import voice_dna
                state = voice_dna.toggle_strict_mode()
                status_str = "\033[1;32mStrict (Exclusively listens to your voice)\033[0m" if state else "\033[1;33mOpen (Listens to all speakers)\033[0m"
                print(f"[Voice Genetic Gate: {status_str}]\n")
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
