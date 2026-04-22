# Skill: Colab Trainer

## Overview

Specialized skill for adapting the Game_Surf NPC training pipeline to run on Google Colab. Generates production-ready `.ipynb` notebooks that follow Colab best practices, VRAM-aware configuration, and output formats compatible with the Unity runtime.

## When to Use

Use this skill when:
- User wants to train NPC models on Google Colab (free T4, Pro, or Pro+ GPUs)
- User requests cloud training instead of local WSL
- Converting local WSL pipeline to cloud-based workflow
- Creating portable training notebooks for sharing

## What This Skill Provides

- **Notebook Generation**: Creates complete `.ipynb` notebooks from the training pipeline
- **VRAM-Aware Configuration**: Auto-selects model/quantization based on GPU type
- **Colab Best Practices**: Drive mounting, session management, checkpoint handling
- **Unity-Compatible Output**: Produces both LoRA adapters + GGUF files

---

## Workflow

### Step 1: Gather Requirements

Determine:
1. **NPC key** to train (e.g., `movies_instructor`, `jazz_history_instructor`)
2. **Dataset location** (Google Drive path or HuggingFace Hub)
3. **GPU tier** (T4, V100, A100, H100)
4. **Output location** (Google Drive folder)

### Step 2: Generate Notebook

Create a notebook with:

```python
# ==== Section 1: Environment Setup ====
# - Install unsloth[torch], transformers, datasets, trl
# - HF login for Llama models
# - Drive mount

# ==== Section 2: Configuration ====
# - NPC-specific parameters
# - VRAM-based model selection
# - Output paths

# ==== Section 3: Data Loading ====
# - Load from JSONL (ChatML format)
# - Quality filtering
# - Train/val split

# ==== Section 4: Model Loading ====
# - VRAM-aware tier fallback
# - float16 on A100, 4-bit on T4

# ==== Section 5: LoRA Setup ====
# - Rank-stabilized LoRA config
# - Target modules

# ==== Section 6: Training ====
# - SFTTrainer with response-only training
# - Checkpointing

# ==== Section 7: Export ====
# - Save adapter
# - Export GGUF
# - Create manifest
```

### Step 3: GPU-Specific Configuration

| GPU | VRAM | Model | Quantization | Max Seq Len |
|-----|-----|-------|------------|------------|
| T4 | 16GB | Llama-3.1-8B | 4-bit | 1024 |
| T4 (experimental) | 16GB | Llama-3.1-8B | 4-bit | 1024 |
| V100 | 16GB | Llama-3.1-8B | float16 | 2048 |
| A100 | 40GB | Llama-3.1-8B | float16 | 4096 |

**Note**: T4 can now run 8B with 4-bit quantization + reduced seq_length=1024

### Step 4: Colab Best Practices

1. **Session Management**
   - Save checkpoints frequently (`save_steps=50`)
   - Use Google Drive for persistence
   - Implement resume logic

2. **Memory Management**
   - Clear CUDA cache before loading model
   - Use gradient checkpointing
   - Disable packing on small VRAM

3. **Error Recovery**
   - Save adapter before GGUF export
   - Checkpoint-based resume
   - Graceful degradation

---

## Notebook Template

```python
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": ["# Game_Surf NPC Training - Google Colab"]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Install dependencies\n",
    "!pip install unsloth[torch] transformers datasets trl --quiet"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Configuration\n",
    "NPC_KEY = 'your_npc'\n",
    "MODEL_NAME = 'unsloth/Llama-3.2-3B-Instruct'\n",
    "# ..."
   ]
  }
 ]
}
```

---

## Key Functions

### VRAM Detection

```python
import torch
def get_gpu_info():
    if torch.cuda.is_available():
        return f"{torch.cuda.get_device_name(0)}: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB"
    return "CPU"
```

### Dataset Format Detection

```python
def detect_format(dataset):
    if 'messages' in dataset.column_names:
        return 'chatml'
    if 'instruction' in dataset.column_names:
        return 'alpaca'
    return 'unknown'
```

### Training Configuration

```python
# VRAM-based config
if 'T4' in gpu_name:
    CONFIG = {'load_in_4bit': True, 'max_seq_length': 1536}
elif 'A100' in gpu_name:
    CONFIG = {'load_in_4bit': False, 'max_seq_length': 4096}
```

---

## Output Artifacts

After running the notebook:

| Artifact | Purpose | Location |
|----------|---------|---------|
| `adapter_model.safetensors` | PEFT LoRA adapter | `{OUTPUT_DIR}/` |
| `*.gguf` | GGUF for Unity/llama.cpp | `{OUTPUT_DIR}/gguf/` |
| `run_config.json` | Reproducibility | `{OUTPUT_DIR}/` |
| `model_manifest.json` | Unity metadata | `{OUTPUT_DIR}/` |

---

## Google Colab Specifics

### Authentication
```python
# HuggingFace
from huggingface_hub import notebook_login
notebook_login()

# Google Drive
from google.colab import drive
drive.mount('/content/drive')
```

### Session Persistence
```python
# Save to Drive frequently
trainer.save_model('/content/drive/MyDrive/game_surf/exports/...')

# Resume from checkpoint
trainer = SFTTrainer(...)
trainer.train(resume_from_checkpoint=True)
```

### VRAM Monitoring
```python
import torch
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.memory_allocated() / 1e9:.2f}GB used / {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f}GB total")
```

---

## Known Limitations

1. **T4 16GB**: May need to reduce `max_seq_length` to 1536 or use 4-bit
2. **Session Timeout**: Save checkpoints frequently; Colab sessions timeout after 90min (free) or 12h (Pro+)
3. **GGUF Export**: May need to reduce `maximum_memory_usage` to 0.5 on limited VRAM

---

## Base Directory

```
/root/Game_Surf/Tools/LLM_WSL/.opencode/skills/colab_trainer/
```

## Reference Files

- `scripts/train_surf_llama.py` - Local training pipeline (source of best practices)
- `scripts/colab_train_llama3_8b.ipynb` - Existing COLAB notebook template

## Tips

- Always mount Google Drive FIRST to persist outputs
- Save LoRA adapter BEFORE attempting GGUF export (safer)
- Use `--resume-from` checkpoint for long training runs
- Set up Google Drive folder structure before starting:
  ```
  game_surf/
  ├── datasets/processed/<npc>/
  └── exports/npc_models/<npc>/
  ```