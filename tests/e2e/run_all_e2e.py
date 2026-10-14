#!/usr/bin/env python3
"""
Unified E2E Test Runner for Project Ezra Overhaul.

Executes and reports on the 4-tier systematic opaque-box E2E test suite:
  - Tier 1: Feature Coverage (>=5 test cases per feature for R1, R2, R3)
  - Tier 2: Boundary & Corner Cases (empty inputs, extreme lengths, 1.0s-1.5s pause, acoustic saturation, invalid app targets)
  - Tier 3: Cross-Feature Interactions (barge-in during TTS, STT driving app launch, UI state broadcast)
  - Tier 4: Real-World Conversational Scenarios (multi-turn British dialogues, Arabic queries, desktop app actions)

Usage:
  python tests/e2e/run_all_e2e.py [--tier {1,2,3,4,all}] [-v]
"""

import os
import sys
import time
import argparse
import unittest
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tier module mapping
TIER_MODULES = {
    1: ("Tier 1: Feature Coverage (R1, R2, R3)", "tests.e2e.test_tier1_features"),
    2: ("Tier 2: Boundary & Corner Cases", "tests.e2e.test_tier2_boundaries"),
    3: ("Tier 3: Cross-Feature Interactions", "tests.e2e.test_tier3_interactions"),
    4: ("Tier 4: Real-World Conversational Scenarios", "tests.e2e.test_tier4_scenarios"),
}


def run_tier(tier_num: int, title: str, module_name: str, verbosity: int = 2) -> unittest.TestResult:
    """Loads and executes a specific test tier module."""
    print(f"\n\033[1;36m{'=' * 75}\033[0m")
    print(f"\033[1;36m▶ EXECUTING: {title}\033[0m")
    print(f"\033[1;36m{'=' * 75}\033[0m")

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(module_name)
    runner = unittest.TextTestRunner(verbosity=verbosity)
    start_time = time.time()
    result = runner.run(suite)
    duration = time.time() - start_time

    status = "\033[1;32mPASSED\033[0m" if result.wasSuccessful() else "\033[1;31mFAILED\033[0m"
    print(f"[{status}] {title} — Ran {result.testsRun} tests in {duration:.3f}s")
    return result


def main():
    parser = argparse.ArgumentParser(description="Project Ezra Unified E2E Test Runner")
    parser.add_argument(
        "--tier",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "all"],
        help="Specify which tier to run (default: all)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=2,
        help="Verbosity level (default: 2)"
    )
    args = parser.parse_args()

    print("\033[1;35m")
    print("╔═══════════════════════════════════════════════════════════════════════════╗")
    print("║               PROJECT EZRA // 4-TIER E2E TEST RUNNER                      ║")
    print("║       Systematic Opaque-Box Audio, VAD, STT & Action Verification        ║")
    print("╚═══════════════════════════════════════════════════════════════════════════╝")
    print("\033[0m")

    tiers_to_run = [1, 2, 3, 4] if args.tier == "all" else [int(args.tier)]
    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    tier_summaries = []

    # Warm-up / settle background neural model loaders
    try:
        from jarvis.voice.speaker import voice_speaker
        if hasattr(voice_speaker, "local_tts"):
            deadline = time.time() + 3.0
            while not voice_speaker.local_tts.is_available() and time.time() < deadline:
                time.sleep(0.1)
    except Exception:
        pass

    overall_start = time.time()

    for t_num in tiers_to_run:
        title, mod_name = TIER_MODULES[t_num]
        res = run_tier(t_num, title, mod_name, verbosity=args.verbose)
        total_tests += res.testsRun
        total_failures += len(res.failures)
        total_errors += len(res.errors)
        total_skipped += len(res.skipped)
        tier_summaries.append((t_num, title, res.testsRun, len(res.failures), len(res.errors)))

    overall_duration = time.time() - overall_start

    print("\n\033[1;33m" + "=" * 75)
    print("E2E TEST EXECUTION SUMMARY REPORT")
    print("=" * 75 + "\033[0m")

    for t_num, title, count, fails, errs in tier_summaries:
        tier_status = "\033[1;32m[PASS]\033[0m" if (fails == 0 and errs == 0) else "\033[1;31m[FAIL]\033[0m"
        print(f"  {tier_status} Tier {t_num}: {count} tests run, {fails} failures, {errs} errors")

    print("-" * 75)
    total_status = "\033[1;32mALL E2E TESTS PASSED CLEANLY\033[0m" if (total_failures == 0 and total_errors == 0) else "\033[1;31mSOME TESTS FAILED\033[0m"
    print(f"Outcome: {total_status}")
    print(f"Total Tests Run: {total_tests}")
    print(f"Total Failures:  {total_failures}")
    print(f"Total Errors:    {total_errors}")
    print(f"Total Skipped:   {total_skipped}")
    print(f"Total Time:      {overall_duration:.3f}s")
    print("=" * 75 + "\n")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if (total_failures == 0 and total_errors == 0) else 1)


if __name__ == "__main__":
    main()
