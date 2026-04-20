#!/usr/bin/env python
"""Test the native llama.cpp integrated server."""

import requests
import json
import time
from typing import Any

BASE_URL = "http://127.0.0.1:8000"

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
    print("\n📊 Testing /status...")
    try:
        resp = requests.get(f"{BASE_URL}/status", timeout=5)
        print(f"   Status: {resp.status_code}")
        data = resp.json()
        print(f"   Model loaded: {data.get('model_loaded')}")
        print(f"   Model path: {data.get('model_path')}")
        print(f"   Index loaded: {data.get('index_loaded')}")
        print(f"   NPC registry size: {data.get('npc_model_registry_size')}")
        if data.get('llm_error'):
            print(f"   ⚠️  LLM Error: {data.get('llm_error')}")
        if data.get('index_error'):
            print(f"   ⚠️  Index Error: {data.get('index_error')}")
        return resp.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_chat(player_id: str = "test_player", npc_id: str = "jazz_historian", message: str = "Hello!") -> bool:
    """Test /chat endpoint."""
    print(f"\n💬 Testing /chat (player={player_id}, npc={npc_id})...")
    try:
        payload = {
            "player_id": player_id,
            "npc_id": npc_id,
            "message": message,
        }
        print(f"   Sending: {json.dumps(payload, indent=4)}")
        resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"   NPC Response: {data.get('npc_response')}")
            print(f"   Session ID: {data.get('session_id')}")
            return True
        else:
            print(f"   Error: {resp.text}")
            return False
    except requests.Timeout:
        print(f"   ❌ Timeout (model inference taking >30s)")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False


def test_session_start(player_id: str = "test_player", npc_id: str = "jazz_historian") -> str | None:
    """Test /session/start endpoint."""
    print(f"\n🔄 Testing /session/start (player={player_id}, npc={npc_id})...")
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
            print(f"   Error: {resp.text}")
            return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def run_full_test_sequence():
    """Run all tests in sequence."""
    print("=" * 60)
    print("🚀 Game_Surf Native LLaMA.cpp Server Test Suite")
    print("=" * 60)
    
    results = {
        "health": test_health(),
        "status": test_status(),
        "session_start": test_session_start() is not None,
        "chat": test_chat(),
    }
    
    print("\n" + "=" * 60)
    print("📈 Test Results")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    all_passed = all(results.values())
    print("\n" + ("✅ All tests passed!" if all_passed else "⚠️  Some tests failed."))
    return all_passed


if __name__ == "__main__":
    run_full_test_sequence()
