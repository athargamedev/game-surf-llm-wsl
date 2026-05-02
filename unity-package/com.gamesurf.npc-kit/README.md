# GameSurf NPC Kit

Local LLM-powered NPC dialogue system for Unity with fine-tuned LoRA personality adapters, persistent memory via Supabase, and runtime model hot-swapping.

## Features

- **Fully Local Inference** — llama.cpp via native bindings, no cloud API costs
- **LoRA Personality Adapters** — Train custom NPC characters with your own knowledge
- **Memory Persistence** — Per-player, per-NPC memory via Supabase
- **Hot-Swap Models** — Switch between NPC adapters at runtime in <500ms
- **Editor Tools** — Custom inspectors, training wizard, model importer

## Quick Start

1. Install via Git URL in Unity Package Manager:
   ```
   https://github.com/AtharvGameDev/gamesurf-npc-kit.git
   ```

2. Create an NPC Profile: `Assets > Create > GameSurf > NPC Profile`

3. Add `NpcDialogueController` component to your NPC GameObject

4. Configure Supabase connection in `Project Settings > GameSurf`

5. Train a custom LoRA adapter:
   ```bash
   pip install gamesurf-train
   gamesurf-train pipeline --npc my_npc --research ./research/
   ```

## Requirements

- Unity 2022.3+
- Base model: `llama-3.2-3b-instruct.Q4_K_M.gguf` (~2GB)
- GPU with 4GB+ VRAM (CPU fallback available)
- Supabase (self-hosted or cloud) for memory persistence

## Documentation

See [Documentation~](Documentation~/index.md) for full setup and training guides.

## License

MIT — see [LICENSE.md](LICENSE.md)
