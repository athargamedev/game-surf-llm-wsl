# Game_Surf NPC Training - Project Knowledge Base

## OVERVIEW

Local LLM training pipeline for Unity NPC characters. Generate trained LoRA adapters from knowledge sources → export to GGUF → integrate with Unity game + Supabase.

## STRUCTURE
```
LLM_WSL/
├── research/<npc_id>/           # Knowledge sources (lore, notebooks)
├── datasets/processed/<npc_id>/  # Prepared training splits
├── exports/npc_models/<npc_id>/  # Trained models + checkpoints
├── scripts/                     # Pipeline scripts
│   ├── run_full_npc_pipeline.py # Main orchestrator
│   ├── generate_npc_dataset.py  # Phase 1: generation
│   ├── prepare_dataset.py      # Phase 2: preparation
│   ├── train_surf_llama.py     # Phase 3: training
│   ├── convert_lora_to_gguf.py # Phase 4: export
│   └── quality_judge.py        # Phase 5: evaluation
├── supabase/                   # Database config
├── benchmarks/                 # Eval benchmarks
└── chat_interface.html        # Test UI
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Run full pipeline | `./run_pipeline.sh` or `python scripts/run_full_npc_pipeline.py` | 5 phases automated |
| Generate dataset | `scripts/generate_npc_dataset.py` | Phase 1 |
| Prepare dataset | `scripts/prepare_dataset.py` | Phase 2 |
| Train model | `scripts/train_surf_llama.py` | Phase 3 - Unsloth |
| Export GGUF | `scripts/convert_lora_to_gguf.py` | Phase 4 |
| Sync to Unity | `scripts/sync_runtime_artifacts.py` | Phase 4 |
| Evaluate | `scripts/quality_judge.py` + `scripts/evaluate_model.py` | Phase 5 |
| Test model | `http://127.0.0.1:8080/chat_interface.html` | After server start |

## CONVENTIONS

- NPC IDs: `kebab-case` (e.g., `greek_mythology_instructor`, `maestro_jazz_instructor`)
- Dataset files: `train.jsonl`, `validation.jsonl`, `test.jsonl`
- Checkpoints: `checkpoint-*` numbered folders
- GGUF files: `adapter_model.gguf`
- Base model: `unsloth/gemma-4-E4B-it` (Gemma 4 E4B instruction-tuned)
- Quantization: Q4_K_M for optimal RTX performance

## COMMANDS

```bash
# Full pipeline
./run_pipeline.sh --npc <npc_id>

# Skip phases
./run_pipeline.sh --npc <npc_id> --skip-generation
./run_pipeline.sh --npc <npc_id> --resume

# GPU check
nvidia-smi
```

## NOTES

- Uses Unsloth + Gemma 4 E4B for efficient local training (2.5GB VRAM on RTX 3060 - 50% reduction!)
- 50% faster inference via RTX Tensor Cores + Q4_K_M quantization
- Multimodal capabilities: Vision + Audio + Video support
- Native function calling for agentic AI
- 35+ languages supported out-of-the-box
- Exports to GGUF for Unity llama.cpp inference
- Supabase stores player memories and dialogue history