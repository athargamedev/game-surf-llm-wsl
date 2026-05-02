#!/usr/bin/env python3
"""
run_benchmarks.py — Lightweight NPC Dialogue Benchmark Runner

Reads benchmark JSON files from benchmarks/npc_dialogue/{npc_key}.json
and validates NPC responses from the running relay server using term checks.

Requires: relay server running at http://127.0.0.1:8000

Format:
  {
    "npc_id": "solar_system_instructor",
    "cases": [
      {
        "id": "case_id",
        "type": "single_turn" | "cross_session_memory",
        "message": "...",
        "checks": {
          "required_terms": [...],
          "min_required_terms": 2,
          "forbidden_terms": [...],
          "min_chars": 100,
          "max_chars": 1200
        }
      }
    ]
  }

Usage:
  python scripts/run_benchmarks.py --benchmark benchmarks/npc_dialogue/solar_system_instructor.json
  python scripts/run_benchmarks.py --all                     # run all benchmark files
  python scripts/run_benchmarks.py --npc solar_system_instructor
  python scripts/run_benchmarks.py --all --output /tmp/bench_results.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "benchmarks" / "npc_dialogue"
API_BASE = "http://127.0.0.1:8000"


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(endpoint: str, payload: dict, timeout: int = 60) -> dict | None:
    try:
        req = request.Request(
            f"{API_BASE}{endpoint}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except error.URLError as e:
        print(f"  ⚠  HTTP error on {endpoint}: {e}")
        return None


def _server_ready() -> bool:
    try:
        with request.urlopen(f"{API_BASE}/status", timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("model_loaded", False)
    except Exception:
        return False


def _select_npc(npc_id: str) -> bool:
    result = _post("/reload-model", {"npc_id": npc_id}, timeout=30)
    return bool(result and result.get("loaded"))


def _start_session(npc_id: str, player_id: str) -> str | None:
    result = _post("/start-session", {"npc_id": npc_id, "player_id": player_id})
    return result.get("session_id") if result else None


def _chat(session_id: str, npc_id: str, player_id: str, message: str) -> str | None:
    result = _post("/chat", {
        "session_id": session_id,
        "npc_id": npc_id,
        "player_id": player_id,
        "message": message,
    })
    if not result:
        return None
    return result.get("response") or result.get("message")


def _end_session(session_id: str, npc_id: str) -> None:
    _post("/end-session", {"session_id": session_id, "npc_id": npc_id})


# ── Check evaluation ──────────────────────────────────────────────────────────

def evaluate_response(response: str, checks: dict) -> tuple[bool, list[str]]:
    """Apply checks to a response. Returns (passed, list of failure reasons)."""
    failures = []
    text_lower = response.lower()

    # Length checks
    if len(response) < checks.get("min_chars", 0):
        failures.append(f"too short ({len(response)} < {checks['min_chars']} chars)")
    if len(response) > checks.get("max_chars", 99999):
        failures.append(f"too long ({len(response)} > {checks['max_chars']} chars)")

    # Required terms
    req_terms = checks.get("required_terms", [])
    min_req = checks.get("min_required_terms", len(req_terms))
    found = [t for t in req_terms if t.lower() in text_lower]
    if len(found) < min_req:
        failures.append(
            f"required terms: found {len(found)}/{min_req} of {req_terms} (got: {found})"
        )

    # Forbidden terms
    for term in checks.get("forbidden_terms", []):
        if term.lower() in text_lower:
            failures.append(f"forbidden term present: '{term}'")

    # Memory denial check
    if checks.get("no_memory_denial"):
        denial_phrases = ["no memory", "don't remember", "do not remember", "cannot recall"]
        for phrase in denial_phrases:
            if phrase in text_lower:
                failures.append(f"memory denial detected: '{phrase}'")

    return len(failures) == 0, failures


# ── Run a benchmark file ──────────────────────────────────────────────────────

def run_benchmark(bench_path: Path, player_id: str, verbose: bool = True) -> dict:
    data = json.loads(bench_path.read_text())
    npc_id = data["npc_id"]
    display = data.get("display_name", npc_id)
    cases = data.get("cases", [])

    results = {"npc_id": npc_id, "display_name": display, "cases": [], "summary": {}}

    if verbose:
        print(f"\n{'━' * 60}")
        print(f"  Benchmarking: {display} ({npc_id})")
        print(f"  Cases: {len(cases)}")
        print(f"{'━' * 60}")

    # Select NPC adapter
    if not _select_npc(npc_id):
        print(f"  ⚠  Could not select NPC adapter for {npc_id} (server may not be running)")

    passed = 0
    failed = 0
    errored = 0

    for case in cases:
        case_id = case["id"]
        case_type = case.get("type", "single_turn")
        checks = case.get("checks", {})

        if verbose:
            print(f"\n  [{case_id}] type={case_type}")

        session_id = _start_session(npc_id, player_id)
        if not session_id:
            if verbose:
                print(f"    ⚠  Could not start session — server not ready")
            results["cases"].append({"id": case_id, "status": "error", "reason": "no session"})
            errored += 1
            continue

        try:
            if case_type == "single_turn":
                response = _chat(session_id, npc_id, player_id, case["message"])
                if response is None:
                    raise RuntimeError("No response from server")
                if verbose:
                    print(f"    Q: {case['message'][:70]}...")
                    print(f"    A: {response[:100]}...")
                ok, failures = evaluate_response(response, checks)

            elif case_type == "cross_session_memory":
                # Seed message in session 1
                seed_resp = _chat(session_id, npc_id, player_id, case["seed_message"])
                _end_session(session_id, npc_id)
                time.sleep(1)

                # Recall in fresh session 2
                session_id2 = _start_session(npc_id, player_id)
                if not session_id2:
                    raise RuntimeError("Could not start recall session")
                recall_resp = _chat(session_id2, npc_id, player_id, case["recall_message"])
                session_id = session_id2

                if recall_resp is None:
                    raise RuntimeError("No recall response")
                if verbose:
                    print(f"    Seed: {case['seed_message'][:60]}...")
                    print(f"    Recall Q: {case['recall_message'][:60]}...")
                    print(f"    Recall A: {recall_resp[:100]}...")
                ok, failures = evaluate_response(recall_resp, checks)
            else:
                ok, failures = False, [f"unknown case type: {case_type}"]

            if ok:
                passed += 1
                status = "PASS"
                if verbose:
                    print(f"    ✅ PASS")
            else:
                failed += 1
                status = "FAIL"
                if verbose:
                    print(f"    ❌ FAIL: {' | '.join(failures)}")

            results["cases"].append({
                "id": case_id,
                "status": status,
                "failures": failures if not ok else [],
            })

        except Exception as exc:
            errored += 1
            if verbose:
                print(f"    ⚠  ERROR: {exc}")
            results["cases"].append({"id": case_id, "status": "error", "reason": str(exc)})
        finally:
            _end_session(session_id, npc_id)
            time.sleep(0.5)

    total = len(cases)
    results["summary"] = {
        "total": total, "passed": passed, "failed": failed, "errored": errored,
        "pass_rate": round(passed / max(total, 1), 2),
    }

    if verbose:
        print(f"\n  Result: {passed}/{total} passed, {failed} failed, {errored} errors")

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global API_BASE
    parser = argparse.ArgumentParser(
        description="Run NPC dialogue benchmarks against the relay server"
    )
    parser.add_argument("--benchmark", default=None, help="Path to a single benchmark JSON")
    parser.add_argument("--npc", default=None, help="NPC key (runs benchmarks/npc_dialogue/{npc}.json)")
    parser.add_argument("--all", action="store_true", help="Run all benchmark files")
    parser.add_argument("--output", default=None, help="Save results to JSON file")
    parser.add_argument("--api-base", default=API_BASE, help="Relay server base URL")
    parser.add_argument("--quiet", action="store_true", help="Suppress per-case output")
    args = parser.parse_args()

    API_BASE = args.api_base

    # Collect benchmark files
    bench_files: list[Path] = []
    if args.benchmark:
        bench_files.append(Path(args.benchmark))
    elif args.npc:
        bench_files.append(BENCH_DIR / f"{args.npc}.json")
    elif args.all:
        bench_files = sorted(BENCH_DIR.glob("*.json"))
    else:
        parser.print_help()
        sys.exit(1)

    missing = [f for f in bench_files if not f.exists()]
    if missing:
        for m in missing:
            print(f"ERROR: Benchmark file not found: {m}")
        sys.exit(1)

    # Server check
    if not _server_ready():
        print("⚠  Relay server not responding at", API_BASE)
        print("   Benchmarks will run but may produce errors.")
        print("   Start with: pm2 start scripts/npc_relay_server.py --name npc-relay\n")

    player_id = f"bench_player_{uuid.uuid4().hex[:8]}"
    all_results = []
    total_pass = 0
    total_cases = 0
    any_fail = False

    for bf in bench_files:
        result = run_benchmark(bf, player_id, verbose=not args.quiet)
        all_results.append(result)
        total_pass += result["summary"]["passed"]
        total_cases += result["summary"]["total"]
        if result["summary"]["failed"] > 0:
            any_fail = True

    # Final summary
    print(f"\n{'═' * 60}")
    print(f"  BENCHMARK SUMMARY")
    print(f"{'═' * 60}")
    for r in all_results:
        s = r["summary"]
        icon = "✅" if s["failed"] == 0 and s["errored"] == 0 else "❌"
        print(f"  {icon} {r['display_name']}: {s['passed']}/{s['total']} ({int(s['pass_rate']*100)}%)")
    print(f"{'─' * 60}")
    print(f"  Total: {total_pass}/{total_cases} cases passed")
    print(f"{'═' * 60}")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({"results": all_results}, indent=2))
        print(f"\n  Results saved → {args.output}")

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
