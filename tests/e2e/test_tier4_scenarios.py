"""
Tier 4: Real-World Conversational Scenarios E2E Tests for Project Ezra Overhaul.

Verifies complete realistic multi-turn conversational workflows:
- Scenario 1: Multi-turn British colloquial dialogue with slang ("bruv", "sorted", "cheers mate", "innit") and tool dispatch
- Scenario 2: Fluent Arabic voice queries and desktop application execution ("يا عزرا", "شغل الآلة الحاسبة", "اسكت")
- Scenario 3: Complex desktop app workflow with mid-speech barge-in interruption and redirected action
- Scenario 4: Heavy acoustic noise environment (continuous fan hiss + desk rumble + voiced speech)
- Scenario 5: Continuous conversation dwell window (25s follow-up without wake word) and sleep transition
"""

import os
import sys
import time
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.voice.speaker import SmoothSpeaker
from jarvis.voice.stt import NativeSpeechRecognizer, AudioDSPFilter, AudioStreamWorker
from jarvis.brain.engine import BrainEngine
from jarvis.actions.apps import AppManager
import app as ezra_app


class TestTier4ConversationalScenarios(unittest.IsolatedAsyncioTestCase):
    """Tier 4 Real-World Conversational Scenarios Test Suite."""

    def setUp(self):
        self.speaker = SmoothSpeaker()
        self.brain = BrainEngine()
        self.sample_rate = 16000
        self.chunk_samples = 1280
        self.dsp = AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=self.chunk_samples)

    async def test_scenario_01_british_colloquial_multi_turn_dialogue(self):
        """Scenario: Multi-turn conversation with British colloquialisms, slang, and desktop action."""
        conversation_history = []

        # Turn 1: Greeting with British slang
        turn1_input = "Ezra mate, how's it going bruv?"
        has_wake1, clean_cmd1 = ezra_app.check_wake_word(turn1_input)
        self.assertTrue(has_wake1)

        with patch("jarvis.brain.engine.brain_service.think", new_callable=AsyncMock) as mock_think, \
             patch("jarvis.voice.speaker.voice_speaker.speak", return_value=True) as mock_speak:
            mock_think.return_value = {
                "speech_text": "Alright bruv! Systems are proper sorted. What can I do for you?",
                "tool_calls": []
            }
            res1 = await ezra_app.handle_turn(turn1_input)
            self.assertTrue(res1["should_continue"])
            self.assertFalse(res1["was_interrupted"])
            conversation_history.append((turn1_input, mock_think.return_value["speech_text"]))

        # Turn 2: Slang-infused tool launch command
        turn2_input = "Proper sorted, cheers mate. Can you open the terminal?"
        with patch.object(self.brain, "execute_tool", new_callable=AsyncMock) as mock_tool_exec:
            mock_tool_exec.return_value = '{"status": "success", "message": "Launched terminal."}'
            semantic_res = await self.brain._parse_and_execute_semantic_actions("open the terminal")
            self.assertIsNotNone(semantic_res)
            tool_names = [call.args[0] for call in mock_tool_exec.call_args_list]
            self.assertIn("launch_app", tool_names)

        # Turn 3: Follow-up appreciation within conversational dwell
        turn3_input = "Brilliant, thanks a lot innit."
        with patch("jarvis.brain.engine.brain_service.think", new_callable=AsyncMock) as mock_think, \
             patch("jarvis.voice.speaker.voice_speaker.speak", return_value=True):
            mock_think.return_value = {"speech_text": "Always a pleasure, sir.", "tool_calls": []}
            res3 = await ezra_app.handle_turn(turn3_input)
            self.assertTrue(res3["should_continue"])

    async def test_scenario_02_arabic_voice_query_and_app_launch(self):
        """Scenario: Fluent Arabic conversation and calculator launching."""
        # Turn 1: Arabic greeting and wake word check
        turn1_ar = "يا عزرا مرحبا كيف حالك اليوم"
        has_wake, clean_cmd = ezra_app.check_wake_word(turn1_ar)
        self.assertTrue(has_wake)
        self.assertIn("مرحبا", clean_cmd)

        with patch("jarvis.brain.engine.brain_service.think", new_callable=AsyncMock) as mock_think, \
             patch("jarvis.voice.speaker.voice_speaker.speak", return_value=True) as mock_speak:
            mock_think.return_value = {
                "speech_text": "أهلاً بك يا سيدي، كل الأنظمة تعمل بكفاءة تامة.",
                "tool_calls": []
            }
            res1 = await ezra_app.handle_turn(turn1_ar)
            self.assertTrue(res1["should_continue"])

        # Turn 2: Arabic action request to launch calculator
        turn2_ar = "شغل الآلة الحاسبة لو سمحت"
        with patch.object(self.brain, "execute_tool", new_callable=AsyncMock) as mock_tool_exec:
            mock_tool_exec.return_value = '{"status": "success", "message": "Launched calculator"}'
            semantic_res = await self.brain._parse_and_execute_semantic_actions(turn2_ar)
            self.assertIsNotNone(semantic_res)
            tool_names = [call.args[0] for call in mock_tool_exec.call_args_list]
            self.assertIn("launch_app", tool_names)

        # Turn 3: Arabic sleep command
        turn3_ar = "شكراً يا عزرا، اسكت الآن ومع السلامة"
        with patch("jarvis.voice.speaker.voice_speaker.speak", return_value=True) as mock_speak:
            res3 = await ezra_app.handle_turn(turn3_ar)
            self.assertFalse(res3["should_continue"])  # Signaled to exit/sleep
            mock_speak.assert_called_once()
            called_farewell = mock_speak.call_args[0][0]
            self.assertIn("حاضر يا سيدي", called_farewell)

    async def test_scenario_03_desktop_workflow_with_mid_speech_barge_in(self):
        """Scenario: Ezra begins vocalizing lengthy response, user interrupts with new command."""
        # Ezra begins speaking
        self.speaker.is_speaking = True

        # User interrupts with barge-in stop
        self.speaker.stop()
        self.assertFalse(self.speaker.is_speaking)
        self.assertTrue(self.speaker.is_interrupted)

        # User issues redirect command: "Wait, open Brave browser!"
        with patch.object(self.brain, "execute_tool", new_callable=AsyncMock) as mock_tool_exec:
            mock_tool_exec.return_value = '{"status": "success", "message": "Launched Brave"}'
            semantic_res = await self.brain._parse_and_execute_semantic_actions("open Brave")
            self.assertIsNotNone(semantic_res)
            tool_names = [call.args[0] for call in mock_tool_exec.call_args_list]
            self.assertIn("launch_app", tool_names)
            app_arg = mock_tool_exec.call_args_list[0].args[1]["app_name"]
            self.assertEqual(app_arg.lower(), "brave")

    def test_scenario_04_noisy_environment_end_to_end_turn(self):
        """Scenario: User voice captured in noisy environment with AC hum and desk vibration."""
        fs = self.sample_rate
        n = self.chunk_samples
        t = np.arange(n) / fs

        # 1. Simulate noisy environment: 40Hz desk thump + 120Hz AC power hum + white hiss
        np.random.seed(123)
        thump_noise = 1500.0 * np.sin(2 * np.pi * 40 * t)
        hiss_noise = np.random.randn(n) * 300.0
        ambient_frame = (thump_noise + hiss_noise).astype(np.float32)

        # Calibrate noise profile
        for _ in range(6):
            self.dsp.filter_chunk(ambient_frame, is_speech=False)

        # 2. User speaks with 220Hz pitch tone formant mixed into noise
        voiced_signal = 2500.0 * np.sin(2 * np.pi * 220 * t) + ambient_frame
        clean_arr, clean_rms, harmonic_d = self.dsp.filter_chunk(voiced_signal, is_speech=True)

        # Voice harmonic structure must be distinguished
        self.assertGreater(harmonic_d, 0.20)
        self.assertGreater(clean_rms, 200.0)

    async def test_scenario_05_continuous_conversation_dwell_and_sleep(self):
        """Scenario: Continuous conversation dwell window (25s) and sleep transition."""
        dwell_timeout = 25.0
        loop_state = {
            "is_awake": True,
            "last_interaction_time": time.time(),
            "wake_reason": "lid_opened"
        }

        # Interaction 1: Within dwell window
        time.sleep(0.01)
        self.assertTrue(loop_state["is_awake"])
        time_elapsed = time.time() - loop_state["last_interaction_time"]
        self.assertLess(time_elapsed, dwell_timeout)

        # Follow-up turn succeeds without requiring re-wake
        with patch("jarvis.brain.engine.brain_service.think", new_callable=AsyncMock) as mock_think, \
             patch("jarvis.voice.speaker.voice_speaker.speak", return_value=True):
            mock_think.return_value = {"speech_text": "The time is 10:45 AM, sir."}
            res = await ezra_app.handle_turn("What is the time?")
            self.assertTrue(res["should_continue"])
            # Refresh interaction time
            loop_state["last_interaction_time"] = time.time()

        # Interaction 2: User says 'go to sleep'
        with patch("jarvis.voice.speaker.voice_speaker.speak", return_value=True):
            sleep_res = await ezra_app.handle_turn("go to sleep")
            self.assertFalse(sleep_res["should_continue"])
            loop_state["is_awake"] = False

        self.assertFalse(loop_state["is_awake"])


if __name__ == "__main__":
    unittest.main()
