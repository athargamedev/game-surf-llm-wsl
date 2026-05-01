#!/usr/bin/env python
"""Run fixed NPC dialogue benchmarks against the local chat server."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BENCHMARK_DIR = ROOT / "benchmarks" / "npc_dialogue"
DEFAULT_OUTPUT_ROOT = ROOT / "reports" / "dialogue_benchmarks"

DENIAL_PATTERNS = (
    "no memory",
    "do not remember",
    "don't remember",
    "cannot remember",
    "can't remember",
    "no saved",
    "no record",
)


def now_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 120) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = request.Request(url, data=body, headers=headers, method=method)
    started = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return {
                "ok": 200 <= resp.status < 300,
                "status_code": resp.status,
                "duration_seconds": round(time.time() - started, 3),
                "body": parsed,
            }
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "duration_seconds": round(time.time() - started, 3),
            "body": raw,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "duration_seconds": round(time.time() - started, 3),
            "body": str(exc),
        }


def body_dict(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def npc_response(chat_result: dict[str, Any] | None) -> str:
    return str(body_dict(chat_result).get("npc_response") or "")


def memory_context(start_result: dict[str, Any] | None, memory_result: dict[str, Any] | None = None) -> str:
    for result in (start_result, memory_result):
        body = body_dict(result)
        text = str(body.get("memory_summary") or body.get("memory_context") or "")
        if text and text != "No saved player memory.":
            return text
    return ""


def terms_found(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term.lower() in lower]


def score_response(response: str, checks: dict[str, Any]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    required_terms = list(checks.get("required_terms") or [])
    forbidden_terms = list(checks.get("forbidden_terms") or [])
    min_required_terms = int(checks.get("min_required_terms", len(required_terms)))
    min_chars = int(checks.get("min_chars", 0))
    max_chars = int(checks.get("max_chars", 0))

    matched_required = terms_found(response, required_terms)
    matched_forbidden = terms_found(response, forbidden_terms)
    if len(matched_required) < min_required_terms:
        issues.append(f"required_terms:{len(matched_required)}/{min_required_terms}")
    if matched_forbidden:
        issues.append(f"forbidden_terms:{','.join(matched_forbidden)}")
    if min_chars and len(response.strip()) < min_chars:
        issues.append(f"too_short:{len(response.strip())}<{min_chars}")
    if max_chars and len(response.strip()) > max_chars:
        issues.append(f"too_long:{len(response.strip())}>{max_chars}")
    if checks.get("no_memory_denial"):
        lower = response.lower()
        denied = [pattern for pattern in DENIAL_PATTERNS if pattern in lower]
        if denied:
            issues.append(f"memory_denial:{','.join(denied)}")
    return not issues, issues


def run_single_turn_case(case: dict[str, Any], npc_id: str, player_id: str, base_url: str) -> dict[str, Any]:
    start = http_json(
        "POST",
        f"{base_url}/session/start",
        {"player_id": player_id, "player_name": player_id, "npc_id": npc_id},
        timeout=20,
    )
    session_id = body_dict(start).get("session_id")
    chat = None
    end = None
    if session_id:
        chat = http_json(
            "POST",
            f"{base_url}/chat",
            {
                "player_id": player_id,
                "npc_id": npc_id,
                "message": case["message"],
                "session_id": session_id,
            },
            timeout=int(case.get("timeout_seconds", 120)),
        )
        end = http_json(
            "POST",
            f"{base_url}/session/end",
            {"session_id": session_id, "player_id": player_id, "npc_id": npc_id},
            timeout=20,
        )
    response = npc_response(chat)
    passed, issues = score_response(response, case.get("checks") or {})
    return {
        "id": case["id"],
        "type": "single_turn",
        "player_id": player_id,
        "session_id": session_id,
        "passed": bool(start.get("ok") and chat and chat.get("ok") and passed),
        "issues": issues,
        "response_preview": response[:800],
        "start_session": start,
        "chat": chat,
        "end_session": end,
    }


def run_memory_case(case: dict[str, Any], npc_id: str, player_id: str, base_url: str, memory_wait_seconds: float) -> dict[str, Any]:
    seed_message = case["seed_message"]
    recall_message = case["recall_message"]
    phase1_start = http_json(
        "POST",
        f"{base_url}/session/start",
        {"player_id": player_id, "player_name": player_id, "npc_id": npc_id},
        timeout=20,
    )
    phase1_session_id = body_dict(phase1_start).get("session_id")
    phase1_chat = None
    phase1_end = None
    if phase1_session_id:
        phase1_chat = http_json(
            "POST",
            f"{base_url}/chat",
            {
                "player_id": player_id,
                "npc_id": npc_id,
                "message": seed_message,
                "session_id": phase1_session_id,
            },
            timeout=int(case.get("timeout_seconds", 120)),
        )
        phase1_end = http_json(
            "POST",
            f"{base_url}/session/end",
            {"session_id": phase1_session_id, "player_id": player_id, "npc_id": npc_id},
            timeout=20,
        )

    if memory_wait_seconds > 0:
        time.sleep(memory_wait_seconds)

    memory_after_phase1 = http_json("GET", f"{base_url}/debug/memory/{player_id}/{npc_id}", timeout=20)
    phase2_start = http_json(
        "POST",
        f"{base_url}/session/start",
        {"player_id": player_id, "player_name": player_id, "npc_id": npc_id},
        timeout=20,
    )
    phase2_session_id = body_dict(phase2_start).get("session_id")
    loaded_memory = memory_context(phase2_start, memory_after_phase1)
    phase2_chat = None
    phase2_end = None
    if phase2_session_id:
        phase2_chat = http_json(
            "POST",
            f"{base_url}/chat",
            {
                "player_id": player_id,
                "npc_id": npc_id,
                "message": recall_message,
                "session_id": phase2_session_id,
            },
            timeout=int(case.get("timeout_seconds", 120)),
        )
        phase2_end = http_json(
            "POST",
            f"{base_url}/session/end",
            {"session_id": phase2_session_id, "player_id": player_id, "npc_id": npc_id},
            timeout=20,
        )

    recall_response = npc_response(phase2_chat)
    checks = dict(case.get("checks") or {})
    checks.setdefault("no_memory_denial", True)
    passed_response, issues = score_response(recall_response, checks)
    if not loaded_memory:
        issues.append("memory_not_loaded_on_phase2_start")
    return {
        "id": case["id"],
        "type": "cross_session_memory",
        "player_id": player_id,
        "phase1_session_id": phase1_session_id,
        "phase2_session_id": phase2_session_id,
        "memory_loaded_on_start": bool(loaded_memory),
        "memory_context_preview": loaded_memory[:800],
        "passed": bool(phase1_start.get("ok") and phase1_chat and phase1_chat.get("ok") and phase2_chat and phase2_chat.get("ok") and loaded_memory and passed_response),
        "issues": issues,
        "recall_response_preview": recall_response[:800],
        "phase1": {"start_session": phase1_start, "chat": phase1_chat, "end_session": phase1_end},
        "phase2": {"start_session": phase2_start, "chat": phase2_chat, "end_session": phase2_end},
        "memory_after_phase1": memory_after_phase1,
    }


def write_summary(report: dict[str, Any], output_dir: Path) -> None:
    lines = [
        f"# Dialogue Benchmark: {report['npc_id']}",
        "",
        f"- Run ID: `{report['run_id']}`",
        f"- Benchmark: `{report['benchmark_path']}`",
        f"- Passed: {report['passed_cases']}/{report['total_cases']}",
        "",
        "## Cases",
    ]
    for case in report["cases"]:
        status = "pass" if case["passed"] else "check"
        issue_text = ", ".join(case.get("issues") or []) or "none"
        lines.append(f"- {case['id']}: {status} ({issue_text})")
    (output_dir / "summary.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npc", required=True, help="NPC id to test.")
    parser.add_argument("--benchmark", type=Path, default=None, help="Benchmark JSON file.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--player-id-prefix", default="dialogue_benchmark")
    parser.add_argument("--memory-wait-seconds", type=float, default=8.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id or now_id()
    benchmark_path = args.benchmark or DEFAULT_BENCHMARK_DIR / f"{args.npc}.json"
    benchmark = read_json(benchmark_path)
    base_url = args.base_url.rstrip("/")
    output_dir = args.output_root / args.npc / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    cases: list[dict[str, Any]] = []
    for index, case in enumerate(benchmark.get("cases") or [], start=1):
        player_id = f"{args.player_id_prefix}_{run_id}_{index:02d}"
        case_type = case.get("type", "single_turn")
        print(f"[dialogue-benchmark] {case['id']} ({case_type})")
        if case_type == "cross_session_memory":
            result = run_memory_case(case, args.npc, player_id, base_url, args.memory_wait_seconds)
        else:
            result = run_single_turn_case(case, args.npc, player_id, base_url)
        cases.append(result)

    passed_cases = sum(1 for case in cases if case.get("passed"))
    report = {
        "run_id": run_id,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "npc_id": args.npc,
        "benchmark_path": benchmark_path.relative_to(ROOT).as_posix() if benchmark_path.is_relative_to(ROOT) else str(benchmark_path),
        "base_url": base_url,
        "total_cases": len(cases),
        "passed_cases": passed_cases,
        "pass_rate": passed_cases / len(cases) if cases else 0,
        "cases": cases,
    }
    (output_dir / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_summary(report, output_dir)
    print(f"[dialogue-benchmark] wrote {output_dir / 'summary.md'}")
    return 0 if passed_cases == len(cases) else 2


if __name__ == "__main__":
    raise SystemExit(main())
