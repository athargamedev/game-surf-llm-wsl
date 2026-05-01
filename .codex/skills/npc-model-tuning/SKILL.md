---
name: "npc-model-tuning"
description: "Use when working on the Game_Surf WSL-native NPC training workflow: verify CUDA/VRAM, train LoRA adapters with Unsloth inside this WSL instance, evaluate training artifacts, reload the WSL runtime server, validate chat/Supabase memory behavior, and sync trained artifacts."
metadata:
  short-description: "Tune and train local NPC LLMs in WSL"
---

# NPC Model Tuning

Use this skill from the WSL workspace root:

```bash
cd /root/Game_Surf/Tools/LLM_WSL
```

This workflow manages WSL-native Unsloth training, evaluates training artifacts, reloads the integrated WSL runtime server, validates chat/Supabase behavior, and syncs trained artifacts back to Unity.

Current canonical path: NotebookLM creates source-backed JSONL datasets, `prepare_dataset.py` builds train/validation splits, and `train_surf_llama.py` trains LoRA adapters inside `unsloth_env` on this WSL instance. Do not require LM Studio for normal dataset, training, or runtime validation.

Reference files to load only when needed:
- `docs/SETUP_GUIDE.md` for native WSL environment setup.
- `docs/PIPELINE_REFERENCE.md` for phase details, schemas, and failure modes.
- `docs/ARCHITECTURE.md` for system architecture.

## When to use this skill
- A WSL Unsloth training run needs to be configured, launched, resumed, diagnosed, or compared.
- Training artifacts, manifests, adapter paths, or runtime reload behavior need validation.
- An NPC profile needs `temperature` or `max_response_tokens` tuned in `datasets/configs/npc_profiles.json`.
- A dataset, training run, LoRA adapter export, optional GGUF export, or Unity runtime sync needs to run from WSL instead of Docker.

## Rules
- Prefer native WSL commands. Do not use Docker wrappers unless the user explicitly asks for the old Docker flow.
- Run commands from the repository root. Paths are relative to this `LLM_WSL` directory, not `Tools/LLM`.
- Use `./run_pipeline.sh` for full training so it runs inside `unsloth_env`.
- Use `conda run --no-capture-output -n unsloth_env python ...` for pipeline scripts when the active shell is not already inside `unsloth_env`.
- Before long training, verify `conda info --envs`, `nvidia-smi`, prepared splits, and available VRAM in this WSL instance.
- Keep `--batch-size 1` for validation and low-VRAM cards. Increase only after a successful small run.
- If a script's flags may have changed, run `python <script> --help` or `conda run -n unsloth_env python <script> --help` first.
- After training, artifact checks, runtime reloads, or memory tests, record evidence with `scripts/track_workflow_run.py` so model changes can be compared across runs.
- When the user needs to test in a browser, start/restart the servers outside the Codex sandbox; otherwise `localhost` may only be visible inside the sandbox.
- Update `docs/PROJECT_CONTEXT_INTELLIGENCE.md` when runtime, test, or memory behavior changes.

## 1. Verify WSL Training Readiness

Check the native WSL training environment before any long run:

```bash
conda info --envs
nvidia-smi
conda run --no-capture-output -n unsloth_env python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no cuda')"
```

If runtime inference is already using VRAM, stop or restart the WSL runtime server before training.

## 2. Tune NPC Generation Defaults
Update `datasets/configs/npc_profiles.json` through the helper instead of manual string edits:

```bash
python .codex/skills/npc-model-tuning/scripts/tune_model.py tune \
  --npc maestro_jazz_instructor \
  --temp 0.95 \
  --tokens 150
```

Typical tuning:
- Increase `temperature` when answers are too flat or generic.
- Decrease `temperature` when answers ignore rules or drift off persona.
- Increase `max_response_tokens` when answers truncate.
- Decrease `max_response_tokens` when answers ramble.

These defaults affect synthetic fallback generation and some runtime behavior. They are not a replacement for source-backed NotebookLM dataset quality.

## 3. Validate Prepared Dataset

NotebookLM dataset creation is owned by `notebooklm-npc-datasets`. Before training here, verify the prepared splits:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_key> \
  --stage prepare
```

## 4. Run the WSL Training Pipeline
For full native WSL training, use the wrapper:

```bash
./run_pipeline.sh \
  --npc <npc_key> \
  --target-count 200 \
  --epochs 3 \
  --batch-size 1 \
  --grad-accum 8
```

If generation already succeeded and only training should run:

```bash
./run_pipeline.sh --npc <npc_key> --skip-generation
```

Outputs are written under `exports/npc_models/<artifact_key>/`, including the LoRA adapter and `npc_model_manifest.json`. A GGUF is optional and should only be exported when a target runtime cannot apply adapters.

For prototype iteration, keep formatted dataset cache disabled. The orchestrator passes `--no-cache-data` to training so changed JSONL files cannot reuse stale formatted rows. Use `--cache-data` only for larger stable datasets.

Capture the training evidence after each run:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_key> \
  --stage train

conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_key> \
  --stage artifact
```

Use `python scripts/training_metrics.py history <npc_key>` and `python scripts/training_metrics.py compare <npc_key>` only after the current run has been logged or traced.

## 5. Runtime Playtest
After a successful LoRA adapter export:
1. Keep the shared base GGUF loaded by the integrated WSL server.
2. Select the NPC adapter through `/reload-model` or the browser test interface.
3. Sync runtime artifacts if the pipeline did not already sync them:

```bash
conda run --no-capture-output -n unsloth_env python scripts/sync_runtime_artifacts.py
```

4. Start the local integrated server or relay expected by Unity:

```bash
conda run --no-capture-output -n unsloth_env python scripts/llm_integrated_server.py
```

5. Playtest the NPC in the Unity Editor.

Record runtime and Supabase proof from the running server:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_key> \
  --stage runtime \
  --reload-model

conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_key> \
  --stage memory \
  --player-id workflow_probe
```

For `/test-10-player`, a pass requires more than memory creation. Confirm Phase 2 reports both `memory_loaded_on_start=true` and `memory_used_in_response=true`. If an NPC says it cannot remember while Supabase returned memory rows, treat it as runtime prompt/model-use failure, not database failure.
