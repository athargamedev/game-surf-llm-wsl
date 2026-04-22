# Colab Training Run - 2024-04-21

## NPC: movies_instructor

### Run 1: Llama-3.2-3B (Auto-selected for T4)

**Date**: 2024-04-21 (morning)
**Status**: COMPLETED

| Setting | Value |
|---------|-------|
| Model | unsloth/Llama-3.2-3B-Instruct |
| GPU | Tesla T4 (15.6GB) |
| Batch Size | 1 |
| Grad Accum | 16 |
| Epochs | 3 |
| LR | 1e-4 |
| LoRA R | 32 |

**Result**:
- Training: Completed
- GGUF export: In progress (then failed/cancelled)
- Output files: WHERE? Did not save to Google Drive properly

**Issue**: Files not found - VSCode Colab extension may not mount Drive correctly

---

### Run 2: Llama-3.1-8B (Forced for T4)

**Date**: 2024-04-21
**Status**: ✅ COMPLETE - WORKING!

| Setting | Value |
|---------|-------|
| Model | unsloth/Llama-3.1-8B-Instruct |
| GPU | Tesla T4 (15.6GB) |
| Max Seq Length | 1024 |
| Batch Size | 1 |
| Grad Accum | 16 |
| LoRA R | 32 |

**Result**:
- Training: ✅ Completed
- GGUF export: ✅ Completed (after re-running!)
- LoRA adapter: adapter_model.safetensors (336MB)
- GGUF adapter: llama-3.1-8b-instruct.Q4_K_M.gguf (1.9GB)

**Chat Test**:
- Q: "What makes Psycho shower scene special?"
- A: "Masterful editing, camera angles, Bernard Herrmann score..." ✅

**Local Status**: Running on server!

---

## Key Learnings

1. VSCode Colab extension saves differently than web Colab
2. T4 can run 3B with 4-bit (~3GB VRAM)
3. Notebook path handling: Use `/content/drive/My Drive/` not `/content/MyDrive/`

---

## Next Action

Run the 8B notebook and observe what happens