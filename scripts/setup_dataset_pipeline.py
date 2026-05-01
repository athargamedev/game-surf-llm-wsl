#!/usr/bin/env python
"""
Setup & Verify the NPC Dataset Generation Environment

Checks and installs:
  1. notebooklm-py (for NotebookLM research)
  2. WSL-local training/project prerequisites
  3. NPC profile configs
  4. Directory structure

Usage:
    python setup_dataset_pipeline.py          # Full check
    python setup_dataset_pipeline.py --install # Auto-install missing deps
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parents[1]  # Tools/LLM

REQUIRED_DIRS = [
    "configs",
    "datasets/personas",
    "datasets/processed",
    "benchmarks",
    "research",
    "exports",
]


def check_notebooklm_cli() -> bool:
    """Check if notebooklm CLI is installed."""
    try:
        result = subprocess.run(
            ["notebooklm", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  [OK] notebooklm CLI: {version}")
            return True
        else:
            print(f"  [X] notebooklm found but returned error: {result.stderr.strip()[:100]}")
            return False
    except FileNotFoundError:
        print("  [X] notebooklm CLI: NOT INSTALLED")
        print("    Install: pip install notebooklm-py")
        print("    Then run: notebooklm login")
        return False
    except subprocess.TimeoutExpired:
        print("  [X] notebooklm: timed out")
        return False


def check_notebooklm_auth() -> bool:
    """Check if NotebookLM authentication is set up."""
    try:
        result = subprocess.run(
            ["notebooklm", "list"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print("  [OK] NotebookLM authentication: OK")
            return True
        else:
            print("  [X] NotebookLM authentication: FAILED")
            print(f"    Run: notebooklm login")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [X] Cannot check NotebookLM auth (notebooklm not available)")
        return False


def check_legacy_local_llm(url: str = "http://127.0.0.1:1234") -> bool:
    """Check if the optional legacy local generation server is reachable."""
    try:
        req = request.Request(f"{url}/v1/models", method="GET")
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data", [])
        if models:
            model_name = models[0].get("id", "unknown")
            print(f"  [OK] Legacy local generation server: {url}")
            print(f"    Model loaded: {model_name}")
            return True
        else:
            print(f"  [!!] Legacy local generation server responds but no model loaded")
            return False
    except Exception:
        print(f"  [X] Legacy local generation server: NOT RUNNING at {url}")
        print("    This is OK for the canonical NotebookLM -> WSL Unsloth workflow.")
        return False


def check_profiles() -> bool:
    """Check that NPC profiles config exists and is valid."""
    profiles_path = ROOT_DIR / "datasets" / "configs" / "npc_profiles.json"
    if not profiles_path.exists():
        print(f"  [X] NPC profiles: NOT FOUND at {profiles_path}")
        return False

    try:
        data = json.loads(profiles_path.read_text(encoding="utf-8"))
        profiles = data.get("profiles", {})
        print(f"  [OK] NPC profiles: {len(profiles)} profiles loaded")
        for key, p in profiles.items():
            print(f"    - {key}: {p.get('display_name', '?')} ({p.get('npc_scope', '?')})")
        return True
    except Exception as exc:
        print(f"  [X] NPC profiles: PARSE ERROR - {exc}")
        return False


def check_directories() -> bool:
    """Check and create required directory structure."""
    all_ok = True
    for rel_dir in REQUIRED_DIRS:
        dir_path = ROOT_DIR / rel_dir
        if dir_path.exists():
            print(f"  [OK] {rel_dir}/")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  + Created {rel_dir}/")
    return all_ok


def check_dataset_schema() -> bool:
    """Check that the dataset schema exists."""
    schema_path = ROOT_DIR / "datasets" / "processed" / "metadata.json"
    if schema_path.exists():
        print(f"  [OK] Dataset schema: {schema_path.name}")
        return True
    else:
        print(f"  [X] Dataset schema: NOT FOUND at {schema_path}")
        return False


def install_notebooklm_cli() -> bool:
    """Attempt to install notebooklm-py."""
    print("\nInstalling notebooklm-py...")
    
    # Try pip first (notebooklm-py is the correct package name)
    for cmd in [
        [sys.executable, "-m", "pip", "install", "notebooklm-py"],
        ["pip", "install", "notebooklm-py"],
    ]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                print(f"  [OK] Installed via: {' '.join(cmd[:3])}")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    print("  [X] Installation failed. Try manually:")
    print("    pip install notebooklm-py")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Setup & verify NPC dataset generation environment"
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Auto-install missing dependencies",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NPC Dataset Generation — Environment Check")
    print(f"Root: {ROOT_DIR}")
    print("=" * 60)

    results = {}

    print("\n--- Directory Structure ---")
    results["dirs"] = check_directories()

    print("\n--- Configuration Files ---")
    results["profiles"] = check_profiles()
    results["schema"] = check_dataset_schema()

    print("\n--- NotebookLM CLI ---")
    results["notebooklm_cli"] = check_notebooklm_cli()
    if not results["notebooklm_cli"] and args.install:
        results["notebooklm_cli"] = install_notebooklm_cli()

    if results["notebooklm_cli"]:
        print("\n--- NotebookLM Authentication ---")
        results["notebooklm_auth"] = check_notebooklm_auth()
    else:
        results["notebooklm_auth"] = False

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_core_ok = results["dirs"] and results["profiles"] and results["schema"]
    notebooklm_ok = results["notebooklm_cli"] and results["notebooklm_auth"]

    if all_core_ok and notebooklm_ok:
        print("[OK] Ready for dataset generation!")
        print("  Backend: NotebookLM datasets + WSL Unsloth training")
        print("\nNext step:")
        print("  conda run --no-capture-output -n unsloth_env python .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py --help")
    elif all_core_ok:
        print("⚠ Core config OK, but NotebookLM is not ready")
        if not notebooklm_ok:
            print("  -> Install: pip install notebooklm-py && notebooklm login")
    else:
        print("[X] Missing core configuration. See errors above.")


if __name__ == "__main__":
    main()
