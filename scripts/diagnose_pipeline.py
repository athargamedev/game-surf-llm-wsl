#!/usr/bin/env python
"""Pipeline diagnostic tool for Game_Surf NPC training."""

import argparse
import json
import sys
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.npc_pipeline_contract import resolve_npc_spec

NPC_PROFILES = ROOT / "datasets" / "configs" / "npc_profiles.json"


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str = ""
    fix: str = ""


def load_profiles() -> dict:
    if not NPC_PROFILES.exists():
        return {}
    data = json.loads(NPC_PROFILES.read_text())
    return data.get("profiles", data)


def check_gpu() -> CheckResult:
    try:
        result = subprocess.run(
            ["python", "-c", "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')"],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        device = result.stdout.strip()
        if device == "cuda":
            return CheckResult("GPU", True, "GPU available (CUDA)", "")
        return CheckResult("GPU", True, f"Using {device}", "No GPU available - training will be slow")
    except Exception as e:
        return CheckResult("GPU", False, str(e), "Check NVIDIA drivers and CUDA installation")


def check_environment() -> CheckResult:
    result = subprocess.run(
        ["conda", "run", "-n", "unsloth_env", "python", "--version"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode == 0:
        return CheckResult("Environment", True, f"Python {result.stdout.strip()}", "")
    return CheckResult("Environment", False, "unsloth_env not found", "Run: conda env create -f environment.yml")


def check_supabase() -> CheckResult:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return CheckResult("Supabase", False, ".env not found", "Create .env with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

    env_content = env_path.read_text()
    has_url = "SUPABASE_URL=" in env_content
    has_key = "SUPABASE_SERVICE_ROLE_KEY=" in env_content

    if has_url and has_key:
        has_local = "127.0.0.1:16433" in env_content
        if has_local:
            return CheckResult("Supabase", True, "Local Supabase configured", "")
        return CheckResult("Supabase", True, "Remote Supabase configured", "")
    return CheckResult("Supabase", False, "Missing credentials", "Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to .env")


def check_npc(npc_id: str) -> dict[CheckResult]:
    results = {}
    profiles = load_profiles()

    if npc_id not in profiles:
        results["Profile"] = CheckResult("Profile", False, f"NPC {npc_id} not found", "Add to datasets/configs/npc_profiles.json")
        return results

    results["Profile"] = CheckResult("Profile", True, f"Found {npc_id} in profiles", "")

    spec = resolve_npc_spec(npc_id)
    raw_path = spec.raw_dataset_path

    if raw_path.exists():
        count = len(raw_path.read_text().strip().split("\n"))
        results["Raw Dataset"] = CheckResult("Raw Dataset", True, f"{count} examples", "")
    else:
        results["Raw Dataset"] = CheckResult(
            "Raw Dataset", False, f"Not found: {raw_path.name}",
            f"Run: python scripts/generate_npc_dataset.py --npc {npc_id}"
        )

    processed_dir = spec.processed_dir
    train_file = processed_dir / "train.jsonl"
    val_file = processed_dir / "validation.jsonl"

    if train_file.exists() and val_file.exists():
        train_count = len(train_file.read_text().strip().split("\n"))
        val_count = len(val_file.read_text().strip().split("\n"))
        results["Prepared Dataset"] = CheckResult(
            "Prepared Dataset", True,
            f"train={train_count}, val={val_count}",
            ""
        )
    else:
        results["Prepared Dataset"] = CheckResult(
            "Prepared Dataset", False, "Missing splits",
            f"Run: python scripts/prepare_dataset.py --input {raw_path}"
        )

    model_dir = spec.output_dir
    manifest_path = model_dir / "npc_model_manifest.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        artifacts = manifest.get("artifacts", {})
        adapter_dir = artifacts.get("adapter_dir", "")

        if adapter_dir:
            adapter_path = ROOT / adapter_dir if not Path(adapter_dir).is_absolute() else Path(adapter_dir)
            if (adapter_path / "adapter_model.safetensors").exists():
                results["Trained Model"] = CheckResult(
                    "Trained Model", True, f"Found adapter: {adapter_path.name}", ""
                )
            else:
                results["Trained Model"] = CheckResult(
                    "Trained Model", False, "Adapter not found",
                    f"Run: python scripts/train_surf_llama.py --npc-key {npc_id}"
                )
        else:
            results["Trained Model"] = CheckResult(
                "Trained Model", False, "No artifacts in manifest",
                f"Run training for {npc_id}"
            )
    else:
        results["Trained Model"] = CheckResult(
            "Trained Model", False, "No manifest",
            f"Run: python scripts/run_full_npc_pipeline.py --npc {npc_id} --skip-generation"
        )

    chat_html = ROOT / "chat_interface.html"
    if chat_html.exists():
        html_content = chat_html.read_text()
        if npc_id in html_content:
            results["Chat UI"] = CheckResult("Chat UI", True, f"NPC {npc_id} in interface", "")
        else:
            results["Chat UI"] = CheckResult(
                "Chat UI", False, f"NPC {npc_id} not in interface",
                f"Add to chat_interface.html npcNames and data-npc attribute"
            )
    else:
        results["Chat UI"] = CheckResult("Chat UI", False, "chat_interface.html not found", "")

    return results


def check_servers() -> CheckResult:
    try:
        import requests
        resp = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if resp.status_code == 200:
            resp = requests.get("http://127.0.0.1:8000/status", timeout=5)
            data = resp.json()
            model_loaded = data.get("model_loaded", False)
            registry = data.get("npc_model_registry_size", 0)
            return CheckResult(
                "Servers", True,
                f"Running (model={model_loaded}, registry={registry})",
                ""
            )
    except Exception as e:
        return CheckResult(
            "Servers", False,
            "Not running",
            "Run: bash scripts/start_servers.sh"
        )

    try:
        resp = requests.get("http://127.0.0.1:8080/", timeout=5)
        if resp.status_code == 200:
            return CheckResult("Servers", True, "Chat server only running", "Start LLM server: bash scripts/start_servers.sh")
    except Exception:
        pass

    return CheckResult("Servers", False, "Not running", "Run: bash scripts/start_servers.sh")


def diagnose_npc(npc_id: str, verbose: bool = False) -> bool:
    print(f"\n{'=' * 50}")
    print(f"Diagnostic: {npc_id}")
    print(f"{'=' * 50}")

    results = check_npc(npc_id)

    trainable = True
    for name, result in results.items():
        icon = "✓" if result.passed else "✗"
        print(f"\n[{icon}] {name}")
        print(f"    {result.message}")
        if result.fix and verbose:
            print(f"    Fix: {result.fix}")
        if not result.passed:
            trainable = False

    print(f"\n{'=' * 50}")
    if trainable:
        print(f"RESULT: {npc_id} is TRAINEABLE")
    else:
        print(f"RESULT: {npc_id} needs attention")
    print(f"{'=' * 50}")

    return trainable


def diagnose_system(verbose: bool = False) -> bool:
    print(f"\n{'=' * 50}")
    print("System Diagnostic")
    print(f"{'=' * 50}")

    checks = [
        ("GPU", check_gpu),
        ("Environment", check_environment),
        ("Supabase", check_supabase),
        ("Servers", check_servers),
    ]

    all_passed = True
    for name, check_fn in checks:
        result = check_fn()
        icon = "✓" if result.passed else "✗"
        print(f"\n[{icon}] {name}")
        print(f"    {result.message}")
        if result.fix and verbose:
            print(f"    Fix: {result.fix}")
        if not result.passed:
            all_passed = False

    print(f"\n{'=' * 50}")
    print(f"RESULT: {'System ready' if all_passed else 'System needs attention'}")
    print(f"{'=' * 50}")

    return all_passed


def main():
    parser = argparse.ArgumentParser(description="Game_Surf Pipeline Diagnostic")
    parser.add_argument("--npc", help="NPC ID to diagnose (default: system)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show fix suggestions")
    parser.add_argument("--list", action="store_true", help="List all known NPCs")

    args = parser.parse_args()

    if args.list:
        profiles = load_profiles()
        print(f"\nKnown NPCs ({len(profiles)}):")
        for npc_id in sorted(profiles.keys()):
            print(f"  - {npc_id}")
        sys.exit(0)

    if args.npc:
        trainable = diagnose_npc(args.npc, args.verbose)
        sys.exit(0 if trainable else 1)
    else:
        ready = diagnose_system(args.verbose)
        if ready:
            print("\nNote: Run with --npc <id> to check specific NPC")
        sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
