#!/usr/bin/env python
"""Run all Game_Surf test suites and generate a combined report."""

import subprocess
import sys
import json
import os
from pathlib import Path
from datetime import datetime

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")


def run_test(test_module: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run a test module, return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + ":" + env.get("PYTHONPATH", "")
    result = subprocess.run(
        ["python", f"tests/{test_module}.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    print("=" * 60)
    print("Game_Surf Complete Test Suite")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    results = {}

    test_suites = [
        ("Server Tests", "test_server", 60),
        ("Pipeline Tests", "test_pipeline", 120),
    ]

    total_passed = 0
    total_failed = 0

    for name, module, timeout in test_suites:
        print(f"\n{'=' * 50}")
        print(f"Running: {name}")
        print(f"{'=' * 50}")

        code, stdout, stderr = run_test(module, timeout)
        output = stdout + stderr

        passed = "PASS" if code == 0 else "FAIL"
        results[name] = {"passed": code == 0, "output": output[:2000]}

        if code == 0:
            total_passed += 1
            print(f"  [{passed}] {name}")
        else:
            total_failed += 1
            print(f"  [{passed}] {name}")
            print(f"  Output: {output[:500]}")

    print("\n" + "=" * 60)
    print("Combined Results Summary")
    print("=" * 60)

    print(f"  Suites Run: {len(test_suites)}")
    print(f"  Passed: {total_passed}")
    print(f"  Failed: {total_failed}")

    if total_failed > 0:
        print("\nFailed suites:")
        for name, result in results.items():
            if not result["passed"]:
                print(f"  - {name}")

    print(f"\nCompleted: {datetime.now().isoformat()}")

    if total_failed > 0:
        print("\nNOTE: To run chat interface tests, you need Playwright installed:")
        print("  pip install playwright && playwright install chromium")
        print("  python tests/test_chat_interface.py")

    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    success = main()
    sys.exit(success)