---
name: "gamesurf-agent"
description: "Use when operating within the Game_Surf project: automate NPC training, run datasets, manage servers, interact with Supabase, and understand the full project architecture."
metadata:
  short-description: "Full Game_Surf project context for OpenCode agent"
---

# Game_Surf Agent

Use this skill when operating in the Game_Surf workspace.

## Canonical NPC Workflow

1. Generate or collect NotebookLM JSONL batches in `research/<npc_key>/`
2. Import and prepare them with the NotebookLM workflow script
3. Train with `run_full_npc_pipeline.py --skip-generation`
4. Validate runtime behavior and memory usage

## Canonical Commands

### Import and prepare NotebookLM batches

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_key> \
  --input research/<npc_key>/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

### Train from imported dataset

```bash
python scripts/run_full_npc_pipeline.py \
  --npc <npc_key> \
  --skip-generation \
  --model-name unsloth/gemma-4-E4B-it
```

### Resume training

```bash
python scripts/run_full_npc_pipeline.py \
  --npc <npc_key> \
  --skip-generation \
  --resume \
  --model-name unsloth/gemma-4-E4B-it
```

### Generate a NotebookLM prompt only

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_key> \
  --subject "<subject slice>" \
  --count 50 \
  --batch-id 1 \
  --write-prompt-only
```

## Safety Rules

- Do not start `run_full_npc_pipeline.py` without `--skip-generation` unless the user explicitly wants the legacy generator and passes `--allow-legacy-generation`.
- Do not treat `scripts/generate_npc_dataset.py` as the default dataset path.
- Check and kill orphaned pipeline processes before starting long-running work.

## Important Paths

- Root: `/root/Game_Surf/Tools/LLM_WSL`
- NPC profiles: `datasets/configs/npc_profiles.json`
- NotebookLM workflow: `.codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py`
- Pipeline orchestrator: `scripts/run_full_npc_pipeline.py`
- Runtime server: `scripts/llm_integrated_server.py`
- Chat UI: `chat_interface.html`

## Validation Targets

- `lora_adapter/` exists
- `npc_model_manifest.json` exists
- runtime chat works
- Supabase memory rows are created
- recall answers prove `memory_used_in_response=true`
