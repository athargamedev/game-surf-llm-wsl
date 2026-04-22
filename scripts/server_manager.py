#!/usr/bin/env python
"""Server manager CLI for Game_Surf chat and LLM servers."""

import argparse
import os
import re
import subprocess
import sys
import time
import json
import requests
from pathlib import Path
from typing import Optional

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")
BASE_PORT = int(os.environ.get("LLM_SERVER_PORT", "8000"))
CHAT_PORT = int(os.environ.get("CHAT_SERVER_PORT", "8080"))
BASE_URL = f"http://127.0.0.1:{BASE_PORT}"
CHAT_URL = f"http://127.0.0.1:{CHAT_PORT}"


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


def find_process_on_port(port: int) -> dict | None:
    """Find process using a port. Returns dict with pid, cmd, or None."""
    result = subprocess.run(
        ["ss", "-tlnp"],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if f":{port}" in line and "LISTEN" in line:
            match = re.search(r'pid=(\d+)', line)
            pid = int(match.group(1)) if match else None
            if pid:
                try:
                    cmd_result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "args="],
                        capture_output=True, text=True, timeout=5
                    )
                    cmd = cmd_result.stdout.strip() if cmd_result.returncode == 0 else "unknown"
                    start_result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "lstart="],
                        capture_output=True, text=True, timeout=5
                    )
                    started = start_result.stdout.strip() if start_result.returncode == 0 else "unknown"
                    return {"pid": pid, "cmd": cmd, "started": started}
                except Exception:
                    pass
            return {"pid": pid, "cmd": "unknown", "started": "unknown"}
    return None


def check_port(port: int) -> dict:
    """Check if a port is in use. Returns {'in_use': bool, 'owner': dict|None}."""
    proc = find_process_on_port(port)
    if proc:
        return {"in_use": True, **proc}
    return {"in_use": False}


def get_next_free_port(start_port: int, max_attempts: int = 5) -> int | None:
    """Find the first free port starting from start_port."""
    for offset in range(max_attempts):
        port = start_port + offset
        if not check_port(port)["in_use"]:
            return port
    return None


def start_chat_server(port: int | None = None, auto: bool = False) -> dict:
    """Start the chat interface server."""
    target_port = port or CHAT_PORT
    
    # Find available port if auto mode
    if auto:
        target_port = get_next_free_port(CHAT_PORT) or CHAT_PORT
    
    port_check = check_port(target_port)
    if port_check["in_use"]:
        owner = port_check.get("cmd", "unknown")
        if auto:
            # Try next port
            alt_port = get_next_free_port(target_port)
            if alt_port:
                target_port = alt_port
                port_check = check_port(target_port)
            else:
                return {"status": "error", "message": f"No free port near {CHAT_PORT}"}
        else:
            return {"status": "error", "message": f"Port {target_port} already in use by: {owner}"}

    url = f"http://127.0.0.1:{target_port}"
    
    # Start in tmux for management
    if session_running("chat-server"):
        return {"status": "already_running", "session": "chat-server", "port": target_port}

    os.environ["CHAT_SERVER_PORT"] = str(target_port)
    run_tmux([
        "new-session", "-d", "-s", "chat-server",
        f"cd {ROOT} && CHAT_SERVER_PORT={target_port} python run_chat_server.py"
    ])

    time.sleep(2)

    chat_url = f"http://127.0.0.1:{target_port}"
    if wait_for_server(f"{chat_url}/", timeout=15):
        return {"status": "started", "session": "chat-server", "port": target_port, "url": f"{chat_url}/chat_interface.html"}
    else:
        kill_session("chat-server")
        return {"status": "error", "message": "Server did not start in time", "port": target_port}


def start_llm_server(port: int | None = None, auto: bool = False) -> dict:
    """Start the LLM integrated server."""
    target_port = port or BASE_PORT
    
    # Find available port if auto mode
    if auto:
        target_port = get_next_free_port(BASE_PORT) or BASE_PORT
    
    port_check = check_port(target_port)
    if port_check["in_use"]:
        owner = port_check.get("cmd", "unknown")
        if auto:
            alt_port = get_next_free_port(target_port)
            if alt_port:
                target_port = alt_port
                port_check = check_port(target_port)
            else:
                return {"status": "error", "message": f"No free port near {BASE_PORT}"}
        else:
            return {"status": "error", "message": f"Port {target_port} already in use by: {owner}"}

    # Start in tmux for management
    if session_running("llm-server"):
        return {"status": "already_running", "session": "llm-server", "port": target_port}

    run_tmux([
        "new-session", "-d", "-s", "llm-server",
        f"HOST=127.0.0.1 PORT={target_port} LLM_SERVER_URL=http://127.0.0.1:{target_port} {ROOT}/scripts/start_llm_backend.sh"
    ])

    time.sleep(2)

    base_url = f"http://127.0.0.1:{target_port}"
    if wait_for_server(f"{base_url}/health", timeout=60):
        return {"status": "started", "session": "llm-server", "port": target_port, "url": base_url}
    else:
        return {"status": "error", "message": "LLM server did not start in time (may need ~40s to load model)", "port": target_port}


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
    """Get status of all servers (tmux + direct processes)."""
    status = {
        "chat_server": {"running": False, "port": CHAT_PORT, "via": None},
        "llm_server": {"running": False, "port": BASE_PORT, "via": None},
    }

    # Check for chat server (tmux)
    if session_running("chat-server"):
        status["chat_server"]["running"] = True
        status["chat_server"]["via"] = "tmux"
        try:
            resp = requests.get(f"{CHAT_URL}/", timeout=2)
            status["chat_server"]["healthy"] = resp.status_code == 200
        except Exception:
            status["chat_server"]["healthy"] = False

    # Check for chat server (direct process on ports)
    if not status["chat_server"]["running"]:
        for port in range(CHAT_PORT, CHAT_PORT + 5):
            port_check = check_port(port)
            if port_check["in_use"]:
                status["chat_server"]["running"] = True
                status["chat_server"]["port"] = port
                status["chat_server"]["via"] = "direct"
                status["chat_server"]["owner"] = port_check.get("cmd", "unknown")
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}/", timeout=2)
                    status["chat_server"]["healthy"] = resp.status_code == 200
                except Exception:
                    status["chat_server"]["healthy"] = False
                break

    # Check for LLM server (tmux)
    if session_running("llm-server"):
        status["llm_server"]["running"] = True
        status["llm_server"]["via"] = "tmux"
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

    # Check for LLM server (direct process on ports)
    if not status["llm_server"]["running"]:
        for port in range(BASE_PORT, BASE_PORT + 5):
            port_check = check_port(port)
            if port_check["in_use"]:
                status["llm_server"]["running"] = True
                status["llm_server"]["port"] = port
                status["llm_server"]["via"] = "direct"
                status["llm_server"]["owner"] = port_check.get("cmd", "unknown")
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
                    status["llm_server"]["healthy"] = resp.status_code == 200
                except Exception:
                    status["llm_server"]["healthy"] = False
                try:
                    resp = requests.get(f"http://127.0.0.1:{port}/status", timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        status["llm_server"]["model_loaded"] = data.get("model_loaded", False)
                        status["llm_server"]["npc_registry"] = data.get("npc_model_registry_size", 0)
                except Exception:
                    pass
                break

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


def kill_port(port: int) -> dict:
    """Kill process listening on a specific port."""
    proc = find_process_on_port(port)
    if not proc:
        return {"status": "not_in_use", "port": port}
    
    pid = proc.get("pid")
    if pid:
        try:
            subprocess.run(["kill", str(pid)], check=True)
            return {"status": "killed", "port": port, "pid": pid, "cmd": proc.get("cmd")}
        except subprocess.CalledProcessError:
            return {"status": "error", "message": f"Failed to kill pid {pid}"}
    return {"status": "error", "message": "No pid found"}


def main():
    parser = argparse.ArgumentParser(description="Game_Surf Server Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    start_parser = subparsers.add_parser("start", help="Start all servers")
    start_parser.add_argument("--chat-only", action="store_true", help="Start only chat server")
    start_parser.add_argument("--llm-only", action="store_true", help="Start only LLM server")
    start_parser.add_argument("--auto", action="store_true", help="Auto-find first free port (8000->8002, 8080->8082)")
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

    check_parser = subparsers.add_parser("check", help="Check a port")
    check_parser.add_argument("port", type=int, help="Port number to check")

    kill_parser = subparsers.add_parser("kill-port", help="Kill process on a port")
    kill_parser.add_argument("port", type=int, help="Port number to kill")

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
            result = start_llm_server(auto=args.auto)
            print(json.dumps(result, indent=2))
            sys.exit(0 if result["status"] == "started" else 1)

        chat_result = start_chat_server(auto=args.auto)
        llm_result = start_llm_server(auto=args.auto)

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

    elif args.command == "check":
        result = check_port(args.port)
        print(json.dumps(result, indent=2))

    elif args.command == "kill-port":
        result = kill_port(args.port)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
