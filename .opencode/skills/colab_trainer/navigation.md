# Colab Trainer Navigation

## Quick Start

This skill creates Google Colab notebooks for training Game_Surf NPC models in the cloud.

### Use Cases

1. **Generate notebook for an NPC** - Creates a complete `.ipynb` tailored to the NPC's dataset
2. **VRAM-based config** - Auto-detects GPU and selects optimal settings
3. **Export existing training** - Converts local LoRA to Colab-compatible format

### Key Capabilities

- Creates `.ipynb` notebooks with all Colab best practices
- VRAM-aware model selection (T4 vs A100)
- Google Drive integration
- GGUF export for Unity

---

## Example Usage

Generate a notebook for `movies_instructor`:

```
Create a Colab notebook to train movies_instructor on Google Colab using the Llama-3.2-3B model. Dataset is in my Google Drive at path /content/drive/MyDrive/game_surf/datasets/processed/movies_instructor/train.jsonl. Output should go to exports/npc_models/movies_instructor/.
```

---

## Files

| File | Description |
|------|-------------|
| SKILL.md | Main skill definition with full workflow |
| navigation.md | This navigation file |