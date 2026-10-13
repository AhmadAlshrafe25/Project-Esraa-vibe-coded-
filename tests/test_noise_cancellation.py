import os
import sys
import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jarvis.voice.stt import AudioDSPFilter, NativeSpeechRecognizer
from jarvis.voice.biometrics import VoiceBiometrics, TIER_VERIFIED, TIER_GUEST
from jarvis.brain.engine import BrainEngine


class TestAudioDSPAndNoiseFiltering(unittest.TestCase):
    def setUp(self):
        self.sample_rate = 16000
        self.chunk_samples = 1280
        self.dsp = AudioDSPFilter(sample_rate=self.sample_rate, chunk_samples=self.chunk_samples)

    def test_bandpass_filter_attenuates_sub_bass_and_high_hiss(self):
        """Bandpass filter (85 Hz to 3500 Hz) must eliminate sub-bass rumbles/thumps and high hiss."""
        fs = self.sample_rate
        n = self.chunk_samples
        t = np.arange(n) / fs

        # 40 Hz sub-bass room rumble / desk thump
        thump_40hz = 2000.0 * np.sin(2 * np.pi * 40 * t)
        # 5500 Hz high frequency screech / coil whine / hiss
        hiss_5500hz = 2000.0 * np.sin(2 * np.pi * 5500 * t)
        # 500 Hz human voice formant tone
        voice_500hz = 1000.0 * np.sin(2 * np.pi * 500 * t)

        _, thump_rms, _ = self.dsp.filter_chunk(thump_40hz, is_speech=False)
        _, hiss_rms, _ = self.dsp.filter_chunk(hiss_5500hz, is_speech=False)
        _, voice_rms, _ = self.dsp.filter_chunk(voice_500hz, is_speech=True)

        raw_thump_rms = np.sqrt(np.mean(thump_40hz ** 2))
        raw_hiss_rms = np.sqrt(np.mean(hiss_5500hz ** 2))

        # Sub-bass thump must be attenuated by > 20 dB (at least 90% power reduction)
        self.assertLess(thump_rms, raw_thump_rms * 0.15)
        # High screech must be attenuated by > 20 dB
        self.assertLess(hiss_rms, raw_hiss_rms * 0.15)
        # Voice band (500 Hz) must be well preserved (> 60% amplitude retained)
        self.assertGreater(voice_rms, 600.0)

    def test_spectral_subtraction_suppresses_continuous_noise(self):
        """Continuous stationary noise (fans, AC) must be subtracted by adaptive noise floor tracker."""
        fs = self.sample_rate
        n = self.chunk_samples

        # Simulate stationary continuous AC / fan noise
        np.random.seed(42)
        stationary_noise = np.random.randn(n).astype(np.float32) * 180.0

        # Calibrate noise profile over several ambient frames
        for _ in range(8):
            self.dsp.filter_chunk(stationary_noise, is_speech=False)

        raw_noise_rms = float(np.sqrt(np.mean(stationary_noise ** 2)))
        _, clean_noise_rms, _ = self.dsp.filter_chunk(stationary_noise, is_speech=False)

        # Spectral subtraction & noise gate must reduce stationary noise by at least 12 dB (> 70% reduction)
        self.assertLess(clean_noise_rms, raw_noise_rms * 0.35)

    def test_vocal_harmonic_density_distinguishes_speech_from_claps(self):
        """Autocorrelation harmonic density must be high for vocal phonation, low for impulse pops/claps."""
        fs = self.sample_rate
        n = self.chunk_samples
        t = np.arange(n) / fs

        # Synthetic human phonation: 140 Hz F0 + harmonics
        voice_signal = (
            np.sin(2 * np.pi * 140 * t) +
            0.6 * np.sin(2 * np.pi * 280 * t) +
            0.4 * np.sin(2 * np.pi * 420 * t)
        ).astype(np.float32) * 1000.0

        # Transient clap/pop: brief impulse burst
        clap_signal = np.zeros(n, dtype=np.float32)
        clap_signal[200:240] = np.random.randn(40).astype(np.float32) * 3500.0

        # Diffuse white room noise
        diffuse_noise = np.random.randn(n).astype(np.float32) * 400.0

        voice_density = self.dsp.calc_harmonic_density(voice_signal)
        clap_density = self.dsp.calc_harmonic_density(clap_signal)
        diffuse_density = self.dsp.calc_harmonic_density(diffuse_noise)

        self.assertGreater(voice_density, 0.40)
        self.assertLess(clap_density, 0.15)
        self.assertLess(diffuse_density, 0.15)

    def test_near_field_speech_energy_barrier_and_duration_check(self):
        """Speech activation must require energy crossing near-field barrier and minimum duration."""
        recognizer = NativeSpeechRecognizer.__new__(NativeSpeechRecognizer)
        recognizer.sample_rate = 16000
        recognizer.chunk_duration = 0.08
        recognizer.chunk_size = 2560
        recognizer.dsp = self.dsp
        recognizer.worker = MagicMock()
        recognizer.worker.calibrated = True
        recognizer.worker.drain = MagicMock()
        recognizer.worker.ambient_baseline = 150.0

        # 1. Distant voice below barrier (RMS = 190.0, barrier for baseline 150 is 150*1.65+60 = 307.5)
        t = np.arange(1280) / 16000
        weak_voice = (150 * np.sin(2 * np.pi * 150 * t)).astype(np.int16).tobytes()
        weak_chunk = (weak_voice, 190.0, 0.5)

        calls = [0]
        def fake_weak():
            calls[0] += 1
            if calls[0] <= 4:
                return weak_chunk
            return None

        recognizer.worker.get_chunk.side_effect = fake_weak
        res_weak = recognizer.record_until_finished(max_wait_sec=0.4, silence_threshold_sec=0.2)
        # Should not trigger speech capture
        self.assertEqual(res_weak, "")

        # 2. Transient pop: 1 loud chunk of clap with no vocal harmonics (RMS = 800.0, harmonic density = 0.02)
        clap_pcm = np.zeros(1280, dtype=np.int16)
        clap_pcm[100:150] = 5000
        clap_chunk = (clap_pcm.tobytes(), 800.0, 0.02)

        calls_clap = [0]
        def fake_clap():
            calls_clap[0] += 1
            if calls_clap[0] == 1:
                return clap_chunk
            return None

        recognizer.worker.get_chunk.side_effect = fake_clap
        res_clap = recognizer.record_until_finished(max_wait_sec=0.4, silence_threshold_sec=0.2)
        # Transient pop must be discarded
        self.assertEqual(res_clap, "")


class TestAmbientAndTVRejection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = BrainEngine()

    def test_tv_dialogue_and_commercials_rejected(self):
        """TV dialogue, commercials, and broadcast markers must be flagged as ambient chatter."""
        tv_phrases = [
            "coming up next on channel 4",
            "we will be right back after these messages",
            "stay tuned for breaking news",
            "don't forget to like and subscribe to the channel",
            "previously on the show",
            "touchdown on the replay",
            "اشترك في القناة وفعل الجرس",
            "نشرة الأخبار اليوم",
            "فاصل ونواصل",
        ]
        for phrase in tv_phrases:
            self.assertTrue(
                NativeSpeechRecognizer.is_ambient_chatter(phrase),
                f"Expected '{phrase}' to be rejected as TV/ambient chatter."
            )
            self.assertTrue(
                self.engine.is_ambient_or_chatter(phrase),
                f"Expected engine to reject '{phrase}'."
            )

    def test_household_and_kids_background_chatter_rejected(self):
        """Undirected household chatter (kids talking to parents, family dinner talk) must be rejected."""
        household_phrases = [
            "hey mom where are my shoes",
            "did you do your homework",
            "dinner is ready come eat",
            "stop fighting give me that",
            "look what i drew",
            "يا ماما وين الأكل",
            "تعال هون شو بتعمل",
            "بدنا نتغدا هلا",
        ]
        for phrase in household_phrases:
            self.assertTrue(
                NativeSpeechRecognizer.is_ambient_chatter(phrase),
                f"Expected '{phrase}' to be rejected as household chatter."
            )

    def test_conversational_fillers_rejected(self):
        """Pure mutterings, fillers, and non-action tokens must be rejected."""
        fillers = [
            "yeah right",
            "right yeah",
            "uh huh",
            "mm hmm",
            "cool cool",
            "whatever",
            "haha",
            "ايوه",
            "اممم",
            "ماشي ماشي",
        ]
        for f in fillers:
            self.assertTrue(
                NativeSpeechRecognizer.is_ambient_chatter(f),
                f"Expected '{f}' to be rejected as filler."
            )

    def test_direct_commands_and_ezra_queries_preserved(self):
        """Direct commands and phrases explicitly addressed to Ezra must NEVER be rejected."""
        valid_queries = [
            "Ezra open chrome",
            "open terminal",
            "close spotify",
            "volume 50",
            "what time is it",
            "search for rust documentation",
            "عزرا شو الأخبار",
            "افتحي المتصفح",
            "سكري الآلة الحاسبة",
            "علي الصوت",
        ]
        for q in valid_queries:
            self.assertFalse(
                NativeSpeechRecognizer.is_ambient_chatter(q),
                f"Direct query '{q}' should NOT be rejected."
            )
            self.assertFalse(
                self.engine.is_ambient_or_chatter(q),
                f"Direct query '{q}' should NOT be rejected by engine."
            )

    async def test_brain_engine_think_returns_rejected_for_ambient(self):
        """BrainEngine.think must return rejected=True for ambient TV/chatter without executing tools."""
        res = await self.engine.think("coming up next on channel 4 news")
        self.assertTrue(res.get("rejected"))
        self.assertEqual(res.get("speech_text"), "")
        self.assertEqual(res.get("tool_calls"), [])


class TestSpeakerBiometricsNearFieldGating(unittest.TestCase):
    def setUp(self):
        self.biometrics = VoiceBiometrics()
        self.patcher_save = patch.object(self.biometrics, "save_profile")
        self.patcher_save.start()

    def tearDown(self):
        self.patcher_save.stop()
        self.biometrics.load_profile()

    def test_is_near_field_detects_near_versus_distant_sound(self):
        """is_near_field must differentiate close microphone speech from distant room audio."""
        fs = 16000
        t = np.arange(fs * 0.8) / fs

        # 1. Near-field speaker: loud direct audio (RMS ~850), 125 Hz fundamental + proximity bass boost
        near_voice = (800 * np.sin(2 * np.pi * 125 * t) + 400 * np.sin(2 * np.pi * 250 * t)).astype(np.int16).tobytes()

        # 2. Distant room audio: attenuated audio (RMS ~110), diffused spectral balance
        far_audio = (120 * np.sin(2 * np.pi * 300 * t) + np.random.randn(len(t)) * 50).astype(np.int16).tobytes()

        is_near_1, score_1, _ = self.biometrics.is_near_field(near_voice)
        is_near_2, score_2, _ = self.biometrics.is_near_field(far_audio)

        self.assertTrue(is_near_1)
        self.assertGreaterEqual(score_1, 0.40)

        self.assertFalse(is_near_2)
        self.assertLess(score_2, 0.35)

    def test_verify_turn_rejects_far_field_as_guest(self):
        """verify_turn must assign TIER_GUEST to distant sound sources failing near-field barrier."""
        fs = 16000
        t = np.arange(fs * 0.8) / fs
        far_pcm = (100 * np.sin(2 * np.pi * 200 * t)).astype(np.int16).tobytes()

        tier, score, detail = self.biometrics.verify_turn(far_pcm, "some background text")
        self.assertEqual(tier, TIER_GUEST)
        self.assertIn("distant_background_voice", detail)

    def test_verify_turn_differentiates_high_pitch_kids_from_enrolled_master(self):
        """Enrolled master with low pitch must reject high-pitched kid voices (280-350 Hz)."""
        fs = 16000
        t = np.arange(fs * 0.8) / fs

        # Enroll master with adult pitch (120 Hz)
        adult_pcm = (900 * np.sin(2 * np.pi * 120 * t) + 400 * np.sin(2 * np.pi * 240 * t)).astype(np.int16).tobytes()
        self.biometrics.enroll(pcm_data=adult_pcm, user_name="Ahmad")
        self.assertTrue(self.biometrics.is_enrolled())

        # Test kid shouting (320 Hz fundamental)
        kid_pcm = (850 * np.sin(2 * np.pi * 320 * t) + 400 * np.sin(2 * np.pi * 640 * t)).astype(np.int16).tobytes()
        tier_kid, score_kid, detail_kid = self.biometrics.verify_turn(kid_pcm)

        # Kid voice should not be verified as adult master
        self.assertNotEqual(tier_kid, TIER_VERIFIED)


if __name__ == "__main__":
    unittest.main()
