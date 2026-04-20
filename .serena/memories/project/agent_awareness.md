# Game_Surf Agent Awareness

Comprehensive context for an AI agent to understand and operate within this project.

## Project Overview

**Mission**: Automate NPC training datasets → generate LoRA adapters → link to Unity game → integrate with Supabase for player data and NPC memories.

**Architecture**:
- Dataset generation (NotebookLM/local) → Training (Unsloth/Llama) → Export (GGUF) → Runtime (chat UI + LLM server)
- Supabase for persistent player data, NPC memories, dialogue history

## Directory Layout

```
/root/Game_Surf/Tools/LLM_WSL/
├── scripts/              # Core automation scripts
├── datasets/             # Raw and processed datasets
├── exports/             # Trained models and adapters
├── research/            # NPC knowledge sources
├── supabase/             # Database migrations and functions
├── .codex/skills/       # Project-specific skills
├── .claude/skills/      # Global Claude skills
├── chat_interface.html  # NPC chat UI
├── run_chat_server.py   # Chat HTTP server
└── run_pipeline.sh     # Pipeline wrapper
```

## Available Skills

| Skill | Path | Triggers | Purpose |
|-------|------|----------|---------|
| notebooklm | /root/.claude/skills/notebooklm/SKILL.md | /notebooklm, "use notebooklm" | Full NotebookLM API control |
| notebooklm-npc-datasets | /root/.claude/skills/notebooklm-npc-datasets/SKILL.md | "NotebookLM direct JSONL batches" | NPC dataset workflow automation |
| notebooklm-npc-datasets | .codex/skills/notebooklm-npc-datasets/SKILL.md | Same | WSL-specific NPC dataset automation |
| npc-model-tuning | .codex/skills/npc-model-tuning/SKILL.md | npc-model-tuning | Local LLM training and tuning |
| playwright-cli | .claude/skills/playwright-cli/SKILL.md | playwright-cli | Browser automation |

## Core Scripts

### Pipeline & Training
- `scripts/run_full_npc_pipeline.py` - End-to-end NPC pipeline orchestrator
- `scripts/train_surf_llama.py` - Core training with Unsloth/LoRA
- `scripts/prepare_dataset.py` - Dataset preparation (ChatML, splits)
- `scripts/export_unsloth_checkpoint.py` - Export to GGUF

### Dataset Generation
- `scripts/generate_npc_dataset.py` - NPC dataset generation
- `scripts/import_notebooklm_jsonl.py` - Import NotebookLM JSONL
- `.codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py` - Full workflow

### Server & Runtime
- `run_chat_server.py` - Chat HTTP server (port 8080)
- `scripts/llm_integrated_server.py` - LLM backend server (port 8000)
- `scripts/start_servers.sh` - Tmux-based server startup

### Utilities
- `scripts/god_memory_worker.py` - Memory embedding
- `scripts/generate_dialogue_relation_graph.py` - Build dialogue graph
- `scripts/sync_runtime_artifacts.py` - Sync to Unity

## NPC System

### Registered NPCs (6)
- `maestro_jazz_instructor` → "The Maestro" (Jazz History)
- `kosmos_instructor` → "Professor Kosmos" (Greek Mythology)
- `llm_instructor` → "Professor LoRA" (LoRA Fine-tuning)
- `brazilian_history` → "Professor Pedro" (Brazilian History)
- `marvel_comics_instructor` → "MarvelOracle" (Marvel Comics)
- `movies_instructor` → "Professor Reel" (Cinema/Film Studies)

### Adding a New NPC
1. Add profile to `datasets/configs/npc_profiles.json`
2. Add button to `chat_interface.html` (`.npc-option`)
3. Add to `npcNames` JavaScript object
4. Generate dataset → Train → Export
5. Start servers via `scripts/start_servers.sh`

### Chat Interface
- URL: http://localhost:8080/chat_interface.html
- Endpoints: /session/start, /session/end, /reload-model, /npc-models, /status

## Supabase Integration

### Key Tables
- `player_profiles` - Player identities
- `dialogue_sessions` - Session metadata
- `dialogue_turns` - Individual messages
- `npc_memories` - Per-player NPC memories
- `player_memory_embeddings` - Vector embeddings (384-dim)
- `dialogue_relation_terms` / `relation_graph_nodes/edges` - Dialogue relationships

### Key Functions (RPCs)
- `summarize_dialogue_session()` - Generate session summary
- `get_player_npc_memory()` - Retrieve NPC memory
- `generate_dialogue_relation_graph()` - Build relationship graph

### HTTP Endpoints
- `/dialogue-relations` - Graph data
- `/summarize-memory` - Memory summarization

### Environment Variables
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## How to...

### Start Servers
```bash
cd /root/Game_Surf/Tools/LLM_WSL
bash scripts/start_servers.sh
# Or manually:
tmux new-session -d -s chat-server "python run_chat_server.py"
tmux new-session -d -s llm-server "conda run -n unsloth_env python scripts/llm_integrated_server.py"
```

### Run Full NPC Pipeline
```bash
cd /root/Game_Surf/Tools/LLM_WSL
./run_pipeline.sh --npc <npc_id> --skip-generation
```

### Generate Dataset
```bash
conda run -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc <npc_id> --subject "<subject>" --count 50 \
  --write-prompt-only
```

### Add New NPC to Chat UI
See `datasets/configs/npc_profiles.json` for profile format. Edit:
- `chat_interface.html`: Add `.npc-option` div
- `chat_interface.html`: Add to `npcNames` object

## Important Constraints

- Servers MUST run in tmux (not foreground) to survive timeouts
- Default to LoRA-only training (no per-NPC GGUF unless requested)
- Keep prototype subjects narrow and concrete
- Quality gate: 45+ valid unique for 50-example batch

## Project Memories

- `task_completion/notebooklm_npc_datasets` - Previous successful session
- `suggested_commands` - Recommended commands for common tasks
- `tech_stack` - Technology stack details
- `system_prompt` - Claude system prompt context