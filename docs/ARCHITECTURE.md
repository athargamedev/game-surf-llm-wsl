# Game_Surf Architecture

> **System architecture, components, and data flow**

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Unity Game Engine                       │
│                  (Assets/StreamingAssets/)                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  NPC Controllers & LLM Integration                 │    │
│  │  - Prompt assembly layer                           │    │
│  │  - Player profile formatting                      │    │
│  │  - Scene context injection                       │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                       │ HTTP/REST
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Game_Surf Backend (WSL2 Linux)                │
│                                                             │
│  ┌─────────────────────┐    ┌────────────────────────┐    │
│  │  Web Server         │    │  LLM Server              │    │
│  │  (run_chat_server)  │    │  (llm_integrated_server) │    │
│  │  Port 8080         │    │  Port 8000               │    │
│  └──────────┬─────────┘    └────────────┬───────────┘    │
│             │                             │                  │
│             └─────────────┬──────────────┘                  │
│                           ▼                                 │
│                  ┌─────────────────┐                        │
│                  │  llama.cpp      │                         │
│                  │  + RAG Engine  │                         │
│                  └────────┬────────┘                        │
│                           ▼                                 │
│                  ┌─────────────────┐                        │
│                  │  GGUF Model     │                         │
│                  │  + Knowledge   │                         │
│                  └─────────────────┘                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Supabase (Database)                      │
│                                                             │
│  - players             - Player profiles                    │
│  - npc_memories      - Per-player NPC memories             │
│  - dialogue_sessions - Session metadata                    │
│  - messages          - Chat messages                      │
└─────────────────────────────────────────────────────────┘
```

---

## Components

### Frontend (Web UI)
| Component | File | Port |
|-----------|------|------|
| Chat Interface | `chat_interface.html` | 8080 |
| Web Server | `run_chat_server.py` | 8080 |

### Backend (API)
| Component | File | Port |
|-----------|------|------|
| LLM Server | `scripts/llm_integrated_server.py` | 8000 |
| Model Engine | llama.cpp via llama-index | - |
| Knowledge Base | `research/` | - |

### Training (Pipeline)
| Component | File |
|-----------|------|
| Orchestrator | `scripts/run_full_npc_pipeline.py` |
| Training | `scripts/train_surf_llama.py` |
| Dataset Gen | `scripts/generate_npc_dataset.py` |
| GGUF Export | `scripts/convert_lora_to_gguf.py` |

### Database
| Component | Location |
|-----------|----------|
| Supabase | `supabase/` |
| Migrations | `supabase/migrations/` |

---

## Data Flow: NPC Prompt Assembly

Each NPC answer is composed from **four layers**:

```
┌─────────────────────┐
│ 1. Base Model + LoRA │
│    - Stable voice    │
│    - Behavioral rules│
│    - Unity vocabulary│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 2. NPC Knowledge    │
│    - Authored facts │
│    - Allowed topics│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 3. Player Profile   │
│    - Skill level   │
│    - Preferences  │
│    - History      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. Runtime Context  │
│    - Scene name   │
│    - GameObjects  │
│    - Game state   │
└─────────────────────┘
```

---

## Directory Structure

```
LLM_WSL/
├── scripts/               # All Python scripts
│   ├── run_full_npc_pipeline.py    # Main orchestrator
│   ├── train_surf_llama.py          # Core training
│   ├── llm_integrated_server.py    # FastAPI server
│   ├── generate_npc_dataset.py     # Dataset generation
│   └── convert_lora_to_gguf.py     # GGUF export
│
├── research/              # NPC knowledge bases
│   ├── maestro_jazz_instructor/
│   ├── brazilian_history/
│   └── greek_mythology_instructor/
│
├── exports/              # Trained model outputs
│   └── npc_models/
│       └── <npc_id>/
│           ├── gguf/          # Quantized GGUF
│           └── lora_adapter/  # LoRA weights
│
├── datasets/             # Training datasets
│   ├── personas/        # Raw generated JSONL
│   └── processed/       # Prepared splits
│
├── supabase/             # Supabase config
│   ├── migrations/      # Database migrations
│   └── config.toml    # Supabase config
│
├── chat_interface.html  # Web UI
├── run_chat_server.py    # Web server (8080)
├── run_pipeline.sh       # Pipeline entry point
└── environment.yml     # Conda environment
```

---

## Pipeline Flow

```
[Research Notes]
        │
        ▼
Phase 1: Dataset Generation   → generate_npc_dataset.py
        │  (local LLM/NotebookLM)
        ▼
Phase 2: Dataset Preparation  → prepare_dataset.py
        │  (filter, dedup, split)
        ▼
Phase 3: Fine-Tuning          → train_surf_llama.py
        │  (Unsloth/LoRA in WSL2)
        ▼
Phase 4: Artifact Sync        → sync_runtime_artifacts.py
        │  (copy to Unity)
        ▼
Phase 5: Quality Evaluation  → quality_judge.py
        │  (benchmark inference)
        ▼
[NPC Model Ready]
```

---

## Performance Targets (Local WSL2)

| Operation | Target |
|-----------|--------|
| Dataset load | < 5s |
| Model init | < 10s |
| 100 steps | ~4 min |
| GGUF export | < 2 min |
| Total pipeline | ~12 min |

---

## Integration: Unity ↔ Game_Surf

### HTTP API

```bash
# Chat endpoint
POST http://127.0.0.1:8000/chat
{
  "player_id": "player_001",
  "npc_id": "jazz_historian",
  "message": "Who was Miles Davis?"
}
```

### Model Files

| File | Location | Purpose |
|------|----------|---------|
| GGUF Model | `exports/npc_models/<npc_id>/gguf/` | llama.cpp inference |
| LoRA Adapter | `exports/npc_models/<npc_id>/lora_adapter/` | Fine-tuned weights |

---

## Supabase Schema

```sql
-- Players
CREATE TABLE players (
  id UUID PRIMARY KEY,
  username TEXT,
  preferences JSONB,
  created_at TIMESTAMPTZ
);

-- NPC Memories (per-player, per-NPC)
CREATE TABLE npc_memories (
  id UUID PRIMARY KEY,
  player_id UUID REFERENCES players(id),
  npc_id TEXT,
  memory JSONB,
  updated_at TIMESTAMPTZ
);

-- Dialogue Sessions
CREATE TABLE dialogue_sessions (
  id UUID PRIMARY KEY,
  player_id UUID REFERENCES players(id),
  npc_id TEXT,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ
);

-- Messages
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  session_id UUID REFERENCES dialogue_sessions(id),
  role TEXT,
  content TEXT,
  created_at TIMESTAMPTZ
);
```

---

## Next Steps

| Task | Document |
|------|----------|
| Quick Start | [docs/QUICK_START.md](QUICK_START.md) |
| Setup | [docs/SETUP_GUIDE.md](SETUP_GUIDE.md) |
| Pipeline | [docs/PIPELINE_REFERENCE.md](PIPELINE_REFERENCE.md) |
| API | [docs/API_REFERENCE.md](API_REFERENCE.md) |
| Supabase | [docs/SUPABASE_INTEGRATION.md](SUPABASE_INTEGRATION.md) |