from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT_DIR / "datasets" / "configs" / "npc_profiles.json"


@dataclass(frozen=True)
class NpcPipelineSpec:
    npc_key: str
    display_name: str
    npc_scope: str
    subject: str
    artifact_key: str
    dataset_name: str
    supabase_npc_id: str
    raw_dataset_path: Path
    processed_dir: Path
    output_dir: Path
    manifest_path: Path


def load_npc_profiles(path: Path = PROFILES_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"NPC profiles not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("profiles", {})


def to_project_relative(path: Path | None, root_dir: Path = ROOT_DIR) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve_npc_spec(npc_key: str, root_dir: Path = ROOT_DIR) -> NpcPipelineSpec:
    profiles = load_npc_profiles(root_dir / "datasets" / "configs" / "npc_profiles.json")
    profile = profiles.get(npc_key)
    if profile is None:
        known = ", ".join(sorted(profiles))
        raise KeyError(f"Unknown NPC key '{npc_key}'. Known profiles: {known}")

    artifact_key = profile.get("artifact_key") or npc_key
    dataset_name = profile.get("dataset_name") or f"{artifact_key}_dataset"
    supabase_npc_id = profile.get("supabase_npc_id") or npc_key
    output_dir = root_dir / "exports" / "npc_models" / artifact_key

    return NpcPipelineSpec(
        npc_key=npc_key,
        display_name=profile.get("display_name", npc_key),
        npc_scope=profile.get("npc_scope", "world"),
        subject=profile.get("subject", ""),
        artifact_key=artifact_key,
        dataset_name=dataset_name,
        supabase_npc_id=supabase_npc_id,
        raw_dataset_path=root_dir / "datasets" / "personas" / artifact_key / f"{dataset_name}.jsonl",
        processed_dir=root_dir / "datasets" / "processed" / dataset_name,
        output_dir=output_dir,
        manifest_path=output_dir / "npc_model_manifest.json",
    )


def build_model_manifest(
    spec: NpcPipelineSpec,
    *,
    base_model: str,
    version: str = "1.0.0",
    target_generation_count: int | None = None,
    quality_threshold: float | None = None,
    val_split: float | None = None,
    epochs: int | float | None = None,
    learning_rate: float | None = None,
    lora_r: int | None = None,
    lora_alpha: int | None = None,
    use_rslora: bool | None = None,
    save_gguf: str | None = None,
    sync_to_unity: bool | None = None,
    train_file: Path | None = None,
    val_file: Path | None = None,
    output_dir: Path | None = None,
    adapter_dir: Path | None = None,
    gguf_path: Path | None = None,
) -> dict[str, Any]:
    effective_output_dir = output_dir or spec.output_dir
    runtime_lora_path = adapter_dir / "adapter_model.gguf" if adapter_dir and (adapter_dir / "adapter_model.gguf").exists() else None
    return {
        "npc_key": spec.npc_key,
        "artifact_key": spec.artifact_key,
        "dataset_name": spec.dataset_name,
        "supabase_npc_id": spec.supabase_npc_id,
        "version": version,
        "base_model": base_model,
        "dataset": {
            "target_generation_count": target_generation_count,
            "quality_threshold": quality_threshold,
            "val_split": val_split,
            "raw_dataset_path": str(spec.raw_dataset_path),
            "processed_dir": str(spec.processed_dir),
            "train_file": str(train_file) if train_file else None,
            "val_file": str(val_file) if val_file else None,
        },
        "training": {
            "epochs": epochs,
            "learning_rate": learning_rate,
            "lora_r": lora_r,
            "lora_alpha": lora_alpha,
            "use_rslora": use_rslora,
        },
        "export": {
            "save_gguf": save_gguf,
            "sync_to_unity": sync_to_unity,
        },
        "artifacts": {
            "output_dir": to_project_relative(effective_output_dir),
            "adapter_dir": to_project_relative(adapter_dir) if adapter_dir else None,
            "gguf_path": to_project_relative(gguf_path) if gguf_path else None,
        },
        "runtime": {
            "base_model_path": to_project_relative(ROOT_DIR / "exports" / "training_test_export" / "gguf_gguf" / "llama-3.2-3b-instruct.Q4_K_M.gguf"),
            "lora_adapter_path": to_project_relative(runtime_lora_path),
            "relay_model_path": to_project_relative(gguf_path) if gguf_path else None,
            "unity_model_name": f"LLM/models/{Path(gguf_path).name}" if gguf_path and gguf_path.suffix == ".gguf" else None,
            "unity_lora_name": f"LLM/loras/{spec.artifact_key}/adapter_model.safetensors" if adapter_dir else None,
        },
        "profile": {
            "display_name": spec.display_name,
            "npc_scope": spec.npc_scope,
            "subject": spec.subject,
        },
    }


def write_model_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def spec_to_dict(spec: NpcPipelineSpec) -> dict[str, Any]:
    data = asdict(spec)
    for key, value in list(data.items()):
        if isinstance(value, Path):
            data[key] = str(value)
    return data
