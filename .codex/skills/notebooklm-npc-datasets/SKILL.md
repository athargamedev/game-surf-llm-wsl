---
name: "notebooklm-npc-datasets"
description: "Use when automating Game_Surf NotebookLM-direct NPC dataset creation in WSL: generate concrete NotebookLM prompts, query/import JSONL batches, enforce dynamic memory slots, validate/deduplicate examples, prepare training splits, and run small LoRA smoke tests without asking the user to manually run each step."
metadata:
  short-description: "Automate NotebookLM NPC dataset batches"
---

# NotebookLM NPC Datasets

Use this skill from the Game_Surf WSL workspace root:

```bash
cd /root/Game_Surf/Tools/LLM_WSL
```

This skill owns the new prototype dataset workflow:

```text
NotebookLM direct JSONL batches
→ strict importer with [MEMORY_CONTEXT: {player_memory_summary}]
→ dataset_registry.json update
→ prepare_dataset.py validation/dedup/splits
→ optional tiny LoRA smoke training
```

## Core Rules

- Do not ask the user to manually run NotebookLM steps when `notebooklm` is installed and authenticated. Try the automated path first.
- Keep prototype subjects simple and concrete. Prefer narrow batches like `early New Orleans jazz, King Oliver, Louis Armstrong` over broad prompts like `jazz history`.
- Use NotebookLM as a source-aware planner, not just a text generator. The prompt should make it inspect loaded sources/project notes, plan coverage internally, fact-check named entities, and output JSONL only.
- Generate/import 50 examples as the normal prototype batch. Use 25 only for smoke checks, narrow repairs, or quick regeneration after validation failures.
- Every system message must include the literal memory slot:

```text
[MEMORY_CONTEXT: {player_memory_summary}]
```

- Leave the slot literal in training data. Runtime Supabase memory will be inserted or appended later.
- Default to LoRA-only training. Do not export per-NPC GGUF unless explicitly requested.
- Use direct orchestrator invocation for training smoke tests; `./run_pipeline.sh` can hide CUDA in this sandbox.
- Keep each stage file-in/file-out so future Google Colab or external MCP processing jobs can take over training/export without changing project layout.

## Bundled Helper

Use the script instead of hand-writing commands whenever possible:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py --help
```

Common dry prompt generation:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --subject "early New Orleans jazz, Buddy Bolden, King Oliver, Louis Armstrong" \
  --batch-id 1 \
  --count 50 \
  --write-prompt-only
```

Automated NotebookLM query if an existing notebook is available:

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

Import existing batch files:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --input research/maestro_jazz_instructor/notebooklm_batch_*.jsonl \
  --import \
  --prepare
```

When importing existing batches, pass all intended batch files together. The importer writes exactly the accepted inputs into the persona dataset, so omitting an older batch can replace the dataset with only the new batch.

Optional tiny smoke training after prepare:

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
  --grad-accum 1 \
  --no-cache-data \
  --skip-sync \
  --skip-eval
```

## Workflow

1. Check prerequisites:
   - `conda run --no-capture-output -n unsloth_env python -c "import torch; print(torch.cuda.is_available(), torch.cuda.device_count())"`
   - `supabase status -o env` if Supabase state matters.
   - `notebooklm list` if using automated NotebookLM.
2. Generate or query a NotebookLM direct JSONL batch with a concrete subject.
3. Run importer dry-run first. Healthy result should have high `Valid unique`, low `Duplicates`, and `Invalid: 0`.
4. Import for real only after dry-run succeeds.
5. Prepare the dataset and inspect dedup output.
6. Run a 2-step LoRA smoke test only if prepare preserves enough unique examples. Keep dataset cache disabled during prototype iteration.
7. Keep runtime using the shared base GGUF plus Supabase memory; do not create a per-NPC GGUF by default.

## Quality Gates

- For a 50-example batch, aim for at least 45 valid unique examples. For a 25-example smoke batch, aim for at least 22 valid unique examples.
- If duplicate count is high, regenerate with a narrower subject and stricter "no duplicate questions or answers" language.
- If invalid examples are caused by missing memory slot, use the importer; it can inject the slot into otherwise valid system prompts.
- If assistant text mentions AI/model/dataset/prompt/system prompt, reject and regenerate.

## Post-Training: Add to Chat Interface & Start Servers

After training completes successfully, automatically:
1. Add the new NPC to `chat_interface.html` buttons
2. Start both servers in tmux (non-blocking)

### Step 1: Add NPC to Chat Interface

Add to `.npc-selector` div (after `<div class="npc-option" data-npc="kosmos_instructor">`):
```html
<div class="npc-option" data-npc="llm_instructor">
    🤖 LoRA Instructor
</div>
```

Add to `npcNames` JavaScript object:
```javascript
'llm_instructor': 'Professor LoRA',
```

### Step 2: Start Servers Gracefully

CRITICAL: Never run servers in foreground - they will be killed when command times out. Use tmux:

```bash
# Kill any existing sessions
tmux kill-session -t chat-server 2>/dev/null
tmux kill-session -t llm-server 2>/dev/null

# Start chat server (port 8080)
tmux new-session -d -s chat-server "cd /root/Game_Surf/Tools/LLM_WSL && python run_chat_server.py"

# Start LLM backend server (port 8000)
tmux new-session -d -s llm-server "cd /root/Game_Surf/Tools/LLM_WSL && conda run --no-capture-output -n unsloth_env python scripts/llm_integrated_server.py"

# Verify they're running
sleep 3 && tmux list-sessions
```

Or use the helper script:
```bash
cd /root/Game_Surf/Tools/LLM_WSL && bash scripts/start_servers.sh
```

## External Job Boundary

Keep this layout stable for Colab/MCP automation later:

- NotebookLM output: `research/<npc_key>/notebooklm_batch_XX.jsonl`
- Imported persona dataset: `datasets/personas/<artifact_key>/<dataset_name>.jsonl`
- Prepared train/validation splits: `datasets/processed/<dataset_name>/`
- Trained adapter return path: `exports/npc_models/<artifact_key>/lora_adapter/`
- Runtime manifest: `exports/npc_models/<artifact_key>/npc_model_manifest.json`

External jobs should consume one stage and write the next stage, not invent alternate paths.

## References

- Prompt template and batch subject examples: `.codex/skills/notebooklm-npc-datasets/references/notebooklm_prompt.md`
- Project importer: `scripts/import_notebooklm_jsonl.py`
- Workflow doc: `docs/NOTEBOOKLM_DATASET_WORKFLOW.md`
- Pipeline reference: `docs/PIPELINE_REFERENCE.md`
