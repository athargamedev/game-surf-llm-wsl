#!/usr/bin/env python
"""Pipeline cleanup utility for Game_Surf NPC training."""

import argparse
import shutil
import sys
from pathlib import Path
import json

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")
NPC_PROFILES = ROOT / "datasets" / "configs" / "npc_profiles.json"


def load_profiles() -> dict:
    if not NPC_PROFILES.exists():
        return {}
    return json.loads(NPC_PROFILES.read_text())


def cleanup_phase(npc_id: str, phase: str, dry_run: bool = False) -> list[str]:
    """Clean up artifacts for a specific phase."""
    profiles = load_profiles()
    actions = []

    if npc_id not in profiles:
        print(f"ERROR: NPC {npc_id} not found in profiles")
        return actions

    prof = profiles[npc_id]
    dataset_name = prof.get("dataset_name", f"{npc_id}_dataset")

    if phase in ["raw", "all"]:
        raw_path = ROOT / "datasets" / "personas" / npc_id / f"{dataset_name}.jsonl"
        if raw_path.exists():
            actions.append(f"Delete raw dataset: {raw_path}")
            if not dry_run:
                raw_path.unlink()

    if phase in ["prepared", "all"]:
        processed_dir = ROOT / "datasets" / "processed" / dataset_name
        if processed_dir.exists():
            actions.append(f"Delete prepared dataset: {processed_dir}")
            if not dry_run:
                shutil.rmtree(processed_dir)

    if phase in ["trained", "all"]:
        model_dir = ROOT / "exports" / "npc_models" / npc_id
        if model_dir.exists():
            actions.append(f"Delete trained model: {model_dir}")
            if not dry_run:
                shutil.rmtree(model_dir)

    if phase in ["chat", "all"]:
        html = ROOT / "chat_interface.html"
        if html.exists():
            content = html.read_text()
            if npc_id in content:
                actions.append(f"WARNING: NPC {npc_id} still in chat_interface.html - remove manually")

    return actions


def cleanup_all(npc_id: str, dry_run: bool = False) -> list[str]:
    """Clean up all artifacts for an NPC."""
    return cleanup_phase(npc_id, "all", dry_run)


def cleanup_cache(dry_run: bool = False) -> list[str]:
    """Clean up common cache directories."""
    actions = []

    cache_dirs = [
        ROOT / ".cache",
        ROOT / "datasets" / "processed" / ".cache",
    ]

    for d in cache_dirs:
        if d.exists():
            actions.append(f"Delete cache: {d}")
            if not dry_run:
                shutil.rmtree(d)

    return actions


def main():
    parser = argparse.ArgumentParser(description="Game_Surf Pipeline Cleanup")
    parser.add_argument("--npc", help="NPC ID to clean up")
    parser.add_argument("--phase", choices=["raw", "prepared", "trained", "all", "chat"],
                        help="Phase to clean (default: all)")
    parser.add_argument("--cache", action="store_true", help="Clean cache directories")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")

    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN - No files will be deleted\n")

    if args.cache:
        actions = cleanup_cache(args.dry_run)
        print("Cache cleanup:")
        for a in actions:
            print(f"  {a}")
        if not actions:
            print("  Nothing to clean")
        return

    if not args.npc:
        print("ERROR: --npc required (or use --cache)")
        parser.print_help()
        sys.exit(1)

    phase = args.phase or "all"

    print(f"\nCleaning up {args.npc} (phase: {phase})...\n")

    actions = cleanup_phase(args.npc, phase, args.dry_run)

    for a in actions:
        print(f"  {a}")

    if not actions:
        print("  Nothing to clean")

    if args.dry_run:
        print("\n(Run without --dry-run to actually delete)")


if __name__ == "__main__":
    main()