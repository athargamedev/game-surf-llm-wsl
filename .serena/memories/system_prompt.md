# System Prompt - Game_Surf NPC System

## Project Overview

Game_Surf is an NPC dialogue system that:
1. **Creates training datasets** from knowledge sources (NotebookLM, lore files, custom content)
2. **Trains LoRA adapters** on Llama 3.2 with optimized hyperparameters for local WSL2 GPU training
3. **Exports GGUF models** for llama.cpp inference in Unity
4. **Integrates with Supabase** for player data and NPC memory persistence

## Key Workflows

### Create New NPC
1. Add knowledge source to `research/<npc_id>/`
2. Generate dataset: `./run_pipeline.sh --npc <npc_id> --skip-generation`
3. Train model: training happens automatically
4. Export to GGUF: outputs to `exports/npc_models/<npc_id>/gguf/`
5. Test in chat interface: select NPC at http://127.0.0.1:8080/chat_interface.html

### Update Existing NPC
1. Update knowledge in `research/<npc_id>/`
2. Run training with resume: `./run_pipeline.sh --npc <npc_id> --resume`
3. Export updated GGUF

### Supabase Data Structure
- `players` - Player profiles and preferences
- `npc_memories` - Persistent NPC memories per player
- `dialogue_sessions` - Session metadata
- `messages` - Individual messages

## Performance Targets (Local Training)

| Metric | Target |
|-------|--------|
| Dataset load | < 5s |
| Model init | < 10s |
| 100 steps training | ~4 min |
| GGUF export | < 2 min |
| Total pipeline | ~12 min |

## GPU Requirements
- NVIDIA GPU with CUDA (RTX 3060+ recommended)
- 16GB+ VRAM recommended
- WSL2 with NVIDIA drivers