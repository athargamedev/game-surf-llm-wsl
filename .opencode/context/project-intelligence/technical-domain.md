<!-- Context: project-intelligence/technical | Priority: critical | Version: 1.3 | Updated: 2026-04-22 -->

# Technical Domain

> Document the technical foundation, architecture, and key decisions.

## Quick Reference

- **Purpose**: Understand how the project works technically
- **Update When**: New features, refactoring, tech stack changes
- **Audience**: Developers, DevOps, technical stakeholders

## Primary Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | 3.10+ | Required for Unsloth, transformers |
| Framework | Unsloth | Latest | 6GB VRAM fine-tuning on RTX 3060 |
| Database | Supabase | PostgreSQL 15 | Player memories, dialogue history |
| Infrastructure | Local GPU | RTX 3060 | Cost-effective LLM training |
| Key Libraries | transformers, trl, llama.cpp, datasets | Latest | Core ML stack |

# Technical Domain

> Document the technical foundation, architecture, and key decisions.

## Quick Reference

- **Purpose**: Understand how the project works technically
- **Update When**: New features, refactoring, tech stack changes
- **Audience**: Developers, DevOps, technical stakeholders

## Primary Stack

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Language | Python | 3.10+ | Required for Unsloth, transformers |
| Framework | Unsloth | Latest | 6GB VRAM fine-tuning on RTX 3060 |
| Database | Supabase | PostgreSQL 15 | Player memories, dialogue history |
| Infrastructure | Local GPU | RTX 3060 | Cost-effective LLM training |
| Key Libraries | transformers, trl, llama.cpp, datasets | Latest | Core ML stack |

## Architecture Pattern

```
Type: Agent-based (LLM Fine-tuning Pipeline)
Pattern: Research → Dataset → Train → Export → Deploy
Diagram: scripts/run_full_npc_pipeline.py (5-phase pipeline)
```

### Why This Architecture?

Game_Surf trains personalized NPCs for Unity games. The agent-based pipeline:
1. **Research** - NotebookLM or local LLM generates domain knowledge
2. **Dataset** - Transforms research into ChatML training examples
3. **Train** - Fine-tunes Llama 3.2 via Unsloth (6GB VRAM on RTX 3060)
4. **Export** - Converts LoRA to GGUF for llama.cpp
5. **Deploy** - Syncs to Unity runtime with player memory integration

**Alternatives considered**:
- SaaS APIs (e.g., OpenAI fine-tuning) - Too expensive per request
- Full model training - Requires 24GB+ VRAM
- RAG only - No persistent NPC personality

## Project Structure

```
[Project Root]
├── scripts/               # Pipeline scripts (20 files)
├── supabase/             # Database config, migrations
├── datasets/             # Raw + processed training data
│   └── processed/<npc_id>/
├── exports/              # Trained models
│   └── npc_models/<npc_id>/
├── research/             # Knowledge sources per NPC
├── benchmarks/          # Evaluation benchmarks
├── chat_interface.html   # Test UI
└── run_chat_server.py  # Local chat server
```

**Key Directories**:
- `scripts/` - All pipeline orchestrators and utilities
- `supabase/` - Database migrations, functions, config
- `datasets/` - JSONL files (train.jsonl, validation.jsonl, test.jsonl)
- `exports/npc_models/` - Trained LoRA adapters + GGUF files

## Key Technical Decisions

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Unsloth for fine-tuning | 4x faster, 70% less VRAM | RTX 3060 training viable |
| LoRA instead of full model | 100MB vs 7GB adapters | Fast iteration |
| GGUF for Unity export | llama.cpp compatible | Cross-platform inference |
| NotebookLM for research | Automated knowledge extraction | Scalable NPC profiles |
| JSONL dataset format | HuggingFace native | Easy dataset loading |

See `decisions-log.md` for full decision history with alternatives.

## Integration Points

| System | Purpose | Protocol | Direction |
|--------|---------|----------|-----------|
| Unity Runtime | NPC dialogue inference | GGUF + llama.cpp | Outbound |
| Supabase | Player memories, dialogue history | PostgreSQL | Internal |
| NotebookLM | Research & knowledge extraction | MCP CLI | Outbound |
| Local LLM (LM Studio) | Fallback research generation | HTTP | Outbound |
| HuggingFace Hub | Model hub access | HTTPS | Outbound |

## Canonical New NPC Workflow

Prefer the **NotebookLM-direct** path for new NPC creation when `generate_npc_dataset.py` still depends on local LLM synthesis.

### Step-by-step

1. **Pick/create notebook and verify NPC profile**
   - Confirm notebook scope matches the NPC subject.
   - Confirm `npc_key`, `artifact_key`, and `dataset_name` in `datasets/configs/npc_profiles.json`.
   - Example: NotebookLM notebook `Brazilian History Research` for `brazilian_history` → `brazilian_history_instructor`.

2. **Generate NotebookLM-direct JSONL batches**
   - Use the NotebookLM-direct workflow script.
   - If a 50-example ask times out, switch to smaller 10-example batches.
   - Proven case: the full 50-example ask timed out; `brazilian_history` succeeded with 5 narrowed batches of 10.

3. **Import and prepare dataset**
   - Import all batch JSONL files, deduplicate, and prepare splits.
   - Accept `45+` valid unique examples for a 50-example target.
   - Require literal memory slot in every system prompt:
     ```
     [MEMORY_CONTEXT: {player_memory_summary}]
     ```
   - `brazilian_history` import result: 49 valid unique, avg quality `0.883`, memory slot rate `1.0`.
   - Prepared splits: `45 train / 4 validation`.

4. **Train LoRA model**
   - Train with `scripts/run_full_npc_pipeline.py --npc <npc_key> --skip-generation` once processed splits exist.
   - If prepared splits stay under ~500 examples, use small-dataset training settings.
   - If VRAM is near full, stop the runtime LLM server before training.
   - `brazilian_history` succeeded on `unsloth/Llama-3.2-3B-Instruct` with LoRA-only artifacts.

5. **Validate artifacts and manifest**
   - Check `exports/npc_models/<artifact_key>/` for `lora_adapter/` and `npc_model_manifest.json`.
   - Confirm manifest paths point at the prepared dataset and artifact key.

6. **Restart servers properly**
   - Preferred start: `python scripts/server_manager.py start --auto`
   - Targeted restart: `python scripts/server_manager.py restart --session llm-server`

7. **Test via chat and `/test-10-player`**
   - Add the NPC to `/test-10-player` before final runtime validation.
   - Validate direct chat responses first, then run `/test-10-player`.

8. **Confirm Supabase memories persist**
   - Final operational proof is: `/test-10-player` succeeds **and** Supabase NPC memories are created.
   - `brazilian_history_instructor` passed runtime validation after being added to `/test-10-player`.

### Decision Tips

- Prefer NotebookLM-direct over default synthetic generation for new NPC creation.
- Use 10-example NotebookLM batches when larger asks time out.
- Accept `45+` valid unique examples for a 50-example target if coverage is still good.
- Keep the memory placeholder literal: `[MEMORY_CONTEXT: {player_memory_summary}]`
- Use small-dataset settings automatically or explicitly when under ~500 examples.
- Stop the runtime LLM server before training if VRAM headroom is low.
- Restart with `start --auto` or `restart --session llm-server`.
- Add the NPC to `/test-10-player` before runtime sign-off.
- Treat `/test-10-player` + Supabase memory creation as the final acceptance test.

## Technical Constraints

| Constraint | Origin | Impact |
|------------|--------|--------|
| VRAM limited to 6GB | RTX 3060 | Must use LoRA, not full model |
| Local-only training | No cloud GPU budget | Pipeline runs locally |
| JSONL dataset size | HuggingFace limit | Max ~10K examples per NPC |

## Development Environment

### Server Manager (Primary)

```bash
# Check status of all servers (detects tmux + direct processes)
python scripts/server_manager.py status

# Auto-start on first available port (8000→8002, 8080→8082)
python scripts/server_manager.py start --auto

# Restart just the runtime LLM server
python scripts/server_manager.py restart --session llm-server

# Kill process on a specific port
python scripts/server_manager.py kill-port 8000

# Attach to server tmux session
python scripts/server_manager.py attach --session llm-server

# Check which process owns a port
python scripts/server_manager.py check 8000
```

### Server Ports

| Server | Default Port | Process Type |
|--------|------------|------------|
| LLM server (FastAPI + llama.cpp) | 8000 | `scripts/llm_integrated_server.py` |
| Chat UI server | 8080 | `run_chat_server.py` |
| Supabase (local) | 16433 | Docker container |

**Auto-port behavior**: When default port is busy, `server_manager.py --auto` scans forward (+0 to +4) and starts on first free port.

### Opening Chat Interface

1. Start servers: `python scripts/server_manager.py start --auto`
2. Open: `http://127.0.0.1:8080/chat_interface.html`
3. Check LLM status: `curl http://127.0.0.1:8000/status`

## Deployment

```
Environment: Local + Unity Runtime
Platform: Local GPU training, Unity export
CI/CD: None (manual pipeline execution)
Monitoring: N/A (local training)
```

## Onboarding Checklist

- [ ] Know the primary tech stack
- [ ] Understand the architecture pattern and why it was chosen
- [ ] Know the key project directories and their purpose
- [ ] Know the canonical NotebookLM-direct new-NPC workflow
- [ ] Understand major technical decisions and rationale
- [ ] Know integration points and dependencies
- [ ] Be able to set up local development environment
- [ ] Know how to start servers: `python scripts/server_manager.py start --auto`
- [ ] Know how to restart runtime only: `python scripts/server_manager.py restart --session llm-server`
- [ ] Check server status: `python scripts/server_manager.py status`

## 📂 Codebase References

**Core Pipeline**: `scripts/run_full_npc_pipeline.py` - 5-phase orchestrator
**Training**: `scripts/train_surf_llama.py` - Unsloth fine-tuning (1824 lines)
**Dataset Generation**: `scripts/generate_npc_dataset.py` - NotebookLM → JSONL
**Export**: `scripts/convert_lora_to_gguf.py` - LoRA → GGUF
**Chat Server**: `run_chat_server.py` - Local LLM inference server
**Supabase**: `scripts/supabase_client.py` - Database client (419 lines)
**Tests**: `test_server.py`, `test_memory_workflow.py`

## Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files (Python) | snake_case | `train_surf_llama.py`, `supabase_client.py` |
| Files (Scripts) | snake_case | `run_full_npc_pipeline.py` |
| NPC IDs | kebab-case | `maestro_jazz_instructor`, `brazilian_history` |
| Classes | PascalCase | `SupabaseClient`, `PlayerProfile`, `NPCMemory` |
| Functions | snake_case | `get_player_profile()`, `check_vram_guard()` |
| Constants | UPPER_SNAKE | `MAX_EPOCHS`, `DEFAULT_BATCH_SIZE` |
| Database Tables | snake_case | `player_profiles`, `dialogue_sessions` |
| Database Columns | snake_case | `player_id`, `npc_id`, `started_at` |

## Code Standards

**Python Style**:
- Follow PEP 8, use Black formatter
- Type hints required for function signatures
- Use dataclasses for data structures
- Docstrings for all public functions

**Project Patterns**:
```python
# Dataclass pattern (from supabase_client.py)
@dataclass
class PlayerProfile:
    player_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime

# Singleton pattern for clients
class SupabaseClient:
    _instance: Optional[Client] = None
    
    @classmethod
    def get_instance(cls) -> Optional[Client]:
        if cls._instance is not None:
            return cls._instance
        # ... initialization

# VRAM guard before GPU operations
def check_vram_guard(threshold_gb: float = 3.5) -> None:
    """Check if enough VRAM is free before heavy tasks."""
    if not torch.cuda.is_available():
        return
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    # ... warning logic
```

**Required Imports**:
```python
from __future__ import annotations  # Always include
from pathlib import Path
from typing import Any, Optional
```

## Security Requirements

| Requirement | Implementation | Location |
|-------------|---------------|----------|
| API Keys | Environment variables only, never hardcoded | `.env` file |
| Supabase Auth | Service role key for server, anon key for client | `scripts/supabase_client.py` |
| Input Validation | Zod-like validation before DB operations | Per-function |
| Query Safety | Parameterized queries via Supabase client | All DB queries |
| Secrets | Never commit `.env` to git | `.gitignore` |

**Environment Variable Pattern**:
```python
def get_config() -> tuple[str, str, bool]:
    env = load_env_file(ROOT / ".env")
    url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL", "http://127.0.0.1:16433")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    enabled = os.environ.get("ENABLE_SUPABASE", "true").lower() == "true"
    return url, key, enabled
```

**Required .gitignore entries**:
```
.env
*.gguf
exports/
datasets/processed/
__pycache__/
*.pyc
```

## Related Files

- `business-domain.md` - Why this technical foundation exists
- `business-tech-bridge.md` - How business needs map to technical solutions
- `decisions-log.md` - Full decision history with context
