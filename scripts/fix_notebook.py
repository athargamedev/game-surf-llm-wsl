#!/usr/bin/env python
"""Fix path handling in Colab notebook."""
import json

with open('scripts/colab_npc_training.ipynb') as f:
    nb = json.load(f)

# Add verification cell after mounting Drive
new_cell = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": [
        "# @title ## 1.5 Verify Dataset Path",
        "import os",
        "",
        "# List available datasets in your Drive",
        "base_path = '/content/drive/My Drive/game_surf/datasets/processed/'",
        "print(f\"Checking: {base_path}\")",
        "if os.path.exists(base_path):",
        "    print(\"Available datasets:\")",
        "    for d in sorted(os.listdir(base_path)):",
        "        print(f\"  - {d}\")",
        "else:",
        "    print(\"Folder not found! Create in Google Drive:\")",
        "    print(\"  game_surf/datasets/processed/<your_npc>/train.jsonl\")",
    ]
}

# Find GPU detection cell and insert after
for i, cell in enumerate(nb['cells']):
    if '1.4 GPU' in cell['source'][0]:
        nb['cells'].insert(i+1, new_cell)
        print(f"Inserted verification cell at index {i+1}")
        break

# Save
with open('scripts/colab_npc_training.ipynb', 'w') as f:
    json.dump(nb, f, indent=2)

print("Done!")