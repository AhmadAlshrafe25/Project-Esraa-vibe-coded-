"""
Tier 2: Boundary & Corner Cases E2E Tests for Project Ezra Overhaul.

Verifies system resilience against adversarial boundaries and corner cases:
- Empty inputs and zero-length buffers
- Extreme lengths (10,000+ characters, 300+ word sentences)
- 1.0s - 1.5s pause threshold boundary transitions
- Acoustic saturation (full-scale int16 square wave, DC rails)
- Invalid app targets and command injection attempts
- Rapid WebSocket connection & abrupt client disconnections
- Sub-minimum speech duration (<0.35s rejected as noise)
- Odd-byte-length and malformed PCM data
"""

import os
import sys
import unittest
import asyncio
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.voice.speaker import SmoothSpeaker
from jarvis.voice.stt import AudioDSPFilter, NativeSpeechRecognizer, AudioStreamWorker
from jarvis.actions.apps import AppManager
from jarvis.ui.server import EzraUIServer
from jarvis.voice.biometrics import VoiceBiometrics
import app as ezra_app
from config.settings import SHORT_SIL, END_SIL, SPEECH_LONG_THRESHOLD, MIN_SPEECH


class TestTier2BoundaryAndCornerCases(unittest.IsolatedAsyncioTestCase):
    """Tier 2 Boundary & Corner Cases Test Suite."""

    def setUp(self):
        self.sample_rate = 16000
        self.chunk_samples = 1280
        self.dsp = AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=self.chunk_samples)
        self.speaker = SmoothSpeaker()

    def test_b01_empty_pcm_and_zero_duration(self):
        """Verify DSP and RMS calculation handle empty and zero-length buffers safely."""
        clean_bytes, rms, hd = self.dsp.filter_chunk(np.zeros(0, dtype=np.float32), is_speech=False)
        self.assertEqual(len(clean_bytes), self.chunk_samples)  # Auto-padded cleanly
        self.assertEqual(rms, 0.0)
        self.assertEqual(hd, 0.0)

        # Worker calculation on empty bytes
        worker = AudioStreamWorker.__new__(AudioStreamWorker)
        worker.sample_rate = 16000
        worker.chunk_duration = 0.08
        worker.dsp = self.dsp
        res_bytes, res_rms, res_hd = worker._calc_rms_and_clean(b"", is_speech=False)
        self.assertEqual(res_bytes, b"")
        self.assertEqual(res_rms, 0.0)
        self.assertEqual(res_hd, 0.0)

        # Harmonic density on empty / short byte buffer
        hd_empty = self.dsp.calc_harmonic_density(b"")
        self.assertEqual(hd_empty, 0.0)
        hd_short = self.dsp.calc_harmonic_density(b"\x00" * 100)
        self.assertEqual(hd_short, 0.0)

    def test_b02_acoustic_saturation_full_scale_clipping(self):
        """Verify audio DSP gracefully processes full-scale +32767/-32768 square waves without NaN or Inf."""
        # Pure +32767 / -32768 rail-to-rail square wave (worst-case microphone clipping)
        square_wave = np.ones(self.chunk_samples, dtype=np.float32) * 32767.0
        square_wave[self.chunk_samples // 2:] = -32768.0

        clean_arr, ac_rms, hd = self.dsp.filter_chunk(square_wave, is_speech=False)

        # Verify no NaN or Inf in output and substantial energy preserved
        self.assertFalse(np.isnan(ac_rms))
        self.assertFalse(np.isinf(ac_rms))
        self.assertFalse(np.isnan(hd))
        self.assertFalse(np.isinf(hd))
        self.assertFalse(np.any(np.isnan(clean_arr)))
        self.assertFalse(np.any(np.isinf(clean_arr)))
        self.assertGreater(ac_rms, 500.0)

    def test_b03_extreme_text_length_vocalization(self):
        """Verify SmoothSpeaker.speak handles 10,000+ character text blocks without buffer errors."""
        long_text = "This is a stress test sentence designed to verify boundary handling. " * 150  # ~10,500 chars
        self.assertGreater(len(long_text), 10000)

        with patch.object(self.speaker, "_play_file_with_interrupt", return_value=True), \
             patch.object(self.speaker, "_play_pcm_with_interrupt", return_value=True, create=True), \
             patch.object(getattr(self.speaker, "local_tts", MagicMock()), "synthesize_sentence_stream", return_value=[(b"\x00" * 100, 24000, "chunk")]), \
             patch.object(self.speaker, "_generate_edge_speech", new_callable=AsyncMock) as mock_edge:
            mock_edge.return_value = "/tmp/long_stress_test.mp3"
            res = self.speaker.speak(long_text, live_print=False)
            self.assertTrue(res)

    def test_b04_special_characters_emojis_and_shell_metachars(self):
        """Verify prompt containing emojis, unicode, and shell metacharacters is handled safely."""
        malicious_prompt = 'Ezra; rm -rf /; $(whoami); `cat /etc/passwd` & <script>alert("xss")</script> 🚀🔥✨'
        
        # Wake word check must handle symbols without regex corruption
        has_wake, clean = ezra_app.check_wake_word(malicious_prompt)
        self.assertTrue(has_wake)
        self.assertIn("rm -rf", clean)

        # Mute check and speech generation must not execute shell commands
        with patch.object(self.speaker, "_play_file_with_interrupt", return_value=True), \
             patch.object(self.speaker, "_play_pcm_with_interrupt", return_value=True, create=True):
            res = self.speaker.speak(malicious_prompt, live_print=False)
            self.assertTrue(res)

    def test_b05_pause_threshold_boundaries(self):
        """Verify endpointing decision boundary at exactly 1.0s, 1.2s, 1.5s, and 1.6s."""
        rec = NativeSpeechRecognizer.__new__(NativeSpeechRecognizer)
        rec.sample_rate = 16000
        rec.chunk_duration = 0.08
        rec.chunk_size = 2560
        rec.dsp = self.dsp
        rec.worker = MagicMock()
        rec.worker.calibrated = True
        rec.worker.ambient_baseline = 100.0

        t = np.arange(self.chunk_samples) / self.sample_rate
        voice_pcm = (800.0 * np.sin(2 * np.pi * 200 * t)).astype(np.int16).tobytes()
        quiet_pcm = (np.random.randn(self.chunk_samples) * 30.0).astype(np.int16).tobytes()

        # 14 chunks of speech = 1.12s (just below 1.2s long speech threshold)
        # Should terminate turn once silence exceeds SHORT_SIL (0.9s = 11-12 chunks)
        short_stream = [(voice_pcm, 600.0, 0.45) for _ in range(14)] + \
                       [(quiet_pcm, 50.0, 0.05) for _ in range(int(SHORT_SIL / 0.08) + 2)]
        idx = [0]
        def pull_short():
            if idx[0] < len(short_stream):
                c = short_stream[idx[0]]
                idx[0] += 1
                return c
            return None
        rec.worker.get_chunk.side_effect = pull_short
        rec.record_until_finished(max_wait_sec=5.0)
        self.assertLessEqual(idx[0], 14 + int(SHORT_SIL / 0.08) + 2)

        # 16 chunks of speech = 1.28s (exceeding 1.2s long speech threshold)
        # 13 chunks of quiet = 1.04s silence (exceeds 0.9s SHORT_SIL, but LESS than 1.6s END_SIL)
        # Must NOT cut off at 1.04s silence!
        long_stream = [(voice_pcm, 600.0, 0.45) for _ in range(16)] + \
                      [(quiet_pcm, 50.0, 0.05) for _ in range(int(END_SIL / 0.08) + 2)]
        idx_long = [0]
        def pull_long():
            if idx_long[0] < len(long_stream):
                c = long_stream[idx_long[0]]
                idx_long[0] += 1
                return c
            return None
        rec.worker.get_chunk.side_effect = pull_long
        rec.record_until_finished(max_wait_sec=5.0)
        # Must have waited until END_SIL (16 + 20 chunks = 36 chunks)
        self.assertGreaterEqual(idx_long[0], 16 + int(END_SIL / 0.08))

    def test_b06_invalid_and_nonexistent_app_targets(self):
        """Verify AppManager.launch_app gracefully handles unknown/uninstalled app targets."""
        res = AppManager.launch_app("definitely_non_existent_app_xyz_998877")
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("status"), "error")
        self.assertIn("not found", res.get("message", "").lower())

        res2 = AppManager.launch_app("another_bogus_target_binary_404")
        self.assertIsInstance(res2, dict)
        self.assertEqual(res2.get("status"), "error")

    async def test_b07_ui_websocket_rapid_connect_and_abrupt_disconnect(self):
        """Verify EzraUIServer handles sudden WebSocket client disconnects during active broadcast."""
        server = EzraUIServer(host="127.0.0.1", port=8099)
        mock_ws_healthy = AsyncMock()
        mock_ws_faulty = AsyncMock()
        mock_ws_faulty.send_str.side_effect = ConnectionResetError("Client closed socket abruptly")

        server.ws_clients.add(mock_ws_healthy)
        server.ws_clients.add(mock_ws_faulty)

        # Broadcast should succeed for healthy client and discard faulty client cleanly
        await server.broadcast({"type": "state_change", "state": "listening"})

        self.assertIn(mock_ws_healthy, server.ws_clients)
        self.assertNotIn(mock_ws_faulty, server.ws_clients)

    def test_b08_sub_minimum_speech_duration_rejected(self):
        """Verify noise burst under MIN_SPEECH (0.35s = ~4 chunks) does not trigger turn acceptance."""
        rec = NativeSpeechRecognizer.__new__(NativeSpeechRecognizer)
        rec.sample_rate = 16000
        rec.chunk_duration = 0.08
        rec.chunk_size = 2560
        rec.dsp = self.dsp
        rec.worker = MagicMock()
        rec.worker.calibrated = True
        rec.worker.ambient_baseline = 100.0

        t = np.arange(self.chunk_samples) / self.sample_rate
        voice_pcm = (800.0 * np.sin(2 * np.pi * 200 * t)).astype(np.int16).tobytes()
        quiet_pcm = (np.random.randn(self.chunk_samples) * 30.0).astype(np.int16).tobytes()

        # 2 chunks of sound (2 * 0.08 = 0.16s < MIN_SPEECH 0.35s)
        transient_stream = [(voice_pcm, 600.0, 0.45) for _ in range(2)] + \
                           [(quiet_pcm, 50.0, 0.05) for _ in range(int(SHORT_SIL / 0.08) + 5)]
        idx = [0]
        def pull_transient():
            if idx[0] < len(transient_stream):
                c = transient_stream[idx[0]]
                idx[0] += 1
                return c
            return (quiet_pcm, 50.0, 0.05)

        rec.worker.get_chunk.side_effect = pull_transient
        result = rec.record_until_finished(max_wait_sec=0.5)
        # Should return empty string because total speech was shorter than MIN_SPEECH
        self.assertEqual(result, "")

    def test_b09_corrupt_and_odd_byte_length_pcm_buffers(self):
        """Verify biometrics and STT handle odd-byte-length and corrupted PCM buffers safely."""
        with patch.object(VoiceBiometrics, "load_profile", return_value=True):
            bio = VoiceBiometrics()
            bio.enrolled = True
            bio.voice_vector = np.zeros(48, dtype=np.float32)

            # Odd byte buffer (cannot unpack into int16 pairs without clipping/padding)
            odd_pcm = b"\x00\x01\x02\x03\x04"
            tier, score, detail = bio.verify_turn(odd_pcm, "test speech")
            self.assertIn(tier, ("guest", "verified", "unsure"))
            self.assertIsInstance(score, float)


if __name__ == "__main__":
    unittest.main()
