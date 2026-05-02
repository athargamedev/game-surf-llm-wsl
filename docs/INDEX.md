# Game_Surf LLM Documentation - Index

> **Central Table of Contents** - Start here for all documentation
> **Last Updated**: 2026-05-01

---

## Quick Start

| Document | Purpose |
|----------|---------|
| [docs/QUICK_START.md](QUICK_START.md) | One-page quick start (open chat, select NPC, ask questions) |
| [docs/SETUP_GUIDE.md](SETUP_GUIDE.md) | Initial environment setup (WSL2, conda, GPU) |

---

## Architecture

| Document | Purpose |
|----------|---------|
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, components, data flow |
| [docs/PIPELINE_REFERENCE.md](PIPELINE_REFERENCE.md) | Full pipeline technical reference |
| [docs/PROJECT_CONTEXT_INTELLIGENCE.md](PROJECT_CONTEXT_INTELLIGENCE.md) | Durable workflow lessons and current project decisions |
| [docs/GAMESURF_WORKFLOW_SKILL_GRAPH.mmd](GAMESURF_WORKFLOW_SKILL_GRAPH.mmd) | Visual workflow map connecting stages, gates, skills, runtime, Supabase memory, and feedback loops |

---

## Pipeline

| Document | Purpose |
|----------|---------|
| [docs/PIPELINE_REFERENCE.md](PIPELINE_REFERENCE.md) | Complete pipeline (generation → training → export) |
| [docs/NOTEBOOKLM_DATASET_WORKFLOW.md](NOTEBOOKLM_DATASET_WORKFLOW.md) | NotebookLM-backed dataset creation workflow |
| [docs/GAMESURF_WORKFLOW_SKILL_GRAPH.mmd](GAMESURF_WORKFLOW_SKILL_GRAPH.mmd) | Mermaid graph for agent handoff and end-to-end workflow execution |
| [docs/test_orchestration_plan.md](test_orchestration_plan.md) | Automated `/test-10-player` memory validation logic |
| [docs/DIALOGUE_WORKFLOW_REVIEW.md](DIALOGUE_WORKFLOW_REVIEW.md) | Review of dialogue testing/tracking gaps and improvement roadmap |
| [scripts/run_full_npc_pipeline.py](../scripts/run_full_npc_pipeline.py) | Main orchestrator entry point |

---

## API Reference

| Document | Purpose |
|----------|---------|
| [docs/API_REFERENCE.md](API_REFERENCE.md) | Server endpoints, testing, curl examples |
| [docs/CHAT_INTERFACE.md](CHAT_INTERFACE.md) | Web UI usage guide |

---

## Supabase Integration

| Document | Purpose |
|----------|---------|
| [docs/SUPABASE_INTEGRATION.md](SUPABASE_INTEGRATION.md) | Player data, NPC memories, schema |

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| [scripts/run_full_npc_pipeline.py](../scripts/run_full_npc_pipeline.py) | Main pipeline orchestrator |
| [scripts/train_surf_llama.py](../scripts/train_surf_llama.py) | Core training (Unsloth) |
| [scripts/llm_integrated_server.py](../scripts/llm_integrated_server.py) | FastAPI server (port 8000) |
| [scripts/generate_npc_dataset.py](../scripts/generate_npc_dataset.py) | Dataset generation |
| [scripts/convert_lora_to_gguf.py](../scripts/convert_lora_to_gguf.py) | GGUF export |
| [scripts/track_workflow_run.py](../scripts/track_workflow_run.py) | Workflow trace and cross-session memory proof |
| [scripts/run_dialogue_benchmark.py](../scripts/run_dialogue_benchmark.py) | Fixed NPC dialogue benchmark runner |
| [scripts/repair_memory_state.py](../scripts/repair_memory_state.py) | Supabase memory diagnostics and metadata repair |

---

## Project Files

| File/Dir | Purpose |
|----------|---------|
| [scripts/](../scripts/) | All Python scripts |
| [research/](../research/) | NPC knowledge bases |
| [exports/](../exports/) | Trained model outputs |
| [datasets/](../datasets/) | Training datasets |
| [supabase/](../supabase/) | Supabase config & migrations |
| [.env](../.env) | Configuration (API keys, paths) |

---

## Knowledge Base (Lore)

NPC knowledge files are stored in `research/<npc_id>/`:
- `research/maestro_jazz_instructor/` - Jazz history
- `research/solar_system_instructor/` - Solar System science
- `research/brazilian_history/` - Brazilian history
- `research/greek_mythology_instructor/` - Greek mythology

---

## URLs

| Service | URL |
|--------|-----|
| Chat Interface | http://127.0.0.1:8080/chat_interface.html |
| LLM API | http://127.0.0.1:8000 |
| Supabase Studio | http://127.0.0.1:54321 |

---

## Commands

```bash
# Train from imported NotebookLM dataset
python scripts/run_full_npc_pipeline.py --npc <npc_id> --skip-generation

# Run servers
python run_chat_server.py  # Web UI (8080)
python scripts/llm_integrated_server.py  # API (8000)

# Test
python test_server.py

# GPU check
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

---

## Current Status

| Component | Status |
|-----------|--------|
| LLM Server | Running on port 8000 |
| Web UI | Running on port 8080 |
| Trained NPCs | jazz_history_instructor, greek_mythology_instructor |

---

## Getting Help

1. **Quick Start**: Start with [docs/QUICK_START.md](QUICK_START.md)
2. **Setup**: [docs/SETUP_GUIDE.md](SETUP_GUIDE.md)
3. **API**: [docs/API_REFERENCE.md](API_REFERENCE.md)
4. **Supabase**: [docs/SUPABASE_INTEGRATION.md](SUPABASE_INTEGRATION.md)
