#!/usr/bin/env python
"""Game_Surf unified agent CLI - single entry point for all operations."""

import argparse
import subprocess
import sys
import json
import requests
from pathlib import Path

ROOT = Path("/root/Game_Surf/Tools/LLM_WSL")
BASE_URL = "http://127.0.0.1:8000"


def run_cmd(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def cmd_status():
    """Show system status."""
    print("\n=== Game_Surf Status ===\n")

    result = run_cmd(["python", "scripts/diagnose_pipeline.py"])
    print(result.stdout)


def cmd_test():
    """Run test suite."""
    print("\n=== Running Test Suite ===\n")
    result = run_cmd(["python", "tests/run_all.py"], timeout=300)
    print(result.stdout)
    print(result.stderr)
    return result.returncode


def cmd_up(wait: int = 60):
    """Start all servers."""
    print("\n=== Starting Servers ===\n")

    print("Starting chat server...")
    result = run_cmd(["tmux", "new-session", "-d", "-s", "chat-server",
                     f"cd {ROOT} && python run_chat_server.py"])
    if result.returncode != 0:
        print(f"  Chat server may already be running")

    print("Starting LLM server...")
    result = run_cmd(["tmux", "new-session", "-d", "-s", "llm-server",
                     f"cd {ROOT} && PYTHONPATH={ROOT}:$PYTHONPATH conda run -n unsloth_env python scripts/llm_integrated_server.py"])
    if result.returncode != 0:
        print(f"  LLM server may already be running")

    print(f"\nWaiting for servers (timeout {wait}s)...")

    import time
    chat_ready = False
    llm_ready = False

    for i in range(0, wait, 5):
        time.sleep(5)

        try:
            if not chat_ready:
                r = requests.get("http://127.0.0.1:8080/", timeout=2)
                if r.status_code == 200:
                    print("  ✓ Chat server ready")
                    chat_ready = True
        except Exception:
            pass

        try:
            if not llm_ready:
                r = requests.get(f"{BASE_URL}/health", timeout=2)
                if r.status_code == 200:
                    print("  ✓ LLM server ready")
                    llm_ready = True
        except Exception:
            pass

        if chat_ready and llm_ready:
            break
        print(f"  Waiting... ({i+5}s)")

    print("\nServers started!")
    print(f"  Chat: http://127.0.0.1:8080/chat_interface.html")
    print(f"  LLM:  {BASE_URL}")

    if not llm_ready:
        print("\n  Note: LLM server needs ~40s to load model after start")


def cmd_down():
    """Stop all servers."""
    print("\n=== Stopping Servers ===\n")
    run_cmd(["tmux", "kill-session", "-t", "chat-server"])
    run_cmd(["tmux", "kill-session", "-t", "llm-server"])
    print("Servers stopped")


def cmd_doctor():
    """Run diagnostic and fix suggestions."""
    print("\n=== Running Doctor ===\n")
    result = run_cmd(["python", "scripts/diagnose_pipeline.py", "-v"])
    print(result.stdout)


def cmd_train(npc: str, epochs: int = 2, skip_generation: bool = False, skip_prep: bool = False,
              max_steps: str = "-1", batch_size: str = "1", grad_accum: str = "8"):
    """Run NPC training pipeline."""
    print(f"\n=== Training {npc} ===\n")

    cmd = [
        "python", "scripts/run_full_npc_pipeline.py",
        "--npc", npc,
        "--epochs", str(epochs),
        "--max-steps", max_steps,
        "--batch-size", batch_size,
        "--grad-accum", grad_accum,
    ]

    if skip_generation:
        cmd.append("--skip-generation")
    if skip_prep:
        cmd.append("--skip-prep")
    if skip_generation and skip_prep:
        cmd.append("--skip-sync")

    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def cmd_validate(npc: str):
    """Validate NPC readiness."""
    print(f"\n=== Validating {npc} ===\n")
    result = run_cmd(["python", "scripts/diagnose_pipeline.py", "--npc", npc, "-v"])
    print(result.stdout)


def cmd_list():
    """List all NPCs."""
    print("\n=== Known NPCs ===\n")
    result = run_cmd(["python", "scripts/diagnose_pipeline.py", "--list"])
    print(result.stdout)


def cmd_servers_status():
    """Show server status."""
    print("\n=== Server Status ===\n")
    result = run_cmd(["python", "scripts/server_manager.py", "status"])
    try:
        data = json.loads(result.stdout)
        print(json.dumps(data, indent=2))
    except Exception:
        print(result.stdout)


def cmd_logs(session: str = "llm-server", lines: int = 50):
    """Show server logs."""
    print(f"\n=== {session} Logs ===\n")
    result = run_cmd(["python", "scripts/server_manager.py", "logs", "--session", session, "--lines", str(lines)])
    print(result.stdout)


def cmd_reload(npc: str = None):
    """Reload LLM server or switch NPC."""
    print("\n=== Reloading ===\n")

    if npc:
        try:
            r = requests.post(f"{BASE_URL}/reload-npc", json={"npc_id": npc}, timeout=60)
            print(f"Reload result: {r.json()}")
        except Exception as e:
            print(f"Error: {e}")
            print("Server may not be running. Start with: python gamesurf_agent.py up")
    else:
        try:
            r = requests.post(f"{BASE_URL}/reload-npc", timeout=60)
            print(f"Reload result: {r.json()}")
        except Exception as e:
            print(f"Error: {e}")
            print("Server may not be running. Start with: python gamesurf_agent.py up")


def cmd_chat(message: str, npc: str = "marvel_comics_instructor", player: str = "test_player"):
    """Send a chat message."""
    print(f"\n=== Chat ===\n")

    try:
        r = requests.post(
            f"{BASE_URL}/chat",
            json={"player_id": player, "npc_id": npc, "message": message},
            timeout=60
        )
        if r.status_code == 200:
            data = r.json()
            print(f"Player: {message}")
            print(f"NPC: {data.get('npc_response')}")
        else:
            print(f"Error: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"Error: {e}")
        print("Server may not be running. Start with: python gamesurf_agent.py up")


def main():
    parser = argparse.ArgumentParser(
        description="Game_Surf Unified Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gamesurf_agent.py status          # Show system status
  python gamesurf_agent.py test             # Run test suite
  python gamesurf_agent.py up               # Start all servers
  python gamesurf_agent.py down             # Stop all servers
  python gamesurf_agent.py doctor           # Run diagnostics
  python gamesurf_agent.py train --npc marvel_comics_instructor
  python gamesurf_agent.py validate --npc marvel_comics_instructor
  python gamesurf_agent.py list             # List all NPCs
  python gamesurf_agent.py chat --message "Hello!"
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    subparsers.add_parser("status", help="Show system status")
    subparsers.add_parser("test", help="Run test suite")
    subparsers.add_parser("up", help="Start all servers")
    subparsers.add_parser("down", help="Stop all servers")
    subparsers.add_parser("doctor", help="Run diagnostics")
    subparsers.add_parser("list", help="List all NPCs")
    subparsers.add_parser("servers", help="Show server status")

    logs_parser = subparsers.add_parser("logs", help="Show server logs")
    logs_parser.add_argument("--session", default="llm-server", choices=["chat-server", "llm-server"])
    logs_parser.add_argument("--lines", type=int, default=50)

    reload_parser = subparsers.add_parser("reload", help="Reload LLM server")
    reload_parser.add_argument("--npc", help="Switch to NPC")

    chat_parser = subparsers.add_parser("chat", help="Send chat message")
    chat_parser.add_argument("--message", required=True)
    chat_parser.add_argument("--npc", default="marvel_comics_instructor")
    chat_parser.add_argument("--player", default="test_player")

    train_parser = subparsers.add_parser("train", help="Train NPC")
    train_parser.add_argument("--npc", required=True)
    train_parser.add_argument("--epochs", type=int, default=2)
    train_parser.add_argument("--skip-generation", action="store_true")
    train_parser.add_argument("--skip-prep", action="store_true")
    train_parser.add_argument("--max-steps", default="-1")
    train_parser.add_argument("--batch-size", default="1")
    train_parser.add_argument("--grad-accum", default="8")

    validate_parser = subparsers.add_parser("validate", help="Validate NPC")
    validate_parser.add_argument("--npc", required=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "status":
        cmd_status()
    elif args.command == "test":
        sys.exit(cmd_test())
    elif args.command == "up":
        cmd_up()
    elif args.command == "down":
        cmd_down()
    elif args.command == "doctor":
        cmd_doctor()
    elif args.command == "list":
        cmd_list()
    elif args.command == "servers":
        cmd_servers_status()
    elif args.command == "logs":
        cmd_logs(args.session, args.lines)
    elif args.command == "reload":
        cmd_reload(args.npc)
    elif args.command == "chat":
        cmd_chat(args.message, args.npc, args.player)
    elif args.command == "train":
        sys.exit(cmd_train(args.npc, args.epochs, args.skip_generation, args.skip_prep,
                          args.max_steps, args.batch_size, args.grad_accum))
    elif args.command == "validate":
        cmd_validate(args.npc)


if __name__ == "__main__":
    main()