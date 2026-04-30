---
name: "notebooklm-dataset-workflow"
description: "Automate Game_Surf NotebookLM NPC dataset creation: generate prompts, import JSONL batches, validate/deduplicate, prepare splits, run smoke tests. Use instead of manual steps."
metadata:
  short-description: "Automate NotebookLM NPC dataset workflow"
---

# NotebookLM Dataset Workflow

Use this workflow for the **canonical new NPC path**. NotebookLM creates source-backed JSONL examples, the importer/prepare scripts build training splits, and WSL-native Unsloth training consumes those splits. Local LLM synthesis is a legacy fallback, not the normal workflow.

## Quick Start

```bash
cd /root/Game_Surf/Tools/LLM_WSL
```

## Core Workflow

1. **Generate prompt** → 2. **Query NotebookLM** → 3. **Import to persona** → 4. **Prepare splits** → 5. **Smoke test**

## Canonical Step-by-Step

1. **Pick/create notebook and verify NPC profile**
   - Confirm NotebookLM notebook matches the subject.
   - Confirm `npc_key`, `artifact_key`, and `dataset_name` in `datasets/configs/npc_profiles.json`.
   - Example notebook: `Brazilian History Research` for `brazilian_history`.

2. **Generate NotebookLM-direct JSONL batches**
   - Prefer NotebookLM-direct for new NPCs.
   - If a 50-example ask times out, split into 10-example batches.
   - Proven example: `brazilian_history` succeeded with 5 narrowed batches of 10 after a full 50-example ask timed out.

3. **Import and prepare dataset**
   - Import all batch files, then prepare splits.
   - Accept `45+` valid unique examples for a 50-example target.
   - Require the literal memory placeholder in every system message:
     ```
     [MEMORY_CONTEXT: {player_memory_summary}]
     ```

4. **Train LoRA model**
   - Once processed splits exist, run the pipeline with `--skip-generation`.
   - If the prepared dataset stays under ~500 examples, use small-dataset settings.
   - Stop the runtime LLM server first if VRAM is close to full.

5. **Validate runtime readiness**
   - Check `lora_adapter/` and `npc_model_manifest.json`.
   - Restart with `python scripts/server_manager.py start --auto` or `python scripts/server_manager.py restart --session llm-server`.
   - Add the NPC to `/test-10-player`, then validate chat + Supabase memory creation.

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

### Brazilian History Example (proven path)

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc brazilian_history \
  --input research/brazilian_history/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

Result snapshot:
- Notebook: `Brazilian History Research`
- Generation strategy: 5 narrowed batches of 10
- Import: `49 valid unique`, avg quality `0.883`, memory slot rate `1.0`
- Prepared splits: `45 train / 4 validation`

### Stricter Import And Prep Gates

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --input research/maestro_jazz_instructor/notebooklm_batch_*.jsonl \
  --import \
  --prepare \
  --min-quality 0.78 \
  --min-task-examples 8
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
- Heuristic import quality should average roughly `0.80+`
- Keep both `teaching` and `quiz` represented after filtering
- Preparation can now enforce minimum per-task coverage with `--min-task-examples`
- Smaller 10-example NotebookLM batches are the preferred fallback when 50-example asks time out

---

## Memory Slot

Every system message MUST include:
```
[MEMORY_CONTEXT: {player_memory_summary}]
```

Leave slot literal - runtime Supabase memory will be inserted later.

Do not paraphrase or rename this placeholder.

## Training Hand-off

```bash
python scripts/run_full_npc_pipeline.py --npc brazilian_history --skip-generation
```

Tips:
- Under ~500 prepared examples, use small-dataset settings.
- If runtime inference is already holding VRAM, stop the LLM server before training.

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
- Audit command: `python scripts/audit_dataset_workflow.py --format markdown --output docs/dataset_workflow_audit.md`
