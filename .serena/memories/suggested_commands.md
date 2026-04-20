# Suggested Commands

## Setup (One-Time)
```bash
# Activate conda environment
conda activate unsloth_env

# Or via conda run
conda run -n unsloth_env python script.py

# Run setup script
chmod +x setup_wsl.sh
./setup_wsl.sh
```

## Training Pipeline
```bash
# Run full NPC pipeline
./run_pipeline.sh --npc maestro_jazz_instructor

# With options
./run_pipeline.sh --npc maestro_jazz_instructor --epochs 3 --resume

# Skip phases
./run_pipeline.sh --npc maestro_jazz_instructor --skip-generation --skip-prep
```

## Running Servers
```bash
# Web UI server (port 8080)
python run_chat_server.py

# LLM backend server (port 8000)
export MODEL_PATH=exports/.../model.gguf
export HOST=127.0.0.1
export PORT=8000
python scripts/llm_integrated_server.py
```

## Testing
```bash
# Test LLM server
python test_server.py

# Run pipeline tests
pytest tests/ -v
```

## GPU/VRAM
```bash
# Check GPU available
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"

# Check VRAM
python -c "import torch; print(torch.cuda.get_device_properties(0).total_memory / 1e9, 'GB')"

# Clear GPU memory
python -c "import torch; torch.cuda.empty_cache()"
```

## Utilities
```bash
# Check conda env
conda env list

# List files
ls -la exports/
ls -la research/world_lore/

# Reload model/index (API)
curl -X POST http://127.0.0.1:8000/reload-model
curl -X POST http://127.0.0.1:8000/reload-index
```

## Supabase Commands
```bash
# Supabase CLI (available)
supabase --help
supabase init
supabase start
supabase db reset
```

## Access Points
- Chat Interface: http://127.0.0.1:8080/chat_interface.html
- LLM API: http://127.0.0.1:8000
- Supabase: Local at http://127.0.0.1:54321