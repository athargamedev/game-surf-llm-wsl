---
name: "notebooklm-dataset-workflow"
description: "Automate Game_Surf NotebookLM NPC dataset creation: generate prompts, import JSONL batches, validate/deduplicate, prepare splits, run smoke tests. Use instead of manual steps."
metadata:
  short-description: "Automate NotebookLM NPC dataset workflow"
---

# NotebookLM Dataset Workflow

Use this skill to automate NPC dataset creation for Game_Surf training pipeline.

## Quick Start

```bash
cd /root/Game_Surf/Tools/LLM_WSL
```

## Core Workflow

1. **Generate prompt** → 2. **Query NotebookLM** → 3. **Import to persona** → 4. **Prepare splits** → 5. **Smoke test**

---

## Commands

### Generate Prompt Only

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --subject "early New Orleans jazz, Buddy Bolden, King Oliver, Louis Armstrong" \
  --batch-id 1 \
  --count 50 \
  --write-prompt-only
```

### Query NotebookLM (if authenticated)

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --subject "early New Orleans jazz, Buddy Bolden, King Oliver, Louis Armstrong" \
  --batch-id 1 \
  --count 50 \
  --notebook-id <NOTEBOOK_ID> \
  --run-notebooklm \
  --import \
  --prepare
```

### Import Existing Batch

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --input research/maestro_jazz_instructor/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

### Smoke Training (2 steps)

```bash
conda run --no-capture-output -n unsloth_env python \
  scripts/run_full_npc_pipeline.py \
  --npc maestro_jazz_instructor \
  --skip-generation \
  --skip-prep \
  --target-count 25 \
  --max-steps 2 \
  --epochs 1 \
  --batch-size 1 \
  --no-cache-data \
  --skip-sync \
  --skip-eval
```

---

## Prerequisites

```bash
# Check GPU
conda run -n unsloth_env python -c "import torch; print(torch.cuda.is_available())"

# Check Supabase (if needed)
supabase status

# List notebooks (if using NotebookLM)
notebooklm list
```

---

## Quality Gates

- 50 examples → aim 45+ valid unique
- 25 examples → aim 22+ valid unique
- No duplicate questions
- No duplicate answers
- No AI/model/dataset mentions in assistant text

---

## Memory Slot

Every system message MUST include:
```
[MEMORY_CONTEXT: {player_memory_summary}]
```

Leave slot literal - runtime Supabase memory will be inserted later.

---

## Output Paths

| Stage | Path |
|-------|------|
| NotebookLM JSONL | `research/<npc_key>/notebooklm_batch_XX.jsonl` |
| Persona dataset | `datasets/personas/<artifact_key>/<dataset_name>.jsonl` |
| Prepared splits | `datasets/processed/<dataset_name>/` |
| LoRA adapter | `exports/npc_models/<artifact_key>/lora_adapter/` |
| Manifest | `exports/npc_models/<artifact_key>/npc_model_manifest.json` |

---

## References

- Prompt template: `references/notebooklm_prompt.md`
- Workflow script: `.codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py`