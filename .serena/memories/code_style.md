# Code Style & Conventions

**Language**: Python 3.11

**Type Hints**: Uses `from __future__ import annotations` and full type hints on functions.

**Docstrings**: Google-style docstrings with Args, Returns sections.

**Naming**: snake_case for functions/variables, PascalCase for classes.

**Imports**: Organized in groups:
1. Standard library
2. Third-party (torch, transformers, unsloth)
3. Local project (`npc_pipeline_contract`, etc.)

**Key Files**:
- `scripts/train_surf_llama.py` - Main training script
- `scripts/llm_integrated_server.py` - FastAPI server
- `scripts/run_full_npc_pipeline.py` - Full pipeline runner
- `scripts/generate_npc_dataset.py` - Dataset generation

**Entry Points**:
- `./run_pipeline.sh --npc <name>` - Run full training
- `python run_chat_server.py` - Web UI server (port 8080)
- `python scripts/llm_integrated_server.py` - LLM backend (port 8000)