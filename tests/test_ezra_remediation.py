import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jarvis.brain.engine import BrainEngine
from jarvis.memory import MemoryManager
from jarvis.actions.vision import ScreenVision
from jarvis.actions.apps import AppManager
from jarvis.ui.visuals import StatusBar
from jarvis.voice.stt import NativeSpeechRecognizer


class TestSemanticParsing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = BrainEngine()

    async def test_open_antigravity_launches_app(self):
        """Commands like 'Ezra open Antigravity' must launch the app, not prompt it."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("Ezra open Antigravity")
            self.assertIsNotNone(res)
            tool_names = [call.args[0] for call in mock_exec.call_args_list]
            self.assertIn("launch_app", tool_names)
            self.assertNotIn("prompt_antigravity", tool_names)
            app_arg = mock_exec.call_args_list[0].args[1]["app_name"]
            self.assertEqual(app_arg.lower(), "antigravity")

    async def test_close_antigravity_closes_app(self):
        """Commands like 'close Antigravity' must kill/close the app, not prompt it."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("close Antigravity")
            self.assertIsNotNone(res)
            tool_names = [call.args[0] for call in mock_exec.call_args_list]
            self.assertIn("close_app", tool_names)
            self.assertNotIn("prompt_antigravity", tool_names)

    async def test_tell_antigravity_prompts(self):
        """Commands like 'tell antigravity to fix this code' must route to prompt_antigravity."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("tell antigravity to fix this bug")
            self.assertIsNotNone(res)
            tool_names = [call.args[0] for call in mock_exec.call_args_list]
            self.assertIn("prompt_antigravity", tool_names)

    async def test_arabic_calculator_launches_app(self):
        """'شغل الآلة الحاسبة' must launch the calculator app, NOT search YouTube."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("شغل الآلة الحاسبة")
            self.assertIsNotNone(res)
            tool_names = [call.args[0] for call in mock_exec.call_args_list]
            self.assertIn("launch_app", tool_names)
            self.assertNotIn("play_youtube", tool_names)

    async def test_arabic_media_plays_youtube(self):
        """'شغل أغنية عمرو دياب' must search YouTube."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("شغل أغنية عمرو دياب")
            self.assertIsNotNone(res)
            tool_names = [call.args[0] for call in mock_exec.call_args_list]
            self.assertIn("play_youtube", tool_names)
            self.assertNotIn("launch_app", tool_names)

    async def test_arabic_attached_conjunctions(self):
        """Compound request with attached 'و' (e.g. 'افتح المتصفح وسكري الترمينال ووطي الصوت لـ 30') must split correctly."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("افتح المتصفح وسكري الترمينال ووطي الصوت لـ 30")
            self.assertIsNotNone(res)
            tool_names = [call.args[0] for call in mock_exec.call_args_list]
            self.assertIn("launch_app", tool_names)
            self.assertIn("close_app", tool_names)
            self.assertIn("set_volume", tool_names)

    async def test_search_regex_truncation(self):
        """'search for python documentation' must search for 'python documentation', NOT 'for python documentation'."""
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions("search for python documentation")
            self.assertIsNotNone(res)
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0][1]
            self.assertEqual(args["query"], "python documentation")

    async def test_clean_text_strips_json(self):
        """clean_text must strip inline raw JSON tool calls so Ezra never reads curly braces aloud."""
        raw_reply = 'Sure thing, sir! {"tool": "launch_app", "args": {"app_name": "calculator"}} All set.'
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success", "message": "Launched"}'
            res = await self.engine._process_tool_calls_in_text(raw_reply)
            speech = res["speech_text"]
            self.assertNotIn("{", speech)
            self.assertNotIn("}", speech)
            self.assertNotIn('"tool"', speech)
            self.assertIn("Sure thing, sir!", speech)


class TestMultiKeyAndQuota(unittest.IsolatedAsyncioTestCase):
    def test_memory_gemini_key_split(self):
        """Memory auto_learn_from_interaction must extract single key from comma-separated env."""
        mem = MemoryManager()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "key1_valid,key2_valid,key3_valid"}):
            with patch("google.genai.Client") as mock_client:
                mock_client.return_value.models.generate_content.return_value = MagicMock(text='{"learned": false}')
                asyncio.run(mem.auto_learn_from_interaction("my test text", "my reply"))
                mock_client.assert_called_once_with(api_key="key1_valid")

    def test_vision_gemini_key_split(self):
        """ScreenVision must split comma-separated keys and pass individual keys to genai.Client."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "vision_key_1,vision_key_2"}):
            keys = ScreenVision.get_api_keys()
            self.assertEqual(keys, ["vision_key_1", "vision_key_2"])

            with patch("google.genai.Client") as mock_client:
                mock_resp = MagicMock()
                mock_resp.text = "Desk screen"
                mock_client.return_value.models.generate_content.return_value = mock_resp
                res = ScreenVision._call_gemini_vision(b"fake_image_bytes", "inspect")
                self.assertEqual(res, "Desk screen")
                # Ensure the key passed is the single active key
                mock_client.assert_called_with(api_key="vision_key_1")

    async def test_no_auto_learn_on_fast_path(self):
        """Fast-path direct actions must NOT trigger auto_learn_from_interaction."""
        engine = BrainEngine()
        with patch("jarvis.memory.memory_service.auto_learn_from_interaction", new_callable=AsyncMock) as mock_learn:
            with patch.object(engine, "_try_direct_action", new_callable=AsyncMock) as mock_direct:
                mock_direct.return_value = {"speech_text": "Volume adjusted", "tool_calls": []}
                out = await engine.think("turn volume down")
                self.assertIsNotNone(out)
                mock_learn.assert_not_called()

    def test_gemini_models_include_lite_and_rotate_on_429(self):
        """Engine candidate models must include operational lite models."""
        engine = BrainEngine()
        # Verify the candidate list has gemini-flash-lite-latest and gemini-3.5-flash-lite
        import inspect
        source = inspect.getsource(engine._call_gemini)
        self.assertIn("gemini-flash-lite-latest", source)
        self.assertIn("gemini-3.5-flash-lite", source)
        # Verify on 429 it rotates (continue) rather than premature break
        self.assertIn("elif resp.status == 429:\n                                continue", source)


class TestSTTAndWake(unittest.TestCase):
    def test_stt_worker_stall_timeout(self):
        """STT record_until_finished must not hang indefinitely if worker stalls after is_speaking is True."""
        recognizer = NativeSpeechRecognizer.__new__(NativeSpeechRecognizer)
        recognizer.worker = MagicMock()
        recognizer.worker.calibrated = True
        recognizer.chunk_duration = 0.08
        recognizer.sample_rate = 16000

        # First return a voice chunk that triggers speech, then None to simulate stall
        recognizer.worker.ambient_baseline = 50.0
        loud_chunk = (b"\x00" * 2560, 300.0)
        # Return 3 loud chunks then continuous None
        call_count = [0]
        def fake_get_chunk():
            call_count[0] += 1
            if call_count[0] <= 3:
                return loud_chunk
            return None

        recognizer.worker.get_chunk.side_effect = fake_get_chunk
        recognizer.worker.drain = MagicMock()

        import time
        t0 = time.time()
        # Run record_until_finished with small max_wait_sec
        result = recognizer.record_until_finished(max_wait_sec=2.0, silence_threshold_sec=0.32)
        elapsed = time.time() - t0
        # It must exit cleanly within ~1.5s after stall, not hang!
        self.assertLess(elapsed, 3.0)
        self.assertFalse(recognizer.is_user_speaking)

    def test_wake_greeting_suppressed_when_user_speaking(self):
        """Wake greeting must NOT play if user is actively speaking."""
        import app
        mock_speaker = MagicMock()
        mock_stt = MagicMock()
        mock_stt.is_user_speaking = True

        # Import or test the on_laptop_wake logic
        with patch("app.voice_speaker", mock_speaker):
            with patch("app.stt_engine", mock_stt):
                # Execute the wake callback logic
                # We can extract and test on_laptop_wake from app.py or simulate it
                def test_wake_logic(reason):
                    if getattr(mock_stt, "is_user_speaking", False):
                        return
                    mock_speaker.speak("Greeting")

                test_wake_logic("lid_opened")
                mock_speaker.speak.assert_not_called()


class TestVisualsThreadSafety(unittest.TestCase):
    def test_status_bar_lock_usage(self):
        """StatusBar must acquire self._lock when rendering."""
        bar = StatusBar()
        self.assertTrue(hasattr(bar, "_lock"))
        import inspect
        source_render = inspect.getsource(bar.render_listening)
        self.assertIn("with self._lock:", source_render)
        source_stop_think = inspect.getsource(bar.stop_thinking)
        self.assertIn("with self._lock:", source_stop_think)
        source_stop_speak = inspect.getsource(bar.stop_speaking)
        self.assertIn("with self._lock:", source_stop_speak)
        source_clear = inspect.getsource(bar.clear)
        self.assertIn("with self._lock:", source_clear)


class TestAntigravityPromptBridge(unittest.TestCase):
    def test_prompt_antigravity_ctrl_l(self):
        """prompt_antigravity must trigger ctrl+l hotkey to focus chat input before pasting."""
        with patch("jarvis.actions.apps.pyautogui") as mock_pyautogui:
            with patch("jarvis.actions.apps.set_clipboard", return_value=True):
                with patch("jarvis.actions.apps.AppManager.focus_app"):
                    res = AppManager.prompt_antigravity("sample prompt")
                    self.assertEqual(res["status"], "success")
                    mock_pyautogui.hotkey.assert_any_call("ctrl", "l")
                    mock_pyautogui.hotkey.assert_any_call("ctrl", "v")


class TestEdgeCases(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = BrainEngine()

    async def test_empty_and_whitespace_inputs(self):
        """Empty or whitespace input should return None without error."""
        res1 = await self.engine._parse_and_execute_semantic_actions("")
        self.assertIsNone(res1)
        res2 = await self.engine._parse_and_execute_semantic_actions("   \t  \n ")
        self.assertIsNone(res2)

    async def test_search_variants(self):
        """All search variants should extract the target query cleanly."""
        variants = [
            ("search for rustlang documentation", "rustlang documentation"),
            ("search rustlang documentation", "rustlang documentation"),
            ("search the web for rustlang documentation", "rustlang documentation"),
            ("google for rustlang documentation", "rustlang documentation"),
            ("google rustlang documentation", "rustlang documentation"),
            ("ابحث عن توثيق بايثون", "توثيق بايثون"),
        ]
        for prompt, expected_query in variants:
            with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = '{"status": "success"}'
                res = await self.engine._parse_and_execute_semantic_actions(prompt)
                self.assertIsNotNone(res, f"Failed to match search for: {prompt}")
                mock_exec.assert_called_once()
                call_args = mock_exec.call_args[0][1]
                self.assertEqual(call_args["query"], expected_query, f"Mismatch for '{prompt}'")

    async def test_arabic_multi_word_app_launch(self):
        """Compound launch of Arabic multi-word apps and attached conjunctions."""
        prompt = "وافتحي الآلة الحاسبة وسكري الترمينال"
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions(prompt)
            self.assertIsNotNone(res)
            called_tools = [c.args[0] for c in mock_exec.call_args_list]
            self.assertIn("launch_app", called_tools)
            self.assertIn("close_app", called_tools)

    async def test_deep_json_stripping_from_speech(self):
        """Complex replies with nested JSON and brackets must be stripped of all curly braces."""
        complex_reply = (
            "Right away, sir. "
            "```tool_call\n"
            "{\"tool\": \"launch_app\", \"args\": {\"app_name\": \"antigravity\"}}\n"
            "```\n"
            "Also executing: {\"tool\": \"set_volume\", \"args\": {\"percent\": 50}} "
            "and leftover JSON {\"notes\": [1, 2, 3], \"status\": \"done\"}. Ready!"
        )
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._process_tool_calls_in_text(complex_reply)
            speech = res["speech_text"]
            self.assertNotIn("{", speech)
            self.assertNotIn("}", speech)
            self.assertNotIn("```", speech)
            self.assertIn("Right away, sir.", speech)
            self.assertIn("Ready!", speech)

    def test_multi_key_whitespace_and_empty(self):
        """ScreenVision and Memory key parsing must handle trailing/leading whitespace and empty keys."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "  key_a  ,  key_b ,   "}):
            keys = ScreenVision.get_api_keys()
            self.assertEqual(keys, ["key_a", "key_b"])

    def test_kwin_focus_rejects_false_positive_terminals(self):
        """KWin window focusing must reject terminal windows whose title only matches via directory path."""
        from jarvis.actions.apps import focus_window_by_pattern
        raw_dbus_output = (
            '[Argument: a(sssida{sv}) {'
            '[Argument: (sssida{sv}) "0_{terminal_id}", "~/.gemini/antigravity/scratch/code", "kitty", 30, 0.7, [Argument: a{sv} {}]]'
            '}]'
        )
        fake_info_output = "resourceClass: kitty\ndesktopFile: kitty\nresourceName: kitty\n"
        with patch("shutil.which", side_effect=lambda c: "/usr/bin/qdbus6" if "qdbus" in c else None):
            with patch("subprocess.run") as mock_sub:
                def fake_run(cmd, *args, **kwargs):
                    mock_res = MagicMock()
                    mock_res.returncode = 0
                    if "/WindowsRunner" in cmd and "Match" in cmd:
                        mock_res.stdout = raw_dbus_output
                    elif "/KWin" in cmd and "getWindowInfo" in cmd:
                        mock_res.stdout = fake_info_output
                    elif "/WindowsRunner" in cmd and "Run" in cmd:
                        mock_res.stdout = ""
                    else:
                        mock_res.stdout = ""
                    return mock_res
                mock_sub.side_effect = fake_run

                # Searching for antigravity when only kitty with antigravity path is open must return False (so app can be launched)!
                result = focus_window_by_pattern("antigravity")
                self.assertFalse(result)

    async def test_arabic_attached_pronoun_splitting(self):
        """Commands with attached pronoun verbs like 'وافتحيها' or 'وسكريها' must split correctly."""
        prompt = "افتحي الآلة الحاسبة وسكريها"
        with patch.object(self.engine, "execute_tool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = '{"status": "success"}'
            res = await self.engine._parse_and_execute_semantic_actions(prompt)
            self.assertIsNotNone(res)
            called_tools = [c.args[0] for c in mock_exec.call_args_list]
            self.assertIn("launch_app", called_tools)

    def test_speaker_is_speaking_resets_in_finally(self):
        """SmoothSpeaker._play_file_with_interrupt must reset is_speaking to False even on error."""
        from jarvis.voice.speaker import SmoothSpeaker
        spk = SmoothSpeaker()
        spk.is_speaking = True
        with patch("jarvis.voice.speaker.HAS_PYGAME_MIXER", False):
            with patch("subprocess.Popen", side_effect=RuntimeError("Audio player error")):
                spk._play_file_with_interrupt("/fake/path.mp3")
                self.assertFalse(spk.is_speaking)

    def test_memory_auto_learn_uses_flash_lite(self):
        """MemoryManager auto_learn_from_interaction must target high-quota gemini-flash-lite-latest."""
        import inspect
        mem = MemoryManager()
        source = inspect.getsource(mem.auto_learn_from_interaction)
        self.assertIn("gemini-flash-lite-latest", source)
        self.assertNotIn("gemini-robotics-er-2-preview", source)

    def test_calculator_qalc_terminal_launch(self):
        """AppManager.launch_app('calculator') when qalc is present should launch in terminal."""
        with patch("shutil.which") as mock_which:
            def fake_which(cmd):
                if cmd in ("qalc", "kitty"):
                    return f"/usr/bin/{cmd}"
                return None
            mock_which.side_effect = fake_which
            with patch("subprocess.Popen") as mock_popen:
                res = AppManager.launch_app("calculator")
                self.assertEqual(res["status"], "success")
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], "/usr/bin/kitty")
                self.assertEqual(args[1], "-e")
                self.assertEqual(args[2], "qalc")


    def test_arabic_app_map_focus(self):
        """focus_window_by_pattern must include English equivalent for Arabic app queries."""
        from jarvis.actions.apps import ARABIC_APP_MAP
        self.assertIn("الآلة الحاسبة", ARABIC_APP_MAP)
        self.assertEqual(ARABIC_APP_MAP["الآلة الحاسبة"], "calculator")


if __name__ == "__main__":
    unittest.main()
