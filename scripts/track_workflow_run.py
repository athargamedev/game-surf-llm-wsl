#!/usr/bin/env python
"""Create a traceable report for one Game_Surf NPC workflow run."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_dataset_workflow import build_audit, summarize_records
from scripts.npc_pipeline_contract import resolve_npc_spec, spec_to_dict
from scripts.training_metrics import get_training_metrics

STAGES = ("prereq", "notebooklm", "import", "prepare", "train", "artifact", "runtime", "memory")

MEMORY_DENIAL_PATTERNS = (
    "no memory",
    "do not remember",
    "don't remember",
    "cannot remember",
    "can't remember",
    "no record",
    "no saved",
    "i don't have",
    "i do not have",
    "past session",
)

MEMORY_STOPWORDS = {
    "about",
    "again",
    "because",
    "before",
    "conversation",
    "current",
    "explain",
    "from",
    "have",
    "last",
    "lesson",
    "memory",
    "more",
    "that",
    "their",
    "there",
    "these",
    "thing",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid JSON: {exc}"}


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return records, [f"missing: {path}"]
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_no}: {exc}")
            continue
        if isinstance(payload, dict):
            records.append(payload)
        else:
            errors.append(f"{path}:{line_no}: expected JSON object")
    return records, errors


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8").strip()
    return len(text.splitlines()) if text else 0


def run_command(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    started = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return {
            "command": cmd,
            "returncode": result.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "output": result.stdout[-8000:],
        }
    except FileNotFoundError as exc:
        return {"command": cmd, "returncode": 127, "duration_seconds": 0, "output": str(exc)}
    except subprocess.TimeoutExpired as exc:
        return {
            "command": cmd,
            "returncode": 124,
            "duration_seconds": round(time.time() - started, 3),
            "output": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "command timed out",
        }


def http_json(method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = request.Request(url, data=body, headers=headers, method=method)
    started = time.time()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(text)
            except json.JSONDecodeError:
                parsed = text
            return {
                "ok": 200 <= resp.status < 300,
                "status_code": resp.status,
                "duration_seconds": round(time.time() - started, 3),
                "body": parsed,
            }
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status_code": exc.code,
            "duration_seconds": round(time.time() - started, 3),
            "body": text,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "duration_seconds": round(time.time() - started, 3),
            "body": str(exc),
        }


def response_uses_memory(memory_context: str, recall_message: str, response: str) -> tuple[bool, str]:
    """Heuristic evidence that a recall answer used loaded memory."""
    memory_text = (memory_context or "").strip()
    response_text = (response or "").strip()
    if not memory_text:
        return False, "no_memory_context_loaded"
    if not response_text:
        return False, "empty_response"

    response_lower = response_text.lower()
    if any(pattern in response_lower for pattern in MEMORY_DENIAL_PATTERNS):
        return False, "response_denies_memory"

    memory_terms = {
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", memory_text.lower())
        if term not in MEMORY_STOPWORDS
    }
    recall_terms = {
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", recall_message.lower())
        if term not in MEMORY_STOPWORDS
    }
    response_terms = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", response_lower))
    matched_memory_terms = sorted((memory_terms - recall_terms) & response_terms)
    if len(matched_memory_terms) >= 2:
        return True, f"matched_memory_terms:{','.join(matched_memory_terms[:8])}"
    if "remember" in response_lower and matched_memory_terms:
        return True, f"explicit_recall_with_term:{matched_memory_terms[0]}"
    return False, "no_specific_memory_overlap"


def _body_dict(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def _extract_memory_context(start_or_memory: dict[str, Any] | None) -> str:
    body = _body_dict(start_or_memory)
    if not body:
        return ""
    return str(
        body.get("memory_summary")
        or body.get("memory_context")
        or body.get("summary")
        or ""
    )


def _extract_npc_response(chat_result: dict[str, Any] | None) -> str:
    body = _body_dict(chat_result)
    return str(body.get("npc_response") or body.get("response") or "")


def stage_prereq() -> dict[str, Any]:
    return {
        "generated_at": now_iso(),
        "cwd": str(ROOT),
        "python": sys.version.split()[0],
        "conda_unsloth": run_command(["conda", "run", "-n", "unsloth_env", "python", "--version"]),
        "gpu": run_command(["nvidia-smi"], timeout=15),
        "supabase": run_command(["supabase", "status", "-o", "env"], timeout=20),
        "env": {
            "enable_supabase": os.environ.get("ENABLE_SUPABASE"),
            "supabase_url": os.environ.get("SUPABASE_URL"),
            "llm_server_url": os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8000"),
        },
    }


def stage_notebooklm(npc: str) -> dict[str, Any]:
    research_dir = ROOT / "research" / npc
    batch_paths = sorted(research_dir.glob("notebooklm_batch_*.jsonl"))
    prompt_paths = sorted(research_dir.glob("notebooklm_batch_*_prompt.txt"))
    raw_paths = sorted(research_dir.glob("notebooklm_batch_*_raw.txt"))
    records: list[dict[str, Any]] = []
    parse_errors: list[str] = []
    per_file: list[dict[str, Any]] = []
    for path in batch_paths:
        file_records, file_errors = read_jsonl(path)
        records.extend(file_records)
        parse_errors.extend(file_errors)
        per_file.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "records": len(file_records),
                "parse_errors": len(file_errors),
            }
        )

    dry_run = None
    if batch_paths:
        dry_run = run_command(
            [
                sys.executable,
                "scripts/import_notebooklm_jsonl.py",
                "--npc",
                npc,
                "--input",
                *[str(path) for path in batch_paths],
                "--dry-run",
            ],
            timeout=60,
        )

    return {
        "research_dir": research_dir.relative_to(ROOT).as_posix(),
        "batch_files": per_file,
        "prompt_files": [path.relative_to(ROOT).as_posix() for path in prompt_paths],
        "raw_response_files": [path.relative_to(ROOT).as_posix() for path in raw_paths],
        "record_count": len(records),
        "parse_errors": parse_errors[:25],
        "summary": summarize_records(records),
        "importer_dry_run": dry_run,
    }


def stage_import(npc: str) -> dict[str, Any]:
    spec = resolve_npc_spec(npc)
    records, errors = read_jsonl(spec.raw_dataset_path)
    import_report_path = (
        ROOT / "datasets" / "personas" / spec.artifact_key / f"{spec.dataset_name}.import_report.json"
    )
    return {
        "raw_dataset_path": spec.raw_dataset_path.relative_to(ROOT).as_posix(),
        "exists": spec.raw_dataset_path.exists(),
        "record_count": len(records),
        "parse_errors": errors[:25],
        "summary": summarize_records(records),
        "import_report_path": import_report_path.relative_to(ROOT).as_posix(),
        "import_report": read_json(import_report_path),
    }


def stage_prepare(npc: str) -> dict[str, Any]:
    spec = resolve_npc_spec(npc)
    train_path = spec.processed_dir / "train.jsonl"
    validation_path = spec.processed_dir / "validation.jsonl"
    test_path = spec.processed_dir / "test.jsonl"
    metadata_path = spec.processed_dir / "metadata.json"
    return {
        "processed_dir": spec.processed_dir.relative_to(ROOT).as_posix(),
        "splits": {
            "train": count_lines(train_path),
            "validation": count_lines(validation_path),
            "test": count_lines(test_path),
        },
        "files": {
            "train": train_path.exists(),
            "validation": validation_path.exists(),
            "test": test_path.exists(),
            "metadata": metadata_path.exists(),
        },
        "metadata": read_json(metadata_path),
    }


def stage_train(npc: str) -> dict[str, Any]:
    spec = resolve_npc_spec(npc)
    training_report_path = spec.output_dir / "checkpoints" / "training_report.json"
    run_config_path = spec.output_dir / "run_config.json"
    return {
        "metrics": get_training_metrics(npc),
        "training_report_path": training_report_path.relative_to(ROOT).as_posix(),
        "training_report": read_json(training_report_path),
        "run_config_path": run_config_path.relative_to(ROOT).as_posix(),
        "run_config": read_json(run_config_path),
    }


def stage_artifact(npc: str) -> dict[str, Any]:
    spec = resolve_npc_spec(npc)
    manifest = read_json(spec.manifest_path)
    adapter_dir = spec.output_dir / "lora_adapter"
    gguf_dir = spec.output_dir / "gguf"
    return {
        "output_dir": spec.output_dir.relative_to(ROOT).as_posix(),
        "manifest_path": spec.manifest_path.relative_to(ROOT).as_posix(),
        "manifest_exists": spec.manifest_path.exists(),
        "manifest": manifest,
        "adapter": {
            "dir": adapter_dir.relative_to(ROOT).as_posix(),
            "safetensors": (adapter_dir / "adapter_model.safetensors").exists(),
            "gguf": (adapter_dir / "adapter_model.gguf").exists(),
        },
        "gguf_files": [path.relative_to(ROOT).as_posix() for path in sorted(gguf_dir.glob("*.gguf"))],
    }


def stage_runtime(npc: str, base_url: str, reload_model: bool) -> dict[str, Any]:
    result = {
        "base_url": base_url,
        "health": http_json("GET", f"{base_url}/health", timeout=8),
        "status": http_json("GET", f"{base_url}/status", timeout=8),
        "npc_models": http_json("GET", f"{base_url}/npc-models", timeout=8),
        "lora_status": http_json("GET", f"{base_url}/debug/lora-status/{npc}", timeout=8),
        "reload_model": {"skipped": not reload_model},
    }
    if reload_model:
        result["reload_model"] = http_json("POST", f"{base_url}/reload-model", {"npc_id": npc}, timeout=120)
    return result


def stage_memory(
    npc: str,
    base_url: str,
    player_id: str,
    message: str,
    skip_live_probe: bool,
    cross_session: bool = False,
    recall_message: str = "Do you remember our last conversation? Continue from that subject.",
    memory_wait_seconds: float = 8.0,
) -> dict[str, Any]:
    if skip_live_probe:
        return {"skipped": True, "reason": "--skip-live-probe"}

    if cross_session:
        return stage_cross_session_memory(
            npc=npc,
            base_url=base_url,
            player_id=player_id,
            seed_message=message,
            recall_message=recall_message,
            memory_wait_seconds=memory_wait_seconds,
        )

    start = http_json(
        "POST",
        f"{base_url}/session/start",
        {"player_id": player_id, "npc_id": npc, "player_name": "Workflow Probe"},
        timeout=20,
    )
    session_id = None
    if isinstance(start.get("body"), dict):
        session_id = start["body"].get("session_id")

    chat = None
    ended = None
    history = None
    memories = None
    if session_id:
        chat = http_json(
            "POST",
            f"{base_url}/chat",
            {"player_id": player_id, "npc_id": npc, "message": message, "session_id": session_id},
            timeout=120,
        )
        ended = http_json(
            "POST",
            f"{base_url}/session/end",
            {"session_id": session_id, "player_id": player_id, "npc_id": npc},
            timeout=20,
        )
        history = http_json("GET", f"{base_url}/session/history/{player_id}/{npc}", timeout=20)
        memories = http_json("GET", f"{base_url}/players/{player_id}/memories", timeout=20)

    return {
        "player_id": player_id,
        "message": message,
        "cross_session": False,
        "start_session": start,
        "chat": chat,
        "end_session": ended,
        "history": history,
        "memories": memories,
    }


def stage_cross_session_memory(
    npc: str,
    base_url: str,
    player_id: str,
    seed_message: str,
    recall_message: str,
    memory_wait_seconds: float,
) -> dict[str, Any]:
    """Mirror /test-10-player Phase 1/Phase 2 memory proof in a report file."""
    phase1_start = http_json(
        "POST",
        f"{base_url}/session/start",
        {"player_id": player_id, "npc_id": npc, "player_name": "Workflow Probe"},
        timeout=20,
    )
    phase1_session_id = _body_dict(phase1_start).get("session_id")
    phase1_chat = None
    phase1_end = None
    phase1_memory = None
    if phase1_session_id:
        phase1_chat = http_json(
            "POST",
            f"{base_url}/chat",
            {
                "player_id": player_id,
                "npc_id": npc,
                "message": seed_message,
                "session_id": phase1_session_id,
            },
            timeout=120,
        )
        phase1_end = http_json(
            "POST",
            f"{base_url}/session/end",
            {"session_id": phase1_session_id, "player_id": player_id, "npc_id": npc},
            timeout=20,
        )

    if memory_wait_seconds > 0:
        time.sleep(memory_wait_seconds)

    phase1_memory = http_json("GET", f"{base_url}/debug/memory/{player_id}/{npc}", timeout=20)
    phase2_start = http_json(
        "POST",
        f"{base_url}/session/start",
        {"player_id": player_id, "npc_id": npc, "player_name": "Workflow Probe"},
        timeout=20,
    )
    phase2_session_id = _body_dict(phase2_start).get("session_id")
    memory_context = _extract_memory_context(phase2_start) or _extract_memory_context(phase1_memory)
    phase2_chat = None
    phase2_end = None
    if phase2_session_id:
        phase2_chat = http_json(
            "POST",
            f"{base_url}/chat",
            {
                "player_id": player_id,
                "npc_id": npc,
                "message": recall_message,
                "session_id": phase2_session_id,
            },
            timeout=120,
        )
        phase2_end = http_json(
            "POST",
            f"{base_url}/session/end",
            {"session_id": phase2_session_id, "player_id": player_id, "npc_id": npc},
            timeout=20,
        )

    recall_response = _extract_npc_response(phase2_chat)
    memory_used, memory_reason = response_uses_memory(memory_context, recall_message, recall_response)
    history = http_json("GET", f"{base_url}/session/history/{player_id}/{npc}", timeout=20)
    memories = http_json("GET", f"{base_url}/players/{player_id}/memories", timeout=20)

    return {
        "player_id": player_id,
        "cross_session": True,
        "seed_message": seed_message,
        "recall_message": recall_message,
        "phase1_session_id": phase1_session_id,
        "phase2_session_id": phase2_session_id,
        "memory_loaded_on_start": bool(memory_context),
        "memory_context_preview": memory_context[:500],
        "memory_used_in_response": memory_used,
        "memory_response_reason": memory_reason,
        "recall_response_preview": recall_response[:500],
        "phase1": {
            "start_session": phase1_start,
            "chat": phase1_chat,
            "end_session": phase1_end,
            "memory_after_end": phase1_memory,
        },
        "phase2": {
            "start_session": phase2_start,
            "chat": phase2_chat,
            "end_session": phase2_end,
        },
        "history": history,
        "memories": memories,
    }


def build_summary(trace: dict[str, Any]) -> str:
    lines = [
        f"# Workflow Run Summary: {trace['npc']}",
        "",
        f"- Run ID: `{trace['run_id']}`",
        f"- Generated: {trace['generated_at']}",
        f"- Report dir: `{trace['report_dir']}`",
        "",
        "## Gates",
    ]
    stages = trace.get("stages", {})
    for stage_name in STAGES:
        data = stages.get(stage_name)
        if data is None:
            continue
        status = gate_status(stage_name, data)
        lines.append(f"- {stage_name}: {status}")

    lines.extend(["", "## Key Metrics"])
    imported = stages.get("import", {})
    prepared = stages.get("prepare", {})
    trained = stages.get("train", {})
    runtime = stages.get("runtime", {})
    memory = stages.get("memory", {})
    lines.append(f"- Raw imported examples: {imported.get('record_count', 0)}")
    lines.append(f"- Memory slot rate: {imported.get('summary', {}).get('memory_slot_rate', 0)}")
    lines.append(f"- Prepared splits: `{prepared.get('splits', {})}`")
    metrics = trained.get("metrics") or {}
    training = metrics.get("training", {}) if isinstance(metrics, dict) else {}
    lines.append(f"- Best eval loss: {training.get('best_eval_loss')}")
    lines.append(f"- Runtime health: {runtime.get('health', {}).get('ok')}")
    if isinstance(memory, dict) and memory.get("cross_session"):
        lines.append(f"- Memory loaded on phase 2 start: {memory.get('memory_loaded_on_start')}")
        lines.append(f"- Memory used in recall response: {memory.get('memory_used_in_response')}")
        lines.append(f"- Memory response reason: {memory.get('memory_response_reason')}")
    else:
        lines.append(f"- Memory probe: {memory.get('end_session', {}).get('ok') if isinstance(memory, dict) else None}")
    lines.extend(["", "## Next Actions"])
    lines.extend(next_actions(trace))
    return "\n".join(lines).rstrip() + "\n"


def gate_status(stage_name: str, data: dict[str, Any]) -> str:
    if stage_name == "prereq":
        conda_ok = data.get("conda_unsloth", {}).get("returncode") == 0
        gpu_ok = data.get("gpu", {}).get("returncode") == 0
        return "pass" if conda_ok and gpu_ok else "check"
    if stage_name == "notebooklm":
        return "pass" if data.get("record_count", 0) > 0 and not data.get("parse_errors") else "check"
    if stage_name == "import":
        summary = data.get("summary", {})
        return "pass" if data.get("record_count", 0) > 0 and summary.get("memory_slot_rate") == 1.0 else "check"
    if stage_name == "prepare":
        splits = data.get("splits", {})
        return "pass" if splits.get("train", 0) > 0 and splits.get("validation", 0) > 0 else "check"
    if stage_name == "train":
        return "pass" if data.get("metrics") else "check"
    if stage_name == "artifact":
        adapter = data.get("adapter", {})
        return "pass" if data.get("manifest_exists") and (adapter.get("safetensors") or adapter.get("gguf")) else "check"
    if stage_name == "runtime":
        return "pass" if data.get("health", {}).get("ok") and data.get("status", {}).get("ok") else "check"
    if stage_name == "memory":
        if data.get("skipped"):
            return "skipped"
        if data.get("cross_session"):
            phase1_ok = data.get("phase1", {}).get("end_session", {}).get("ok")
            phase2_ok = data.get("phase2", {}).get("end_session", {}).get("ok")
            memory_ok = data.get("memory_loaded_on_start") and data.get("memory_used_in_response")
            return "pass" if phase1_ok and phase2_ok and memory_ok else "check"
        return "pass" if data.get("start_session", {}).get("ok") and data.get("end_session", {}).get("ok") else "check"
    return "check"


def next_actions(trace: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    stages = trace.get("stages", {})
    imported = stages.get("import", {})
    prepared = stages.get("prepare", {})
    artifact = stages.get("artifact", {})
    runtime = stages.get("runtime", {})
    memory = stages.get("memory", {})
    if "import" in stages and imported.get("record_count", 0) == 0:
        actions.append("- Generate/import NotebookLM JSONL batches for this NPC.")
    elif "import" in stages and imported.get("summary", {}).get("memory_slot_rate") != 1.0:
        actions.append("- Re-import with the NotebookLM importer so every system prompt has the memory slot.")
    if "prepare" in stages and prepared.get("splits", {}).get("train", 0) == 0:
        actions.append("- Run dataset preparation after import succeeds.")
    if "artifact" in stages and not artifact.get("manifest_exists"):
        actions.append("- Run a LoRA smoke train or full training run to create the manifest and adapter.")
    if "runtime" in stages and not runtime.get("health", {}).get("ok"):
        actions.append("- Start the LLM/chat servers before runtime validation.")
    if isinstance(memory, dict) and not memory.get("skipped"):
        if memory.get("cross_session") and not memory.get("memory_used_in_response"):
            actions.append("- Inspect cross-session recall: memory loaded but the response did not use specific stored facts.")
        elif not memory.get("cross_session") and not memory.get("end_session", {}).get("ok"):
            actions.append("- Check Supabase connection and session end flow before relying on runtime memory.")
    if not actions:
        actions.append("- Compare this trace with the previous run and tune the weakest metric first.")
    return actions


def write_report_files(report_dir: Path, trace: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "trace.json").write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    if "import" in trace.get("stages", {}):
        audit = build_audit(trace["npc"])
        from scripts.audit_dataset_workflow import to_markdown

        (report_dir / "dataset_audit.md").write_text(to_markdown(audit), encoding="utf-8")
    if "train" in trace.get("stages", {}):
        train_data = trace["stages"]["train"].get("metrics") or {}
        (report_dir / "training_metrics.json").write_text(
            json.dumps(train_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if "runtime" in trace.get("stages", {}):
        (report_dir / "runtime_chat_test.json").write_text(
            json.dumps(trace["stages"]["runtime"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    if "memory" in trace.get("stages", {}):
        (report_dir / "supabase_memory_check.json").write_text(
            json.dumps(trace["stages"]["memory"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    (report_dir / "summary.md").write_text(build_summary(trace), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npc", required=True, help="NPC key from datasets/configs/npc_profiles.json.")
    parser.add_argument("--stage", choices=("all", *STAGES), default="all")
    parser.add_argument("--run-id", default=None, help="Stable run ID. Defaults to a timestamp.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "reports" / "workflow_runs")
    parser.add_argument("--base-url", default=os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--player-id", default="workflow_probe")
    parser.add_argument("--message", default="Give me one quick review question from our current lesson.")
    parser.add_argument(
        "--cross-session-memory",
        action="store_true",
        help="During memory stage, run Phase 1 create-memory plus Phase 2 recall proof.",
    )
    parser.add_argument(
        "--recall-message",
        default="Do you remember our last conversation? Continue from that subject.",
        help="Recall prompt for --cross-session-memory.",
    )
    parser.add_argument(
        "--memory-wait-seconds",
        type=float,
        default=8.0,
        help="Seconds to wait after ending Phase 1 before starting recall.",
    )
    parser.add_argument("--reload-model", action="store_true", help="POST /reload-model during runtime stage.")
    parser.add_argument("--skip-live-probe", action="store_true", help="Skip live session/chat/end memory probe.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = resolve_npc_spec(args.npc)
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = args.output_root / spec.npc_key / run_id
    stages_to_run = STAGES if args.stage == "all" else (args.stage,)

    trace: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": now_iso(),
        "npc": spec.npc_key,
        "artifact_key": spec.artifact_key,
        "dataset_name": spec.dataset_name,
        "report_dir": report_dir.relative_to(ROOT).as_posix() if report_dir.is_relative_to(ROOT) else str(report_dir),
        "spec": spec_to_dict(spec),
        "stages": {},
    }

    for stage_name in stages_to_run:
        print(f"[workflow-trace] {stage_name}")
        if stage_name == "prereq":
            trace["stages"][stage_name] = stage_prereq()
        elif stage_name == "notebooklm":
            trace["stages"][stage_name] = stage_notebooklm(spec.npc_key)
        elif stage_name == "import":
            trace["stages"][stage_name] = stage_import(spec.npc_key)
        elif stage_name == "prepare":
            trace["stages"][stage_name] = stage_prepare(spec.npc_key)
        elif stage_name == "train":
            trace["stages"][stage_name] = stage_train(spec.npc_key)
        elif stage_name == "artifact":
            trace["stages"][stage_name] = stage_artifact(spec.npc_key)
        elif stage_name == "runtime":
            trace["stages"][stage_name] = stage_runtime(spec.npc_key, args.base_url.rstrip("/"), args.reload_model)
        elif stage_name == "memory":
            trace["stages"][stage_name] = stage_memory(
                spec.npc_key,
                args.base_url.rstrip("/"),
                args.player_id,
                args.message,
                args.skip_live_probe,
                args.cross_session_memory,
                args.recall_message,
                args.memory_wait_seconds,
            )

    write_report_files(report_dir, trace)
    print(f"[workflow-trace] wrote {report_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
