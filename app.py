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
    from config.settings import TELEGRAM_BOT_TOKEN
    if voice_speaker.is_muted:
        voice_status = "\033[1;31mMuted (Silent Mode)\033[0m"
    elif voice_speaker.robotic_mode:
        voice_status = "\033[1;36mActive (Cybernetic Robot Synth)\033[0m"
    else:
        voice_status = "\033[1;32mActive (Silky Neural JARVIS)\033[0m"
    tg_status = "\033[1;32mActive (Remote Control Ready)\033[0m" if TELEGRAM_BOT_TOKEN else "\033[1;33mStandby (Configure in .env)\033[0m"
    print(BANNER)
    print("\033[1;32m[+] Engine:\033[0m Ultra-Fast Neural Core (Direct Voice Stream)")
    print(f"\033[1;32m[+] Voice:\033[0m  {voice_status}")
    print(f"\033[1;32m[+] Remote:\033[0m Telegram Daemon {tg_status}")
    print("\033[1;32m[+] Memory:\033[0m Google Drive Two-Way Synchronizer Active")
    print("\033[1;33m[!] Press ENTER once to activate Hands-Free Conversation!\033[0m")
    print("\033[1;33m[!] Tap ENTER or SPACE to interrupt Ezra at any time!\033[0m")
    print("-" * 65 + "\n")

async def handle_turn(text: str, speaker_tier: str = "verified") -> dict:
    """Processes a user turn: think → speak. Clean conversational flow with biometric security."""
    clean = text.lower().strip()
    is_sleep_command = (
        clean in ("stop listening", "exit conversation", "quit conversation", "goodbye ezra", "bye ezra", "sleep ezra", "shut down", "go to sleep", "sleep", "be quiet")
        or any(w in clean for w in ("اسكت", "نام", "توقف", "مع السلامة", "اخرس"))
    )
    if is_sleep_command:
        import re
        has_arabic = bool(re.search(r"[\u0600-\u06FF]", clean))
        farewell = "حاضر يا سيدي، في وضع الاستعداد دائماً. اضغط ENTER للاستئناف." if has_arabic else "Understood. Pausing hands-free mode, sir. Press ENTER anytime to resume."
        voice_speaker.speak(farewell, prefix="\n\033[1;36m[Ezra]:\033[0m ", live_print=True)
        return {"should_continue": False, "was_interrupted": False}

    print(f"\n\033[1;34m[You]:\033[0m {text}")

    # Animated Futuristic Thinking Loading Bar
    from jarvis.ui.visuals import status_bar
    status_bar.start_thinking("Reasoning with AI...")
    try:
        response = await brain_service.think(text, speaker_tier=speaker_tier)
    finally:
        status_bar.stop_thinking()

    reply_speech = response.get("speech_text", "")
    tools = response.get("tool_calls", [])

    if response.get("rejected"):
        return {"should_continue": True, "rejected": True, "was_interrupted": False}

    if tools:
        for t in tools:
            if "tool" in t:
                print(f"\033[1;33m[Action]:\033[0m {t['tool']}")

    # Speak the reply with live typewriter and barge-in support
    prefix = "\033[1;35m[Ezra (Silent)]:\033[0m " if voice_speaker.is_muted else "\033[1;36m[Ezra]:\033[0m "
    completed = voice_speaker.speak(reply_speech, prefix=prefix, live_print=True)
    return {"should_continue": True, "was_interrupted": not completed, "rejected": False}

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
    
    audio_file = stt_engine.record_until_finished(max_wait_sec=12.0, silence_threshold_sec=1.5)
    pcm = stt_engine.get_last_pcm()
    if not pcm or len(pcm) < 16000:
        print("\033[1;31m[-] Calibration incomplete: No vocal profile captured. Please speak a little louder.\033[0m\n")
        return

    try:
        success = voice_dna.enroll(pcm_data=pcm, user_name="Ahmad")
        if success:
            msg = f"Voice biometrics locked in for {voice_dna.get_user_name()}! F0 pitch calibrated at {voice_dna.f0_mean:.1f}Hz."
            print(f"\n\033[1;32m[+] SUCCESS: Biometric profile calibrated for {voice_dna.get_user_name()}!\033[0m\n")
            voice_speaker.speak(msg)
        else:
            print("\033[1;31m[-] Calibration failed. Please try again.\033[0m\n")
    except Exception as e:
        print(f"\033[1;31m[-] Calibration error: {e}\033[0m\n")

def check_wake_word(text: str) -> tuple:
    """Checks if text begins with or contains a wake word (Ezra / عزرا) anywhere."""
    import re
    if not text:
        return False, ""
    low = text.lower().strip()

    # 1. Flexible English detection: 'Ezra', 'Hey Ezra', 'Hello Ezra', 'Ok Ezra' anywhere
    m_en = re.search(r"\b(ezra|israel|esra|asra|azra|ezrah)\b", low, re.IGNORECASE)
    if m_en:
        # Strip wake word and conversational preamble
        clean_cmd = re.sub(r"^(?:hey|hi|hello|ok|okay|yo)?\s*(?:ezra|israel|esra|asra|azra|ezrah)[\s,.:;]*", "", low, flags=re.IGNORECASE).strip()
        if not clean_cmd:
            clean_cmd = re.sub(r"[\s,.:;]*(?:ezra|israel|esra|asra|azra|ezrah)\s*$", "", low, flags=re.IGNORECASE).strip()
        return True, clean_cmd

    # 2. Flexible Arabic detection: 'عزرا', 'يا عزرا', 'ابو عزرا' anywhere
    m_ar = re.search(r"\b(عزرا|إسراء|اسراء|عزرائيل)\b", low)
    if m_ar:
        clean_cmd = re.sub(r"^(?:يا|ابو|أبو|أهلا|اهلا)?\s*(?:عزرا|إسراء|اسراء|عزرائيل)[\s,.:;]*", "", low).strip()
        if not clean_cmd:
            clean_cmd = re.sub(r"[\s,.:;]*(?:عزرا|إسراء|اسراء|عزرائيل)\s*$", "", low).strip()
        return True, clean_cmd

    return False, ""

def continuous_conversation_loop():
    """
    Continuous conversation loop:
    1. Starts immediately ACTIVE (awake) because user pressed ENTER!
    2. Active 3-minute dwell window before auto-standby.
    3. Flexible wake word reactivation ('Ezra' / 'عزرا').
    4. Instant sleep command ('اسكت' / 'go to sleep').
    """
    import re
    from jarvis.voice.biometrics import voice_dna

    DWELL_TIMEOUT_SEC = 25.0  # 25 seconds natural conversational follow-up window
    loop_state = {
        "is_awake": True,
        "last_interaction_time": time.time(),
        "wake_reason": ""
    }

    def on_laptop_wake(reason: str):
        loop_state["is_awake"] = True
        loop_state["last_interaction_time"] = time.time()
        print(f"\n\033[1;32m[⚡ LAPTOP ACTIVATED]:\033[0m Instant wake triggered ({reason})! Ezra online and listening.")
        try:
            from jarvis.actions.system import SystemManager
            SystemManager.send_desktop_notification("⚡ Project Ezra Activated", "Laptop open: Standing by and listening.", urgency="normal")
        except Exception:
            pass
        # Gate wake greeting playback: do NOT collide with active user speech
        if getattr(stt_engine, "is_user_speaking", False):
            return

        has_arabic = bool(getattr(voice_speaker, "last_language", "en") == "ar")
        greet = "أهلاً بك يا سيدي، الأنظمة جاهزة ومستعدة." if has_arabic else "Welcome back, sir. Systems operational and listening."
        voice_speaker.speak(greet, prefix="\n\033[1;36m[Ezra]:\033[0m ", live_print=True)
        # Drain microphone buffer after greeting so greeting acoustic residue is never recorded
        if hasattr(stt_engine, "worker") and stt_engine.worker:
            stt_engine.worker.drain(keep_recent=0)

    # Initialize zero-overhead hardware Lid & Wake monitor
    from jarvis.actions.lid_monitor import LidWakeMonitor
    lid_mon = LidWakeMonitor(on_wake_callback=on_laptop_wake)
    lid_mon.start()

    from config.settings import ANSWER_ONLY_ON_WAKE, PUSH_TO_TALK, END_SIL, SHORT_SIL, MAX_UTT, HOST, PORT

    # Launch background Holographic UI server & interface window
    try:
        from jarvis.ui.server import start_ui_server_thread, open_ui_in_browser
        start_ui_server_thread(host=HOST, port=PORT)
        open_ui_in_browser(host=HOST, port=PORT)
        print(f"\033[1;32m[+] Holographic UI:\033[0m Online at http://{HOST}:{PORT}")
    except Exception as ui_err:
        print(f"\033[1;33m[!] UI Server Notice:\033[0m {ui_err}")

    print("\n\033[1;32m╔═══════════════════════════════════════════════════════════════╗\033[0m")
    print("\033[1;32m║          ⚡ HANDS-FREE INTELLIGENT CONVERSATION ENGINE        ║\033[0m")
    print("\033[1;32m╚═══════════════════════════════════════════════════════════════╝\033[0m")
    print("\033[1;36m[•] Active Mode:\033[0m Listening now! Speak freely (laptop mic active).")
    print(f"\033[1;36m[•] Musa Timing:\033[0m {END_SIL}s quiet wait (>1.2s speech), {SHORT_SIL}s on short replies, {MAX_UTT:.0f}s max.")
    if PUSH_TO_TALK:
        print("\033[1;33m[•] Push-To-Talk:\033[0m ENABLED (Hold key to talk, release to finish).")
    if ANSWER_ONLY_ON_WAKE:
        print("\033[1;33m[•] Wake Only Mode:\033[0m ENABLED (Responds only to 'Ezra' / 'عزرا').")
    print("\033[1;36m[•] Instant Wake:\033[0m Activates the second the laptop lid opens or wakes from sleep.")
    print("\033[1;36m[•] Dwell Window:\033[0m 25s conversational follow-up (enters quiet standby so colleague chats aren't overheard).")
    print("\033[1;36m[•] Sleep Command:\033[0m Say \033[1;31m'go to sleep'\033[0m or \033[1;31m'اسكت'\033[0m to return to standby.")
    print("\033[1;36m[•] Interrupt:\033[0m Speak to interrupt, or tap ENTER/SPACE anytime.\n")

    # Immediate voice prompt so user knows Ezra is live
    voice_speaker.speak("I'm listening, sir. Speak freely.", prefix="\033[1;36m[Ezra]:\033[0m ", live_print=True)

    from jarvis.ui.visuals import status_bar

    try:
        while True:
            try:
                # Check dwell timeout if currently awake
                if loop_state["is_awake"] and (time.time() - loop_state["last_interaction_time"] > DWELL_TIMEOUT_SEC):
                    loop_state["is_awake"] = False
                    print(f"\n\033[1;33m[Standby Mode]:\033[0m Standing by (Say 'Ezra' anytime to wake me).\n")

                # Instant Mic Handover: render live mic indicator immediately!
                status_bar.render_listening(level=0, is_heard=False)

                # Record turn from microphone using Musa's exact turn-taking & silence endpointing architecture
                audio_file = stt_engine.record_until_finished(
                    max_wait_sec=15.0,
                    is_busy=False,
                    push_to_talk=PUSH_TO_TALK
                )
                if not audio_file:
                    continue

                status_bar.start_thinking("Processing voice...")
                transcription = stt_engine.transcribe_audio_file(audio_file)
                status_bar.stop_thinking()

                pcm_data = stt_engine.get_last_pcm()

                # Speaker biometrics evaluation (3-tier security)
                tier, score, detail = voice_dna.verify_turn(pcm_data, transcription)

                if not transcription or not transcription.strip():
                    # Ambient tick or empty sound
                    continue

                # Ambient TV, broadcast, and non-directed room chatter filter
                if stt_engine.is_ambient_chatter(transcription):
                    # Do not refresh dwell interaction time on ambient chatter!
                    print(f"\033[1;30m[Acoustic Filter]: Suppressed ambient chatter / TV dialogue: \"{transcription}\"\033[0m")
                    continue

                has_wake, wake_cmd = check_wake_word(transcription)

                # Musa Setting: Answer only when I say "Ezra"
                if ANSWER_ONLY_ON_WAKE and not has_wake:
                    print(f"\033[1;30m[Wake Filter]: Ignored speech without wake word (ANSWER_ONLY_ON_WAKE=True): \"{transcription}\"\033[0m")
                    continue

                # In dwell mode: ignore guest or far-field voices if not addressed to Ezra
                if loop_state["is_awake"] and tier in ("guest", "unsure") and not has_wake:
                    print(f"\033[1;30m[Biometric Near-Field Gate]: Suppressed unaddressed background voice: \"{transcription}\" ({detail})\033[0m")
                    continue

                # Always display captured transcription so user has visual feedback
                print(f"\n\033[1;34m[Heard]:\033[0m \"{transcription}\" \033[1;30m(Tier: {tier})\033[0m")

                # Check if sleep command
                clean_low = transcription.lower().strip()
                is_sleep = (
                    clean_low in ("stop listening", "exit conversation", "sleep", "go to sleep", "sleep now", "be quiet", "shut down")
                    or any(w in clean_low for w in ("اسكت", "نام", "توقف", "مع السلامة", "اخرس"))
                )
                if is_sleep:
                    loop_state["is_awake"] = False
                    farewell = "حاضر يا سيدي، في وضع الاستعداد." if re.search(r"[\u0600-\u06FF]", clean_low) else "Entering standby, sir. Say 'Ezra' anytime to wake me."
                    voice_speaker.speak(farewell, prefix="\n\033[1;36m[Ezra]:\033[0m ", live_print=True)
                    continue

                if not loop_state["is_awake"]:
                    # In standby: check for wake word
                    if not has_wake:
                        print(f"\033[1;33m[Standby Mode]:\033[0m Say 'Ezra' or tap ENTER to activate.")
                        continue

                    # Reject distant background or guest voices trying to wake Ezra from across the room
                    if tier == "guest":
                        print(f"\033[1;30m[Biometric Near-Field Gate]: Ignored wake word from background/guest source: \"{transcription}\" ({detail})\033[0m")
                        continue

                    loop_state["is_awake"] = True
                    loop_state["last_interaction_time"] = time.time()
                    print(f"\033[1;32m[⚡ WAKE TRIGGERED]\033[0m Biometrics: {tier.upper()} ({score:.2f})")

                    if wake_cmd:
                        turn_res = asyncio.run(handle_turn(wake_cmd, speaker_tier=tier))
                        loop_state["last_interaction_time"] = time.time()
                        if isinstance(turn_res, dict) and not turn_res.get("should_continue", True):
                            loop_state["is_awake"] = False
                        else:
                            print("\033[1;36m[🎙️ Go ahead — I'm listening]\033[0m\n")
                    else:
                        has_ar = bool(re.search(r"[\u0600-\u06FF]", transcription))
                        greet = "أهلاً بك يا سيدي، في خدمتك دائماً." if has_ar else "Good day, sir. At your command."
                        voice_speaker.speak(greet, prefix="\n\033[1;36m[Ezra]:\033[0m ", live_print=True)
                        print("\033[1;36m[🎙️ Go ahead — I'm listening]\033[0m\n")
                else:
                    # Currently awake (Active dwell mode)
                    actual_query = wake_cmd if (has_wake and wake_cmd) else transcription

                    if has_wake and not wake_cmd:
                        loop_state["last_interaction_time"] = time.time()
                        voice_speaker.speak("Right beside you, sir.", prefix="\n\033[1;36m[Ezra]:\033[0m ", live_print=True)
                        print("\033[1;36m[🎙️ Go ahead — I'm listening]\033[0m\n")
                        continue

                    turn_res = asyncio.run(handle_turn(actual_query, speaker_tier=tier))
                    if isinstance(turn_res, dict) and turn_res.get("rejected"):
                        # Dwell window does NOT refresh on rejected turn!
                        continue

                    loop_state["last_interaction_time"] = time.time()
                    should_continue = turn_res.get("should_continue", True) if isinstance(turn_res, dict) else turn_res
                    if not should_continue:
                        loop_state["is_awake"] = False
                    else:
                        print("\033[1;36m[🎙️ Go ahead — I'm listening]\033[0m\n")

            except Exception as loop_err:
                status_bar.clear()
                print(f"\033[1;31m[Turn recovery]: {loop_err}\033[0m")

    except KeyboardInterrupt:
        print("\n\033[1;33m[Conversation paused. Press ENTER to resume.]\033[0m\n")
    except Exception as e:
        print(f"\n[Error in loop]: {e}\n")
    finally:
        lid_mon.stop()

def main():
    # 1. Take memory from Google Drive on startup
    from jarvis.gdrive_sync import gdrive_sync
    gdrive_sync.pull_from_drive()

    # 2. Launch Telegram Remote Daemon in background
    from jarvis.comms.telegram_daemon import start_telegram_daemon_background
    start_telegram_daemon_background()

    # 3. Check for --daemon, --auto, or --hands-free CLI flags
    is_daemon_mode = any(arg in sys.argv for arg in ("--daemon", "--auto", "--hands-free", "-d"))

    print_banner()
    initial_greet = "Systems operational, sir. How can I assist you today?"
    prefix = "\033[1;35m[Ezra (Silent)]:\033[0m " if voice_speaker.is_muted else "\033[1;36m[Ezra]:\033[0m "
    voice_speaker.speak(initial_greet, prefix=prefix, live_print=True)

    if is_daemon_mode:
        print("\033[1;32m[+] Daemon Mode Active: Instant laptop wake & hands-free conversation started automatically!\033[0m\n")
        while True:
            try:
                continuous_conversation_loop()
            except KeyboardInterrupt:
                break
            except Exception as e:
                time.sleep(1.0)
        return

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
                print("\033[1;32m[Ezra Voice: Active]\033[0m\n")
                voice_speaker.speak("Voice restored, sir.")
                continue

            if user_choice.lower() in ("/robot", "/robotic", "robot"):
                voice_speaker.set_robotic_mode(True)
                print("\033[1;36m[Ezra Voice: Cybernetic Robot Synth Active]\033[0m\n")
                voice_speaker.speak("Robotic synthesis module activated, sir.")
                continue

            if user_choice.lower() in ("/neural", "/smooth", "/human", "neural"):
                voice_speaker.set_robotic_mode(False)
                print("\033[1;32m[Ezra Voice: Silky Neural JARVIS Active]\033[0m\n")
                voice_speaker.speak("Neural voice restored, sir.")
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

            if user_choice.lower() in ("/brief", "brief", "briefing"):
                from jarvis.actions.apis import api_manager
                b = api_manager.get_daily_briefing()
                print(f"\n\033[1;36m[Ezra Executive Briefing]:\033[0m\n{b.get('summary')}\n")
                voice_speaker.speak(b.get("summary", ""), prefix="\033[1;36m[Ezra]:\033[0m ")
                continue

            if user_choice.lower() in ("/status", "status"):
                from jarvis.actions.system import SystemManager
                s = SystemManager.get_system_status()
                g = SystemManager.git_status()
                print(f"\n\033[1;32m[System Status]:\033[0m CPU: {s['cpu_percent']} | RAM: {s['ram_used_gb']} | Battery: {s['battery']}")
                print(f"\033[1;32m[Git Status]:\033[0m Branch: {g.get('branch')} | Clean: {g.get('is_clean')} ({g.get('modified_files_count')} changes)\n")
                continue

            if user_choice.lower().startswith("/git"):
                from jarvis.actions.system import SystemManager
                sub = user_choice.split()
                if len(sub) > 1 and sub[1] in ("publish", "push", "commit"):
                    msg = " ".join(sub[2:]) if len(sub) > 2 else ""
                    res = SystemManager.git_publish(commit_message=msg)
                    print(f"\n\033[1;32m[Git Publish]:\033[0m {res.get('message')}\n")
                elif len(sub) > 1 and sub[1] in ("log", "recent"):
                    res = SystemManager.git_log_recent(limit=5)
                    print(f"\n\033[1;32m[Git Recent Commits]:\033[0m\n" + "\n".join(res.get("commits", [])) + "\n")
                else:
                    res = SystemManager.git_status()
                    print(f"\n\033[1;32m[Git Status]:\033[0m\n{res.get('details')}\n")
                continue

            if user_choice.lower() == "/telegram":
                from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
                token_disp = f"Set (starts with {TELEGRAM_BOT_TOKEN[:6]}...)" if TELEGRAM_BOT_TOKEN else "NOT SET in .env"
                chat_disp = TELEGRAM_CHAT_ID or "NOT SET (send /start from bot to register)"
                print(f"\n\033[1;36m[Telegram Remote Link]:\033[0m")
                print(f"• Bot Token: {token_disp}")
                print(f"• Chat ID:   {chat_disp}")
                print(f"• Commands:  /status, /snap, /brief, /say <text>, /run <cmd>\n")
                continue

            if user_choice.lower() in ("/sync", "sync", "/push"):
                from jarvis.gdrive_sync import gdrive_sync
                res = gdrive_sync.push_to_drive()
                print(f"\n\033[1;32m[Google Drive Sync]:\033[0m Synced memory and biometrics to {res.get('target_dir')}\n")
                continue

            if user_choice.lower() in ("/pull", "pull"):
                from jarvis.gdrive_sync import gdrive_sync
                pulled = gdrive_sync.pull_from_drive()
                status_str = "Restored latest memory and voice DNA from Google Drive!" if pulled else "Local memory is already up to date with Google Drive."
                print(f"\n\033[1;32m[Google Drive Sync]:\033[0m {status_str}\n")
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
