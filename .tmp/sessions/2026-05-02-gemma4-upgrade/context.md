# Task Context: Gemma 4 Upgrade Implementation

Session ID: 2026-05-02-gemma4-upgrade
Created: 2026-05-02T04:00:00Z
Status: in_progress

## Current Request
Implement Gemma 4 upgrade holistically, step-by-step across 6 phases:
1. Model Migration (Llama 3.1 8B → Gemma 4 E4B)
2. Multimodal Capabilities (Vision + Audio)
3. Agentic AI with Function Calling
4. Multilingual NPCs
5. Performance Optimization (Q4_K_M quantization)
6. NVIDIA Ecosystem Integration

## Context Files (Standards to Follow)
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/core/standards/code-quality.md
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/project-intelligence/code-standards.md

## Reference Files (Source Material)
- /root/Game_Surf/Tools/LLM_WSL/docs/GEMMA4_UPGRADE_PLAN.md
- /root/Game_Surf/Tools/LLM_WSL/AGENTS.md
- /root/Game_Surf/Tools/LLM_WSL/scripts/train_surf_llama.py
- /root/Game_Surf/Tools/LLM_WSL/scripts/generate_npc_dataset.py
- /root/Game_Surf/Tools/LLM_WSL/scripts/convert_lora_to_gguf.py
- /root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py
- /root/Game_Surf/Tools/LLM_WSL/datasets/configs/npc_profiles.json

## External Docs Fetched
- NVIDIA Blog: https://blogs.nvidia.com/blog/rtx-ai-garage-open-models-google-gemma-4/
- Key improvements: 50% faster inference, multimodal (vision/audio), native function calling, 35+ languages

## Components

### Phase 1: Model Migration (Week 1) ✅ PARTIAL
- ✅ Task 01: Update base model in train_surf_llama.py → `unsloth/gemma-4-E4B-it`
- ⏳ Task 02: Update generate_npc_dataset.py (uses "local-model" placeholder - may not need changes)
- ⏳ Task 03: Update npc_profiles.json (no model_name field - may not need changes)
- Task 04: Update Unsloth configuration for Gemma 4
- Task 05: Run smoke test with greek_mythology_instructor

### Phase 2: Multimodal Capabilities (Week 2)
- Task 06: Enable vision capabilities for multimodal NPCs
- Task 07: Enable audio capabilities for voice NPCs
- Task 08: Update dataset generation for multimodal content

### Phase 3: Agentic AI with Function Calling (Week 3)
- Task 09: Implement native function calling with tool definitions
- Task 10: Update NPC prompt templates for function calling

### Phase 4: Multilingual NPCs (Week 4)
- Task 11: Enable 35+ languages in dataset generation
- Task 12: Update Supabase schema for multilingual dialogue

### Phase 5: Performance Optimization (Week 5)
- Task 13: Apply Q4_K_M quantization in convert_lora_to_gguf.py
- Task 14: Update llama.cpp config for RTX acceleration

### Phase 6: NVIDIA Ecosystem Integration (Week 6)
- Task 15: Test Gemma 4 with Ollama integration
- Task 16: Benchmark with llama-bench tool
- Task 17: Document DGX Spark integration option

## Constraints
- RTX 3060 6GB VRAM (target: reduce usage from ~6GB to ~2.5GB)
- Use Unsloth day-one support for Gemma 4
- Maintain backward compatibility with existing NPC profiles
- Q4_K_M quantization for optimal speed/quality balance

## Exit Criteria
- [ ] Gemma 4 E4B model loads and trains successfully
- [ ] VRAM usage reduced to ~2.5GB
- [ ] Inference speed improved by 50% (30 → 45 tok/s)
- [ ] Multimodal capabilities working (vision + audio)
- [ ] Function calling implemented with tool definitions
- [ ] Multilingual support for 35+ languages enabled
- [ ] Q4_K_M quantization applied
- [ ] Ollama integration tested
- [ ] Documentation updated (AGENTS.md, etc.)
