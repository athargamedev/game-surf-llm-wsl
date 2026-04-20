# Project Purpose

**Primary Goal**: Automate the creation of NPC datasets → generate LoRA adapters → link to NPC characters in Unity game → integrate with Supabase for player data and NPC memories.

**Full Pipeline**:
1. **Dataset Generation**: Create training datasets from knowledge sources (NotebookLM, lore files, custom content)
2. **Training**: Fine-tune Llama 3.2 models locally (WSL2) with optimized hyperparameters for best local GPU performance
3. **Export**: Export LoRA adapters in GGUF format for llama.cpp inference
4. **Integration**: Link adapters to NPC characters in Unity game
5. **Data Layer**: Supabase stores player data, NPC memories, dialogue history

**NPCs Currently Supported**:
- Jazz Historian
- Greek Mythology
- Brazil History
- Marvel Comics

**Supabase Integration**: Player profiles, NPC memory persistence, dialogue sessions