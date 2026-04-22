#!/usr/bin/env python
"""Test suite for the Game_Surf NPC training pipeline phases."""

import json
import subprocess
import sys
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")
NPC_PROFILES = ROOT / "datasets" / "configs" / "npc_profiles.json"


@dataclass
class PhaseResult:
    phase: str
    passed: bool
    message: str = ""
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


def log(msg: str):
    print(f"  {msg}")


def run_cmd(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def load_profiles() -> dict:
    if not NPC_PROFILES.exists():
        return {}
    data = json.loads(NPC_PROFILES.read_text())
    # Handle both formats: direct dict or {"profiles": {...}}
    if "profiles" in data:
        return data["profiles"]
    return data


def test_gpu_available() -> PhaseResult:
    log("Checking GPU availability...")
    try:
        code, stdout, stderr = run_cmd([
            "python", "-c",
            "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')"
        ])
        if code != 0:
            return PhaseResult("GPU", False, f"Error: {stderr}")

        output = stdout.strip()
        if output == "cuda":
            return PhaseResult("GPU", True, "GPU available", {"device": "cuda"})
        else:
            return PhaseResult("GPU", True, "Using CPU", {"device": "cpu"})
    except Exception as e:
        return PhaseResult("GPU", False, str(e))


def test_environment() -> PhaseResult:
    log("Checking environment...")
    code, stdout, stderr = run_cmd(["conda", "run", "-n", "unsloth_env", "python", "--version"])
    if code == 0:
        return PhaseResult("Environment", True, f"Python: {stdout.strip()}")
    return PhaseResult("Environment", False, f"Error: {stderr[:200]}")


def test_dataset_exists(npc_id: str = "marvel_comics_instructor") -> PhaseResult:
    log(f"Checking dataset for {npc_id}...")
    profiles = load_profiles()
    if npc_id not in profiles:
        return PhaseResult("Phase1-Dataset", False, f"NPC {npc_id} not in profiles")

    prof = profiles[npc_id]
    raw_path = ROOT / "datasets" / "personas" / npc_id / f"{prof.get('dataset_name', npc_id)}.jsonl"

    if raw_path.exists():
        count = len(raw_path.read_text().strip().split("\n"))
        return PhaseResult("Phase1-Dataset", True, f"Found {count} examples", {"path": str(raw_path), "count": count})
    else:
        return PhaseResult("Phase1-Dataset", False, f"Not found: {raw_path}")


def test_prepared_dataset(npc_id: str = "marvel_comics_instructor", dataset_name: str = None) -> PhaseResult:
    log(f"Checking prepared dataset for {npc_id}...")
    if dataset_name is None:
        profiles = load_profiles()
        dataset_name = profiles.get(npc_id, {}).get('dataset_name', f"{npc_id}_dataset")

    processed_dir = ROOT / "datasets" / "processed" / dataset_name
    train_file = processed_dir / "train.jsonl"
    val_file = processed_dir / "validation.jsonl"

    results = {"train": False, "validation": False}
    if train_file.exists():
        count = len(train_file.read_text().strip().split("\n"))
        results["train"] = True
        log(f"  train.jsonl: {count} examples")
    if val_file.exists():
        count = len(val_file.read_text().strip().split("\n"))
        results["validation"] = True
        log(f"  validation.jsonl: {count} examples")

    passed = results["train"] and results["validation"]
    msg = "Prepared splits exist" if passed else "Missing splits"
    return PhaseResult("Phase2-Prepare", passed, msg, results)


def test_trained_model(npc_id: str = "marvel_comics_instructor") -> PhaseResult:
    log(f"Checking trained model for {npc_id}...")
    model_dir = ROOT / "exports" / "npc_models" / npc_id
    manifest_path = model_dir / "npc_model_manifest.json"

    if not manifest_path.exists():
        return PhaseResult("Phase3-Training", False, f"No manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    artifacts = manifest.get("artifacts", {})
    adapter_dir = artifacts.get("adapter_dir", "")

    has_adapter = False
    if adapter_dir:
        adapter_dir = ROOT / adapter_dir if not Path(adapter_dir).is_absolute() else Path(adapter_dir)
        has_adapter = adapter_dir.exists() and (adapter_dir / "adapter_model.safetensors").exists()

    if has_adapter:
        return PhaseResult("Phase3-Training", True, f"Found adapter: {adapter_dir.name}", manifest)
    else:
        return PhaseResult("Phase3-Training", False, "No adapter found")


def test_supabase_connection() -> PhaseResult:
    log("Checking Supabase connection...")
    env_path = ROOT / ".env"
    if not env_path.exists():
        return PhaseResult("Supabase", False, ".env not found")

    env_content = env_path.read_text()
    supabase_url = ""
    supabase_key = ""

    for line in env_content.split("\n"):
        if line.startswith("SUPABASE_URL="):
            supabase_url = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("SUPABASE_SERVICE_ROLE_KEY="):
            supabase_key = line.split("=", 1)[1].strip().strip('"')

    if not supabase_url or not supabase_key:
        return PhaseResult("Supabase", False, "Missing credentials")

    if supabase_url == "http://127.0.0.1:16433":
        return PhaseResult("Supabase", True, "Local Supabase", {"url": "local"})

    return PhaseResult("Supabase", True, f"Remote: {supabase_url[:30]}...", {"url": supabase_url[:30]})


def test_npc_profiles() -> PhaseResult:
    log("Checking NPC profiles...")
    if not NPC_PROFILES.exists():
        return PhaseResult("Profiles", False, "npc_profiles.json not found")

    profiles = load_profiles()
    count = len(profiles)
    trained = 0

    for npc_id in profiles:
        manifest_path = ROOT / "exports" / "npc_models" / npc_id / "npc_model_manifest.json"
        if manifest_path.exists():
            trained += 1

    return PhaseResult("Profiles", True, f"{count} NPCs, {trained} trained", {"total": count, "trained": trained})


def test_server_health() -> PhaseResult:
    log("Checking integrated server health...")
    try:
        import requests
        resp = requests.get("http://127.0.0.1:8000/health", timeout=5)
        if resp.status_code == 200:
            return PhaseResult("Server", True, "Server running", resp.json())
        return PhaseResult("Server", False, f"Status: {resp.status_code}")
    except Exception as e:
        return PhaseResult("Server", False, str(e))


def test_chat_interface() -> PhaseResult:
    log("Checking chat interface...")
    html_path = ROOT / "chat_interface.html"
    if not html_path.exists():
        return PhaseResult("ChatUI", False, "Not found")

    content = html_path.read_text()
    if "maestro_jazz_instructor" in content:
        return PhaseResult("ChatUI", True, "Interface available")
    return PhaseResult("ChatUI", False, "Missing NPCs")


def run_dry_pipeline(npc_id: str = "marvel_comics_instructor") -> PhaseResult:
    log(f"Running dry-run for {npc_id}...")
    code, stdout, stderr = run_cmd([
        "python", "scripts/run_full_npc_pipeline.py",
        "--npc", npc_id,
        "--skip-generation",
        "--skip-prep",
        "--skip-training",
        "--skip-sync",
        "--skip-eval",
    ], timeout=30)

    output = stdout + stderr
    if "NPC Pipeline Contract" in output:
        return PhaseResult("DryRun", True, "Pipeline resolves correctly", {"stdout": output[:500]})
    else:
        return PhaseResult("DryRun", False, "Error resolving NPC", {"stderr": stderr[:200]})


def test_pipeline_diagnostic(npc_id: str = "marvel_comics_instructor") -> PhaseResult:
    log(f"Running full diagnostic for {npc_id}...")
    results = {
        "dataset_raw": False,
        "dataset_processed": False,
        "model_trained": False,
    }

    profiles = load_profiles()
    if npc_id not in profiles:
        return PhaseResult("Diagnostic", False, f"NPC {npc_id} not found")

    prof = profiles[npc_id]
    dataset_name = prof.get("dataset_name", f"{npc_id}_dataset")

    raw_path = ROOT / "datasets" / "personas" / npc_id / f"{dataset_name}.jsonl"
    if raw_path.exists():
        results["dataset_raw"] = True

    processed_dir = ROOT / "datasets" / "processed" / dataset_name
    if (processed_dir / "train.jsonl").exists():
        results["dataset_processed"] = True

    model_dir = ROOT / "exports" / "npc_models" / npc_id
    if (model_dir / "npc_model_manifest.json").exists():
        manifest = json.loads((model_dir / "npc_model_manifest.json").read_text())
        if manifest.get("artifacts", {}).get("adapter_dir"):
            results["model_trained"] = True

    passed = results["dataset_raw"] and results["dataset_processed"] and results["model_trained"]
    return PhaseResult(
        "Diagnostic",
        passed,
        f"Ready: raw={results['dataset_raw']}, prepared={results['dataset_processed']}, trained={results['model_trained']}",
        results
    )


def run_all():
    print("=" * 60)
    print("Game_Surf Pipeline Test Suite")
    print("=" * 60)

    results: list[PhaseResult] = []

    tests = [
        ("Environment", test_environment),
        ("GPU", test_gpu_available),
        ("NPC Profiles", test_npc_profiles),
        ("Phase1: Dataset Exists", lambda: test_dataset_exists()),
        ("Phase2: Prepared Dataset", lambda: test_prepared_dataset()),
        ("Phase3: Trained Model", lambda: test_trained_model()),
        ("Supabase", test_supabase_connection),
        ("Server", test_server_health),
        ("Chat Interface", test_chat_interface),
        ("Pipeline Dry-Run", run_dry_pipeline),
        ("Full Diagnostic", lambda: test_pipeline_diagnostic()),
    ]

    for name, test_fn in tests:
        try:
            result = test_fn()
            icon = "✓" if result.passed else "✗"
            print(f"\n[{icon}] {name}: {result.message}")
            results.append(result)
        except Exception as e:
            print(f"\n[✗] {name}: EXCEPTION - {e}")
            results.append(PhaseResult(name, False, str(e)))

    print("\n" + "=" * 60)
    print("Results Summary")
    print("=" * 60)

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    total = len(results)

    print(f"  Total: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.phase}: {r.message}")

    print()
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)