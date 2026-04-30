---
name: "gamesurf-workflow-trace"
description: "Use when analyzing, testing, or improving the full Game_Surf NPC dataflow across NotebookLM dataset batches, import/prepare gates, LoRA training metrics, runtime chat validation, Supabase memory persistence, and Unity readiness. Coordinates the NotebookLM and model-tuning skills and records traceable workflow run reports."
metadata:
  short-description: "Trace Game_Surf NPC workflow runs"
---

# Game_Surf Workflow Trace

Use this skill from the WSL workspace root:

```bash
cd /root/Game_Surf/Tools/LLM_WSL
```

This skill coordinates the end-to-end evidence loop:

```text
NotebookLM sources
-> JSONL batches
-> persona dataset
-> processed train/validation splits
-> WSL Unsloth LoRA training report
-> adapter/manifest artifacts
-> WSL runtime reload/chat
-> Supabase session + memory proof
```

## Core Rules

- Use `notebooklm-npc-datasets` for NotebookLM prompts, batch import, dedup, and preparation.
- Use `npc-model-tuning` for WSL CUDA/VRAM checks, Unsloth training, artifact validation, runtime reloads, and chat testing.
- Always write a trace report before claiming a workflow step is complete.
- Use `npc_id` for runtime calls. Do not use `npc_key` in `/chat` or `/reload-model` payloads.
- Keep `/root/Game_Surf/Tools/LLM_WSL` as the training source of truth.
- Preserve Supabase memory tables and columns. Validate the live contract before proposing schema changes.
- Do not require LM Studio for the canonical workflow. Dataset generation is NotebookLM-backed and training runs inside WSL with Unsloth.

## Tracker Command

Use the tracker to collect evidence into:

```text
reports/workflow_runs/<npc_id>/<run_id>/
```

Common full snapshot without live chat/session writes:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_id> \
  --stage all \
  --skip-live-probe
```

Runtime and memory proof after servers are running:

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_id> \
  --stage runtime \
  --reload-model

conda run --no-capture-output -n unsloth_env python \
  scripts/track_workflow_run.py \
  --npc <npc_id> \
  --stage memory \
  --player-id workflow_probe
```

Narrow stage checks:

```bash
conda run --no-capture-output -n unsloth_env python scripts/track_workflow_run.py --npc <npc_id> --stage notebooklm
conda run --no-capture-output -n unsloth_env python scripts/track_workflow_run.py --npc <npc_id> --stage import
conda run --no-capture-output -n unsloth_env python scripts/track_workflow_run.py --npc <npc_id> --stage prepare
conda run --no-capture-output -n unsloth_env python scripts/track_workflow_run.py --npc <npc_id> --stage train
```

## Gates

- NotebookLM: batch files parse, importer dry-run succeeds, examples are concrete and source-backed.
- Import: valid unique examples are high, duplicates are low, assistant text has no prompt/model/dataset leakage.
- Prepare: train and validation splits exist, task coverage remains usable, memory slot rate is `1.0`.
- Train: training report exists, eval loss is recorded, overfitting flag is checked.
- Artifact: manifest exists and adapter files are present under the resolved artifact key.
- Runtime: `/health`, `/status`, `/npc-models`, and LoRA status respond.
- Memory: `/session/start` -> `/chat` -> `/session/end` succeeds and history/memory endpoints return useful evidence.

## Reporting

Read `summary.md` first, then inspect `trace.json` for details. Compare consecutive run folders for the same NPC before changing training hyperparameters; dataset quality problems should be fixed before increasing training length.
