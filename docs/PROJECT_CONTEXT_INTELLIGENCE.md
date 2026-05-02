# Project Context Intelligence

Last updated: 2026-05-02

This file records durable workflow rules for Game_Surf NPC dataset generation, WSL training, runtime validation, and memory testing.

## Canonical Workflow

- Dataset creation is **NotebookLM-direct first**, not model-written first.
- Use:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_key> \
  --input research/<npc_key>/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

- Then train with:

```bash
python scripts/run_full_npc_pipeline.py --npc <npc_key> --skip-generation
```

- `scripts/generate_npc_dataset.py` is legacy local synthesis and must only run by explicit opt-in.
- `run_full_npc_pipeline.py` now blocks Phase 1 legacy generation unless `--allow-legacy-generation` is passed.
- `run_big_workflow.sh` now defaults to `--skip-generation` behavior so it cannot silently start local dataset generation.

## Process Safety Rules

- Always check for orphaned processes before a new training or generation run.
- If you find `run_big_workflow.sh`, `run_full_npc_pipeline.py`, or `generate_npc_dataset.py` still running from an old session, stop them before starting new work.
- Do not background pipeline runs with `&` unless the user explicitly asked for that behavior.

## Durable Lessons

- Smaller 10-example NotebookLM requests are more reliable than broad 50-example requests when the CLI stalls.
- Every system prompt must preserve the literal memory slot:

```text
[MEMORY_CONTEXT: {player_memory_summary}]
```

- Runtime validation is not complete until both are true:
  - `memory_loaded_on_start=true`
  - `memory_used_in_response=true`

## Current Source of Truth

- `docs/PIPELINE_REFERENCE.md`
- `docs/NOTEBOOKLM_DATASET_WORKFLOW.md`
- `scripts/run_full_npc_pipeline.py`
- `.codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py`
- `scripts/import_notebooklm_jsonl.py`
- `scripts/prepare_dataset.py`
- `scripts/train_surf_llama.py`

## Consistency Notes

- `.codex/skills/notebooklm-npc-datasets/...` is the canonical script path.
- `.opencode/skills/notebooklm-npc-datasets/...` now exists as a compatibility wrapper so old references still resolve.
- Gemma 4 is the default training base model:
  - `unsloth/gemma-4-E4B-it`
