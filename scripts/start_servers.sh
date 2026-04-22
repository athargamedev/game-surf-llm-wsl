#!/bin/bash
# Start both chat and LLM servers in tmux for non-blocking operation

set -e

cd /root/Game_Surf/Tools/LLM_WSL

echo "=== Game_Surf Server Starter ==="

# Kill existing sessions
echo "Cleaning up existing sessions..."
tmux kill-session -t chat-server 2>/dev/null || true
tmux kill-session -t llm-server 2>/dev/null || true

# Start chat interface server (port 8080)
echo "Starting chat server on port 8080..."
tmux new-session -d -s chat-server "cd /root/Game_Surf/Tools/LLM_WSL && python run_chat_server.py"

# Start LLM backend server (port 8000) - IMPORTANT: Set PYTHONPATH for imports
echo "Starting LLM server on port 8000..."
tmux new-session -d -s llm-server "cd /root/Game_Surf/Tools/LLM_WSL && PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:\$PYTHONPATH conda run --no-capture-output -n unsloth_env python scripts/llm_integrated_server.py"

# Wait for servers to initialize (LLM needs ~40s to load)
echo "Waiting for servers to initialize..."
sleep 5

# Verify chat server immediately
echo ""
echo "=== Checking Chat Server (8080) ==="
if curl -s --connect-timeout 2 http://127.0.0.1:8080/ >/dev/null 2>&1; then
    echo "✓ Chat interface: http://localhost:8080/chat_interface.html"
else
    echo "✗ Chat interface: NOT ready"
fi

# Check LLM server (may take 30-40 seconds to load model)
echo ""
echo "=== Checking LLM Server (8000) ==="
echo "Note: LLM server needs ~40s to load the model..."
for i in 1 2 3 4 5 6 7 8; do
    if curl -s --connect-timeout 2 http://127.0.0.1:8000/status >/dev/null 2>&1; then
        echo "✓ LLM backend: Ready!"
        break
    else
        echo "  Waiting... ($i/8)"
        sleep 10
    fi
done

echo ""
echo "=== Ready ==="
echo "Open: http://localhost:8080/chat_interface.html"
echo ""
echo "Alternative commands:"
echo "  python scripts/server_manager.py status"
echo "  python gamesurf_agent.py test"