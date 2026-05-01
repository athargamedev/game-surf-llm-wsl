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
- Keep durable project lessons in `docs/PROJECT_CONTEXT_INTELLIGENCE.md` when workflow behavior changes.
- For browser-facing runtime tests, restart servers outside the Codex sandbox so `localhost` in the user's browser sees the updated app.

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
  --player-id workflow_probe \
  --cross-session-memory
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
- Memory: Phase 1 `/session/start` -> `/chat` -> `/session/end` creates memory; Phase 2 starts a new session, loads memory, and recall answers actually use loaded memory.
- Dialogue benchmark: `scripts/run_dialogue_benchmark.py --npc <npc_id>` passes fixed factual, redirect, and memory cases before training parameters are compared.
- Supabase diagnostics: `scripts/repair_memory_state.py --json` is clean or has understood residual issues before using memory metrics as tuning evidence.

## `/test-10-player` Gate

Use `http://127.0.0.1:8000/test-10-player` for multi-NPC operational proof after adding a trained NPC to the page. Cross-session mode is the important memory test:

```text
Phase 1: message 1 -> end session -> memory row exists
Phase 2: new session -> memory_loaded_on_start=true -> message 2 answer uses memory
```

Treat `memory_loaded_on_start=true` as necessary but not sufficient. The test must also report `memory_used_in_response=true`; otherwise Supabase loaded memory but the model ignored it.

Use unique per-run player IDs for automated tests so old `TestPlayer_*` memory rows do not contaminate new results. Keep slower pacing for LoRA swaps and memory processing: message delay 5s, identity probe 4s, player delay 4s, NPC switch 8s, phase memory delay 35s.

## Reporting

Read `summary.md` first, then inspect `trace.json` for details. Compare consecutive run folders for the same NPC before changing training hyperparameters; dataset quality problems should be fixed before increasing training length.
