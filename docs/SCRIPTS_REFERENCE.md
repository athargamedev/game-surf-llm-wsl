# Game_Surf LLM_WSL — Scripts & Libraries Reference

> **Audience:** Developers working on or extending the NPC AI training pipeline.  
> **Last updated:** 2026-05-02

---

## Overview

The pipeline has **five execution phases** and **three long-running services**. Every Python script belongs to exactly one category:

| Category | Purpose |
|----------|---------|
| **Entrypoint** | Single command that runs everything |
| **Pipeline Phase** | Training, data prep, export — run sequentially |
| **Service** | Servers that run continuously in background |
| **Support Utility** | Helpers called by pipeline or operators |
| **Testing / Diagnostics** | Validation and debugging, never modify data |

---

## Recommended Execution Order

> [!IMPORTANT]
> **Always start services BEFORE pipeline scripts.** The LLM server must be available for dataset generation. Supabase must be running before starting the LLM server.

```
Phase 0 — Services (start once, leave running)
  └─ 1. start_supabase_lmstudio.sh       # Local Supabase + patched Studio
  └─ 2. scripts/llm_integrated_server.py  # NPC inference + memory API

Phase 1 — Dataset Generation
  └─ 3. scripts/generate_npc_dataset.py

Phase 2 — Dataset Preparation
  └─ 4. scripts/prepare_dataset.py

Phase 3 — Model Training
  └─ 5. scripts/train_surf_llama.py

Phase 4 — Export & Sync
  └─ 6. scripts/convert_lora_to_gguf.py   (only if not already done by trainer)
  └─ 7. scripts/sync_runtime_artifacts.py

Phase 5 — Evaluation
  └─ 8. scripts/quality_judge.py
  └─ 9. scripts/evaluate_model.py

Async Worker (start alongside services)
  └─ 10. scripts/god_memory_worker.py

Orchestrator (runs Phases 1–5 automatically)
  └─ scripts/run_full_npc_pipeline.py
```

---

## Phase 0 — Services

### `scripts/start_supabase_lmstudio.sh`
**Type:** Shell entrypoint | **Conflicts:** Must run before `llm_integrated_server.py`

Starts the local Supabase stack using the patched CLI binary and custom Studio Docker image. Bridges Studio's AI assistant to LM Studio via `host.docker.internal:1234/v1`. Passes environment variables `STUDIO_OPENAI_BASE_URL`, `STUDIO_OPENAI_MODEL`, and `STUDIO_OPENAI_ADVANCED_MODEL` into the Studio container.

```bash
bash scripts/start_supabase_lmstudio.sh
```

**Depends on:** Docker, patched CLI at `/mnt/d/GithubRepos/supabasecli/bin/supabase-lmstudio`, `.env`

---

### `scripts/llm_integrated_server.py`
**Type:** Service (FastAPI) | **Port:** `8000` | **~3500 lines**

The primary runtime server for the game. This is the largest and most critical script in the project. It:

- Loads the base GGUF model (`llama-3.2-3b-instruct.Q4_K_M.gguf`) via `llama_index.llms.llama_cpp`
- Resolves and hot-swaps LoRA adapters per NPC from `npc_model_manifest.json` files
- Assembles 4-layer prompts: System → Memory → History → User
- Injects Supabase player memory into `[MEMORY_CONTEXT]` slots
- Streams responses token-by-token via SSE (`/chat/stream`)
- Manages session lifecycle (`/session/start`, `/session/end`)
- Enqueues async GOD Memory and graph rebuild jobs on session end
- Tracks request metrics at `/metrics`

**Key env vars:** `MODEL_PATH`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `ENABLE_SUPABASE`, `LLAMA_N_GPU_LAYERS`, `ENABLE_NPC_LORA`

```bash
python scripts/llm_integrated_server.py
# Or via helper:
bash scripts/start_servers.sh
```

**Endpoints summary:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness check |
| `/status` | GET | Model + Supabase state |
| `/chat` | POST | Non-streaming NPC response |
| `/chat/stream` | POST | SSE streaming response |
| `/session/start` | POST | Create session, load memory |
| `/session/end` | POST | End session, enqueue memory job |
| `/npc-models` | GET | List registered NPC adapters |
| `/reload-npc` | POST | Hot-swap to different NPC |
| `/memory/god` | POST | Fetch GOD memory for player |
| `/graph/rebuild` | POST | Trigger relation graph rebuild |
| `/metrics` | GET | Request stats and timing |

---

### `scripts/god_memory_worker.py`
**Type:** Service (background worker) | **Depends on:** Supabase + embedding model

Polls two PostgreSQL message queues (`memory_embedding_queue`, `dialogue_graph_queue`) using `pgmq_read` and processes async jobs enqueued by the LLM server after each session ends:

- **Memory Embedding Jobs:** Fetches session summaries from `npc_memories`, generates `BAAI/bge-small-en-v1.5` embeddings, and upserts into `player_memory_embeddings` for semantic memory search.
- **Graph Rebuild Jobs:** Calls `generate_relation_graph_enhanced()` Supabase RPC to rebuild the dialogue term relationship graph, then persists it to `relation_graph_nodes` and `relation_graph_edges`.

> [!WARNING]
> Do not run multiple instances of this worker simultaneously. Both jobs operate on shared tables without row-level locking.

```bash
python scripts/god_memory_worker.py
```

---

## Phase 1 — Dataset Generation

### `scripts/generate_npc_dataset.py`
**Type:** Pipeline Phase 1 | **~1900 lines** | **Inputs:** NPC profile config, research backend

Legacy local-synthesis generator. It is not the canonical Game_Surf dataset path.

Transforms NPC domain knowledge into structured ChatML training examples. Supports two research backends:

- **`notebooklm`**: Creates a NotebookLM notebook, adds source URLs, queries it for domain knowledge, and extracts structured `ResearchNote` objects.
- **legacy local synthesis**: Falls back to a local OpenAI-compatible server when old workflows intentionally use it.

Generation runs in three phases:
1. **Fact extraction** — Research notes → discrete facts (cached in `research/<npc_id>/extracted_facts.json`)
2. **Task-specific examples** — Generates `teaching` and `quiz` examples in async batches
3. **Multi-turn conversations** — Sequential generation of 2–4 turn exchanges

Outputs JSONL to `datasets/personas/<artifact_key>/<dataset_name>.jsonl`.

**Libraries used:** `asyncio`, `openai` (AsyncOpenAI for concurrent generation), `notebooklm-mcp`

Preferred replacement:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc my_npc \
  --input research/my_npc/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

---

### `scripts/extract_notebooklm_jsonl.py`
**Type:** Support Utility | **Inputs:** NotebookLM export JSON

Parses raw NotebookLM export files and converts them into JSONL format compatible with the dataset pipeline. Use this when you have a pre-existing NotebookLM export rather than running live queries.

```bash
python scripts/extract_notebooklm_jsonl.py --input export.json --output datasets/raw/
```

---

### `scripts/import_notebooklm_jsonl.py`
**Type:** Support Utility | **~1100 lines**

Imports processed JSONL files from NotebookLM sources into the local dataset structure, handles deduplication, and validates format compatibility with the training schema.

---

## Phase 2 — Dataset Preparation

### `scripts/prepare_dataset.py`
**Type:** Pipeline Phase 2 | **~850 lines** | **Inputs:** Raw JSONL from Phase 1

Takes raw generated JSONL and produces clean, balanced training splits. Operations include:

- **Quality filtering** — Removes examples scoring below `--quality-threshold` (default 0.75)
- **Deduplication** — Removes near-duplicate responses using hash matching on the `response` field
- **Stratification** — Splits by `task_type` field to maintain distribution across train/val/test
- **Format validation** — Ensures all examples follow the ChatML `messages` schema

Outputs `train.jsonl`, `validation.jsonl`, `test.jsonl` to `datasets/processed/<npc_id>/`.

```bash
python scripts/prepare_dataset.py \
  --input datasets/<npc_id>/<npc_id>_dataset.jsonl \
  --output datasets/processed/<npc_id>/ \
  --val-split 0.1 --quality-threshold 0.75 --deduplicate
```

---

### `scripts/setup_dataset_pipeline.py`
**Type:** Support Utility

Initializes the directory structure and config files required before running the dataset generation pipeline for a new NPC. Creates the profile entry in `datasets/configs/npc_profiles.json` if it doesn't exist.

---

### `scripts/audit_dataset_workflow.py`
**Type:** Diagnostics | **~350 lines**

Scans all datasets in `datasets/processed/` and reports:
- Total example counts per NPC
- Task type distribution percentages
- Missing or malformed fields
- Duplicate rate estimates

Use this to verify dataset health before training.

---

## Phase 3 — Model Training

### `scripts/train_surf_llama.py`
**Type:** Pipeline Phase 3 | **~2300 lines** | **Requires:** CUDA GPU, 6GB+ VRAM

The training engine built on **Unsloth** for memory-efficient LoRA fine-tuning of Gemma 4 E4B Instruct. Key responsibilities:

- Loads base model from `unsloth/gemma-4-E4B-it` (HuggingFace) with 4-bit quantization
- Applies LoRA configuration (rank, alpha, target modules) via `FastLanguageModel`
- Formats training examples using Llama 3.2 chat template
- Trains with `SFTTrainer` (TRL library) with configurable batch size, gradient accumulation, and learning rate
- Saves LoRA adapter to `exports/npc_models/<npc_id>/lora_adapter/`
- Optionally exports merged GGUF (`--save-gguf q4_k_m`) during training
- Writes `npc_model_manifest.json` with all artifact paths for runtime resolution
- Supports `--resume-from` for checkpoint recovery

> [!WARNING]
> Close LM Studio and other GPU applications before running. The 3B model requires ~5–6GB VRAM for training.

```bash
python scripts/train_surf_llama.py \
  --datasets my_npc_dataset \
  --npc-key my_npc \
  --output-dir exports/npc_models/my_npc \
  --save-gguf q4_k_m
```

**Libraries used:** `unsloth`, `transformers`, `trl`, `torch`, `datasets`

---

### `scripts/training_metrics.py`
**Type:** Support Utility | **~300 lines**

Reads the training metrics JSONL file (`.training_metrics.jsonl`) written by the trainer and produces training curve summaries, loss progression, and step-by-step stats. Used for post-training analysis.

---

## Phase 4 — Export & Runtime Sync

### `scripts/convert_lora_to_gguf.py`
**Type:** Pipeline Phase 4 | **Inputs:** LoRA adapter in `exports/npc_models/<npc_id>/lora_adapter/`

Converts a saved Unsloth LoRA adapter to GGUF format using `llama.cpp`'s `convert_lora_to_gguf.py`. The output `adapter_model.gguf` is what the runtime server loads for NPC inference. This step is only needed when the training phase did not include `--save-gguf`.

```bash
python scripts/convert_lora_to_gguf.py --npc my_npc
```

---

### `scripts/sync_runtime_artifacts.py`
**Type:** Pipeline Phase 4 | **~330 lines**

Copies the final GGUF base model and LoRA adapter files to the Unity `StreamingAssets/NpcModels/<npc_id>/` directory, and updates `npc_model_manifest.json` with final runtime paths. This is the bridge between the WSL training environment and the Unity game.

```bash
python scripts/sync_runtime_artifacts.py \
  --models exports/npc_models/my_npc/gguf \
  --loras exports/npc_models/my_npc/lora_adapter \
  --manifest exports/npc_models/my_npc/npc_model_manifest.json
```

---

### `scripts/export_unsloth_checkpoint.py`
**Type:** Support Utility

Manually exports a specific Unsloth training checkpoint (not the final model) to a LoRA adapter directory. Use when you want to test an intermediate checkpoint without completing the full training run.

---

### `scripts/backfill_npc_manifests.py`
**Type:** Support Utility

Scans all `exports/npc_models/` directories and regenerates missing or outdated `npc_model_manifest.json` files. Run this after moving directories or recovering from a partial export.

---

### `scripts/sync_npc_profiles.py`
**Type:** Support Utility

Syncs NPC profiles from `datasets/configs/npc_profiles.json` to the Supabase `npc_profiles` table. Must be run after adding a new NPC profile or modifying personality/voice rules.

```bash
python scripts/sync_npc_profiles.py
```

---

## Phase 5 — Evaluation

### `scripts/quality_judge.py`
**Type:** Pipeline Phase 5 | **~880 lines** | **Requires:** Running LLM server

Scores training examples for quality using the running LLM server as a judge. For each sampled example it asks the model to rate:
- Identity consistency (does the NPC stay in character?)
- Subject boundary compliance (does it refuse off-topic questions?)
- Response length appropriateness
- Factual coherence

Outputs a quality report JSON and can filter/remove low-scoring examples.

```bash
python scripts/quality_judge.py --input datasets/<npc_id>/<npc_id>_dataset.jsonl \
  --npc my_npc --report --max-examples 50
```

---

### `scripts/evaluate_model.py`
**Type:** Pipeline Phase 5 | **~540 lines** | **Requires:** Running LLM server

Runs structured NPC evaluation benchmarks from `benchmarks/npc_eval.json`. Tests the model against a fixed set of prompts for each NPC scope and compares responses to expected patterns. Generates a pass/fail report per benchmark.

```bash
python scripts/evaluate_model.py --benchmark benchmarks/npc_eval.json --npc-scope instructor
```

---

### `scripts/run_dialogue_benchmark.py`
**Type:** Diagnostics | **~430 lines** | **Requires:** Running LLM server

Runs a sequence of pre-scripted dialogue turns against a live NPC and measures:
- Response latency (ms per token)
- Memory injection success
- Character drift across multi-turn sessions
- Correct topic refusal rate

Used as a gating benchmark before a model is marked "ready" for distribution.

---

## Orchestrator

### `scripts/run_full_npc_pipeline.py`
**Type:** Entrypoint (Orchestrator) | **Runs:** Phases 1–5 sequentially

Single-command runner for the complete training pipeline. Calls each phase script as a subprocess, handles VRAM pre-flight checks, and supports `--skip-*` flags for resuming from any phase.

```bash
# Train from imported NotebookLM dataset
python scripts/run_full_npc_pipeline.py --npc my_npc --skip-generation

# Resume from training (skip generation + prep)
python scripts/run_full_npc_pipeline.py --npc my_npc --skip-generation --skip-prep --resume

# Training only, no GGUF export
python scripts/run_full_npc_pipeline.py --npc my_npc --skip-generation --skip-prep --skip-sync --skip-eval
```

Legacy note: running the orchestrator without `--skip-generation` now hits the Phase 1 guard unless `--allow-legacy-generation` is explicitly supplied.

---

## Support Library Scripts

### `scripts/supabase_client.py`
**Type:** Library module | **~420 lines** | **Imported by:** server, worker, test scripts

Centralized Python Supabase client. Provides:
- `SupabaseClient` class with session management, memory CRUD, and player profile operations
- `get_client()` singleton factory
- Helper functions: `load_player_context()`, `save_npc_memory()`, `refresh_dialogue_session_turn_count()`

> [!IMPORTANT]
> This is the **only** place that directly interacts with Supabase tables. All other scripts should import from here rather than using the Supabase client directly.

---

### `scripts/npc_pipeline_contract.py`
**Type:** Library module | **~200 lines** | **Imported by:** orchestrator, training scripts

Defines the `NpcSpec` dataclass and `resolve_npc_spec()` function. This is the canonical contract between pipeline phases — it resolves an NPC key to all canonical file paths (raw dataset, processed dir, output dir, manifest path) so all phases operate on the same files.

---

### `scripts/server_manager.py`
**Type:** Support Utility | **~580 lines**

Manages the lifecycle of the LLM server process: start, stop, health checks, log rotation, and graceful restart. Used by `start_servers.sh` and CI automation.

---

### `scripts/start_servers.sh`
**Type:** Shell entrypoint

Starts both the Supabase stack and the LLM integrated server. Waits for health checks before exiting. Use in dev environments as a single startup command.

```bash
bash scripts/start_servers.sh
```

---

### `scripts/start_llm_backend.sh`
**Type:** Shell entrypoint

Minimal script that only starts the LLM integrated server (no Supabase). Use when Supabase is already running.

---

### `scripts/generate_dialogue_relation_graph.py`
**Type:** Support Utility | **~310 lines**

Standalone script to manually trigger a full dialogue relation graph rebuild without going through the job queue. Calls the `generate_relation_graph_enhanced` Supabase RPC directly and persists results. Useful for one-time backfills or testing.

---

### `scripts/track_workflow_run.py`
**Type:** Support Utility | **~1000 lines**

Records and tracks pipeline run metadata (NPC, timestamp, phase outcomes, artifact paths) to a run history log. Useful for auditing which models were trained with which datasets.

---

## Diagnostic Scripts

> [!NOTE]
> Diagnostic scripts are read-only. They never modify the database or filesystem (except writing reports). Safe to run at any time.

### `scripts/test_supabase_studio_ai.py`
**Type:** Diagnostics | **~500 lines**

Validates the Supabase Studio AI assistant integration with local LM Studio. Runs 12 automated tests across 5 phases:
1. Infrastructure (LMStudio reachable, Studio container, API health)
2. SQL generation quality (SELECT, JOIN, DDL, schema awareness, RPC)
3. Structured JSON output compatibility
4. Absence of remote OpenAI calls
5. Multi-model switching

```bash
python scripts/test_supabase_studio_ai.py
python scripts/test_supabase_studio_ai.py --studio-url http://127.0.0.1:16434
```

Saves JSON reports to `reports/studio_ai_tests/`.

---

### `scripts/diagnose_memory_workflow.py`
**Type:** Diagnostics | **~360 lines**

Tests the full memory lifecycle end-to-end: starts a session, sends messages, ends the session, and verifies that memory was correctly summarized and stored in `npc_memories`. Reports the exact memory content loaded on next session start.

---

### `scripts/diagnose_pipeline.py`
**Type:** Diagnostics | **~340 lines**

Checks the health of all pipeline dependencies in sequence: Python environment, CUDA/GPU, Supabase connection, LLM server, model files, and manifest integrity. Outputs a go/no-go checklist.

---

### `scripts/repair_memory_state.py`
**Type:** Diagnostics (with repair capability) | **~410 lines**

> [!CAUTION]
> This script can modify data. Review the repair plan it generates before confirming.

Detects and optionally repairs inconsistencies in memory state: orphaned sessions (active sessions with no turns), duplicate memory summaries, and stale player profiles. Always shows a preview before making changes.

---

### `scripts/cleanup_pipeline.py`
**Type:** Diagnostics | **~140 lines**

Removes intermediate pipeline artifacts (cached fact extractions, temp JSONL files, old checkpoints beyond the keep limit) to free disk space. Safe to run between training runs.

---

## Conflict & Concurrency Rules

| Rule | Reason |
|------|--------|
| Start Supabase before `llm_integrated_server.py` | Server connects to Supabase on startup |
| Start `llm_integrated_server.py` before Phase 1 generation | Dataset generation calls the LLM server for NPC responses |
| Never run `train_surf_llama.py` while `llm_integrated_server.py` is using the GPU | Both compete for VRAM; kill the server first or use `--n-gpu-layers 0` |
| Never run two `god_memory_worker.py` instances | Both write to the same tables without distributed locking |
| Never run two `run_full_npc_pipeline.py` for the same NPC simultaneously | Shared output directories and manifest files |
| Always complete Phase 2 before Phase 3 | Trainer expects `train.jsonl` to exist |
| Always complete Phase 3 before Phase 4 | `convert_lora_to_gguf.py` requires the LoRA adapter directory |
| `sync_npc_profiles.py` requires a running Supabase | Writes directly to the database |

---

## Library Dependencies Summary

| Library | Used By | Purpose |
|---------|---------|---------|
| `unsloth` | `train_surf_llama.py` | Memory-efficient LoRA training |
| `transformers` | training, export | HuggingFace model loading |
| `trl` | `train_surf_llama.py` | `SFTTrainer` supervised fine-tuning |
| `torch` | training, server | CUDA tensor operations |
| `llama_index` | `llm_integrated_server.py`, `god_memory_worker.py` | LlamaCPP runtime, embeddings |
| `llama_index.llms.llama_cpp` | server | GGUF model inference |
| `llama_index.embeddings.huggingface` | server, worker | Text embeddings (BAAI/bge-small-en-v1.5) |
| `supabase` | server, worker, utilities | Database client |
| `fastapi` | `llm_integrated_server.py` | REST API framework |
| `openai` (AsyncOpenAI) | `generate_npc_dataset.py` | Async LLM calls to LM Studio |
| `requests` | test scripts, diagnostics | HTTP calls to server/Supabase |
| `notebooklm-mcp` | `generate_npc_dataset.py` | NotebookLM research backend |
| `datasets` | `train_surf_llama.py` | HuggingFace dataset loading |
| `pydantic` | server | Request/response models |
