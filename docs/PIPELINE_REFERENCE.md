# Game_Surf NPC LLM Pipeline — Developer & Agent Reference

> **Audience:** Human developers, AI coding agents, and automated CI systems.
> **Working directory:** `/root/Game_Surf/Tools/LLM_WSL`
> **Python environment:** `conda activate unsloth_env`
> **Training:** Native WSL2 (not Docker)

---

## 1. Architecture Overview

The pipeline converts source-backed NotebookLM dataset batches into a WSL-trained LoRA adapter that powers a Unity NPC through the integrated runtime server and Supabase memory. It is composed of five sequential phases:

```
[Research Notes]
      │
      ▼
Phase 1 ─ Dataset Creation        NotebookLM JSONL + import_notebooklm_jsonl.py
      │      (source-backed NotebookLM batches)
      ▼
Phase 2 ─ Dataset Preparation     prepare_dataset.py
      │      (filter, dedup, train/val split)
      ▼
Phase 3 ─ Fine-Tuning             train_surf_llama.py
      │      (Unsloth / LoRA in WSL2)
      ▼
Phase 4 ─ Artifact Sync           sync_runtime_artifacts.py
      │      (copy LoRA/runtime artifacts for Unity/server use)
      ▼
Phase 5 ─ Runtime Evaluation      track_workflow_run.py / evaluate_model.py
               (training metrics + runtime chat + Supabase memory proof)
```

All five phases are orchestrated by one entry point:

```bash
python scripts/run_full_npc_pipeline.py --npc <npc_key> [flags]
```

> **Preferred path for new NPCs:** use the NotebookLM-direct workflow to create/import dataset batches first, then run the pipeline with `--skip-generation`.

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
3. Prefer NotebookLM-direct batch generation/import.
4. Run the full pipeline with `--npc <your_new_key> --skip-generation` once processed splits exist.

The key contract resolver (`scripts/npc_pipeline_contract.py`) auto-derives all paths from the registry — **never hardcode paths in scripts**.

### Canonical New NPC Workflow

1. Pick/create NotebookLM notebook and verify NPC profile
2. Generate NotebookLM-direct JSONL batches
3. Import and prepare dataset
4. Train LoRA model
5. Validate artifacts and manifest
6. Restart servers properly
7. Test via chat and `/test-10-player`
8. Confirm Supabase memories persist
9. Confirm recall answers actually use the loaded memory

**Decision tips**
- Prefer NotebookLM-direct for dataset creation; local synthetic generation is a fallback only
- Use 10-example batches if 50-example asks time out
- Accept `45+` valid unique for a 50-example target
- Require literal `[MEMORY_CONTEXT: {player_memory_summary}]`
- Use small-dataset settings when prepared splits stay under ~500 examples
- Stop the runtime LLM server before training if VRAM is near full
- Restart with `python scripts/server_manager.py start --auto` or `python scripts/server_manager.py restart --session llm-server`
- Add the NPC to `/test-10-player` before final runtime validation
- Treat `/test-10-player` + Supabase memory creation + `memory_used_in_response=true` as final operational proof
- Use unique per-run test player IDs so old memories do not contaminate new test results

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

### 4.2 NotebookLM Dataset Creation — Phase 1

The canonical workflow uses NotebookLM to create source-backed JSONL batches under `research/<npc_key>/`, then imports them into `datasets/personas/<artifact_key>/<dataset_name>.jsonl`.

```bash
conda run --no-capture-output -n unsloth_env python \
  .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --input research/maestro_jazz_instructor/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

`scripts/generate_npc_dataset.py` still exists for legacy local/synthetic generation, but it is not the normal path for this project workflow.

Trace the dataset evidence after import/prepare:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc maestro_jazz_instructor \
  --stage all \
  --skip-live-probe
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
    "source_kind":  "notebooklm_direct",
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

### 4.6 `track_workflow_run.py` — Evaluation Trace (Phase 5)

Collects stage evidence into `reports/workflow_runs/<npc_key>/<run_id>/`, including dataset audit, training metrics, artifact checks, runtime status, and optional Supabase memory proof.

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc maestro_jazz_instructor \
  --stage all \
  --skip-live-probe
```

Run `--stage runtime --reload-model` and `--stage memory` after the WSL runtime server is running. Use cross-session memory proof before comparing training runs:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc solar_system_instructor \
  --stage memory \
  --cross-session-memory \
  --player-id workflow_probe_solar
```

Fixed dialogue benchmarks live under `benchmarks/npc_dialogue/` and write reports under `reports/dialogue_benchmarks/`:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/run_dialogue_benchmark.py \
  --npc solar_system_instructor
```

Supabase memory diagnostics are dry-run by default:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/repair_memory_state.py --json
```

---

### 4.7 `llm_integrated_server.py` — Runtime Relay Server

Full integrated relay server with Supabase memory injection (RAG). Must be running during playtesting.

```bash
conda run --no-capture-output -n unsloth_env python scripts/llm_integrated_server.py
# Default port: 8000
```

The relay:
1. Receives a POST request from Unity with the player message + NPC key.
2. Fetches the NPC's conversation history from Supabase.
3. Prepends the system prompt and memory context.
4. Runs the shared base model plus the selected NPC LoRA adapter in the WSL runtime.
5. Writes the assistant response back to Supabase and returns it to Unity.

Memory validation contract:
- `memory_loaded_on_start=true` proves Supabase returned a prior memory row.
- `memory_used_in_response=true` proves the answer actually used loaded memory.
- If an NPC denies memory while memory loaded, treat it as prompt/model-use failure, not a missing database row.
- Python `/chat` writes `dialogue_turns`; keep `dialogue_sessions.turn_count` synchronized for diagnostics and Edge-function parity.

---

### 4.8 `npc_pipeline_contract.py` — Path Contract (Library)

**Do not call directly.** Imported by all orchestration scripts. Resolves all paths and IDs from `npc_profiles.json`. This is the single source of truth — any new script that needs the path to a dataset, export dir, or Supabase NPC ID must call `resolve_npc_spec(npc_key)`.

---

## 5. Skill Interface (Agent Automation)

Use the local Codex skills under `.opencode/skills/`:

```bash
# Dataset creation/import/prepare
conda run --no-capture-output -n unsloth_env python \
  .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py --help

# Workflow trace
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py --help
```

The `npc-model-tuning` skill owns WSL CUDA readiness, Unsloth training, adapter validation, runtime reload, and Supabase memory checks. It does not require LM Studio.

---

## 6. End-to-End Quickstart for a New NPC

```bash
# 1. Register the NPC in npc_profiles.json (manual step)

# 2. Generate/import NotebookLM-direct batches (preferred path)
conda run --no-capture-output -n unsloth_env python \
  .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_key> \
  --input research/<npc_key>/notebooklm_batch_*.jsonl \
  --import \
  --prepare

# 3. Fine-tune (skipping generation because processed splits now exist)
python scripts/run_full_npc_pipeline.py --npc <npc_key> --skip-generation

# 4. Restart runtime
python scripts/server_manager.py start --auto

# 5. Validate in chat and /test-10-player, then confirm Supabase memories
```

### Worked Example: `brazilian_history`

- NotebookLM notebook: `Brazilian History Research`
- 50-example ask timed out; reliable path was 5 narrowed batches of 10
- Import result: `49 valid unique`, avg quality `0.883`, memory slot rate `1.0`
- Prepared splits: `45 train / 4 validation`
- Training: `unsloth/Llama-3.2-3B-Instruct`, LoRA-only artifacts
- Final losses: train `1.875`, eval `1.936`
- Runtime validation succeeded after adding `brazilian_history_instructor` to `/test-10-player`
- Automated test answered correctly and populated Supabase NPC memories

### Worked Example: `solar_system_instructor`

- NotebookLM notebook: `Solar_System_Instructor`
- Reliable generation strategy: narrowed 10-example batches
- Import result: `49 valid unique`, memory slot rate `1.0`
- Prepared splits: `45 train / 4 validation`
- Training: WSL-native Unsloth smoke training
- Eval loss: `1.7207202911376953`
- Runtime validation succeeded after adding `Professor Sol` to `chat_interface.html` and `/test-10-player`
- Cross-session memory test initially revealed false-positive logic: Supabase loaded memory, but the NPC still denied recall
- Runtime/test fix added `memory_used_in_response` and a memory-recall retry guard; focused Solar validation then answered from the stored Jupiter memory

---

## 7. Known Failure Modes & Resolutions

| Error | Root Cause | Resolution |
|---|---|---|
| `ValueError: Unknown format for *.jsonl` | Generated data uses `chatml` format, not in `--format` choices | Fixed: `chatml` added to choices; `detect_format` now raises instead of silent `"unknown"` |
| `UnboundLocalError: cannot access local variable 'test'` | `test` not initialized when `--test-split 0.0` | Fixed: `test = None` in else branch |
| `ZeroDivisionError` in quality filter | All 0 examples passed quality filter | Fixed: division guarded; raises `ValueError` with actionable message |
| NotebookLM import has zero valid records | Batch output is not strict JSONL or is missing required ChatML fields | Regenerate the batch with the NotebookLM prompt template, then run importer dry-run before writing |
| `unrecognized arguments: --train-only` | Wrong flag; pipeline uses opt-out not opt-in | Use `--skip-generation` to skip Phase 1 |
| `conda run` fails on training | `unsloth_env` missing or CUDA packages are unavailable in WSL | Verify `conda info --envs`, `nvidia-smi`, and `torch.cuda.is_available()` inside `unsloth_env` |

---

## 8. Data Quality Standards

| Field | Expected Value | Enforcement |
|---|---|---|
| `quality` | `0.7` – `1.0` | `--quality-threshold 0.7` (default) |
| `source_kind` | `"notebooklm_direct"` | Set by `import_notebooklm_jsonl.py` |
| `npc_scope` | Must be in schema choices | Validated by `prepare_dataset.py` |
| `task_type` | Must be in schema choices | Validated by `prepare_dataset.py` |
| `messages` | Must have `system`, `user`, `assistant` turns | Required by `convert_to_chatml()` |

Minimum recommended dataset size for meaningful LoRA fine-tuning: **100 examples** (production: 200+).

For NotebookLM-direct prototype NPCs, a smaller set can still be operational if import quality is high, memory slot coverage is `1.0`, and runtime validation passes.
