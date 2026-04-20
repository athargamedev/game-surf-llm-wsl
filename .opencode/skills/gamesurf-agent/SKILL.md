---
name: "gamesurf-agent"
description: "Use when operating within the Game_Surf project: automate NPC training, run datasets, manage servers, interact with Supabase, and understand the full project architecture. Provides full context awareness for the NPC training system with LoRA, Supabase, and chat UI."
metadata:
  short-description: "Full Game_Surf project context for OpenCode agent"
---

# Game_Surf Agent

Use this skill when operating in the Game_Surf workspace. It provides complete context awareness.

## Project Purpose

**Mission**: Automate NPC training datasets → generate LoRA adapters → link to Unity game → integrate with Supabase for player data and NPC memories.

**Architecture**:
```
Dataset Generation (NotebookLM/local) 
  → Training (Unsloth/Llama) 
    → Export (GGUF) 
      → Runtime (chat UI + LLM server)
        → Supabase (player data, NPC memories)
```

## Important Paths

Always use these paths:
- **Root**: `/root/Game_Surf/Tools/LLM_WSL`
- **Datasets**: `datasets/personas/<npc_id>/`
- **Exports**: `exports/npc_models/<npc_id>/`
- **NPC profiles**: `datasets/configs/npc_profiles.json`
- **Chat UI**: `chat_interface.html`

## Registered NPCs

Currently available (6):
| NPC ID | Display Name | Subject |
|-------|-----------|---------|
| maestro_jazz_instructor | The Maestro | Jazz History |
| kosmos_instructor | Professor Kosmos | Greek Mythology |
| llm_instructor | Professor LoRA | LoRA Fine-tuning |
| brazilian_history | Professor Pedro | Brazilian History |
| marvel_comics_instructor | MarvelOracle | Marvel Comics |
| movies_instructor | Professor Reel | Cinema/Film Studies |

## Core Skills Available

This agent can invoke these skills when needed:

| Skill | Trigger | Purpose |
|-------|---------|---------|
| notebooklm | /notebooklm | Full NotebookLM API control |
| notebooklm-npc-datasets | "NotebookLM direct JSONL batches" | NPC dataset automation |
| npc-model-tuning | npc-model-tuning | Local LLM training |
| playwright-cli | playwright-cli | Browser automation |

## Core Commands

### Start Servers (ALWAYS use tmux)
```bash
cd /root/Game_Surf/Tools/LLM_WSL
bash scripts/start_servers.sh  # Starts chat-server (8080) and llm-server (8000)
```

**Troubleshooting:**
- If LLM server fails to start, check PYTHONPATH is set: `PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH`
- Server needs ~40 seconds to load the model - be patient after starting
- Check status: `curl http://127.0.0.1:8000/status`

### Run Full NPC Pipeline
```bash
cd /root/Game_Surf/Tools/LLM_WSL
./run_pipeline.sh --npc <npc_id> --skip-generation
```

### Generate Dataset
```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_id> --subject "<subject>" --count 50 --write-prompt-only
```

### Check GPU
```bash
conda run --no-capture-output -n unsloth_env python -c "import torch; print(torch.cuda.is_available())"
```

## How to Add a New NPC

### Step 1: Add Profile
Edit `datasets/configs/npc_profiles.json` - add new profile under `profiles`:
```json
"new_npc_id": {
  "display_name": "Professor X",
  "npc_scope": "instructor",
  "artifact_key": "new_npc_id",
  "dataset_name": "new_npc_dataset",
  "subject": "Topic description",
  ...
}
```

### Step 2: Add to Chat UI
Edit `chat_interface.html`:
1. Add to `npcNames`:
```javascript
'new_npc_id': 'Display Name',
```
2. Add button:
```html
<div class="npc-option" data-npc="new_npc_id">Label</div>
```

### Step 3: Train
```bash
./run_pipeline.sh --npc new_npc_id
```

## Supabase Integration

### Key Tables
- `player_profiles` - Player identities
- `dialogue_sessions` - Session metadata
- `dialogue_turns` - Individual messages
- `npc_memories` - Per-player NPC memories
- `player_memory_embeddings` - Vector embeddings (384-dim)

### Key RPCs
- `summarize_dialogue_session()` - Generate session summary
- `get_player_npc_memory()` - Retrieve NPC memory
- `generate_dialogue_relation_graph()` - Build graph

### Environment Variables
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## Context Awareness

### Scripts Available
- **Pipeline**: `scripts/run_full_npc_pipeline.py`, `run_pipeline.sh`
- **Training**: `scripts/train_surf_llama.py`, `scripts/export_unsloth_checkpoint.py`
- **Dataset**: `scripts/generate_npc_dataset.py`, `scripts/prepare_dataset.py`, `scripts/import_notebooklm_jsonl.py`
- **Server**: `run_chat_server.py`, `scripts/llm_integrated_server.py`, `scripts/start_servers.sh`
- **Memory**: `scripts/god_memory_worker.py`, `scripts/generate_dialogue_relation_graph.py`

### Chat Interface
- **URL**: http://localhost:8080/chat_interface.html
- **Endpoints**: /session/start, /session/end, /reload-model, /npc-models, /status
- **Ports**: chat (8080), llm (8000)

## Important Constraints

1. **ALWAYS use tmux for servers** - foreground servers will be killed on timeout
2. **LoRA-only by default** - don't export per-NPC GGUF unless requested
3. **Keep subjects narrow** - quality over breadth
4. **Quality gate**: 45+ valid unique for 50-example batch

## Memory Locations

For context, read these memories:
- `project/agent_awareness` - Full project overview
- `project/skills_catalog` - Skills catalog
- `task_completion/notebooklm_npc_datasets` - Previous session
- `suggested_commands` - Common commands
- `tech_stack` - Technology stack

## References

- NPC profiles: `datasets/configs/npc_profiles.json`
- Chat UI: `chat_interface.html`
- Supabase docs: `docs/SUPABASE_INTEGRATION.md`
- Pipeline docs: `docs/PIPELINE_REFERENCE.md`

---

## Troubleshooting Guide

### Server Issues

**Problem**: LLM server fails to start with `ModuleNotFoundError: No module named 'scripts.supabase_client'`

**Solution**: Set PYTHONPATH before starting:
```bash
export PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH
# Or use start_servers.sh which handles this automatically
```

**Problem**: Chat interface shows "Uncaught SyntaxError: Identifier 'supabase' has already been declared"

**Solution**: The Supabase CDN declares a global `supabase` variable. Rename the local variable to `supabaseClient` in `chat_interface.html`:
```javascript
let supabaseClient = null;  // Instead of: let supabase = null
```

**Problem**: LLM server takes too long to respond or times out

**Solution**: Model needs ~40 seconds to load. The server is working - just wait. Check with:
```bash
curl http://127.0.0.1:8000/status
```

---

### Dataset Generation Issues

**Problem**: NotebookLM returns single JSON object instead of JSONL

**Solution**: Parse the response - the JSONL is in the `answer` field:
```python
import json
with open('research/<npc>/notebooklm_batch_01.jsonl', 'r') as f:
    data = json.loads(f.read().strip())
# Save the answer field as the actual JSONL file
with open('research/<npc>/notebooklm_batch_01_fixed.jsonl', 'w') as f:
    f.write(data['answer'])
```

**Problem**: Import fails with "messages must contain exactly 3 entries"

**Solution**: The JSONL file wasn't properly formatted. After fixing above, run import with the corrected file.

---

### Pipeline Issues

**Problem**: Pipeline can't find prepared dataset

**Solution**: Folder naming matters. Pipeline expects:
- `datasets/processed/<npc_id>_dataset/` (NOT `datasets/processed/<npc_id>/`)
- Files: `train.jsonl`, `validation.jsonl`, `test.jsonl`

---

### Chat Interface Issues

**Problem**: Chat interface can't connect to LLM server

**Solution**: Ensure both servers are running:
```bash
# Check ports
ss -tlnp | grep -E "8080|8000"

# Check status
curl http://127.0.0.1:8000/status
curl http://127.0.0.1:8080/chat_interface.html
```

**Problem**: NPC doesn't appear in chat interface dropdown

**Solution**: Add to both:
1. `npcNames` object in chat_interface.html
2. NPC selector div in chat_interface.html