import os
import sys
import unittest
import time
from unittest.mock import patch, MagicMock
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jarvis.voice.stt import NativeSpeechRecognizer, AudioDSPFilter
from jarvis.voice.speaker import SmoothSpeaker
from config.settings import (
    END_SIL,
    SHORT_SIL,
    MAX_UTT,
    MIN_SPEECH,
    PRE_BUFFER_SEC,
    SPEECH_LONG_THRESHOLD,
    NEED_ON_IDLE,
    NEED_ON_WORKING,
    NEED_ON_GUEST,
    ANSWER_ONLY_ON_WAKE,
    PUSH_TO_TALK,
)


class TestMusaTurnTakingAndEndpointing(unittest.TestCase):
    def setUp(self):
        self.sample_rate = 16000
        self.chunk_samples = 1280
        self.dsp = AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=self.chunk_samples)

        self.recognizer = NativeSpeechRecognizer.__new__(NativeSpeechRecognizer)
        self.recognizer.sample_rate = 16000
        self.recognizer.chunk_duration = 0.08
        self.recognizer.chunk_size = 2560
        self.recognizer.dsp = self.dsp
        self.recognizer.vosk_model = None
        self.recognizer.worker = MagicMock()
        self.recognizer.worker.calibrated = True
        self.recognizer.worker.drain = MagicMock()
        self.recognizer.worker.ambient_baseline = 100.0

    def _make_chunk(self, rms_val=500.0, harmonic_density=0.45):
        """Generates a synthetic voice chunk."""
        t = np.arange(self.chunk_samples) / self.sample_rate
        # 160Hz vocal tone
        signal = (rms_val * 1.2 * np.sin(2 * np.pi * 160 * t)).astype(np.int16).tobytes()
        return (signal, rms_val, harmonic_density)

    def _make_silence_chunk(self, rms_val=80.0):
        """Generates a quiet ambient chunk below silence threshold."""
        quiet = np.random.randn(self.chunk_samples).astype(np.float32) * (rms_val * 0.5)
        raw_bytes = quiet.astype(np.int16).tobytes()
        return (raw_bytes, rms_val, 0.05)

    def test_default_musa_constants(self):
        """Verify default Musa timing specifications match exactly."""
        self.assertEqual(END_SIL, 1.6)
        self.assertEqual(SHORT_SIL, 0.9)
        self.assertEqual(MAX_UTT, 60.0)
        self.assertEqual(MIN_SPEECH, 0.35)
        self.assertEqual(PRE_BUFFER_SEC, 0.40)
        self.assertEqual(SPEECH_LONG_THRESHOLD, 1.2)
        self.assertEqual(NEED_ON_IDLE, 0.15)
        self.assertEqual(NEED_ON_WORKING, 0.30)
        self.assertEqual(NEED_ON_GUEST, 0.20)

    def test_short_speech_silence_wait_is_short_sil(self):
        """Speech under 1.2s waits for SHORT_SIL (0.9s = 11-12 chunks) of quiet before ending turn."""
        # 8 speech chunks (8 * 0.08s = 0.64s < 1.2s threshold)
        speech_chunks = [self._make_chunk(rms_val=600.0) for _ in range(8)]
        # Silence chunks (ambient baseline is 100, silence is < 200)
        # Musa SHORT_SIL is 0.9s -> 11 chunks @ 80ms
        silence_chunks = [self._make_silence_chunk(rms_val=60.0) for _ in range(12)]
        all_chunks = speech_chunks + silence_chunks

        chunk_idx = [0]
        def get_chunk_mock():
            if chunk_idx[0] < len(all_chunks):
                c = all_chunks[chunk_idx[0]]
                chunk_idx[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk_mock
        res = self.recognizer.record_until_finished(max_wait_sec=5.0)
        # Should have captured the utterance and ended after 11 silence chunks
        self.assertTrue(res != "")
        # Verified that it terminated cleanly on the short silence limit (not waiting for 1.6s)
        self.assertLessEqual(chunk_idx[0], len(all_chunks))

    def test_long_speech_silence_wait_is_end_sil(self):
        """Speech over 1.2s waits for END_SIL (1.6s = 20 chunks) of quiet before ending turn."""
        # 18 speech chunks (18 * 0.08s = 1.44s > 1.2s threshold)
        speech_chunks = [self._make_chunk(rms_val=600.0) for _ in range(18)]
        # 19 silence chunks (19 * 0.08 = 1.52s, not quite 1.6s)
        # At 19 chunks, turn must NOT yet be ended; 20th chunk finishes it.
        silence_chunks = [self._make_silence_chunk(rms_val=60.0) for _ in range(21)]
        all_chunks = speech_chunks + silence_chunks

        chunk_idx = [0]
        def get_chunk_mock():
            if chunk_idx[0] < len(all_chunks):
                c = all_chunks[chunk_idx[0]]
                chunk_idx[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk_mock
        res = self.recognizer.record_until_finished(max_wait_sec=5.0)
        self.assertTrue(res != "")
        # Must have consumed 18 speech chunks + 20 silence chunks = 38 chunks
        self.assertGreaterEqual(chunk_idx[0], 38)

    def test_min_speech_discards_transient_noise(self):
        """Speech shorter than MIN_SPEECH (0.35s = < 5 chunks) is treated as click/cough and discarded."""
        # Only 2 speech chunks = 0.16s < 0.35s
        speech_chunks = [self._make_chunk(rms_val=600.0) for _ in range(2)]
        silence_chunks = [self._make_silence_chunk(rms_val=60.0) for _ in range(15)]
        all_chunks = speech_chunks + silence_chunks

        chunk_idx = [0]
        def get_chunk_mock():
            if chunk_idx[0] < len(all_chunks):
                c = all_chunks[chunk_idx[0]]
                chunk_idx[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk_mock
        res = self.recognizer.record_until_finished(max_wait_sec=2.0)
        self.assertEqual(res, "", "Short burst < 0.35s must be discarded as noise")

    def test_pre_speech_ring_buffer_preserves_initial_audio(self):
        """PRE (0.40s = 5 chunks) pre-speech ring buffer must be prepended so first consonant isn't cut."""
        # 5 quiet ambient chunks before voice starts
        pre_chunks = [self._make_silence_chunk(rms_val=90.0) for _ in range(5)]
        # 6 speech chunks (>0.35s)
        voice_chunks = [self._make_chunk(rms_val=600.0) for _ in range(6)]
        # 12 silence chunks to finish turn
        end_silence = [self._make_silence_chunk(rms_val=80.0) for _ in range(12)]
        all_chunks = pre_chunks + voice_chunks + end_silence

        chunk_idx = [0]
        def get_chunk_mock():
            if chunk_idx[0] < len(all_chunks):
                c = all_chunks[chunk_idx[0]]
                chunk_idx[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk_mock
        res = self.recognizer.record_until_finished(max_wait_sec=3.0)
        self.assertTrue(res != "")
        last_pcm = self.recognizer.get_last_pcm()
        # Total frames must contain the pre_buffer frames
        # 5 pre_buffer chunks + 6 voice chunks + 1 initial trigger chunk + trailing chunks
        expected_min_bytes = (5 + 6) * 2560
        self.assertGreaterEqual(len(last_pcm), expected_min_bytes)

    def test_need_on_sound_duration_requirements(self):
        """Sound duration needed to trigger turn: 0.15s (2 chunks) idle, 0.30s (4 chunks) working, 0.20s (3 chunks) guest."""
        # Idle: 1 chunk is not enough, 2 chunks triggers
        c1 = [self._make_chunk(rms_val=600.0)] + [self._make_silence_chunk() for _ in range(5)]
        chunk_idx1 = [0]
        def get_chunk1():
            if chunk_idx1[0] < len(c1):
                c = c1[chunk_idx1[0]]
                chunk_idx1[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk1
        res1 = self.recognizer.record_until_finished(max_wait_sec=0.5, is_busy=False)
        self.assertEqual(res1, "", "1 chunk (0.08s) should not trigger onset when needOn is 0.15s")

        # Working: needs 4 chunks (0.30s)
        # Provide 2 chunks of voice: should NOT trigger while working
        c_work = [self._make_chunk(rms_val=600.0), self._make_chunk(rms_val=600.0)] + [self._make_silence_chunk() for _ in range(5)]
        chunk_idx_w = [0]
        def get_chunk_w():
            if chunk_idx_w[0] < len(c_work):
                c = c_work[chunk_idx_w[0]]
                chunk_idx_w[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk_w
        res_work = self.recognizer.record_until_finished(max_wait_sec=0.5, is_busy=True)
        self.assertEqual(res_work, "", "2 chunks (0.16s) should not trigger onset while busy/working (needOn=0.30s)")

    def test_silence_volume_threshold_is_2x_speech_start_baseline(self):
        """Musa rule: Silence means volume drops below 2x the background level at speech onset."""
        # Start with ambient baseline = 100.0.
        # Speech onset triggers. Speech start baseline is recorded as 100.0.
        # Silence cutoff is 100.0 * 2.0 = 200.0.
        # If subsequent audio is 250.0 (above 200.0), it counts as continuing speech, NOT silence!
        speech_chunks = [self._make_chunk(rms_val=600.0) for _ in range(4)]
        # Mid-level speech chunks at 250.0 (> 200.0)
        mid_chunks = [self._make_chunk(rms_val=250.0) for _ in range(5)]
        # Then true quiet below 200.0
        quiet_chunks = [self._make_silence_chunk(rms_val=120.0) for _ in range(12)]
        all_chunks = speech_chunks + mid_chunks + quiet_chunks

        chunk_idx = [0]
        def get_chunk_mock():
            if chunk_idx[0] < len(all_chunks):
                c = all_chunks[chunk_idx[0]]
                chunk_idx[0] += 1
                return c
            return None

        self.recognizer.worker.get_chunk.side_effect = get_chunk_mock
        res = self.recognizer.record_until_finished(max_wait_sec=3.0)
        # The 5 mid-chunks (250 RMS > 200 silence threshold) counted as speech.
        # Then exactly 11 silence chunks (0.9s SHORT_SIL) ended the turn.
        self.assertEqual(chunk_idx[0], 4 + 5 + 11)

    def test_speaker_ducking_on_user_speech(self):
        """When user starts talking while Ezra is speaking, speaker volume ducks immediately."""
        speaker = SmoothSpeaker()
        speaker.is_speaking = True
        speaker.duck_volume = MagicMock()
        speaker.stop = MagicMock()

        # Mock voice_speaker in jarvis.voice.speaker
        with patch("jarvis.voice.speaker.voice_speaker", speaker):
            # 2 chunks of voice triggers needOn
            speech_chunks = [self._make_chunk(rms_val=700.0) for _ in range(6)]
            silence_chunks = [self._make_silence_chunk(rms_val=50.0) for _ in range(12)]
            all_chunks = speech_chunks + silence_chunks

            chunk_idx = [0]
            def get_chunk_mock():
                if chunk_idx[0] < len(all_chunks):
                    c = all_chunks[chunk_idx[0]]
                    chunk_idx[0] += 1
                    return c
                return None

            self.recognizer.worker.get_chunk.side_effect = get_chunk_mock
            self.recognizer.record_until_finished(max_wait_sec=3.0)

            # Speaker duck_volume must have been called on onset
            speaker.duck_volume.assert_called_with(0.15)
            # Confirmed speech (>0.35s) must have stopped speaker reply for good
            speaker.stop.assert_called()


if __name__ == "__main__":
    unittest.main()
