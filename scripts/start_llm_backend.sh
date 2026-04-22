#!/bin/bash
# Start the Game_Surf integrated LLM backend with the WSL-local runtime settings.

set -e

cd /root/Game_Surf/Tools/LLM_WSL

export HOST="${HOST:-127.0.0.1}"
export PORT="${PORT:-8000}"
export LLM_SERVER_URL="${LLM_SERVER_URL:-http://127.0.0.1:${PORT}}"
export PYTHONPATH="/root/Game_Surf/Tools/LLM_WSL:${PYTHONPATH:-}"

exec conda run --no-capture-output -n unsloth_env python scripts/llm_integrated_server.py
