#!/usr/bin/env python
"""Comprehensive test suite for the Game_Surf integrated LLM server."""

import requests
import json
import time
import sys
from typing import Any
from dataclasses import dataclass

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 30


@dataclass
class TestResult:
    passed: bool
    message: str = ""
    details: dict[str, Any] | str | None = None
    name: str = ""

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class TestRunner:
    def __init__(self):
        self.results: list[TestResult] = []
        self.server_available = False

    def log(self, msg: str):
        print(f"  {msg}")

    def check_server(self) -> bool:
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=5)
            self.server_available = resp.status_code == 200
            return self.server_available
        except Exception:
            self.server_available = False
            return False

    def test_health(self) -> TestResult:
        self.log("Testing /health endpoint...")
        try:
            resp = requests.get(f"{BASE_URL}/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(True, "Health check passed", f"status: {data.get('status')}")
            return TestResult(False, f"Health failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Health error: {e}")

    def test_status(self) -> TestResult:
        self.log("Testing /status endpoint...")
        try:
            resp = requests.get(f"{BASE_URL}/status", timeout=5)
            if resp.status_code != 200:
                return TestResult(False, f"Status failed: {resp.status_code}")

            data = resp.json()
            model_loaded = data.get('model_loaded', False)
            return TestResult(
                True,
                "Status check passed",
                details={
                    'model_loaded': model_loaded,
                    'model_path': data.get('model_path', '')[:50],
                    'npc_registry': data.get('npc_model_registry_size', 0),
                    'supabase': data.get('supabase_connected', False)
                }
            )
        except Exception as e:
            return TestResult(False, f"Status error: {e}")

    def test_metrics(self) -> TestResult:
        self.log("Testing /metrics endpoint...")
        try:
            resp = requests.get(f"{BASE_URL}/metrics", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(True, "Metrics available", details=data)
            return TestResult(False, f"Metrics failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Metrics error: {e}")

    def test_debug_sessions(self) -> TestResult:
        self.log("Testing /debug/sessions endpoint...")
        try:
            resp = requests.get(f"{BASE_URL}/debug/sessions", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(True, "Debug sessions available", details=data)
            return TestResult(False, f"Debug sessions failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Debug sessions error: {e}")

    def test_debug_npc_state(self) -> TestResult:
        self.log("Testing /debug/npc-state endpoint...")
        try:
            resp = requests.get(f"{BASE_URL}/debug/npc-state", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(True, "NPC state available", details=data)
            return TestResult(False, f"Debug npc-state failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Debug npc-state error: {e}")

    def test_session_start(self, player_id: str = "test_player", npc_id: str = "marvel_comics_instructor") -> TestResult:
        self.log(f"Testing /session/start ({player_id}, {npc_id})...")
        try:
            payload = {"player_id": player_id, "npc_id": npc_id}
            resp = requests.post(f"{BASE_URL}/session/start", json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                session_id = data.get('session_id')
                return TestResult(True, f"Session started: {session_id[:8]}...", details=data)
            return TestResult(False, f"Session start failed: {resp.status_code}", resp.text)
        except Exception as e:
            return TestResult(False, f"Session start error: {e}")

    def test_session_end(self, session_id: str, player_id: str = "test_player", npc_id: str = "marvel_comics_instructor") -> TestResult:
        self.log(f"Testing /session/end ({session_id[:8]}...)...")
        try:
            payload = {"session_id": session_id, "player_id": player_id, "npc_id": npc_id}
            resp = requests.post(f"{BASE_URL}/session/end", json=payload, timeout=10)
            if resp.status_code == 200:
                return TestResult(True, "Session ended", details=resp.json())
            return TestResult(False, f"Session end failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Session end error: {e}")

    def test_chat(self, player_id: str = "test_player", npc_id: str = "marvel_comics_instructor", message: str = "Hello!") -> TestResult:
        self.log(f"Testing /chat ({player_id}, {npc_id})...")
        try:
            payload = {"player_id": player_id, "npc_id": npc_id, "message": message}
            resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                response = data.get('npc_response', '')
                return TestResult(True, f"Chat response: {response[:50]}...", details=data)
            return TestResult(False, f"Chat failed: {resp.status_code}", resp.text)
        except requests.Timeout:
            return TestResult(False, "Chat timeout (>30s)")
        except Exception as e:
            return TestResult(False, f"Chat error: {e}")

    def test_chat_stream(self, player_id: str = "stream_test", npc_id: str = "marvel_comics_instructor") -> TestResult:
        self.log(f"Testing /chat/stream ({player_id}, {npc_id})...")
        try:
            payload = {"player_id": player_id, "npc_id": npc_id, "message": "Hi"}
            resp = requests.post(f"{BASE_URL}/chat/stream", json=payload, timeout=TIMEOUT, stream=True)
            if resp.status_code == 200:
                chunks = []
                for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk and not chunk.startswith("data:"):
                        chunks.append(chunk.strip())
                    if len(chunks) > 5:
                        break
                return TestResult(True, f"Stream OK ({len(chunks)} chunks)", {'chunks': len(chunks)})
            return TestResult(False, f"Stream failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Stream error: {e}")

    def test_reload_npc(self, npc_id: str = "marvel_comics_instructor") -> TestResult:
        self.log(f"Testing /reload-npc ({npc_id})...")
        try:
            payload = {"npc_id": npc_id}
            resp = requests.post(f"{BASE_URL}/reload-npc", json=payload, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(True, "NPC reload OK", data)
            return TestResult(False, f"Reload failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Reload error: {e}")

    def test_list_npc_models(self) -> TestResult:
        self.log("Testing /npc-models endpoint...")
        try:
            resp = requests.get(f"{BASE_URL}/npc-models", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get('models', [])
                return TestResult(True, f"Found {len(models)} NPC models", data)
            return TestResult(False, f"List models failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"List models error: {e}")

    def test_reset_memory(self) -> TestResult:
        self.log("Testing /reset-memory endpoint...")
        try:
            resp = requests.post(f"{BASE_URL}/reset-memory", timeout=5)
            if resp.status_code == 200:
                return TestResult(True, "Memory reset OK", resp.json())
            return TestResult(False, f"Reset failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Reset error: {e}")

    def test_reload_index(self) -> TestResult:
        self.log("Testing /reload-index endpoint...")
        try:
            resp = requests.post(f"{BASE_URL}/reload-index", timeout=10)
            if resp.status_code == 200:
                return TestResult(True, "Index reload OK", resp.json())
            return TestResult(False, f"Reload index failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Reload index error: {e}")

    def test_clear_history(self, player_id: str = "test_player", npc_id: str = "marvel_comics_instructor") -> TestResult:
        self.log(f"Testing /debug/clear-history ({player_id}, {npc_id})...")
        try:
            payload = {"player_id": player_id, "npc_id": npc_id}
            resp = requests.post(f"{BASE_URL}/debug/clear-history", json=payload, timeout=5)
            if resp.status_code == 200:
                return TestResult(True, "Clear history OK", resp.json())
            return TestResult(False, f"Clear history failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Clear history error: {e}")

    def test_clear_all_sessions(self) -> TestResult:
        self.log("Testing /debug/clear-all-sessions...")
        try:
            resp = requests.post(f"{BASE_URL}/debug/clear-all-sessions", timeout=5)
            if resp.status_code == 200:
                return TestResult(True, "Clear all sessions OK", resp.json())
            return TestResult(False, f"Clear all failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Clear all error: {e}")

    def test_clear_player_memory(self, player_id: str = "test_player") -> TestResult:
        self.log(f"Testing /clear-player-memory ({player_id})...")
        try:
            payload = {"player_id": player_id}
            resp = requests.post(f"{BASE_URL}/clear-player-memory", json=payload, timeout=5)
            if resp.status_code == 200:
                return TestResult(True, "Clear player memory OK", resp.json())
            return TestResult(False, f"Clear player memory failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Clear player memory error: {e}")

    def test_invalid_npc(self) -> TestResult:
        self.log("Testing /chat with invalid NPC (should fail gracefully)...")
        try:
            payload = {"player_id": "test", "npc_id": "nonexistent_npc_xyz", "message": "Hi"}
            resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=TIMEOUT)
            if resp.status_code == 500:
                return TestResult(True, "Invalid NPC handled gracefully")
            if resp.status_code == 200:
                return TestResult(True, "Invalid NPC accepted (using base model)", resp.json())
            return TestResult(False, f"Unexpected status: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Invalid NPC error: {e}")

    def test_player_memory_debug(self, player_id: str = "test_player", npc_id: str = "marvel_comics_instructor") -> TestResult:
        self.log(f"Testing /debug/memory ({player_id}, {npc_id})...")
        try:
            resp = requests.get(f"{BASE_URL}/debug/memory/{player_id}/{npc_id}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(True, "Player memory available", data)
            return TestResult(False, f"Memory debug failed: {resp.status_code}")
        except Exception as e:
            return TestResult(False, f"Memory debug error: {e}")

    def run_all(self) -> bool:
        print("=" * 60)
        print("Game_Surf Integrated Server Test Suite")
        print("=" * 60)

        if not self.check_server():
            print(f"\nERROR: Server not available at {BASE_URL}")
            print("Start the server with: bash scripts/start_servers.sh")
            return False

        print(f"\nServer is available. Running tests...\n")

        tests = [
            ("Health", self.test_health),
            ("Status", self.test_status),
            ("Metrics", self.test_metrics),
            ("Debug Sessions", self.test_debug_sessions),
            ("Debug NPC State", self.test_debug_npc_state),
            ("List NPC Models", self.test_list_npc_models),
            ("Reset Memory", self.test_reset_memory),
            ("Session Start", self.test_session_start),
            ("Chat", self.test_chat),
            ("Chat Stream", self.test_chat_stream),
            ("Reload NPC", self.test_reload_npc),
            ("Reload Index", self.test_reload_index),
            ("Clear History", self.test_clear_history),
            ("Clear Player Memory", self.test_clear_player_memory),
            ("Clear All Sessions", self.test_clear_all_sessions),
            ("Player Memory Debug", self.test_player_memory_debug),
            ("Invalid NPC", self.test_invalid_npc),
            ("Session End", lambda: self.test_session_end("test_session_end")),
        ]

        session_id = None

        for name, test_fn in tests:
            try:
                result = test_fn()
                if name == "Session Start" and result.passed:
                    result = test_fn("test_player", "marvel_comics_instructor")
                    session_id = result.details.get('session_id')
                    if session_id:
                        self.test_session_end(session_id, "test_player", "marvel_comics_instructor")

                status = "PASS" if result.passed else "FAIL"
                icon = "✓" if result.passed else "✗"
                print(f"  [{icon}] {name}: {status}")
                if result.message:
                    print(f"      {result.message}")
                self.results.append(result)
            except Exception as e:
                print(f"  [✗] {name}: EXCEPTION - {e}")
                self.results.append(TestResult(False, name, str(e)))

        print("\n" + "=" * 60)
        print("Results Summary")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        print(f"  Total: {len(self.results)}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")

        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message}")

        print()
        return failed == 0


def main():
    runner = TestRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
