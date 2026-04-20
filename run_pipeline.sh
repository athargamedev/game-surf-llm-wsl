#!/bin/bash

CONDA_ENV="unsloth_env"

echo ">>> Running NPC Pipeline via WSL (Native)"
exec conda run --no-capture-output -n "$CONDA_ENV" python scripts/run_full_npc_pipeline.py "$@"
