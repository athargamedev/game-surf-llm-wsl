---
name: "npc-model-tuning"
description: "Use when working on the Game_Surf local LLM training workflow in WSL: manage LM Studio local models, test the OpenAI-compatible local inference server, tune NPC generation defaults, generate NPC datasets, run Unsloth fine-tuning, evaluate outputs, and sync trained artifacts."
metadata:
  short-description: "Tune and train local NPC LLMs in WSL"
---

# NPC Model Tuning

Use this skill from the WSL workspace root:

```bash
cd /root/Game_Surf/Tools/LLM_WSL
```

This workflow manages the local LM Studio inference server, tunes NPC generation defaults, generates synthetic NPC data, runs native WSL Unsloth training, evaluates results, and syncs trained artifacts back to Unity.

Reference files to load only when needed:
- `docs/SETUP_GUIDE.md` for native WSL environment setup.
- `docs/PIPELINE_REFERENCE.md` for phase details, schemas, and failure modes.
- `docs/ARCHITECTURE.md` for system architecture.

## When to use this skill
- A local LM Studio model needs to be listed, loaded, unloaded, downloaded, or tested.
- The generation pipeline is slow, timing out, or producing weak NPC dialogue.
- An NPC profile needs `temperature` or `max_response_tokens` tuned in `datasets/configs/npc_profiles.json`.
- A dataset, training run, LoRA adapter export, optional GGUF export, or Unity runtime sync needs to run from WSL instead of Docker.

## Rules
- Prefer native WSL commands. Do not use Docker wrappers unless the user explicitly asks for the old Docker flow.
- Run commands from the repository root. Paths are relative to this `LLM_WSL` directory, not `Tools/LLM`.
- Use `./run_pipeline.sh` for full training so it runs inside `unsloth_env`.
- Use `conda run --no-capture-output -n unsloth_env python ...` for pipeline scripts when the active shell is not already inside `unsloth_env`.
- Before long training, verify `conda info --envs`, `nvidia-smi`, and the LM Studio connection.
- Keep `--batch-size 1` for validation and low-VRAM cards. Increase only after a successful small run.
- If a script's flags may have changed, run `python <script> --help` or `conda run -n unsloth_env python <script> --help` first.

## 1. Manage LM Studio
LM Studio should be running on Windows or WSL with the local server enabled at `http://127.0.0.1:1234`. Use the bundled helper:

```bash
python .codex/skills/npc-model-tuning/scripts/tune_model.py lm-list

python .codex/skills/npc-model-tuning/scripts/tune_model.py lm-download TheBloke/Llama-2-7B-GGUF

python .codex/skills/npc-model-tuning/scripts/tune_model.py lm-load cognitivecomputations/dolphin-2.2.1-mistral-7b-gguf

python .codex/skills/npc-model-tuning/scripts/tune_model.py lm-unload cognitivecomputations/dolphin-2.2.1-mistral-7b-gguf
```

If the REST management endpoints fail with 404, LM Studio is likely exposing only the OpenAI-compatible `/v1` API. Continue with connection testing and use the LM Studio UI for load/unload.

## 2. Test Local Inference
Test the active OpenAI-compatible server before generating data:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/npc-model-tuning/scripts/tune_model.py test-connection \
  --model <loaded_model_id>
```

If latency exceeds 15 seconds, use small sequential settings during dataset generation and warn the user before full runs.

## 3. Tune NPC Generation Defaults
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

## 4. Generate a Small Validation Dataset
Run a minimal generation batch before any full dataset or training job:

```bash
conda run --no-capture-output -n unsloth_env python scripts/generate_npc_dataset.py \
  --npc <npc_key> \
  --target-count 2 \
  --batch-size 1 \
  --skip-research \
  --llm-model <loaded_model_id>
```

Inspect `datasets/personas/<artifact_key>/`. If the NPC ignores tone, slang, or rules, tune the profile and rerun the small batch.

## 5. Evaluate Generated Data
Use the judge when LM Studio is available:

```bash
conda run --no-capture-output -n unsloth_env python scripts/quality_judge.py \
  --input datasets/personas/<artifact_key>/<dataset_name>.jsonl \
  --npc <npc_key> \
  --report \
  --max-examples 20
```

## 6. Run the WSL Training Pipeline
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

## 7. Runtime Playtest
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
