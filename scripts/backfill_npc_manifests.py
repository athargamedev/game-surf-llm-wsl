from __future__ import annotations

import argparse
import json
from pathlib import Path

from npc_pipeline_contract import build_model_manifest, load_npc_profiles, resolve_npc_spec, write_model_manifest


ROOT_DIR = Path(__file__).resolve().parents[1]
EXPORTS_DIR = ROOT_DIR / "exports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill NPC model manifests for legacy export folders.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing manifest files.")
    return parser.parse_args()


def load_run_config(export_dir: Path) -> dict:
    run_config_path = export_dir / "run_config.json"
    if not run_config_path.exists():
        return {}
    return json.loads(run_config_path.read_text(encoding="utf-8"))


def infer_spec(export_dir: Path, run_config: dict):
    if run_config.get("npc_key"):
        return resolve_npc_spec(run_config["npc_key"])

    profiles = load_npc_profiles()
    dataset_name = run_config.get("dataset_name")
    datasets = run_config.get("datasets") or []
    candidates = [dataset_name, *datasets, export_dir.name]

    for npc_key in profiles:
        spec = resolve_npc_spec(npc_key)
        if spec.dataset_name in candidates or spec.artifact_key in candidates or spec.npc_key in candidates:
            return spec
    return None


def find_gguf_path(export_dir: Path) -> Path | None:
    gguf_files = [
        path for path in export_dir.rglob("*.gguf")
        if "checkpoint" not in path.as_posix().lower()
    ]
    if not gguf_files:
        return None
    gguf_files.sort(key=lambda path: len(path.parts))
    return gguf_files[0]


def main() -> int:
    args = parse_args()
    export_dirs = [path for path in EXPORTS_DIR.iterdir() if path.is_dir()]
    created = 0

    for export_dir in sorted(export_dirs):
        run_config = load_run_config(export_dir)
        if not run_config:
            continue

        manifest_path = export_dir / "npc_model_manifest.json"
        if manifest_path.exists() and not args.overwrite:
            continue

        spec = infer_spec(export_dir, run_config)
        if spec is None:
            print(f"Skipping {export_dir.name}: could not infer NPC mapping")
            continue

        adapter_dir = export_dir / "lora_adapter"
        gguf_path = find_gguf_path(export_dir)

        manifest = build_model_manifest(
            spec,
            base_model=run_config.get("model_name", "unknown"),
            target_generation_count=run_config.get("dataset_target_count"),
            quality_threshold=run_config.get("prepared_quality_threshold", run_config.get("quality_threshold")),
            val_split=run_config.get("prepared_val_split", run_config.get("val_split")),
            epochs=run_config.get("num_train_epochs") or run_config.get("max_steps"),
            learning_rate=run_config.get("learning_rate"),
            lora_r=run_config.get("lora_r"),
            lora_alpha=run_config.get("lora_alpha"),
            use_rslora=run_config.get("use_rslora"),
            save_gguf=run_config.get("save_gguf"),
            sync_to_unity=None,
            train_file=Path(run_config["train_file"]) if run_config.get("train_file") else None,
            val_file=Path(run_config["val_file"]) if run_config.get("val_file") else None,
            output_dir=export_dir,
            adapter_dir=adapter_dir if adapter_dir.exists() else None,
            gguf_path=gguf_path,
        )
        write_model_manifest(manifest_path, manifest)
        created += 1
        print(f"Backfilled manifest for {spec.npc_key}: {manifest_path}")

    print(f"Created {created} manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
