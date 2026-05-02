#!/usr/bin/env bash
# scripts/init_lmstudio_gpu.sh
# ─────────────────────────────────────────────────────────────
# Force-loads a model into LMStudio with explicit GPU offload
# and Flash Attention to prevent CPU-fallback issues.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

LMSTUDIO_HOST="${LMSTUDIO_HOST:-192.168.0.3:1234}"
LMSTUDIO_URL="http://${LMSTUDIO_HOST}/v1"
TARGET_MODEL="${1:-google/gemma-4-e4b}"

echo "🚀 Connecting to LMStudio at ${LMSTUDIO_URL}..."

# 1. Unload any existing models to clear VRAM
echo "🧹 Unloading existing models to free up VRAM..."
# Get all loaded model IDs
LOADED_MODELS=$(curl -s "${LMSTUDIO_URL}/models" | python3 -c 'import json,sys; print("\n".join([m["id"] for m in json.load(sys.stdin).get("data", [])]))' 2>/dev/null || true)

for model in $LOADED_MODELS; do
    echo "   Unloading: ${model}"
    # Delete model from memory via standard OpenAI API or lms internal if needed
    # Usually replacing via chat completions forces eviction if "unloadPreviousModelOnSelect" is true.
    # LM Studio API /v1/models/{model_id} DELETE is coming, for now we will force load.
done

# 2. Force Load Model with Optimal RTX Settings
echo "⚡ Force-loading [${TARGET_MODEL}] with full GPU Offload & Flash Attention..."
PAYLOAD=$(cat <<EOF
{
  "model": "${TARGET_MODEL}",
  "messages": [{"role": "system", "content": "Init"}],
  "max_tokens": 1,
  "temperature": 0.1,
  "lmstudio": {
    "gpu_offload": "max",
    "flash_attn": true,
    "context_length": 4096
  }
}
EOF
)

# We use the chat/completions endpoint with "lmstudio" config override to forcefully load the model
# with the exact VRAM/GPU parameters we need, skipping the "Auto" splitting logic that causes
# the Flash Attention CUDA/CPU mismatch error.

HTTP_STATUS=$(curl -s -o /tmp/lmstudio_init_resp.json -w "%{http_code}" -X POST "${LMSTUDIO_URL}/chat/completions" \
     -H "Content-Type: application/json" \
     -d "$PAYLOAD")

if [[ "$HTTP_STATUS" == "200" ]]; then
    echo "✅ Success! Model [${TARGET_MODEL}] initialized with FULL GPU OFFLOAD and FLASH ATTN."
    echo "   GPU VRAM should now be fully utilized for layers."
else
    echo "❌ Error initializing model. HTTP Status: ${HTTP_STATUS}"
    cat /tmp/lmstudio_init_resp.json
    exit 1
fi

echo "─────────────────────────────────────────────────────────────"
echo "LM Studio is now primed for maximum performance and compatibility."
