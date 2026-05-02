---
name: "notebooklm-npc-datasets"
description: "Compatibility wrapper for the canonical NotebookLM-direct NPC dataset workflow."
metadata:
  short-description: "Use the canonical NotebookLM-direct dataset workflow"
---

# NotebookLM NPC Datasets

Canonical implementation lives at:

`/.codex/skills/notebooklm-npc-datasets/`

Use this command path when invoking the workflow script:

```bash
conda run --no-capture-output -n unsloth_env python \
  .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py --help
```

This wrapper exists so older `.opencode/...` references still resolve to a valid skill location while the project standardizes on the canonical script path above.
