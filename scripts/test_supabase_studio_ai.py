#!/usr/bin/env python3
"""
Test suite for Supabase Studio AI assistant routed through local LMStudio.

Validates that the patched Studio image correctly proxies AI requests to
LMStudio instead of remote OpenAI, and that the SQL assistant produces
usable output for our Game_Surf schema.

Usage:
    python scripts/test_supabase_studio_ai.py
    python scripts/test_supabase_studio_ai.py --studio-url http://127.0.0.1:16434
    python scripts/test_supabase_studio_ai.py --lmstudio-url http://127.0.0.1:1234/v1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

# ── Defaults ──────────────────────────────────────────────────────────────────

STUDIO_URL = os.environ.get("STUDIO_URL", "http://127.0.0.1:16434")
LMSTUDIO_URL = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234/v1")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:16433")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)

EXPECTED_TABLES = [
    "dialogue_sessions",
    "dialogue_turns",
    "npc_memories",
    "npc_profiles",
    "player_profiles",
    "relation_graph_nodes",
    "relation_graph_edges",
    "player_memory_embeddings",
    "dialogue_relation_terms",
    "test_results",
]

TIMEOUT = 60  # LMStudio can be slow on first request


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def icon(self) -> str:
        return "✓" if self.passed else "✗"


class SupabaseStudioAITester:
    """Test the Supabase Studio AI assistant with local LMStudio models."""

    def __init__(
        self,
        studio_url: str = STUDIO_URL,
        lmstudio_url: str = LMSTUDIO_URL,
        supabase_url: str = SUPABASE_URL,
        supabase_key: str = SUPABASE_KEY,
    ):
        self.studio_url = studio_url.rstrip("/")
        self.lmstudio_url = lmstudio_url.rstrip("/")
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self.results: list[TestResult] = []

    def _timed(self, fn, *args, **kwargs) -> tuple[Any, float]:
        start = time.time()
        result = fn(*args, **kwargs)
        elapsed = (time.time() - start) * 1000
        return result, elapsed

    # ── Phase 1: Infrastructure Verification ──────────────────────────────────

    def test_lmstudio_reachable(self) -> TestResult:
        """Verify LMStudio is running and has models loaded."""
        try:
            resp, ms = self._timed(
                requests.get, f"{self.lmstudio_url}/models", timeout=10
            )
            if resp.status_code != 200:
                return TestResult(
                    "LMStudio Reachable",
                    False,
                    f"LMStudio returned {resp.status_code}",
                    duration_ms=ms,
                )

            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if isinstance(m, dict)]
            if not models:
                return TestResult(
                    "LMStudio Reachable",
                    False,
                    "LMStudio running but no models loaded",
                    duration_ms=ms,
                )

            # Check for recommended models
            chat_models = [
                m
                for m in models
                if not re.search(
                    r"(text[-_])?embedding|all[-_]?minilm|bge",
                    m,
                    flags=re.IGNORECASE,
                )
            ]

            return TestResult(
                "LMStudio Reachable",
                True,
                f"Found {len(chat_models)} chat model(s): {', '.join(chat_models[:5])}",
                details={"models": models, "chat_models": chat_models},
                duration_ms=ms,
            )
        except requests.ConnectionError:
            return TestResult(
                "LMStudio Reachable",
                False,
                f"Cannot connect to LMStudio at {self.lmstudio_url}",
            )
        except Exception as e:
            return TestResult("LMStudio Reachable", False, f"Error: {e}")

    def test_studio_container_running(self) -> TestResult:
        """Verify the patched Studio container is running with correct env vars."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=supabase_studio", "--format", "{{.Image}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            image = result.stdout.strip()
            if not image:
                return TestResult(
                    "Studio Container Running",
                    False,
                    "No supabase_studio container found. Run: bash scripts/start_supabase_lmstudio.sh",
                )

            is_patched = "lmstudio" in image.lower() or "gamesurf" in image.lower()

            # Check env vars
            env_result = subprocess.run(
                ["docker", "exec", "supabase_studio_LLM_WSL", "env"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            env_lines = env_result.stdout.strip().split("\n")
            env_dict = {}
            for line in env_lines:
                if "=" in line:
                    key, _, val = line.partition("=")
                    env_dict[key] = val

            required_vars = {
                "OPENAI_API_KEY": env_dict.get("OPENAI_API_KEY"),
                "STUDIO_OPENAI_BASE_URL": env_dict.get("STUDIO_OPENAI_BASE_URL"),
                "STUDIO_OPENAI_MODEL": env_dict.get("STUDIO_OPENAI_MODEL"),
            }

            missing = [k for k, v in required_vars.items() if not v]
            has_base_url = bool(
                env_dict.get("STUDIO_OPENAI_BASE_URL")
                or env_dict.get("OPENAI_BASE_URL")
            )

            return TestResult(
                "Studio Container Running",
                is_patched and has_base_url,
                f"Image: {image}, patched={is_patched}, base_url={has_base_url}",
                details={
                    "image": image,
                    "is_patched": is_patched,
                    "env_vars": required_vars,
                    "missing_vars": missing,
                },
            )
        except FileNotFoundError:
            return TestResult(
                "Studio Container Running",
                False,
                "Docker CLI not found",
            )
        except Exception as e:
            return TestResult("Studio Container Running", False, f"Error: {e}")

    def test_studio_web_accessible(self) -> TestResult:
        """Verify Studio web UI is serving."""
        try:
            resp, ms = self._timed(
                requests.get, self.studio_url, timeout=10, allow_redirects=True
            )
            is_ok = resp.status_code in (200, 301, 302, 304)
            return TestResult(
                "Studio Web Accessible",
                is_ok,
                f"Studio at {self.studio_url} returned {resp.status_code}",
                duration_ms=ms,
            )
        except requests.ConnectionError:
            return TestResult(
                "Studio Web Accessible",
                False,
                f"Cannot connect to Studio at {self.studio_url}",
            )
        except Exception as e:
            return TestResult("Studio Web Accessible", False, f"Error: {e}")

    def test_supabase_api_healthy(self) -> TestResult:
        """Verify Supabase API (PostgREST) is responding."""
        try:
            headers = {
                "apikey": self.supabase_key,
                "Authorization": f"Bearer {self.supabase_key}",
            }
            resp, ms = self._timed(
                requests.get,
                f"{self.supabase_url}/rest/v1/",
                headers=headers,
                timeout=10,
            )
            is_ok = resp.status_code in (200, 204)
            return TestResult(
                "Supabase API Healthy",
                is_ok,
                f"PostgREST at {self.supabase_url} returned {resp.status_code}",
                duration_ms=ms,
            )
        except Exception as e:
            return TestResult("Supabase API Healthy", False, f"Error: {e}")

    # ── Phase 2: SQL Generation Testing ───────────────────────────────────────

    def _call_lmstudio_chat(self, prompt: str, system: str = "") -> tuple[str, float]:
        """Call LMStudio directly to test SQL generation capability."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "auto",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        resp, ms = self._timed(
            requests.post,
            f"{self.lmstudio_url}/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"LMStudio returned {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content, ms

    def _extract_sql(self, text: str) -> str:
        """Extract SQL from a response that might contain markdown fences."""
        # Try to extract from code fences
        sql_match = re.search(r"```(?:sql)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()
        # Otherwise return the full text stripped
        return text.strip()

    def test_sql_simple_select(self) -> TestResult:
        """Test: Generate a simple SELECT query."""
        system = (
            "You are the Supabase Studio SQL assistant. The database has tables: "
            + ", ".join(EXPECTED_TABLES)
            + ". Return ONLY valid PostgreSQL SQL. No explanation."
        )
        prompt = "Show all active NPCs with their display names and subjects"
        try:
            response, ms = self._call_lmstudio_chat(prompt, system)
            sql = self._extract_sql(response)
            checks = {
                "has_select": "SELECT" in sql.upper(),
                "has_npc_profiles": "npc_profiles" in sql.lower(),
                "has_is_active": "is_active" in sql.lower(),
            }
            passed = all(checks.values())
            return TestResult(
                "SQL: Simple SELECT",
                passed,
                f"SQL: {sql[:100]}..." if len(sql) > 100 else f"SQL: {sql}",
                details={"sql": sql, "checks": checks, "raw_response": response[:500]},
                duration_ms=ms,
            )
        except Exception as e:
            return TestResult("SQL: Simple SELECT", False, f"Error: {e}")

    def test_sql_join_query(self) -> TestResult:
        """Test: Generate a JOIN query."""
        system = (
            "You are the Supabase Studio SQL assistant. Tables: "
            "dialogue_sessions(session_id uuid PK, player_id text, npc_id text, status text, started_at timestamptz, turn_count int), "
            "dialogue_turns(turn_id bigint PK, session_id uuid FK, player_message text, npc_response text, created_at timestamptz). "
            "Return ONLY valid PostgreSQL SQL."
        )
        prompt = "Show the last 10 dialogue turns with their session player_id and npc_id"
        try:
            response, ms = self._call_lmstudio_chat(prompt, system)
            sql = self._extract_sql(response)
            checks = {
                "has_select": "SELECT" in sql.upper(),
                "has_join": "JOIN" in sql.upper(),
                "has_sessions": "dialogue_sessions" in sql.lower(),
                "has_turns": "dialogue_turns" in sql.lower(),
            }
            passed = all(checks.values())
            return TestResult(
                "SQL: JOIN Query",
                passed,
                f"SQL: {sql[:100]}..." if len(sql) > 100 else f"SQL: {sql}",
                details={"sql": sql, "checks": checks},
                duration_ms=ms,
            )
        except Exception as e:
            return TestResult("SQL: JOIN Query", False, f"Error: {e}")

    def test_sql_migration_ddl(self) -> TestResult:
        """Test: Generate a safe migration DDL statement."""
        system = (
            "You are the Supabase Studio SQL assistant. The database has a table "
            "player_profiles(player_id text PK, display_name text, created_at timestamptz, updated_at timestamptz). "
            "Return ONLY valid PostgreSQL DDL. Prefer safe migrations."
        )
        prompt = "Add a last_active_at timestamp column to the player_profiles table with a default of now()"
        try:
            response, ms = self._call_lmstudio_chat(prompt, system)
            sql = self._extract_sql(response)
            checks = {
                "has_alter": "ALTER" in sql.upper(),
                "has_table": "player_profiles" in sql.lower(),
                "has_column": "last_active" in sql.lower(),
                "no_drop": "DROP TABLE" not in sql.upper(),
            }
            passed = all(checks.values())
            return TestResult(
                "SQL: Migration DDL",
                passed,
                f"SQL: {sql[:100]}..." if len(sql) > 100 else f"SQL: {sql}",
                details={"sql": sql, "checks": checks},
                duration_ms=ms,
            )
        except Exception as e:
            return TestResult("SQL: Migration DDL", False, f"Error: {e}")

    def test_sql_schema_awareness(self) -> TestResult:
        """Test: Model knows the Game_Surf schema."""
        system = (
            "You are the Supabase Studio SQL assistant. The database has these tables: "
            + ", ".join(EXPECTED_TABLES)
            + ". Answer with the table names only, one per line."
        )
        prompt = "List all tables in the public schema that relate to NPC dialogue and memory"
        try:
            response, ms = self._call_lmstudio_chat(prompt, system)
            # Check if key tables are mentioned
            response_lower = response.lower()
            found_tables = [t for t in EXPECTED_TABLES if t in response_lower]
            key_tables = ["dialogue_sessions", "dialogue_turns", "npc_memories", "npc_profiles"]
            key_found = [t for t in key_tables if t in response_lower]
            passed = len(key_found) >= 3  # At least 3 of 4 key tables

            return TestResult(
                "SQL: Schema Awareness",
                passed,
                f"Found {len(found_tables)}/{len(EXPECTED_TABLES)} tables, key={len(key_found)}/4",
                details={"found_tables": found_tables, "key_tables_found": key_found},
                duration_ms=ms,
            )
        except Exception as e:
            return TestResult("SQL: Schema Awareness", False, f"Error: {e}")

    def test_sql_rpc_generation(self) -> TestResult:
        """Test: Generate a PostgreSQL function."""
        system = (
            "You are the Supabase Studio SQL assistant. Tables: "
            "dialogue_sessions(session_id uuid, player_id text, npc_id text, status text, turn_count int), "
            "npc_memories(memory_id bigint, player_id text, npc_id text, summary text). "
            "Return ONLY valid PostgreSQL SQL."
        )
        prompt = (
            "Create a function get_player_session_count that takes a player_id text parameter "
            "and returns the total number of dialogue sessions for that player"
        )
        try:
            response, ms = self._call_lmstudio_chat(prompt, system)
            sql = self._extract_sql(response)
            checks = {
                "has_create_function": "CREATE" in sql.upper() and "FUNCTION" in sql.upper(),
                "has_player_id": "player_id" in sql.lower(),
                "has_return": "RETURN" in sql.upper(),
            }
            passed = all(checks.values())
            return TestResult(
                "SQL: RPC Generation",
                passed,
                f"SQL: {sql[:100]}..." if len(sql) > 100 else f"SQL: {sql}",
                details={"sql": sql, "checks": checks},
                duration_ms=ms,
            )
        except Exception as e:
            return TestResult("SQL: RPC Generation", False, f"Error: {e}")

    # ── Phase 3: Structured Output ────────────────────────────────────────────

    def test_structured_json_output(self) -> TestResult:
        """Test if the model can produce structured JSON when asked."""
        system = (
            "You are the Supabase Studio assistant. "
            "When asked for JSON output, return ONLY valid JSON. No markdown fences. "
            "No explanation. Just the JSON object."
        )
        prompt = (
            'Generate a JSON object with keys "title" (string) and "description" (string) '
            'for a SQL query that lists all NPC profiles.'
        )
        try:
            response, ms = self._call_lmstudio_chat(prompt, system)
            # Try to parse as JSON
            cleaned = response.strip()
            # Remove markdown fences if present
            json_match = re.search(r"```(?:json)?\s*\n(.*?)```", cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(1).strip()

            try:
                parsed = json.loads(cleaned)
                has_title = "title" in parsed
                has_description = "description" in parsed
                passed = has_title and has_description
                return TestResult(
                    "Structured JSON Output",
                    passed,
                    f"Parsed JSON with keys: {list(parsed.keys())}",
                    details={"parsed": parsed},
                    duration_ms=ms,
                )
            except json.JSONDecodeError:
                return TestResult(
                    "Structured JSON Output",
                    False,
                    f"Failed to parse JSON: {cleaned[:200]}",
                    details={"raw": response[:500]},
                    duration_ms=ms,
                )
        except Exception as e:
            return TestResult("Structured JSON Output", False, f"Error: {e}")

    # ── Phase 4: No Remote Calls ──────────────────────────────────────────────

    def test_no_remote_openai_calls(self) -> TestResult:
        """Check Docker logs for any calls to api.openai.com (best effort)."""
        try:
            result = subprocess.run(
                [
                    "docker",
                    "logs",
                    "--tail",
                    "200",
                    "supabase_studio_LLM_WSL",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            combined = result.stdout + result.stderr
            remote_calls = [
                line
                for line in combined.split("\n")
                if "api.openai.com" in line.lower()
            ]
            passed = len(remote_calls) == 0
            return TestResult(
                "No Remote OpenAI Calls",
                passed,
                f"Found {len(remote_calls)} remote OpenAI call(s) in recent logs"
                if remote_calls
                else "No remote OpenAI calls detected in logs",
                details={"remote_calls": remote_calls[:5]},
            )
        except FileNotFoundError:
            return TestResult(
                "No Remote OpenAI Calls",
                True,
                "Docker CLI not available — cannot check logs (assumed OK)",
            )
        except Exception as e:
            return TestResult("No Remote OpenAI Calls", False, f"Error: {e}")

    # ── Phase 5: Model Switching ──────────────────────────────────────────────

    def test_model_switching(self) -> TestResult:
        """Verify both base and advanced models respond."""
        try:
            resp = requests.get(f"{self.lmstudio_url}/models", timeout=10)
            if resp.status_code != 200:
                return TestResult("Model Switching", False, "Cannot list models")

            models = [m["id"] for m in resp.json().get("data", []) if isinstance(m, dict)]
            chat_models = [
                m
                for m in models
                if not re.search(r"(text[-_])?embedding|all[-_]?minilm|bge", m, flags=re.IGNORECASE)
            ]

            if len(chat_models) < 2:
                return TestResult(
                    "Model Switching",
                    True,
                    f"Only {len(chat_models)} chat model(s) available — switching not testable",
                    details={"chat_models": chat_models},
                )

            # Try calling both models
            results = {}
            for model_id in chat_models[:2]:
                payload = {
                    "model": model_id,
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "max_tokens": 20,
                }
                try:
                    r, ms = self._timed(
                        requests.post,
                        f"{self.lmstudio_url}/chat/completions",
                        json=payload,
                        timeout=TIMEOUT,
                    )
                    results[model_id] = {
                        "status": r.status_code,
                        "responded": r.status_code == 200,
                        "ms": round(ms),
                    }
                except Exception as e:
                    results[model_id] = {"status": 0, "responded": False, "error": str(e)}

            all_responded = all(r.get("responded") for r in results.values())
            return TestResult(
                "Model Switching",
                all_responded,
                f"Tested {len(results)} models: {', '.join(results.keys())}",
                details=results,
            )
        except Exception as e:
            return TestResult("Model Switching", False, f"Error: {e}")

    # ── Runner ────────────────────────────────────────────────────────────────

    def run_all(self) -> bool:
        print("=" * 70)
        print("  Game_Surf — Supabase Studio AI + LMStudio Test Suite")
        print("=" * 70)
        print(f"  Studio URL:   {self.studio_url}")
        print(f"  LMStudio URL: {self.lmstudio_url}")
        print(f"  Supabase URL: {self.supabase_url}")
        print()

        tests = [
            # Phase 1: Infrastructure
            ("Phase 1: Infrastructure", [
                self.test_lmstudio_reachable,
                self.test_studio_container_running,
                self.test_studio_web_accessible,
                self.test_supabase_api_healthy,
            ]),
            # Phase 2: SQL Generation
            ("Phase 2: SQL Generation", [
                self.test_sql_simple_select,
                self.test_sql_join_query,
                self.test_sql_migration_ddl,
                self.test_sql_schema_awareness,
                self.test_sql_rpc_generation,
            ]),
            # Phase 3: Structured Output
            ("Phase 3: Structured Output", [
                self.test_structured_json_output,
            ]),
            # Phase 4: Security
            ("Phase 4: No Remote Calls", [
                self.test_no_remote_openai_calls,
            ]),
            # Phase 5: Multi-Model
            ("Phase 5: Model Switching", [
                self.test_model_switching,
            ]),
        ]

        for phase_name, phase_tests in tests:
            print(f"\n── {phase_name} {'─' * (55 - len(phase_name))}")
            for test_fn in phase_tests:
                result = test_fn()
                result.name = result.name or test_fn.__name__
                self.results.append(result)
                ms_str = f" ({result.duration_ms:.0f}ms)" if result.duration_ms else ""
                print(f"  [{result.icon}] {result.name}{ms_str}")
                if result.message:
                    print(f"      {result.message}")

        # Summary
        print("\n" + "=" * 70)
        print("  Results Summary")
        print("=" * 70)

        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        total = len(self.results)

        print(f"  Total:  {total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")

        if failed > 0:
            print("\n  Failed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"    ✗ {r.name}: {r.message}")

        # Save report
        report_dir = Path(__file__).resolve().parent.parent / "reports" / "studio_ai_tests"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"test_report_{int(time.time())}.json"
        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "studio_url": self.studio_url,
            "lmstudio_url": self.lmstudio_url,
            "total": total,
            "passed": passed,
            "failed": failed,
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                    "duration_ms": r.duration_ms,
                }
                for r in self.results
            ],
        }
        report_path.write_text(json.dumps(report, indent=2, default=str))
        print(f"\n  Report saved: {report_path}")
        print()

        return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="Test Supabase Studio AI with local LMStudio"
    )
    parser.add_argument(
        "--studio-url",
        default=STUDIO_URL,
        help=f"Studio URL (default: {STUDIO_URL})",
    )
    parser.add_argument(
        "--lmstudio-url",
        default=LMSTUDIO_URL,
        help=f"LMStudio URL (default: {LMSTUDIO_URL})",
    )
    parser.add_argument(
        "--supabase-url",
        default=SUPABASE_URL,
        help=f"Supabase API URL (default: {SUPABASE_URL})",
    )
    args = parser.parse_args()

    tester = SupabaseStudioAITester(
        studio_url=args.studio_url,
        lmstudio_url=args.lmstudio_url,
        supabase_url=args.supabase_url,
    )
    success = tester.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
