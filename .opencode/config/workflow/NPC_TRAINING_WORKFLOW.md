# NPC Dialogue Training Pipeline - Workflow Automation Manifest

## Overview

This manifest maps ALL available OpenCode agents, subagents, skills, tools, MCP servers, and CLI commands to the 5-phase NPC training pipeline for Unity NPC characters.

**Project:** Game_Surf NPC Local LLM Training  
**Purpose:** Generate trained LoRA adapters for Unity NPC dialogue characters  
**Pipeline:** 5 phases (Generation → Preparation → Training → Export → Evaluation)

---

## Pipeline Phases Quick Reference

| Phase | Description | Entry Command | Skip Flag |
|-------|-------------|---------------|-----------|
| 1 | Dataset Generation | `./run_pipeline.sh --npc <npc_id>` | `--skip-generation` |
| 2 | Dataset Preparation | Auto (after gen) | `--skip-prep` |
| 3 | Model Training | Auto (after prep) | `--skip-training` |
| 4 | Unity Sync | Auto (after training) | `--skip-sync` |
| 5 | Evaluation | Auto (after sync) | `--skip-eval` |

---

## Phase 1: Dataset Generation

**Purpose:** Create raw training data from knowledge sources using NotebookLM or local LLM

**Canonical choice:** Prefer the NotebookLM-direct path for new NPCs when default `generate_npc_dataset.py` still depends on local LLM synthesis.

### Available agents/subagents

| Agent | Role | When to delegate |
|-------|------|-----------------|
| **DatasetTrainer** | Primary - dataset generation expert | Always for Phase 1 |
| **ExternalScout** | Fetch current NotebookLM/API docs | When using new external services |
| **TaskManager** | Break down batch generation tasks | When generating >200 examples |

### Available skills

| Skill | Purpose | Usage |
|-------|---------|-------|
| **notebooklm** | Generate dialogue data via NotebookLM | `skill(name="notebooklm")` |
| **notebooklm-npc-datasets** | Automate JSONL batch generation | `skill(name="notebooklm-npc-datasets")` |

### Available MCP tools

| MCP Server | Tool | Purpose |
|------------|-----|---------|
| **context7** | `context7_resolve-library-id` | Resolve NotebookLM library ID |
| **context7** | `context7_query-docs` | Get current NotebookLM API docs |
| **notebooklm** | (MCP server) | Full NotebookLM API access |

### CLI commands/scripts

```bash
# Preferred: import existing NotebookLM-direct batches
conda run --no-capture-output -n unsloth_env python \
  .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_id> \
  --input research/<npc_id>/notebooklm_batch_*.jsonl \
  --import \
  --prepare

# Generate with local LLM
python scripts/generate_npc_dataset.py --npc <npc_id> --target-count 150 --backend local --llm-url http://127.0.0.1:1234

# Skip research, use existing knowledge
python scripts/generate_npc_dataset.py --npc <npc_id> --skip-research

# Async batch generation
python scripts/generate_npc_dataset.py --npc <npc_id> --async-batch --batch-size 5

# Import existing NotebookLM JSONL
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --input research/<npc_id>/notebooklm_batch_01.jsonl

# Run via pipeline orchestrator
./run_pipeline.sh --npc <npc_id>
```

### Decision tips

- Prefer NotebookLM-direct generation for new NPC activation work.
- If a 50-example NotebookLM ask times out, switch to 10-example batches.
- Accept `45+` valid unique examples for a nominal 50-example target.
- Require literal `[MEMORY_CONTEXT: {player_memory_summary}]` in system prompts.

### Input requirements

- Knowledge source in `research/<npc_id>/` (lore files, txt, PDFs)
- Optional: NotebookLM prompt in `research/<npc_id>/notebooklm_batch_XX_prompt.txt`
- Optional: Deep Research report in `research/<npc_id>/report.md`

### Output artifacts

- Raw dataset: `research/<npc_id>/notebooklm_batch_XX.jsonl`
- Raw text: `research/<npc_id>/notebooklm_batch_XX_raw.txt`

### Automation hints

```bash
# Check if knowledge source exists
ls research/<npc_id>/*.txt research/<npc_id>/*.md

# Check existing batches
ls research/<npc_id>/notebooklm_batch_*.jsonl

# Count examples
wc -l research/<npc_id>/notebooklm_batch_*.jsonl
```

---

## Phase 2: Dataset Preparation

**Purpose:** Filter, deduplicate, quality-check, and split into train/validation/test sets

### Available agents/subagents

| Agent | Role | When to delegate |
|-------|------|-----------------|
| **DatasetTrainer** | Primary - data preparation expert | Always for Phase 2 |
| **TestEngineer** | Validate dataset quality | When adding test cases |

### Available skills

| Skill | Purpose | Usage |
|-------|---------|-------|
| **npc-model-tuning** | Dataset validation & splits | `skill(name="npc-model-tuning")` |

### CLI commands/scripts

```bash
# Standard preparation
./run_pipeline.sh --npc <npc_id> --skip-generation --input research/<npc_id>/raw.jsonl --output datasets/processed/<npc_id>/

# With quality filtering
./run_pipeline.sh --npc <npc_id> --skip-generation --input research/<npc_id>/raw.jsonl --output datasets/processed/<npc_id>/ --quality-threshold 0.75

# With deduplication
./run_pipeline.sh --npc <npc_id> --skip-generation --input research/<npc_id>/raw.jsonl --output datasets/processed/<npc_id>/ --deduplicate --dedup-by response

# With stratification
./run_pipeline.sh --npc <npc_id> --skip-generation --input research/<npc_id>/raw.jsonl --output datasets/processed/<npc_id>/ --stratify-by task_type --val-split 0.1 --test-split 0.1

# Run as part of pipeline
./run_pipeline.sh --npc <npc_id> --skip-generation
```

### Input requirements

- Raw dataset: `research/<npc_id>/notebooklm_batch_XX.jsonl`

### Output artifacts

- `datasets/processed/<npc_id>/train.jsonl`
- `datasets/processed/<npc_id>/validation.jsonl`
- `datasets/processed/<npc_id>/test.jsonl` (if `--test-split > 0`)

### Automation hints

```bash
# Check prepared dataset size
wc -l datasets/processed/<npc_id>/*.jsonl

# Validate JSONL format
python -c "import json; [json.loads(l) for l in open('datasets/processed/<npc_id>/train.jsonl')]"

# Check quality scores distribution
cut -f3 datasets/processed/<npc_id>/train.jsonl | sort | uniq -c | sort -rn
```

### Decision tips

- Keep both `teaching` and `quiz` after filtering when possible.
- Memory slot coverage should remain `1.0`.
- Under ~500 prepared examples, plan for small-dataset training settings.

---

## Phase 3: Model Training

**Purpose:** Fine-tune Llama 3.2 with Unsloth for local WSL2 GPU

### Available agents/subagents

| Agent | Role | When to delegate |
|-------|------|-----------------|
| **DatasetTrainer** | Primary - training expert | Always for Phase 3 |
| **BuildAgent** | Validate build/step | After each checkpoint |
| **TaskManager** | Manage parallel training | When resuming/continuing |

### Available skills

| Skill | Purpose | Usage |
|-------|---------|-------|
| **npc-model-tuning** | Full training workflow | `skill(name="npc-model-tuning")` |

### CLI commands/scripts

```bash
# Standard training (2 epochs)
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <dataset_name> --train-file datasets/processed/<npc_id>/train.jsonl

# Small-dataset preset (<500 samples)
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <dataset_name> --train-file datasets/processed/<npc_id>/train.jsonl --small-dataset

# Custom hyperparameters
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <dataset_name> --train-file datasets/processed/<npc_id>/train.jsonl \
  --num-train-epochs 3 --batch-size 1 --gradient-accumulation-steps 8 \
  --learning-rate 2e-4 --lora-r 16 --lora-alpha 32

# With validation
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <dataset_name> --train-file datasets/processed/<npc_id>/train.jsonl \
  --val-file datasets/processed/<npc_id>/validation.jsonl

# Resume from checkpoint
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <dataset_name> --train-file datasets/processed/<npc_id>/train.jsonl \
  --resume-from exports/npc_models/<npc_id>/checkpoints/checkpoint-12

# Export to GGUF during training
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <dataset_name> --train-file datasets/processed/<npc_id>/train.jsonl \
  --save-gguf q4_k_m

# GPU memory check before starting
nvidia-smi --query-gpu=memory.free,memory.total --format=csv

# Run via pipeline orchestrator
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep
```

### Decision tips

- Stop the runtime LLM server before training if VRAM is near full.
- Small-dataset settings are appropriate when prepared splits stay under ~500 examples.

### Proven example

- `brazilian_history` imported to `49 valid unique`
- Prepared splits: `45 train / 4 validation`
- Training succeeded on `unsloth/Llama-3.2-3B-Instruct`

### Input requirements

- Prepared dataset: `datasets/processed/<npc_id>/train.jsonl`
- Optional: validation set `datasets/processed/<npc_id>/validation.jsonl`

### Output artifacts

- Checkpoints: `exports/npc_models/<npc_id>/checkpoints/checkpoint-*`
- Training report: `exports/npc_models/<npc_id>/checkpoints/training_report.json`
- Run config: `exports/npc_models/<npc_id>/run_config.json`

### GPU Requirements

| GPU | VRAM | Recommended batch size | Max steps (100ep) |
|-----|-----|----------------------|-------------------|
| RTX 3060 | 6GB | 1 | ~500 |
| RTX 3060 Ti | 8GB | 1-2 | ~800 |
| RTX 4070 | 12GB | 2-4 | ~1200 |
| RTX 4090 | 24GB | 4-8 | ~2000 |

### Automation hints

```bash
# Check GPU availability
nvidia-smi

# Check available VRAM
nvidia-smi --query-gpu=memory.free --format=csv,noheader

# Monitor training in real-time
watch -n 5 nvidia-smi

# List checkpoints
ls -la exports/npc_models/<npc_id>/checkpoints/

# Check training progress
cat exports/npc_models/<npc_id>/checkpoints/training_report.json | jq '.epoch, .global_step'
```

---

## Phase 4: Export & Unity Sync

**Purpose:** Convert LoRA adapter to GGUF format and sync to Unity runtime

### Available agents/subagents

| Agent | Role | When to delegate |
|-------|------|-----------------|
| **DatasetTrainer** | Primary - export expert | Always for Phase 4 |
| **DevOpsSpecialist** | Runtime sync validation | After sync completion |

### Available skills

| Skill | Purpose | Usage |
|-------|---------|-------|
| **npc-model-tuning** | GGUF export & sync | `skill(name="npc-model-tuning")` |

### CLI commands/scripts

```bash
# Export checkpoint to GGUF
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --checkpoint exports/npc_models/<npc_id>/checkpoints/checkpoint-12 --output exports/npc_models/<npc_id>/gguf/

# Export with quantization
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --checkpoint exports/npc_models/<npc_id>/checkpoints/checkpoint-12 --output exports/npc_models/<npc_id>/gguf/ --quantize q4_k_m

# Sync to Unity runtime
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --skip-eval --models exports/npc_models/<npc_id>/gguf/ --loras exports/npc_models/<npc_id>/lora_adapter/ --lora-name <artifact_key> --manifest exports/npc_models/<npc_id>/npc_model_manifest.json

# Run via pipeline (includes sync)
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training
```

### Input requirements

- Trained checkpoint: `exports/npc_models/<npc_id>/checkpoints/checkpoint-*`

### Output artifacts

- GGUF model: `exports/npc_models/<npc_id>/gguf/adapter_model.gguf`
- LoRA adapter: `exports/npc_models/<npc_id>/lora_adapter/`
- Model manifest: `exports/npc_models/<npc_id>/npc_model_manifest.json`

### Unity integration

| File | Unity path | Usage |
|------|-----------|-------|
| `adapter_model.gguf` | `Assets/Models/NPC/<npc_id>/` | llama.cpp inference |
| `npc_model_manifest.json` | `Assets/Models/NPC/<npc_id>/` | Model config |

### Final runtime validation

1. Validate `lora_adapter/` and `npc_model_manifest.json`
2. Restart runtime with `python scripts/server_manager.py start --auto` or `python scripts/server_manager.py restart --session llm-server`
3. Test direct chat for the new NPC
4. Add the NPC to `/test-10-player`
5. Run `/test-10-player`
6. Confirm Supabase memories persist

**Acceptance proof:** `/test-10-player` succeeds and Supabase memory rows are created for the NPC.

### Automation hints

```bash
# Check GGUF size
ls -lh exports/npc_models/<npc_id>/gguf/*.gguf

# Verify GGUF validity
llama-cli --metadata exports/npc_models/<npc_id>/gguf/adapter_model.gguf

# Check manifest
cat exports/npc_models/<npc_id>/npc_model_manifest.json | jq '.npc_key, .artifact_key, .supabase_npc_id'
```

---

## Phase 5: Evaluation

**Purpose:** Validate model quality and alignment with expected behavior

### Available agents/subagents

| Agent | Role | When to delegate |
|-------|------|-----------------|
| **CodeReviewer** | Quality assessment | After generation |
| **TestEngineer** | Run evaluation benchmarks | Always for Phase 5 |
| **DatasetTrainer** | Interpret evaluation results | Always for Phase 5 |

### Available skills

| Skill | Purpose | Usage |
|-------|---------|-------|
| **npc-model-tuning** | Model evaluation | `skill(name="npc-model-tuning")` |

### CLI commands/scripts

```bash
# Start model server for evaluation
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --skip-sync --skip-eval &
# Then start server: python scripts/llm_integrated_server.py --port 8000 &
# Or: # Chat server (use start_servers.sh)

# Judge dataset quality
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --skip-sync --input research/<npc_id>/raw.jsonl --npc <npc_id> --report --max-examples 20

# Run NPC evaluation benchmarks
./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --skip-sync --benchmark benchmarks/npc_eval.json --npc-scope <scope>

# Test via chat interface
# Open: http://127.0.0.1:8080/chat_interface.html

# Run via pipeline (full evaluation)
./run_pipeline.sh --npc <npc_id>
```

### Input requirements

- Raw dataset: `research/<npc_id>/raw.jsonl`
- Benchmark file: `benchmarks/npc_eval.json`
- Running model server

### Output artifacts

- Quality report: `exports/npc_models/<npc_id>/quality_report.md`
- Evaluation results: `exports/npc_models/<npc_id>/eval_results.json`

### Automation hints

```bash
# Check server is running
curl -s http://127.0.0.1:8000/health

# Test single prompt
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Tell me about [topic]"}],"model":"<npc_id>"}'

# Check benchmark file structure
cat benchmarks/npc_eval.json | jq '.[0]'
```

---

## Supabase Integration

**Purpose:** Store NPC memories, player data, and dialogue history

### Available MCP tools

| MCP Server | Tool | Purpose |
|-----------|-----|---------|
| **supabase** | `supabase_execute_sql` | Run queries |
| **supabase** | `supabase_list_tables` | List schema |
| **supabase** | `supabase_get_project_url` | Get API URL |

### CLI commands

```bash
# Start local Supabase
cd supabase && supabase start

# List tables
supabase db psql -c "\dt"

# Query NPC memories
supabase db psql -c "SELECT * FROM npc_memories WHERE npc_id = '<supabase_npc_id>' LIMIT 10;"

# Query player data
supabase db psql -c "SELECT * FROM players LIMIT 10;"

# Check auth logs
supabase get-logs --service auth
```

### Schema

| Table | Purpose |
|-------|---------|
| `players` | Player profiles, preferences |
| `npc_memories` | NPC memories per player (persistent) |
| `dialogue_sessions` | Session metadata |
| `messages` | Individual chat messages |

---

## OpenCode Skills Available

### Global skills (from ~/clone)

| Skill | Location | Purpose |
|-------|----------|---------|
| **notebooklm** | `~/clone/.claude/skills/notebooklm/SKILL.md` | NotebookLM full API |
| **notebooklm-npc-datasets** | `~/clone/.claude/skills/notebooklm-npc-datasets/SKILL.md` | Dataset automation |

### Project skills (from .opencode/skills)

| Skill | Location | Purpose |
|-------|----------|---------|
| **notebooklm-npc-datasets** | `.opencode/skills/notebooklm-npc-datasets/SKILL.md` | Project-specific dataset automation |
| **npc-model-tuning** | `.opencode/skills/npc-model-tuning/SKILL.md` | Full NPC model workflow |

### OpenCode skills (from .opencode/skills)

| Skill | Location | Purpose |
|-------|----------|---------|
| **context7** | `.opencode/skills/context7/SKILL.md` | Context7 library docs |
| **gamesurf-agent** | `.opencode/skills/gamesurf-agent/SKILL.md` | Game_Surf project automation |
| **task-management** | `.opencode/skills/task-management/SKILL.md` | Subtask management |

---

## OpenCode Subagents Available

### Core subagents (.opencode/agent/subagents/core)

| Subagent | File | Purpose |
|---------|------|---------|
| **ContextScout** | `core/contextscout.md` | Discover patterns before execution |
| **TaskManager** | `core/task-manager.md` | Break complex features into tasks |
| **ExternalScout** | `core/externalscout.md` | Fetch live docs for external libs |

### Code subagents (.opencode/agent/subagents/code)

| Subagent | File | Purpose |
|---------|------|---------|
| **CoderAgent** | `code/coder-agent.md` | Write code implementations |
| **TestEngineer** | `code/test-engineer.md` | Write tests |
| **CodeReviewer** | `code/reviewer.md` | Code review, security |
| **BuildAgent** | `code/build-agent.md` | Build validation |

### Dataset subagent (.opencode/agent)

| Subagent | File | Purpose |
|---------|------|---------|
| **DatasetTrainer** | `dataset-trainer.md` | Dataset generation & LLM training |

---

## Complete NPC Creation Workflow

### Full command (all 5 phases)

```bash
# Create new NPC
./run_pipeline.sh --npc <npc_id> --target-count 150

# Skip specific phases
./run_pipeline.sh --npc <npc_id> --skip-generation  # Use existing dataset
./run_pipeline.sh --npc <npc_id> --skip-prep         # Use existing splits
./run_pipeline.sh --npc <npc_id> --skip-training   # Use existing checkpoint
./run_pipeline.sh --npc <npc_id> --skip-sync         # Manual sync
./run_pipeline.sh --npc <npc_id> --skip-eval         # Skip eval

# Resume training
./run_pipeline.sh --npc <npc_id> --resume

# Custom hyperparameters
./run_pipeline.sh --npc <npc_id> --epochs 3 --batch-size 1 --save-gguf q4_k_m
```

### Using skills directly

```bash
# Load project skill
skill(name="npc-model-tuning")

# Then delegate to subagent
task(subagent_type="DatasetTrainer", description="Generate dataset for new NPC", prompt="...")
```

### Using MCP for external docs

```bash
# Get NotebookLM docs
context7_resolve-library-id(query="notebooklm api", libraryName="Google NotebookLM")
context7_query-docs(libraryId="/google/notebooklm", query="how to generate JSONL")

# Get Supabase docs
supabase_search_docs(query="best practices for storing chat history")
```

---

## NPC Model Manifest Schema

Each NPC model has a manifest at `exports/npc_models/<npc_id>/npc_model_manifest.json`:

```json
{
  "npc_key": "<npc_id>",
  "artifact_key": "<unique_artifact_name>",
  "supabase_npc_id": "uuid-here",
  "npc_scope": "world_lore|kosmos|maestro_jazz|...",
  "dataset_name": "npc_<npc_id>_dataset",
  "base_model": "unsloth/Llama-3.2-3B-Instruct",
  "training": {
    "epochs": 2,
    "batch_size": 1,
    "learning_rate": 2e-4,
    "lora_r": 16,
    "lora_alpha": 32
  },
  "export": {
    "gguf_quantization": "q4_k_m",
    "sync_to_unity": true,
    "exported_at": "2025-01-15T10:30:00Z"
  }
}
```

---

## Task Management Integration

Use the task-management skill for complex NPC workflows:

```bash
# Create task breakdown
skill(name="task-management")
# Then: delegate to TaskManager for feature breakdown

# Track progress
.bash .opencode/skills/task-management/router.sh status <npc_id>
```

---

## Error Handling

| Error | Solution |
|-------|-----------|
| OOM during training | Reduce batch_size, enable gradient checkpointing |
| Dataset quality low | Run quality_judge.py, raise threshold |
| Training diverges | Reduce learning_rate, check dataset format |
| Sync fails | Check Unity paths, permissions |
| Server not responding | Restart: `# Chat server (use start_servers.sh)` |

---

## Monitoring Commands

```bash
# GPU monitoring
nvidia-smi
watch -n 5 nvidia-smi

# Training progress
tail -f exports/npc_models/<npc_id>/checkpoints/checkpoint-*/trainer_state.json

# Server logs
tail -f server.log

# Supabase logs
supabase get-logs --service auth
supabase get-logs --service api
```

---

## Quick Reference Cards

### Phase 1: Generation
```
Delegate → DatasetTrainer
Skill → notebooklm-npc-datasets
CLI → python scripts/generate_npc_dataset.py --npc <npc_id>
```

### Phase 2: Preparation
```
Delegate → DatasetTrainer  
Skill → npc-model-tuning
CLI → ./run_pipeline.sh --npc <npc_id> --skip-generation --input <raw> --output <processed>
```

### Phase 3: Training
```
Delegate → DatasetTrainer + BuildAgent
Skill → npc-model-tuning
CLI → ./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --datasets <name> --train-file <file>
Check → nvidia-smi
```

### Phase 4: Export
```
Delegate → DevOpsSpecialist
Skill → npc-model-tuning
CLI → ./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --checkpoint <ckpt> --output <gguf>
```

### Phase 5: Evaluation
```
Delegate → TestEngineer + CodeReviewer
Skill → npc-model-tuning
CLI → ./run_pipeline.sh --npc <npc_id> --skip-generation --skip-prep --skip-training --skip-sync --input <file> --npc <npc_id>
Test → http://127.0.0.1:8080/chat_interface.html
```

---

## Files Reference

### Key scripts

| Script | Purpose |
|--------|---------|
| `run_pipeline.sh` | Main orchestrator (bash) |
| `scripts/run_full_npc_pipeline.py` | Main orchestrator (Python) |
| `scripts/generate_npc_dataset.py` | Dataset generation |
| `scripts/prepare_dataset.py` | Dataset preparation |
| `scripts/train_surf_llama.py` | Model training |
| `scripts/convert_lora_to_gguf.py` | GGUF export |
| `scripts/sync_runtime_artifacts.py` | Unity sync |
| `scripts/quality_judge.py` | Quality evaluation |
| `scripts/evaluate_model.py` | Benchmark evaluation |
| `scripts/llm_integrated_server.py` | Model server |
| `scripts/import_notebooklm_jsonl.py` | NotebookLM import |

### Directories

| Directory | Purpose |
|-----------|---------|
| `research/<npc_id>/` | Knowledge sources |
| `datasets/processed/<npc_id>/` | Prepared splits |
| `exports/npc_models/<npc_id>/` | Trained models |
| `exports/npc_models/<npc_id>/checkpoints/` | Training checkpoints |
| `exports/npc_models/<npc_id>/gguf/` | GGUF exports |
| `exports/npc_models/<npc_id>/lora_adapter/` | LoRA adapters |
| `benchmarks/` | Evaluation benchmarks |
| `supabase/` | Database config |

---

*Generated: 2026-04-19*
*Project: Game_Surf NPC Training*
*Pipeline version: 2.0*
