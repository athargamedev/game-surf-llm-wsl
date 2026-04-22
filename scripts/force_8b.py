#!/usr/bin/env python
"""Force 8B model in notebook."""
import json

with open('scripts/colab_npc_training.ipynb') as f:
    nb = json.load(f)

# Find and replace model settings cell
new_source = [
    "# @title ## 2.2 Model Settings (FORCE 8B)",
    "# ==== FORCE 8B MODEL ON T4 ====",
    "MODEL_NAME = 'unsloth/Llama-3.1-8B-Instruct'  # @param {type:\"string\"}",
    "MAX_SEQ_LENGTH = 1024  # Reduced to help with T4 memory",
    "LOAD_IN_4BIT = True   # 4-bit to fit in T4 memory",
    "DTYPE = torch.float16",
    "",
    "print(f\"Model: {MODEL_NAME}\")",
    "print(f\"Max Seq Length: {MAX_SEQ_LENGTH}\")",
    "print(f\"4-bit: {LOAD_IN_4BIT}\")",
]

for cell in nb['cells']:
    if '2.2 Model Settings' in cell['source'][0]:
        cell['source'] = new_source
        print("Updated cell 2.2 to force 8B model")
        break

with open('scripts/colab_npc_training.ipynb', 'w') as f:
    json.dump(nb, f, indent=2)

print("Done! - Now upload to Colab and run")