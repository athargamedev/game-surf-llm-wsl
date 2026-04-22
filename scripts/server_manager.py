#!/usr/bin/env python
"""Server manager CLI for Game_Surf chat and LLM servers."""

import argparse
import subprocess
import sys
import time
import json
import requests
from pathlib import Path
from typing import Optional

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")
BASE_URL = "http://127.0.0.1:8000"
CHAT_URL = "http://127.0.0.1:8080"


def run_tmux(cmd: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    """Run a tmux command."""
    return subprocess.run(
        ["tmux"] + cmd,
        capture_output=capture,
        text=True,
    )


def get_tmux_sessions() -> list[dict]:
    """Get list of active tmux sessions."""
    result = run_tmux(["list-sessions", "-F", "#{session_name}"], capture=True)
    if result.returncode != 0:
        return []
    return [{"name": line.strip()} for line in result.stdout.strip().split("\n") if line.strip()]


def session_running(name: str) -> bool:
    """Check if a tmux session is running."""
    sessions = get_tmux_sessions()
    return any(s["name"] == name for s in sessions)


def kill_session(name: str) -> bool:
    """Kill a tmux session."""
    if session_running(name):
        run_tmux(["kill-session", "-t", name])
        return True
    return False


def wait_for_server(url: str, timeout: int = 60, step: int = 5) -> bool:
    """Wait for a server to be ready."""
    for i in range(0, timeout, step):
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def check_port(port: int) -> bool:
    """Check if a port is in use."""
    result = subprocess.run(
        ["ss", "-tlnp"],
        capture_output=True,
        text=True,
    )
    return f":{port}" in result.stdout


def start_chat_server() -> dict:
    """Start the chat interface server."""
    if session_running("chat-server"):
        return {"status": "already_running", "session": "chat-server"}

    if check_port(8080):
        return {"status": "error", "message": "Port 8080 already in use"}

    run_tmux([
        "new-session", "-d", "-s", "chat-server",
        f"cd {ROOT} && python run_chat_server.py"
    ])

    time.sleep(2)

    if wait_for_server(f"{CHAT_URL}/", timeout=15):
        return {"status": "started", "session": "chat-server", "url": f"{CHAT_URL}/chat_interface.html"}
    else:
        kill_session("chat-server")
        return {"status": "error", "message": "Server did not start in time"}


def start_llm_server() -> dict:
    """Start the LLM integrated server."""
    if session_running("llm-server"):
        return {"status": "already_running", "session": "llm-server"}

    if check_port(8000):
        return {"status": "error", "message": "Port 8000 already in use"}

    run_tmux([
        "new-session", "-d", "-s", "llm-server",
        f"cd {ROOT} && PYTHONPATH={ROOT}:$PYTHONPATH conda run -n unsloth_env python scripts/llm_integrated_server.py"
    ])

    time.sleep(2)

    if wait_for_server(f"{BASE_URL}/health", timeout=60):
        return {"status": "started", "session": "llm-server", "url": BASE_URL}
    else:
        return {"status": "error", "message": "LLM server did not start in time (may need ~40s to load model)"}


def stop_server(session: str) -> dict:
    """Stop a server by session name."""
    if session_running(session):
        kill_session(session)
        return {"status": "stopped", "session": session}
    return {"status": "not_running", "session": session}


def restart_server(session: str) -> dict:
    """Restart a server."""
    was_running = session_running(session)
    if was_running:
        kill_session(session)
        time.sleep(2)

    if session == "chat-server":
        return start_chat_server()
    elif session == "llm-server":
        return start_llm_server()
    return {"status": "error", "message": f"Unknown session: {session}"}


def get_server_status() -> dict:
    """Get status of all servers."""
    status = {
        "chat_server": {"running": False, "port": 8080},
        "llm_server": {"running": False, "port": 8000},
    }

    if session_running("chat-server"):
        status["chat_server"]["running"] = True
        try:
            resp = requests.get(f"{CHAT_URL}/", timeout=2)
            status["chat_server"]["healthy"] = resp.status_code == 200
        except Exception:
            status["chat_server"]["healthy"] = False

    if session_running("llm-server"):
        status["llm_server"]["running"] = True
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=2)
            status["llm_server"]["healthy"] = resp.status_code == 200
        except Exception:
            status["llm_server"]["healthy"] = False

        try:
            resp = requests.get(f"{BASE_URL}/status", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                status["llm_server"]["model_loaded"] = data.get("model_loaded", False)
                status["llm_server"]["npc_registry"] = data.get("npc_model_registry_size", 0)
        except Exception:
            pass

    return status


def server_logs(session: str, lines: int = 50) -> str:
    """Get logs from a tmux session."""
    if not session_running(session):
        return f"Session {session} not running"

    result = run_tmux(["capture-pane", "-t", session, "-p", "-S", str(-lines)])
    if result.returncode == 0:
        return result.stdout
    return f"Error getting logs: {result.stderr}"


def attach_session(session: str) -> None:
    """Attach to a tmux session."""
    print(f"Attaching to session: {session}")
    print("Use Ctrl+b, d to detach")
    subprocess.run(["tmux", "attach-session", "-t", session])


def main():
    parser = argparse.ArgumentParser(description="Game_Surf Server Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    start_parser = subparsers.add_parser("start", help="Start all servers")
    start_parser.add_argument("--chat-only", action="store_true", help="Start only chat server")
    start_parser.add_argument("--llm-only", action="store_true", help="Start only LLM server")
    start_parser.add_argument("--wait", type=int, default=60, help="Wait timeout for LLM")

    stop_parser = subparsers.add_parser("stop", help="Stop all servers")
    stop_parser.add_argument("--session", choices=["chat-server", "llm-server"], help="Specific session to stop")

    restart_parser = subparsers.add_parser("restart", help="Restart servers")
    restart_parser.add_argument("--session", choices=["chat-server", "llm-server"], help="Specific session")

    subparsers.add_parser("status", help="Show server status")

    logs_parser = subparsers.add_parser("logs", help="Show server logs")
    logs_parser.add_argument("--session", required=True, choices=["chat-server", "llm-server"])
    logs_parser.add_argument("--lines", type=int, default=50, help="Number of lines")

    attach_parser = subparsers.add_parser("attach", help="Attach to a server session")
    attach_parser.add_argument("--session", required=True, choices=["chat-server", "llm-server"])

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "start":
        print("Starting servers...")

        if args.chat_only:
            result = start_chat_server()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result["status"] == "started" else 1)

        if args.llm_only:
            result = start_llm_server()
            print(json.dumps(result, indent=2))
            sys.exit(0 if result["status"] == "started" else 1)

        chat_result = start_chat_server()
        llm_result = start_llm_server()

        print("\nChat Server:")
        print(json.dumps(chat_result, indent=2))
        print("\nLLM Server:")
        print(json.dumps(llm_result, indent=2))

        if llm_result["status"] == "started":
            print(f"\nNote: LLM server needs ~{args.wait}s to load the model")
            print(f"     Check status: curl {BASE_URL}/status")

    elif args.command == "stop":
        if args.session:
            result = stop_server(args.session)
            print(json.dumps(result, indent=2))
        else:
            chat = stop_server("chat-server")
            llm = stop_server("llm-server")
            print(json.dumps({"chat_server": chat, "llm_server": llm}, indent=2))

    elif args.command == "restart":
        if args.session:
            result = restart_server(args.session)
            print(json.dumps(result, indent=2))
        else:
            chat = restart_server("chat-server")
            llm = restart_server("llm-server")
            print(json.dumps({"chat_server": chat, "llm_server": llm}, indent=2))

    elif args.command == "status":
        status = get_server_status()
        print(json.dumps(status, indent=2))

    elif args.command == "logs":
        logs = server_logs(args.session, args.lines)
        print(logs)

    elif args.command == "attach":
        attach_session(args.session)


if __name__ == "__main__":
    main()