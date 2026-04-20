# NotebookLM NPC Dataset Training - Successful Session

## Session Date: 2025-04-19

## What Worked

### Pipeline Success
- Created new skill: `notebooklm-npc-datasets` for automated NPC dataset creation
- Successfully trained new NPC: `llm_instructor` on LoRA fine-tuning topics
- Full pipeline executed: profile → generation → import → prepare → smoke training (2 steps)
- Result: 50/50 valid examples, 45 train/5 validation splits
- LoRA adapter saved to: exports/npc_models/llm_instructor/lora_adapter/adapter_model.gguf

### Technical Decisions
- Servers MUST run in tmux to survive command timeouts
- Skill auto-adds new NPC to chat interface after training
- Narrow subject = higher quality dataset (LoRA fine-tuning)

### New Files Created
- .codex/skills/notebooklm-npc-datasets/SKILL.md - Skill automation logic
- scripts/start_servers.sh - tmux server startup helper
- datasets/personas/llm_instructor/llm_instructor_dataset.jsonl - Final dataset
- exports/npc_models/llm_instructor/lora_adapter/adapter_model.gguf - LoRA adapter

### UI Updates
- Added new "LoRA Instructor" button to chat_interface.html
- Added llm_instructor to npcNames JavaScript object
- Servers running in tmux: chat-server (8080), llm-server (8000)

## Next Phase Goals

### Training Logic Enhancements
- Add resume capability for incremental training
- Multi-epoch support with early stopping
- Hyperparameter tuning (learning rate, rank, alpha)
- Batch size optimization for VRAM constraints

### Supabase Integration
- Link NPC memories to player sessions
- Store dialogue history
- Player preference tracking
- NPC personality persistence across sessions

## Key Files to Reference
- .codex/skills/notebooklm-npc-datasets/SKILL.md
- scripts/start_servers.sh
- chat_interface.html (NPC button + npcNames mapping)
- datasets/configs/npc_profiles.json
- exports/npc_models/llm_instructor/

## Constraints to Maintain
- Default to LoRA-only training (don't export per-NPC GGUF unless requested)
- Keep prototype subjects simple and concrete
- Quality gate: 45+ valid unique examples for 50-example batch