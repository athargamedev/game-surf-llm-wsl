#!/usr/bin/env python
"""
Setup & Verify the NPC Dataset Generation Environment

Checks and installs:
  1. notebooklm-mcp-cli (for NotebookLM research)
  2. Local LLM server connectivity (LM Studio)
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
    "datasets/world",
    "datasets/personas",
    "datasets/processed",
    "datasets/evals",
    "research",
    "exports",
]


def check_notebooklm_cli() -> bool:
    """Check if notebooklm-mcp-cli is installed."""
    try:
        result = subprocess.run(
            ["nlm", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  [OK] notebooklm-mcp-cli: {version}")
            return True
        else:
            print(f"  [X] nlm found but returned error: {result.stderr.strip()[:100]}")
            return False
    except FileNotFoundError:
        print("  [X] notebooklm-mcp-cli: NOT INSTALLED")
        print("    Install: uv tool install notebooklm-mcp-cli")
        print("    Or:      pip install notebooklm-mcp-cli")
        return False
    except subprocess.TimeoutExpired:
        print("  [X] nlm: timed out")
        return False


def check_nlm_auth() -> bool:
    """Check if NotebookLM authentication is set up."""
    try:
        result = subprocess.run(
            ["nlm", "notebook", "list"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print("  [OK] NotebookLM authentication: OK")
            return True
        else:
            print("  [X] NotebookLM authentication: FAILED")
            print(f"    Run: nlm login")
            return False
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [X] Cannot check NotebookLM auth (nlm not available)")
        return False


def check_local_llm(url: str = "http://127.0.0.1:1234") -> bool:
    """Check if local LLM server is reachable."""
    try:
        req = request.Request(f"{url}/v1/models", method="GET")
        with request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data", [])
        if models:
            model_name = models[0].get("id", "unknown")
            print(f"  [OK] Local LLM server: {url}")
            print(f"    Model loaded: {model_name}")
            return True
        else:
            print(f"  [!!] Local LLM server responds but no model loaded")
            return False
    except Exception:
        print(f"  [X] Local LLM server: NOT RUNNING at {url}")
        print(f"    Start LM Studio and load a model, or run llama.cpp server")
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
    """Attempt to install notebooklm-mcp-cli."""
    print("\nInstalling notebooklm-mcp-cli...")

    # Try uv first, then pip
    for cmd in [
        ["uv", "tool", "install", "notebooklm-mcp-cli"],
        [sys.executable, "-m", "pip", "install", "notebooklm-mcp-cli"],
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
    print("    uv tool install notebooklm-mcp-cli")
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
    parser.add_argument(
        "--llm-url",
        default="http://127.0.0.1:1234",
        help="Local LLM server URL",
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

    print("\n--- NotebookLM MCP CLI ---")
    results["nlm_cli"] = check_notebooklm_cli()
    if not results["nlm_cli"] and args.install:
        results["nlm_cli"] = install_notebooklm_cli()

    if results["nlm_cli"]:
        print("\n--- NotebookLM Authentication ---")
        results["nlm_auth"] = check_nlm_auth()
    else:
        results["nlm_auth"] = False

    print("\n--- Local LLM Server ---")
    results["local_llm"] = check_local_llm(args.llm_url)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_core_ok = results["dirs"] and results["profiles"] and results["schema"]
    nlm_ok = results["nlm_cli"] and results["nlm_auth"]
    local_ok = results["local_llm"]

    if all_core_ok and (nlm_ok or local_ok):
        print("[OK] Ready for dataset generation!")
        if nlm_ok:
            print("  Backend: NotebookLM (primary) + Local LLM (generation)")
        elif local_ok:
            print("  Backend: Local LLM only (NotebookLM not configured)")
        print("\nNext step:")
        print("  python scripts\\generate_npc_dataset.py --npc kai_instructor --dry-run")
    elif all_core_ok:
        print("⚠ Core config OK, but no research backend available")
        if not nlm_ok:
            print("  -> Install nlm: uv tool install notebooklm-mcp-cli && nlm login")
        if not local_ok:
            print(f"  -> Start LM Studio at {args.llm_url}")
    else:
        print("[X] Missing core configuration. See errors above.")


if __name__ == "__main__":
    main()
