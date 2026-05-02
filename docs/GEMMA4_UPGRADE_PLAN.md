# Game_Surf Gemma 4 Upgrade Plan

## Overview
Upgrade Game_Surf NPC training pipeline from Llama 3.1 8B to Gemma 4 E4B for:
- 50% faster inference on RTX 3060 (6GB VRAM)
- Multimodal NPCs (vision/audio capabilities)
- Native function calling for agentic AI
- Multilingual support (35+ languages)
- Day-one Unsloth optimization

## Phase 1: Model Migration (Week 1)

### Task 1.1: Update Base Model Configuration
**Files to modify:**
- `scripts/train_surf_llama.py`
- `scripts/generate_npc_dataset.py`
- `configs/npc_profiles.json`

**Changes:**
```python
# OLD
"model_name": "unsloth/Llama-3.1-8B-Instruct"

# NEW  
"model_name": "unsloth/gemma-4-E4B-it"  # Instruction-tuned E4B model
```

**Benefits:**
- 4B params vs 8B = 50% less VRAM usage
- Q4_K_M quantization = 2.5GB VRAM (vs ~6GB for Llama 8B)
- Native RTX Tensor Core acceleration

### Task 1.2: Update Unsloth Configuration
**Changes:**
```python
# train_surf_llama.py
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/gemma-4-E4B-it",
    max_seq_length=2048,  # Gemma 4 supports longer contexts
    load_in_4bit=True,     # Q4_K_M quantization
    use_gradient_checkpointing="unsloth",
)
```

### Task 1.3: Test Gemma 4 with Unsloth
**Action:** Run smoke test with one NPC (greek_mythology_instructor)
```bash
./run_pipeline.sh --npc greek_mythology_instructor --skip-generation --resume
```

## Phase 2: Multimodal NPC Capabilities (Week 2)

### Task 2.1: Enable Vision Capabilities
**New Feature:** NPCs can "see" game screenshots, player gestures, environment

**Implementation:**
```python
# scripts/train_surf_llama.py
# Gemma 4 supports interleaved multimodal input
# Mix text and images in any order within a single prompt

from unsloth import FastLanguageModel
model = FastLanguageModel.from_pretrained(
    model_name="unsloth/gemma-4-E4B-it",
    load_in_4bit=True,
)

# Example: NPC responds to player's screenshot
messages = [
    {"role": "user", "content": [
        {"type": "image", "image": "player_screenshot.png"},
        {"type": "text", "text": "What do you see in this scene?"}
    ]}
]
```

### Task 2.2: Enable Audio Capabilities  
**New Feature:** NPCs respond to voice input, generate voice responses

**Integration:**
- Use Gemma 4's audio transcription capabilities
- Pair with TTS (Text-to-Speech) for NPC voices
- Store audio memories in Supabase

### Task 2.3: Update Dataset Generation
**Modify:** `scripts/generate_npc_dataset.py`
- Add multimodal examples (image+text pairs)
- Generate audio interaction examples
- Update NotebookLM prompts for multimodal content

## Phase 3: Agentic AI with Function Calling (Week 3)

### Task 3.1: Implement Native Function Calling
**Gemma 4 Feature:** Structured tool use (native support)

**Example NPC Tools:**
```python
# NPC can call these functions during dialogue
AVAILABLE_TOOLS = [
    {
        "name": "check_player_inventory",
        "description": "Check what items the player is carrying",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_quest_status", 
        "description": "Get current quest progress",
        "parameters": {"type": "object", "properties": {"quest_id": {"type": "string"}}}
    },
    {
        "name": "spawn_item",
        "description": "Spawn an item in the game world",
        "parameters": {"type": "object", "properties": {"item_id": {"type": "string"}, "quantity": {"type": "integer"}}}
    }
]
```

### Task 3.2: Update NPC Prompt Templates
**Modify:** `datasets/configs/npc_profiles.json`
```json
{
  "cosmos_instructor": {
    "system_prompt_template": "You are {display_name}. You have access to tools: {tool_list}. Use them when relevant."
  }
}
```

### Task 3.3: Integrate with OpenClaw (Optional)
**NVIDIA Blog Mention:** Gemma 4 works with OpenClaw for local agents

**Benefit:** Always-on AI assistants that can automate tasks

## Phase 4: Multilingual NPCs (Week 4)

### Task 4.1: Enable 35+ Languages
**Gemma 4 Feature:** Out-of-the-box support for 35+ languages

**Implementation:**
```python
# Generate datasets in multiple languages
LANGUAGES = ["en", "es", "fr", "de", "pt", "ja", "ko", "zh"]

for lang in LANGUAGES:
    generate_npc_dataset(npc_id, language=lang)
```

### Task 4.2: Update Supabase for Multilingual
**Modify:** Supabase schema to store multilingual dialogue
```sql
ALTER TABLE dialogue_sessions ADD COLUMN language_code VARCHAR(5) DEFAULT 'en';
```

## Phase 5: Performance Optimization (Week 5)

### Task 5.1: Apply Q4_K_M Quantization
**NVIDIA Blog:** 50% faster inference with Q4_K_M on RTX GPUs

**Implementation:**
```python
# scripts/convert_lora_to_gguf.py
from unsloth import FastLanguageModel

model.save_pretrained_gguf(
    "exports/npc_models/{npc_id}/",
    tokenizer,
    quantization_method="q4_k_m",  # Optimized for RTX
)
```

### Task 5.2: Optimize for RTX Tensor Cores
**Benefit:** Higher throughput, lower latency

**Benchmark:**
```bash
# Before (Llama 8B): ~30 tokens/sec
# After (Gemma 4 E4B Q4_K_M): ~45 tokens/sec (50% faster)
```

### Task 5.3: Update llama.cpp Configuration
**Modify:** `scripts/llm_integrated_server.py`
```python
# Use optimized GGUF with RTX acceleration
LLM = LlamaCPP(
    model_path="exports/npc_models/{npc_id}/adapter_model.gguf",
    n_gpu_layers=-1,  # Offload all layers to RTX GPU
    main_gpu=0,       # Use RTX 3060
)
```

## Phase 6: Integration with NVIDIA Ecosystem (Week 6)

### Task 6.1: Test with Ollama
**NVIDIA Blog:** Gemma 4 optimized for Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Run Gemma 4 locally
ollama run gemma-4-E4B
```

### Task 6.2: Benchmark with llama-bench
**Tool:** `llama-bench` (mentioned in NVIDIA blog)

```bash
llama-bench -m exports/npc_models/*/adapter_model.gguf -p "Hello" -n 100
```

### Task 6.3: Optional DGX Spark Integration
**For future scaling:** NVIDIA DGX Spark personal AI supercomputer

## Expected Outcomes

| Metric | Before | After | Improvement |
|--------|--------|------|------------|
| **VRAM Usage** | ~6GB | ~2.5GB | 58% reduction |
| **Inference Speed** | 30 tok/s | 45 tok/s | 50% faster |
| **Model Size** | 8B | 4B | 50% smaller |
| **Multimodal** | ❌ | ✅ | Vision + Audio |
| **Function Calling** | Basic | Native | Structured tools |
| **Languages** | 1 | 35+ | 35x more |
| **Reasoning** | Standard | Enhanced | Agentic AI |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Gemma 4 E4B availability** | Use Unsloth day-one support (confirmed in blog) |
| **Training stability** | Start with 1 NPC, validate before scaling |
| **Quantization quality loss** | Use Q4_K_M (balanced quality/speed) |
| **Multimodal complexity** | Phase rollout (text → vision → audio) |
| **Supabase schema changes** | Backup before migration |

## Next Steps

1. **Immediate (this week):** Test Gemma 4 E4B with greek_mythology_instructor
2. **Week 2:** Enable vision capabilities for maestro_jazz_instructor (music notation images)
3. **Week 3:** Add function calling for supabase_instructor (database tools)
4. **Week 4:** Generate multilingual datasets for cosmos_instructor
5. **Week 5:** Benchmark and optimize Q4_K_M quantization
6. **Week 6:** Document upgrade and share results

## References

- NVIDIA Blog: https://blogs.nvidia.com/blog/rtx-ai-garage-open-models-google-gemma-4/
- Google DeepMind Announcement: https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/
- NVIDIA Technical Blog: https://developer.nvidia.com/blog/bringing-ai-closer-to-the-edge-and-on-device-with-gemma-4/
- Unsloth Gemma 4: https://unsloth.ai/docs/models/gemma-4
