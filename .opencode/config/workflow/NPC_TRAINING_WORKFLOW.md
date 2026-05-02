# NPC Dialogue Training Pipeline - Workflow Automation Manifest

## Canonical Rule

The project-standard dataset path is:

1. NotebookLM creates source-backed JSONL batches in `research/<npc_key>/`
2. `import_notebooklm_jsonl.py` imports them into `datasets/personas/<artifact_key>/<dataset_name>.jsonl`
3. `prepare_dataset.py` creates prepared splits
4. `run_full_npc_pipeline.py --skip-generation` trains, syncs, and evaluates

`scripts/generate_npc_dataset.py` is a legacy local-synthesis generator and must not be treated as the default workflow.

## Approved Commands

### Phase 1 — NotebookLM dataset workflow

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_key> \
  --input research/<npc_key>/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

Prompt-only generation:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_key> \
  --subject "<subject slice>" \
  --batch-id 1 \
  --count 50 \
  --write-prompt-only
```

### Phase 2/3/4/5 — pipeline from imported data

```bash
python scripts/run_full_npc_pipeline.py \
  --npc <npc_key> \
  --skip-generation \
  --model-name unsloth/gemma-4-E4B-it
```

Resume training:

```bash
python scripts/run_full_npc_pipeline.py \
  --npc <npc_key> \
  --skip-generation \
  --resume \
  --model-name unsloth/gemma-4-E4B-it
```

Smoke train:

```bash
python scripts/run_full_npc_pipeline.py \
  --npc <npc_key> \
  --skip-generation \
  --skip-prep \
  --max-steps 2 \
  --epochs 1 \
  --batch-size 1 \
  --skip-sync \
  --skip-eval
```

## Guardrails

- Do not run `run_full_npc_pipeline.py` without `--skip-generation` unless the caller explicitly wants the legacy generator and also passes `--allow-legacy-generation`.
- Do not use `run_big_workflow.sh` for dataset creation. It is now retrain-first and passes `--skip-generation` by default.
- Do not use backgrounded `&` pipeline commands for long-running training.
- Always kill orphaned pipeline processes before starting a new run.

## Relevant Files

- `scripts/run_full_npc_pipeline.py`
- `.codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py`
- `scripts/import_notebooklm_jsonl.py`
- `scripts/prepare_dataset.py`
- `scripts/train_surf_llama.py`
- `docs/PIPELINE_REFERENCE.md`
- `docs/NOTEBOOKLM_DATASET_WORKFLOW.md`
