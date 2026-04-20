from __future__ import annotations

import argparse
import shutil
from pathlib import Path

TOOLS_LLM_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
UNITY_STREAMING_ASSETS = WORKSPACE_ROOT / "Assets" / "StreamingAssets" / "LLM"
DEFAULT_MODEL_SOURCE = Path("exports") / "gguf"
DEFAULT_LORA_SOURCE = Path("exports") / "lora_adapter"

MODEL_TARGET_DIR = UNITY_STREAMING_ASSETS / "models"
LORA_TARGET_DIR = UNITY_STREAMING_ASSETS / "loras"
MANIFEST_TARGET_DIR = UNITY_STREAMING_ASSETS / "manifests"

MODEL_EXTENSIONS = {".gguf", ".bin", ".safetensors", ".pth"}
LORA_EXTENSIONS = {".safetensors", ".pt", ".ckpt"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync exported LLM runtime artifacts into Unity StreamingAssets for local game runtime.")
    parser.add_argument(
        "--models", type=Path, default=DEFAULT_MODEL_SOURCE,
        help="Source directory containing exported model files (default: Tools/LLM/exports/gguf)")
    parser.add_argument(
        "--loras", type=Path, default=DEFAULT_LORA_SOURCE,
        help="Source directory containing exported LoRA adapter folders (default: Tools/LLM/exports/lora_adapter)")
    parser.add_argument(
        "--lora-name", type=str, default=None,
        help="Target adapter folder name when --loras points to a single adapter directory.")
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="Optional NPC model manifest JSON to publish alongside runtime assets.")
    parser.add_argument(
        "--target", type=Path, default=UNITY_STREAMING_ASSETS,
        help="Target Unity StreamingAssets folder for runtime LLM assets (default: Assets/StreamingAssets/LLM)")
    parser.add_argument(
        "--clean", action="store_true",
        help="Delete existing runtime LLM publish folders before copying.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be copied without modifying files.")
    return parser.parse_args()


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_files(source: Path, target: Path, extensions: set[str], dry_run: bool = False) -> list[Path]:
    copied = []
    if not source.exists():
        return copied

    ensure_directory(target)
    for source_file in sorted(source.rglob("*")):
        if source_file.is_file() and source_file.suffix.lower() in extensions:
            relative_path = source_file.relative_to(source)
            destination = target / relative_path
            ensure_directory(destination.parent)
            if dry_run:
                print(f"Would copy: {source_file} -> {destination}")
            else:
                shutil.copy2(source_file, destination)
            copied.append(destination)
    return copied


def copy_lora_folders(source: Path, target: Path, dry_run: bool = False) -> list[Path]:
    copied = []
    if not source.exists():
        return copied

    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        adapter_name = folder.name
        destination = target / adapter_name
        if dry_run:
            print(f"Would sync LoRA folder: {folder} -> {destination}")
        else:
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(folder, destination)
        copied.append(destination)
    return copied


def source_is_single_lora_adapter(source: Path) -> bool:
    if not source.exists() or not source.is_dir():
        return False
    return any(
        file.is_file() and file.suffix.lower() in LORA_EXTENSIONS
        for file in source.rglob("*")
    )


def copy_single_lora_folder(
    source: Path,
    target: Path,
    adapter_name: str,
    dry_run: bool = False,
) -> list[Path]:
    copied = []
    if not source.exists():
        return copied

    destination = target / adapter_name
    if dry_run:
        print(f"Would sync LoRA folder: {source} -> {destination}")
    else:
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    copied.append(destination)
    return copied


def copy_manifest_file(source: Path | None, target: Path, dry_run: bool = False) -> Path | None:
    if source is None or not source.exists():
        return None
    ensure_directory(target)
    destination = target / source.name
    if dry_run:
        print(f"Would copy manifest: {source} -> {destination}")
    else:
        shutil.copy2(source, destination)
    return destination


def preview_lora_files(source: Path, target: Path, adapter_name: str | None = None) -> list[Path]:
    if not source.exists():
        return []

    files: list[Path] = []
    if source_is_single_lora_adapter(source):
        destination_root = target / (adapter_name or source.name)
        for file in sorted(source.rglob("*")):
            if file.is_file() and file.suffix.lower() in LORA_EXTENSIONS:
                files.append(destination_root / file.relative_to(source))
        return files

    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        for file in sorted(folder.rglob("*")):
            if file.is_file() and file.suffix.lower() in LORA_EXTENSIONS:
                files.append(target / folder.name / file.relative_to(folder))
    return files


def find_model_files(target: Path) -> list[Path]:
    if not target.exists():
        return []
    return sorted(p for p in target.glob("**/*") if p.is_file() and p.suffix.lower() in MODEL_EXTENSIONS)


def find_lora_adapter_files(target: Path) -> list[Path]:
    if not target.exists():
        return []
    candidates = []
    for folder in sorted(target.iterdir()):
        if not folder.is_dir():
            continue
        for file in folder.rglob("*"):
            if file.is_file() and file.suffix.lower() in LORA_EXTENSIONS:
                candidates.append(file)
    return sorted(candidates)


def print_summary(models: list[Path], loras: list[Path], target: Path, manifest: Path | None = None) -> None:
    def display_path(path: Path) -> str:
        try:
            return path.relative_to(target).as_posix()
        except ValueError:
            return path.as_posix()

    print("\nPublished LLM runtime artifacts:")
    if models:
        print("  Models:")
        for model in models:
            print(f"    - {display_path(model)}")
    else:
        print("  No model files found.")

    if loras:
        print("  LoRA adapters:")
        for lora in loras:
            print(f"    - {display_path(lora)}")
    else:
        print("  No LoRA adapter files found.")

    if manifest is not None:
        print(f"  Manifest: {display_path(manifest)}")

    if models or loras:
        print("\nRecommended DialogueDefinitionSO names:")
        for model in models:
            print(f"  ModelName: LLM/{display_path(model)}")
        for lora in loras:
            print(f"  LoraName: LLM/{display_path(lora)}")
        print("\nUse paths relative to StreamingAssets. Example values: 'LLM/models/<model>.gguf' and 'LLM/loras/<adapter>/adapter_model.safetensors'.")


def main() -> int:
    args = parse_args()
    source_models = (TOOLS_LLM_ROOT / args.models).resolve() if not args.models.is_absolute() else args.models.resolve()
    source_loras = (TOOLS_LLM_ROOT / args.loras).resolve() if not args.loras.is_absolute() else args.loras.resolve()
    target = (WORKSPACE_ROOT / args.target).resolve() if not args.target.is_absolute() else args.target.resolve()

    if args.clean and not args.dry_run:
        if target.exists():
            shutil.rmtree(target)
        print(f"Deleted existing target folder: {target}")

    if not args.dry_run:
        ensure_directory(target / "models")
        ensure_directory(target / "loras")
        ensure_directory(target / "manifests")

    copied_models = copy_files(source_models, target / "models", MODEL_EXTENSIONS, dry_run=args.dry_run)
    if source_is_single_lora_adapter(source_loras):
        adapter_name = args.lora_name or source_loras.name
        copied_loras = copy_single_lora_folder(
            source_loras,
            target / "loras",
            adapter_name,
            dry_run=args.dry_run,
        )
    else:
        copied_loras = copy_lora_folders(source_loras, target / "loras", dry_run=args.dry_run)
    copied_manifest = copy_manifest_file(
        (TOOLS_LLM_ROOT / args.manifest).resolve() if args.manifest and not args.manifest.is_absolute() else args.manifest,
        target / "manifests",
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        runtime_models = find_model_files(target / "models")
        runtime_loras = find_lora_adapter_files(target / "loras")
    else:
        runtime_models = copied_models
        runtime_loras = preview_lora_files(source_loras, target / "loras", args.lora_name)

    print_summary(runtime_models, runtime_loras, target, copied_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
