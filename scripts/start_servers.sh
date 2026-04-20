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

# Start LLM backend server (port 8000)
echo "Starting LLM server on port 8000..."
tmux new-session -d -s llm-server "cd /root/Game_Surf/Tools/LLM_WSL && conda run --no-capture-output -n unsloth_env python scripts/llm_integrated_server.py"

# Wait for servers to initialize
sleep 5

# Verify
echo ""
echo "=== Server Status ==="
tmux list-sessions 2>/dev/null || echo "No tmux sessions running"

# Check ports
if curl -s --connect-timeout 2 http://127.0.0.1:8080/ >/dev/null 2>&1; then
    echo "✓ Chat interface: http://localhost:8080/chat_interface.html"
else
    echo "✗ Chat interface: NOT ready"
fi

if curl -s --connect-timeout 2 http://127.0.0.1:8000/status >/dev/null 2>&1; then
    echo "✓ LLM backend: http://localhost:8000"
else
    echo "✗ LLM backend: NOT ready"
fi

echo ""
echo "=== Ready ==="
echo "Open: http://localhost:8080/chat_interface.html"