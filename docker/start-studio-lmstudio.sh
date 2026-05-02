#!/usr/bin/env bash
# start-studio-lmstudio.sh
# ─────────────────────────────────────────────────────────────
# Starts (or restarts) the custom Supabase Studio container with
# LMStudio local LLM integration for the AI assistant.
#
# Usage:
#   ./docker/start-studio-lmstudio.sh                          # default LMStudio host
#   LMSTUDIO_HOST=192.168.1.100:1234 ./docker/start-studio-lmstudio.sh
#
# Prerequisites:
#   1. Supabase local stack running: supabase start --exclude studio
#   2. Custom Studio image built:
#      docker build -t localhost/gamesurf/supabase-studio:lmstudio-local \
#        docker/supabase-studio-lmstudio/
#   3. LMStudio running with at least one model loaded.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CONTAINER_NAME="supabase_studio_LLM_WSL"
IMAGE="localhost/gamesurf/supabase-studio:lmstudio-local"
NETWORK="supabase_network_LLM_WSL"

# ── LMStudio endpoint (override with env var) ──
LMSTUDIO_HOST="${LMSTUDIO_HOST:-192.168.0.3:1234}"
LMSTUDIO_URL="http://${LMSTUDIO_HOST}/v1"

# ── Models (override with env vars) ──
# Comma-separated list of model IDs available in LMStudio
STUDIO_MODELS="${STUDIO_OPENAI_MODEL:-qwen2.5-coder-7b-instruct,google/gemma-4-e4b,unity-llama32-unsloth@f16,unity-llama32-unsloth@q4_k_m,llama-3.2-3b-instruct,unity-coder-7b-i1,qwen3-4b-qwen3.6-plus-reasoning-distilled,qwen3-8b,meta-llama-3-8b-instruct}"
STUDIO_ADVANCED="${STUDIO_OPENAI_ADVANCED_MODEL:-qwen3-8b}"
STUDIO_EMBEDDING="${STUDIO_OPENAI_EMBEDDING_MODEL:-nomic-embed-text-v1.5}"

# ── Supabase local keys (standard demo keys) ──
ANON_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
SERVICE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"

# ── Studio port (matches config.toml) ──
STUDIO_PORT="${STUDIO_PORT:-16434}"

# ── Preflight checks ──
echo "🔍 Checking LMStudio at ${LMSTUDIO_URL}..."
if ! curl -sf --connect-timeout 5 "${LMSTUDIO_URL}/models" >/dev/null 2>&1; then
  echo "❌ LMStudio not reachable at ${LMSTUDIO_URL}"
  echo "   Make sure LMStudio is running and the server is started."
  exit 1
fi
MODEL_COUNT=$(curl -sf "${LMSTUDIO_URL}/models" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('data',[])))" 2>/dev/null || echo "0")
echo "✅ LMStudio responding — ${MODEL_COUNT} models available"

echo "🔍 Checking Docker network ${NETWORK}..."
if ! docker network inspect "${NETWORK}" >/dev/null 2>&1; then
  echo "❌ Network ${NETWORK} not found. Run 'supabase start --exclude studio' first."
  exit 1
fi
echo "✅ Network exists"

# ── Stop existing container ──
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "🛑 Stopping existing ${CONTAINER_NAME}..."
  docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

# ── Start container ──
echo "🚀 Starting ${CONTAINER_NAME}..."
echo "   Image:    ${IMAGE}"
echo "   LMStudio: ${LMSTUDIO_URL}"
echo "   Models:   ${STUDIO_MODELS}"
echo "   Advanced: ${STUDIO_ADVANCED}"
echo "   Port:     ${STUDIO_PORT}"

docker run -d \
  --name "${CONTAINER_NAME}" \
  --network "${NETWORK}" \
  --restart unless-stopped \
  -p "${STUDIO_PORT}:3000/tcp" \
  -e HOSTNAME=0.0.0.0 \
  -e STUDIO_PG_META_URL=http://supabase_pg_meta_LLM_WSL:8080 \
  -e POSTGRES_PASSWORD=postgres \
  -e NEXT_PUBLIC_ENABLE_LOGS=true \
  -e NEXT_ANALYTICS_BACKEND_PROVIDER=postgres \
  -e SUPABASE_URL=http://supabase_kong_LLM_WSL:8000 \
  -e SUPABASE_PUBLIC_URL=http://127.0.0.1:16433 \
  -e SUPABASE_ANON_KEY="${ANON_KEY}" \
  -e SUPABASE_SERVICE_KEY="${SERVICE_KEY}" \
  -e DEFAULT_ORGANIZATION_NAME="Default Organization" \
  -e DEFAULT_PROJECT_NAME="Default Project" \
  -e OPENAI_API_KEY=lm-studio \
  -e OPENAI_BASE_URL="${LMSTUDIO_URL}" \
  -e NEXT_PUBLIC_IS_PLATFORM=false \
  -e STUDIO_OPENAI_BASE_URL="${LMSTUDIO_URL}" \
  -e STUDIO_OPENAI_MODEL="${STUDIO_MODELS}" \
  -e STUDIO_OPENAI_ADVANCED_MODEL="${STUDIO_ADVANCED}" \
  -e STUDIO_OPENAI_EMBEDDING_MODEL="${STUDIO_EMBEDDING}" \
  -e EDGE_FUNCTIONS_MANAGEMENT_FOLDER=/app/supabase/functions \
  -e SUPABASE_REST_URL=http://supabase_kong_LLM_WSL:8000/rest/v1 \
  -e SUPABASE_INTERNAL_JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long \
  -v "$(pwd)/supabase/functions:/app/supabase/functions" \
  "${IMAGE}" >/dev/null

# ── Start Background Workers (via PM2) ──
echo "🚀 Starting PM2 processes..."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"

pm2 delete god-memory-worker 2>/dev/null || true
pm2 start scripts/god_memory_worker.py --name "god-memory-worker" --interpreter python3 --log /tmp/god_memory_worker.log --time

pm2 delete log-forwarder 2>/dev/null || true
pm2 start /root/.gemini/antigravity/brain/e0c30f61-91f4-49d7-9852-2add9b6d6c7c/scratch/log-forwarder.js --name "log-forwarder" --log /tmp/log_forwarder.log --time

pm2 save

# ── Wait for healthy ──
echo "⏳ Waiting for Studio to become ready..."
for i in $(seq 1 30); do
  if curl -sf --connect-timeout 2 "http://127.0.0.1:${STUDIO_PORT}/project/default" >/dev/null 2>&1; then
    echo "Supabase Studio is ready!"
    echo ""
    echo "   🌐 Dashboard:     http://127.0.0.1:${STUDIO_PORT}/project/default"
    echo "   🤖 AI Assistant:  Powered by LMStudio @ ${LMSTUDIO_HOST}"
    echo "   📊 SQL Editor:    http://127.0.0.1:${STUDIO_PORT}/project/default/sql/new"
    echo ""
    exit 0
  fi
  sleep 1
done

echo "Studio container started but not yet responding. Check logs:"
echo "   docker logs ${CONTAINER_NAME}"
