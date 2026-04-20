#!/usr/bin/env python
"""Comprehensive test suite for Game_Surf NPC memories + Supabase integration."""

import requests
import json
import os
import time
from typing import Any, Optional
from datetime import datetime
from pathlib import Path

def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


ENV = load_env_file(Path(__file__).resolve().parent / ".env")
BASE_URL = os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8000")
SUPABASE_URL = os.environ.get("SUPABASE_URL") or ENV.get("SUPABASE_URL", "http://127.0.0.1:16433")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SERVICE_ROLE_KEY")
    or ENV.get("SUPABASE_SERVICE_ROLE_KEY")
    or ENV.get("SERVICE_ROLE_KEY")
    or ""
)

def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def test_health() -> bool:
    """Test /health endpoint."""
    print("🏥 Testing /health...")
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"   Status: {resp.status_code}")
        print(f"   Response: {resp.json()}")
        return resp.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_status() -> bool:
    """Test /status endpoint."""
    print("📊 Testing /status...")
    try:
        resp = requests.get(f"{BASE_URL}/status", timeout=5)
        print(f"   Status: {resp.status_code}")
        data = resp.json()
        print(f"   Model loaded: {data.get('model_loaded')}")
        print(f"   Index loaded: {data.get('index_loaded')}")
        print(f"   Supabase connected: {data.get('supabase_connected')}")
        return resp.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_session_start(player_id: str = "alice", npc_id: str = "jazz_historian") -> Optional[str]:
    """Test /session/start endpoint."""
    print(f"🔄 Testing /session/start...")
    print(f"   Player: {player_id}, NPC: {npc_id}")
    try:
        payload = {
            "player_id": player_id,
            "npc_id": npc_id,
        }
        resp = requests.post(f"{BASE_URL}/session/start", json=payload, timeout=5)
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            session_id = data.get('session_id')
            print(f"   Session ID: {session_id}")
            print(f"   Memory Summary: {data.get('memory_summary')}")
            return session_id
        else:
            print(f"   ❌ Error: {resp.text}")
            return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def test_multi_turn_chat(player_id: str, npc_id: str, session_id: str) -> bool:
    """Test multiple turns in a single session."""
    print(f"💬 Testing multi-turn chat...")
    messages = [
        "Tell me about Miles Davis",
        "What era of jazz was he famous for?",
        "Can you explain cool jazz?",
    ]
    
    try:
        for i, message in enumerate(messages, 1):
            print(f"\n   Turn {i}: {message}")
            payload = {
                "player_id": player_id,
                "npc_id": npc_id,
                "message": message,
                "session_id": session_id,
            }
            resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=120)
            
            if resp.status_code == 200:
                data = resp.json()
                response = data.get('npc_response', '')
                # Print first 150 chars
                print(f"   Response: {response[:150]}...")
            else:
                print(f"   ❌ Error: {resp.status_code}")
                return False
        
        return True
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_session_end(session_id: str, player_id: str, npc_id: str) -> bool:
    """Test /session/end endpoint."""
    print(f"🛑 Testing /session/end...")
    try:
        payload = {
            "session_id": session_id,
            "player_id": player_id,
            "npc_id": npc_id,
        }
        resp = requests.post(f"{BASE_URL}/session/end", json=payload, timeout=5)
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            print(f"   Response: {resp.json()}")
            return True
        else:
            print(f"   ❌ Error: {resp.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_supabase_memory_retrieval(player_id: str, npc_id: str) -> bool:
    """Test retrieving memory from Supabase."""
    print(f"🧠 Testing Supabase memory retrieval...")
    print(f"   Player: {player_id}, NPC: {npc_id}")
    try:
        # Query via PostgREST API
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
            "Content-Type": "application/json",
        }
        
        # Construct RPC call to get_player_npc_memory
        payload = {
            "player_id_param": player_id,
            "npc_id_param": npc_id,
        }
        
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/get_player_npc_memory",
            json=payload,
            headers=headers,
            timeout=5
        )
        
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            if data:
                memory = data[0]
                print(f"   Memory Summary: {memory.get('summary', 'N/A')[:200]}...")
                print(f"   Session Count: {memory.get('session_count', 0)}")
                print(f"   Updated At: {memory.get('updated_at', 'N/A')}")
                return True
            else:
                print(f"   ℹ️  No memory found yet")
                return True
        else:
            print(f"   ❌ Error: {resp.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_supabase_session_history(player_id: str, npc_id: str) -> bool:
    """Test retrieving session history from Supabase."""
    print(f"📜 Testing Supabase session history...")
    try:
        headers = {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "apikey": SUPABASE_KEY,
        }
        
        # Query dialogue_sessions table
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/dialogue_sessions?player_id=eq.{player_id}&npc_id=eq.{npc_id}&order=started_at.desc&limit=5",
            headers=headers,
            timeout=5
        )
        
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            sessions = resp.json()
            print(f"   Found {len(sessions)} session(s)")
            for session in sessions:
                print(f"   - Session: {session['session_id']}, Status: {session['status']}")
            return True
        else:
            print(f"   ❌ Error: {resp.text}")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def run_complete_memory_workflow():
    """Run a complete memory workflow test."""
    print_section("🎯 COMPLETE NPC MEMORY WORKFLOW TEST")
    
    player_id = "alice"
    npc_id = "jazz_historian"
    
    results = {}
    
    # Phase 1: Basic connectivity
    print_section("PHASE 1: Connectivity & Status")
    results["health"] = test_health()
    results["status"] = test_status()
    
    if not results["health"] or not results["status"]:
        print("\n❌ Server not responding. Aborting.")
        return results
    
    # Phase 2: Session workflow
    print_section("PHASE 2: Session Workflow")
    session_id = test_session_start(player_id, npc_id)
    results["session_start"] = session_id is not None
    
    if session_id:
        # Multi-turn conversation
        results["multi_turn_chat"] = test_multi_turn_chat(player_id, npc_id, session_id)
        
        # End session (triggers memory summarization)
        results["session_end"] = test_session_end(session_id, player_id, npc_id)
        
        # Wait for trigger to process
        print("\n⏳ Waiting for memory summarization trigger (3 seconds)...")
        time.sleep(3)
    
    # Phase 3: Memory persistence
    print_section("PHASE 3: Memory Persistence (Supabase)")
    results["memory_retrieval"] = test_supabase_memory_retrieval(player_id, npc_id)
    results["session_history"] = test_supabase_session_history(player_id, npc_id)
    
    # Summary
    print_section("TEST RESULTS SUMMARY")
    for test_name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {test_name}")
    
    passed_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    print(f"\n  Result: {passed_count}/{total_count} tests passed")
    
    return results


if __name__ == "__main__":
    run_complete_memory_workflow()
