<!-- Context: project-intelligence/technical | Priority: critical | Version: 1.2 | Updated: 2026-04-20 -->

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

## Technical Constraints

| Constraint | Origin | Impact |
|------------|--------|--------|
| VRAM limited to 6GB | RTX 3060 | Must use LoRA, not full model |
| Local-only training | No cloud GPU budget | Pipeline runs locally |
| JSONL dataset size | HuggingFace limit | Max ~10K examples per NPC |

## Development Environment

```
Setup: pip install -r requirements.txt (or use scripts/setup_dataset_pipeline.py)
Requirements: Python 3.10+, CUDA 12+, 6GB VRAM GPU
Local Dev: python run_chat_server.py (starts local LLM server)
Testing: python test_server.py or test_memory_workflow.py
```

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
- [ ] Understand major technical decisions and rationale
- [ ] Know integration points and dependencies
- [ ] Be able to set up local development environment
- [ ] Know how to run tests and deploy

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
