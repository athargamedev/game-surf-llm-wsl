import argparse
import json
import subprocess
import sys
from pathlib import Path

from npc_pipeline_contract import resolve_npc_spec

# Force UTF-8 output on Windows so Docker/Unsloth emoji don't crash the pipeline.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


ROOT_DIR = Path(__file__).resolve().parents[1]


def to_workspace_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR.resolve()).as_posix()
    except ValueError:
        return str(path)


def run_command(cmd: list[str], cwd: Path = ROOT_DIR) -> None:
    print(f"\n[{'=' * 50}]")
    print(f"Executing: {' '.join(cmd)}")
    print(f"[{'=' * 50}]\n")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
        process.wait()

        if process.returncode != 0:
            print(f"\n[ERROR] Command failed with exit code {process.returncode}")
            sys.exit(process.returncode)
    except KeyboardInterrupt:
        print("\n[WARN] Job cancelled by user.")
        process.terminate()
        sys.exit(1)



def update_manifest_sync_state(manifest_path: Path, synced: bool) -> None:
    if not manifest_path.exists():
        return

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    export = data.setdefault("export", {})
    export["sync_to_unity"] = synced
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="End-to-end NPC NotebookLM dataset and WSL Unsloth training orchestrator.")
    parser.add_argument("--npc", required=True, help="Registered NPC key (e.g., 'kai_instructor')")
    parser.add_argument("--subject", default="", help="Optional specific subject for dataset generation.")
    parser.add_argument("--target-count", type=int, default=150, help="Number of interactions to generate.")
    parser.add_argument("--skip-generation", action="store_true", help="Skip generation and reuse the existing raw dataset.")
    parser.add_argument("--skip-prep", action="store_true", help="Skip dataset preparation and reuse existing prepared splits.")
    parser.add_argument("--skip-training", action="store_true", help="Skip the Unsloth fine-tuning phase.")
    parser.add_argument("--skip-sync", action="store_true", help="Skip runtime artifact sync to Unity.")
    parser.add_argument("--skip-eval", action="store_true", help="Skip post-training evaluation.")

    parser.add_argument("--quality-threshold", type=float, default=0.75, help="Minimum quality score to keep during preparation.")
    parser.add_argument("--val-split", type=float, default=0.1, help="Validation split ratio during preparation.")
    parser.add_argument("--test-split", type=float, default=0.0, help="Test split ratio during preparation.")
    parser.add_argument("--output-dir", default=None, help="Optional override for the NPC model output directory.")

    parser.add_argument("--model-name", default="unsloth/Llama-3.2-3B-Instruct", help="Base model to use.")
    parser.add_argument("--save-gguf", default="", help="Optional GGUF quantization (e.g. q4_k_m). Empty keeps this run as a LoRA adapter.")
    parser.add_argument("--epochs", type=int, default=2, help="Training epochs.")
    parser.add_argument("--max-steps", default="-1", help="Override epochs with a fixed number of training steps.")
    parser.add_argument("--batch-size", default="1", help="Batch size per device.")
    parser.add_argument("--grad-accum", default="8", help="Gradient accumulation steps.")
    parser.add_argument("--lora-r", default="16", help="LoRA rank.")
    parser.add_argument("--lora-alpha", default="32", help="LoRA alpha.")
    parser.add_argument("--learning-rate", default="2e-4", help="Learning rate.")
    parser.add_argument("--generation-backend", choices=["notebooklm", "local", "auto"], default="auto", help="Research backend for dataset generation.")
    parser.add_argument("--report-path", default=None, help="Markdown research report exported from NotebookLM Deep Research.")
    parser.add_argument("--llm-url", default="http://127.0.0.1:1234", help="Legacy fallback only: OpenAI-compatible generation server URL for synthetic example generation.")
    parser.add_argument("--llm-model", default="local-model", help="Legacy fallback only: model ID loaded in the optional generation server.")
    parser.add_argument("--generation-batch-size", default="1", help="Async generation batch size.")
    parser.add_argument("--skip-research", action="store_true", help="Reuse existing research notes during generation.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Attempt to resume training from the last checkpoint if it exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    spec = resolve_npc_spec(args.npc)
    output_dir = Path(args.output_dir).resolve() if args.output_dir else spec.output_dir
    manifest_path = output_dir / "npc_model_manifest.json"
    train_file = spec.processed_dir / "train.jsonl"
    val_file = spec.processed_dir / "validation.jsonl"

    print("\n>>> NPC Pipeline Contract")
    print(f"NPC key: {spec.npc_key}")
    print(f"Artifact key: {spec.artifact_key}")
    print(f"Dataset name: {spec.dataset_name}")
    print(f"Supabase NPC ID: {spec.supabase_npc_id}")
    print(f"Raw dataset: {spec.raw_dataset_path}")
    print(f"Prepared dataset dir: {spec.processed_dir}")
    print(f"Output dir: {output_dir}")

    if not args.skip_generation:
        print("\n>>> Phase 1: Dataset Generation")
        gen_cmd = [
            "python",
            "scripts/generate_npc_dataset.py",
            "--npc",
            spec.npc_key,
            "--target-count",
            str(args.target_count),
            "--deduplicate",
            "--backend",
            args.generation_backend,
            "--async-batch",
            "--batch-size",
            args.generation_batch_size,
            "--llm-url",
            args.llm_url,
            "--llm-model",
            args.llm_model,
            "--seed",
            "3407",
        ]
        if args.skip_research:
            gen_cmd.append("--skip-research")
        if args.subject:
            gen_cmd.extend(["--subject", args.subject])
        if args.report_path:
            gen_cmd.extend(["--report-path", args.report_path])
        run_command(gen_cmd)
    else:
        print("\n>>> Skipping Phase 1 (Dataset Generation).")

    if not args.skip_prep:
        print("\n>>> Phase 2: Dataset Preparation")
        if not spec.raw_dataset_path.exists():
            raise FileNotFoundError(
                f"Raw dataset not found for {spec.npc_key}: {spec.raw_dataset_path}. "
                "Run generation first or provide the expected dataset file."
            )

        prep_cmd = [
            sys.executable,
            "scripts/prepare_dataset.py",
            "--input",
            str(spec.raw_dataset_path),
            "--output",
            str(spec.processed_dir),
            "--val-split",
            str(args.val_split),
            "--test-split",
            str(args.test_split),
            "--quality-threshold",
            str(args.quality_threshold),
            "--deduplicate",
            "--dedup-by",
            "response",
            "--stratify-by",
            "task_type",
        ]
        run_command(prep_cmd)
    else:
        print("\n>>> Skipping Phase 2 (Dataset Preparation).")

    if not args.skip_training:
        print("\n>>> Phase 3: Native WSL Model Training")
        if not train_file.exists():
            raise FileNotFoundError(
                f"Prepared training file not found: {train_file}. "
                "Run the preparation phase or remove --skip-prep."
            )

        train_cmd = [
            sys.executable,
            "scripts/train_surf_llama.py",
            "--datasets",
            spec.dataset_name,
            "--train-file",
            to_workspace_relative(train_file),
            "--npc-key",
            spec.npc_key,
            "--artifact-key",
            spec.artifact_key,
            "--dataset-name",
            spec.dataset_name,
            "--manifest-path",
            to_workspace_relative(manifest_path),
            "--dataset-target-count",
            str(args.target_count),
            "--prepared-quality-threshold",
            str(args.quality_threshold),
            "--prepared-val-split",
            str(args.val_split),
            "--npc-scope",
            spec.npc_scope,
            "--model-name",
            args.model_name,
            "--output-dir",
            to_workspace_relative(output_dir),
            "--save-gguf",
            args.save_gguf,
            "--num-train-epochs",
            str(args.epochs),
            "--max-steps",
            args.max_steps,
            "--batch-size",
            args.batch_size,
            "--gradient-accumulation-steps",
            args.grad_accum,
            "--learning-rate",
            args.learning_rate,
            "--lora-r",
            args.lora_r,
            "--lora-alpha",
            args.lora_alpha,
            "--use-rslora",
            "--no-cache-data",
        ]
        if val_file.exists():
            train_cmd.extend(["--val-file", to_workspace_relative(val_file)])

        # Auto-resume logic
        if args.resume:
            checkpoints_dir = output_dir / "checkpoints"
            if checkpoints_dir.exists():
                # Find the latest checkpoint folder (sorted by number)
                checkpoint_folders = list(checkpoints_dir.glob("checkpoint-*"))
                if checkpoint_folders:
                    try:
                        latest_checkpoint = sorted(checkpoint_folders, key=lambda x: int(x.name.split("-")[-1]))[-1]
                        # Must be workspace-relative for docker
                        resume_path = to_workspace_relative(latest_checkpoint)
                        print(f"[RECOVER] Found existing checkpoint. Resuming from: {resume_path}")
                        train_cmd.extend(["--resume-from", resume_path])
                    except Exception as e:
                        print(f"[WARNING] Could not parse checkpoint numbers for auto-resume: {e}")

        run_command(train_cmd)
    else:
        print("\n>>> Skipping Phase 3 (Model Training).")

    if not args.skip_sync:
        print("\n>>> Phase 4: Sync Runtime Artifacts to Unity")
        sync_cmd = [
            "python",
            "scripts/sync_runtime_artifacts.py",
            "--models",
            to_workspace_relative(output_dir / "gguf"),
            "--loras",
            to_workspace_relative(output_dir / "lora_adapter"),
            "--lora-name",
            spec.artifact_key,
            "--manifest",
            to_workspace_relative(manifest_path),
        ]
        run_command(sync_cmd)
        update_manifest_sync_state(manifest_path, synced=True)
    else:
        print("\n>>> Skipping Phase 4 (Unity Sync).")
        update_manifest_sync_state(manifest_path, synced=False)

    # ── Phase 5: Quality Evaluation ───────────────────────────────────
    if not args.skip_eval:
        print("\n>>> Phase 5: Post-Training Evaluation")

        # 5a: Score the generated dataset with quality_judge
        if spec.raw_dataset_path.exists():
            print("\n  [5a] Scoring dataset quality...")
            judge_cmd = [
                "python",
                "scripts/quality_judge.py",
                "--input",
                str(spec.raw_dataset_path),
                "--npc",
                spec.npc_key,
                "--report",
                "--max-examples",
                "20",  # Quick sample for pipeline validation
            ]
            try:
                run_command(judge_cmd)
            except SystemExit:
                print("  [WARN] Quality judge failed (non-fatal). LLM server may not be running.")

        # 5b: Run NPC eval benchmarks if benchmark file exists
        benchmark_file = ROOT_DIR / "benchmarks" / "npc_eval.json"
        if benchmark_file.exists():
            print("\n  [5b] Running NPC evaluation benchmarks...")
            eval_cmd = [
                "python",
                "scripts/evaluate_model.py",
                "--benchmark",
                str(benchmark_file),
                "--npc-scope",
                spec.npc_scope,
            ]
            try:
                run_command(eval_cmd)
            except SystemExit:
                print("  [WARN] Evaluation failed (non-fatal). Model server may not be running.")
    else:
        print("\n>>> Skipping Phase 5 (Evaluation).")

    print("\n[SUCCESS] NPC Pipeline completed successfully.")
    print("You can now test the linked NPC model in Unity or restart the relay server.")


if __name__ == "__main__":
    main()
