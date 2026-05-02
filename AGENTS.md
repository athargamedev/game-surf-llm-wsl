# Game_Surf NPC Training - Project Knowledge Base

## OVERVIEW

Local LLM training pipeline for Unity NPC characters. Generate trained LoRA adapters from knowledge sources → export to GGUF → integrate with Unity game + Supabase.

## STRUCTURE
```
LLM_WSL/
├── research/ai_news_instructor/           # Knowledge sources (lore, notebooks)
├── datasets/processed/ai_news_instructor/  # Prepared training splits
├── exports/npc_models/ai_news_instructor/  # Trained models + checkpoints
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
./run_pipeline.sh --npc ai_news_instructor

# Skip phases
./run_pipeline.sh --npc ai_news_instructor --skip-generation
./run_pipeline.sh --npc ai_news_instructor --resume

# GPU check
nvidia-smi
```

## NOTES

- **AGENT BEHAVIOR RULE:** AI Agents MUST verify and kill orphaned or failed background processes (using `ps`, `pkill`, or checking `pm2 status`) before starting new long-running scripts or tests to avoid port conflicts and memory leaks.
- Uses Unsloth + Gemma 4 E4B for efficient local training (2.5GB VRAM on RTX 3060 - 50% reduction!)
- 50% faster inference via RTX Tensor Cores + Q4_K_M quantization
- Multimodal capabilities: Vision + Audio + Video support
- Native function calling for agentic AI
- 35+ languages supported out-of-the-box
- Exports to GGUF for Unity llama.cpp inference
- Supabase stores player memories and dialogue history

## HARDWARE & GPU OFFLOAD
- **Flash Attention:** Requires 100% of model layers to be loaded into GPU VRAM.
- **CPU Spillover:** If LM Studio falls back to CPU to prevent OOM (Out of Memory) on the 6GB RTX 3060, Flash Attention disables, causing a massive drop in inference speed (< 10 tokens/sec).
- **The Fix:** In LM Studio GUI Settings -> Hardware -> Set `GPU Offload` to **Max** (not Auto) and enable Flash Attention. Ensure you load the `Q4_K_M` quantization of Gemma 4 E4B (~2.5GB VRAM) to fit within limits.
- **Diagnostics:** Run `python scripts/lmstudio_gpu_watchdog.py` to benchmark Time-to-First-Token (TTFT) and detect silent CPU spillover.

## 🧠 OPENCODE & OAC WORKFLOWS
This project utilizes **OpenCode** and **OpenAgentsControl (OAC)** for powerful, context-aware AI development workflows.

- **Location:** All custom agent logic, skills, and project contexts live in `./.opencode/`.
- **Context System:** OAC uses MVI (Minimal Viable Information) and `ContextScout` to automatically load project standards before generating code.
- **Custom Agents:** The primary agents configured are `OpenAgent` (general tasks) and `OpenCoder` (production development).
- **Running Workflows:** AI tools and developers should leverage the CLI (`opencode --agent OpenCoder`) to initiate structured, multi-file refactoring and component generation that strictly adheres to the project's established conventions.
- **Skills:** Custom JSON skills (e.g., `skill_notebooklm_dataset.json`, `skill_npc_model_tuning.json`) map specific CLI capabilities for automated NPC training tasks.