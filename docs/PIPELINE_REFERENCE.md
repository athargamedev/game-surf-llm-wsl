# Game_Surf NPC LLM Pipeline — Developer & Agent Reference

> **Audience:** Human developers, AI coding agents, and automated CI systems.
> **Working directory:** `/root/Game_Surf/Tools/LLM_WSL`
> **Python environment:** `conda activate unsloth_env`
> **Training:** Native WSL2 (not Docker)

---

## 1. Architecture Overview

The pipeline converts a free-text subject (e.g., _Jazz History_) into a fully quantized, fine-tuned GGUF model that powers a self-aware NPC inside the Unity surfing game. It is composed of five sequential phases:

```
[Research Notes]
      │
      ▼
Phase 1 ─ Dataset Generation      generate_npc_dataset.py
      │      (local LLM via LM Studio)
      ▼
Phase 2 ─ Dataset Preparation     prepare_dataset.py
      │      (filter, dedup, train/val split)
      ▼
Phase 3 ─ Fine-Tuning             train_surf_llama.py
      │      (Unsloth / LoRA in WSL2)
      ▼
Phase 4 ─ Artifact Sync           sync_runtime_artifacts.py
      │      (copy .gguf + LoRA adapter into Unity project)
      ▼
Phase 5 ─ Quality Evaluation      quality_judge.py  /  evaluate_model.py
               (score dataset + benchmark inference)
```

All five phases are orchestrated by one entry point:

```bash
python scripts/run_full_npc_pipeline.py --npc <npc_key> [flags]
```

> [!TIP]
> **Current setup:** Native WSL2 (not Docker). See [docs/SETUP_GUIDE.md](SETUP_GUIDE.md).

---

---

## 2. Directory Layout

```
LLM_WSL/
├── scripts/                   # All executable Python scripts
├── datasets/
│   ├── configs/
│   │   └── npc_profiles.json   # NPC registry — source of truth for all keys
│   ├── personas/               # Raw generated JSONL per NPC
│   │   └── <artifact_key>/
│   │       └── <dataset_name>.jsonl
│   ├── processed/              # Prepared train/val splits
│   │   └── <dataset_name>/
│   │       ├── train.jsonl
│   │       ├── validation.jsonl
│   │       └── metadata.json
│   └── evals/                  # Golden evaluation sets
├── exports/
│   └── npc_models/
│       └── <artifact_key>/
│           ├── gguf/           # Quantized .gguf output
│           ├── lora_adapter/   # HuggingFace safetensors adapter
│           └── npc_model_manifest.json
├── research/
│   └── <npc_key>/              # Markdown research notes (input to generation)
├── docs/
│   └── PIPELINE_REFERENCE.md    # Full pipeline reference
├── run_pipeline.sh             # Pipeline entrypoint
```

---

## 3. NPC Profile Registry

All NPC keys, display names, subjects, and Supabase IDs are stored in:

```
Tools/LLM/datasets/configs/npc_profiles.json
```

### Registered Profiles

| `npc_key` | `display_name` | `artifact_key` | Subject |
|---|---|---|---|
| `maestro_jazz_instructor` | The Maestro | `jazz_history_instructor` | Jazz history, music theory, improvisation |
| `brazilian_history` | Professor Pedro | `brazilian_history_instructor` | History of Brazil, Colonial era, Empire |
| `marvel_comics_instructor` | MarvelOracle | `marvel_comics_instructor` | Marvel Comics lore, Avengers, X-Men |
| `kosmos_instructor` | Professor Kosmos | `greek_mythology_instructor` | Greek/Roman Mythology, heroic epics |

### Adding a New NPC

1. Add an entry to `datasets/configs/npc_profiles.json` following the existing schema.
2. Create a research notes directory at `research/<npc_key>/` with markdown `.md` files.
3. Run the full pipeline with `--npc <your_new_key>`.

The key contract resolver (`scripts/npc_pipeline_contract.py`) auto-derives all paths from the registry — **never hardcode paths in scripts**.

---

## 4. Script Reference

### 4.1 `run_full_npc_pipeline.py` — Orchestrator

The single entry point. Runs all five phases in sequence.

```bash
python scripts/run_full_npc_pipeline.py \
  --npc maestro_jazz_instructor \
  [--skip-generation]          # Reuse existing raw .jsonl (already generated)
  [--skip-prep]                # Reuse existing processed splits
  [--skip-training]            # Skip Unsloth fine-tuning
  [--skip-sync]                # Skip Unity artifact copy
  [--skip-eval]                # Skip post-training evaluation
  [--target-count 200]         # Examples to generate (Phase 1)
  [--epochs 3]
  [--lora-r 16]
  [--learning-rate 2e-4]
  [--save-gguf q4_k_m]         # GGUF quantization type
  [--model-name unsloth/Llama-3.2-3B-Instruct]
```

> **Agent rule:** Always check `--help` before running. Do not assume flag names.

---

### 4.2 `generate_npc_dataset.py` — Dataset Generation (Phase 1)

Reads research notes from `research/<npc_key>/`, calls the local LM Studio server, and writes ChatML-formatted training examples to `datasets/personas/<artifact_key>/<dataset_name>.jsonl`.

```bash
python scripts/generate_npc_dataset.py \
  --npc maestro_jazz_instructor \
  --target-count 200 \
  --batch-size 1 \
  --async-batch \
  --skip-research \            # Skip NotebookLM research step
  --llm-model llama-3.1-8b-unsloth   # MUST match the exact model ID from LM Studio
```

**Critical:** The `--llm-model` value must exactly match the model ID returned by:
```bash
python -c "from openai import OpenAI; c = OpenAI(base_url='http://127.0.0.1:1234/v1', api_key='dummy'); print([m.id for m in c.models.list()])"
```

**Output schema** (each JSONL line):
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user",   "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "metadata": {
    "npc_scope":    "instructor",
    "task_type":    "teaching",
    "source_kind":  "synthetic",
    "quality":      0.8,
    "npc_key":      "maestro_jazz_instructor"
  }
}
```

**Task type distribution** for 200 examples:
| Task | Count | Purpose |
|---|---|---|
| `teaching` | 70 | Core subject knowledge |
| `multi_turn` | 30 | Conversational continuity |
| `greeting` | 20 | First contact |
| `hint` | 20 | In-game guidance |
| `refusal` | 20 | Stays in character |
| `game_context_blend` | 20 | Merges subject with surfing game |
| `redirect` | 10 | Deflects off-topic questions |
| `scene_explanation` | 10 | Explains Unity scene context |

---

### 4.3 `prepare_dataset.py` — Dataset Preparation (Phase 2)

Filters, deduplicates, and splits the raw JSONL into train/validation sets.

```bash
python scripts/prepare_dataset.py \
  --input  datasets/personas/jazz_history_instructor/jazz_history_dataset.jsonl \
  --output datasets/processed/jazz_history_dataset \
  --val-split 0.1 \
  --test-split 0.0 \
  --quality-threshold 0.7 \
  [--deduplicate] \
  [--stratify-by task_type]
```

**Supported input formats:** `chatml`, `jsonl`, `json`, `alpaca`, `sharegpt`, `auto` (default — auto-detects).

**Known behaviours to be aware of:**
- `--test-split 0.0` (the default) skips test set creation entirely — this is correct.
- If `--quality-threshold` removes all examples, the script raises a `ValueError` with the threshold value.
- `--deduplicate` always runs independently; it is not gated on whether quality filtering was applied.

---

### 4.4 `train_surf_llama.py` — Fine-Tuning (Phase 3)

Running natively in WSL2, `train_surf_llama.py` runs Unsloth LoRA fine-tuning and saves:
- `exports/npc_models/<artifact_key>/lora_adapter/` — raw adapter weights
- `exports/npc_models/<artifact_key>/gguf/` — quantized `.gguf` file
- `exports/npc_models/<artifact_key>/npc_model_manifest.json` — training metadata manifest

**Prerequisites:** GPU must be available. Run `nvidia-smi` to verify.

---

### 4.5 `sync_runtime_artifacts.py` — Unity Sync (Phase 4)

Copies the final `.gguf` and LoRA adapter into the Unity project's `Assets/` structure so that `llm_integrated_server.py` and the Relay can pick them up at runtime.

---

### 4.6 `quality_judge.py` — Evaluation (Phase 5)

Scores generated examples using the local LM Studio model as the judge. Produces a per-example quality report.

```bash
python scripts/quality_judge.py \
  --input datasets/personas/jazz_history_instructor/jazz_history_dataset.jsonl \
  --npc maestro_jazz_instructor \
  --report \
  --max-examples 20
```

> Requires LM Studio to be running with a model loaded. Non-fatal if the server is offline.

---

### 4.7 `llm_integrated_server.py` — Runtime Relay Server

Full integrated relay server with Supabase memory injection (RAG). Must be running during playtesting.

```bash
python scripts/llm_integrated_server.py
# Default port: 8005
```

The relay:
1. Receives a POST request from Unity with the player message + NPC key.
2. Fetches the NPC's conversation history from Supabase.
3. Prepends the system prompt and memory context.
4. Forwards to LM Studio at `http://127.0.0.1:1234/v1/chat/completions`.
5. Writes the assistant response back to Supabase and returns it to Unity.

---

### 4.8 `npc_pipeline_contract.py` — Path Contract (Library)

**Do not call directly.** Imported by all orchestration scripts. Resolves all paths and IDs from `npc_profiles.json`. This is the single source of truth — any new script that needs the path to a dataset, export dir, or Supabase NPC ID must call `resolve_npc_spec(npc_key)`.

---

## 5. Skill Interface (Agent Automation)

The `npc-model-tuning` skill at `.agents/skills/npc-model-tuning/` provides a higher-level CLI wrapper (`tune_model.py`) for model management and pipeline control:

```bash
# Verify server and benchmark a specific model
python .agents/skills/npc-model-tuning/scripts/tune_model.py test-connection --model llama-3.1-8b-unsloth

# List all models available in LM Studio
python .agents/skills/npc-model-tuning/scripts/tune_model.py lm-list

# Load a model into LM Studio inference
python .agents/skills/npc-model-tuning/scripts/tune_model.py lm-load <model_id>

# Tune generation parameters for a persona
python .agents/skills/npc-model-tuning/scripts/tune_model.py tune \
  --npc maestro_jazz_instructor --temp 0.9 --tokens 500
```

> **Latency warning:** If `test-connection` reports > 15s, set `--batch-size 1` and **do not** use `--async-batch`. Sequential extraction is mandatory at that latency.

---

## 6. End-to-End Quickstart for a New NPC

```bash
# 1. Register the NPC in npc_profiles.json (manual step)

# 2. Run validation batch (2 examples) to test pipeline integrity
python scripts/generate_npc_dataset.py \
  --npc <npc_key> --target-count 2 --batch-size 1 --skip-research \
  --llm-model <loaded_model_id>

# 3. If output looks correct, generate the full dataset
python scripts/generate_npc_dataset.py \
  --npc <npc_key> --target-count 200 --batch-size 1 --async-batch \
  --skip-research --llm-model <loaded_model_id>

# 4. Fine-tune (skipping generation since we just did it)
python scripts/run_full_npc_pipeline.py --npc <npc_key> --skip-generation

# 5. Load the exported .gguf in LM Studio, then start the relay
python scripts/llm_integrated_server.py

# 6. Play the Unity scene — your new NPC is live
```

---

## 7. Known Failure Modes & Resolutions

| Error | Root Cause | Resolution |
|---|---|---|
| `ValueError: Unknown format for *.jsonl` | Generated data uses `chatml` format, not in `--format` choices | Fixed: `chatml` added to choices; `detect_format` now raises instead of silent `"unknown"` |
| `UnboundLocalError: cannot access local variable 'test'` | `test` not initialized when `--test-split 0.0` | Fixed: `test = None` in else branch |
| `ZeroDivisionError` in quality filter | All 0 examples passed quality filter | Fixed: division guarded; raises `ValueError` with actionable message |
| LLM returns empty string | LM Studio requires exact model ID; wildcard `local-model` no longer accepted | Pass `--llm-model` with exact ID from `lm-list` |
| `unrecognized arguments: --train-only` | Wrong flag; pipeline uses opt-out not opt-in | Use `--skip-generation` to skip Phase 1 |
| `conda run` fails on training | `unsloth_env` not activated or Docker not running | Ensure `conda activate unsloth_env` and Docker daemon is up |

---

## 8. Data Quality Standards

| Field | Expected Value | Enforcement |
|---|---|---|
| `quality` | `0.7` – `1.0` | `--quality-threshold 0.7` (default) |
| `source_kind` | `"synthetic"` | Set by `generate_npc_dataset.py` automatically |
| `npc_scope` | Must be in schema choices | Validated by `prepare_dataset.py` |
| `task_type` | Must be in schema choices | Validated by `prepare_dataset.py` |
| `messages` | Must have `system`, `user`, `assistant` turns | Required by `convert_to_chatml()` |

Minimum recommended dataset size for meaningful LoRA fine-tuning: **100 examples** (production: 200+).
