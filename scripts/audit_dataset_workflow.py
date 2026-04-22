#!/usr/bin/env python
"""Audit Game_Surf dataset generation and training artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "datasets" / "configs" / "npc_profiles.json"
REGISTRY_PATH = ROOT / "datasets" / "configs" / "dataset_registry.json"
PERSONAS_DIR = ROOT / "datasets" / "personas"
PROCESSED_DIR = ROOT / "datasets" / "processed"
EXPORTS_DIR = ROOT / "exports" / "npc_models"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    task_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    user_lengths: list[int] = []
    assistant_lengths: list[int] = []
    users: list[str] = []
    assistants: list[str] = []
    memory_slot_count = 0
    repeated_openings: Counter[str] = Counter()

    for record in records:
        metadata = record.get("metadata", {}) or {}
        task_counter[str(metadata.get("task_type", "unknown"))] += 1
        source_counter[str(metadata.get("source_kind", "unknown"))] += 1

        messages = record.get("messages", []) or []
        system = next((msg.get("content", "") for msg in messages if msg.get("role") == "system"), "")
        user = next((msg.get("content", "") for msg in messages if msg.get("role") == "user"), "")
        assistant = next((msg.get("content", "") for msg in messages if msg.get("role") == "assistant"), "")
        if "[MEMORY_CONTEXT:" in system:
            memory_slot_count += 1

        if user:
            users.append(normalize_text(user))
            user_lengths.append(len(user.split()))
        if assistant:
            normalized_assistant = normalize_text(assistant)
            assistants.append(normalized_assistant)
            assistant_lengths.append(len(assistant.split()))
            opening = " ".join(normalized_assistant.split()[:3])
            if opening:
                repeated_openings[opening] += 1

    total = len(records)
    duplicate_users = max(0, len(users) - len(set(users)))
    duplicate_assistants = max(0, len(assistants) - len(set(assistants)))
    hot_openings = {opening: count for opening, count in repeated_openings.items() if count >= 3}

    return {
        "count": total,
        "task_distribution": dict(sorted(task_counter.items())),
        "source_distribution": dict(sorted(source_counter.items())),
        "avg_user_words": round(sum(user_lengths) / len(user_lengths), 2) if user_lengths else 0.0,
        "avg_assistant_words": round(sum(assistant_lengths) / len(assistant_lengths), 2) if assistant_lengths else 0.0,
        "memory_slot_rate": round(memory_slot_count / total, 3) if total else 0.0,
        "duplicate_user_count": duplicate_users,
        "duplicate_assistant_count": duplicate_assistants,
        "repeated_openings": dict(sorted(hot_openings.items())),
    }


def latest_eval_loss(*candidates: str) -> float | None:
    for candidate in candidates:
        report_path = EXPORTS_DIR / candidate / "checkpoints" / "training_report.json"
        if not report_path.exists():
            continue
        data = load_json(report_path)
        eval_losses = data.get("eval_losses") or []
        if not eval_losses:
            continue
        latest = eval_losses[-1]
        value = latest.get("eval_loss")
        if value is not None:
            return round(float(value), 4)
    return None


def build_audit(npc_filter: str | None = None) -> dict[str, Any]:
    profiles = load_json(PROFILES_PATH).get("profiles", {})
    registry = load_json(REGISTRY_PATH).get("datasets", [])
    registry_by_name = {entry.get("name"): entry for entry in registry if entry.get("name")}

    rows: list[dict[str, Any]] = []
    for npc_key, profile in sorted(profiles.items()):
        artifact_key = profile.get("artifact_key", npc_key)
        dataset_name = profile.get("dataset_name", f"{artifact_key}_dataset")
        if npc_filter and npc_filter not in {npc_key, artifact_key, dataset_name}:
            continue

        registry_entry = registry_by_name.get(dataset_name, {})
        raw_path = ROOT / registry_entry.get(
            "path",
            str(PERSONAS_DIR / artifact_key / f"{dataset_name}.jsonl"),
        )
        if not raw_path.is_absolute():
            raw_path = ROOT / raw_path

        processed_dir = PROCESSED_DIR / dataset_name
        processed_meta_path = processed_dir / "metadata.json"
        import_report_path = PERSONAS_DIR / artifact_key / f"{dataset_name}.import_report.json"

        raw_records = load_jsonl(raw_path)
        raw_summary = summarize_records(raw_records)
        processed_meta = load_json(processed_meta_path) if processed_meta_path.exists() else {}
        import_report = load_json(import_report_path) if import_report_path.exists() else {}

        rows.append(
            {
                "npc_key": npc_key,
                "artifact_key": artifact_key,
                "dataset_name": dataset_name,
                "subject": profile.get("subject", ""),
                "raw_path": raw_path.relative_to(ROOT).as_posix() if raw_path.exists() else raw_path.as_posix(),
                "raw": raw_summary,
                "processed_splits": processed_meta.get("splits", {}),
                "processed_report": processed_meta.get("report", {}),
                "import_report": import_report,
                "latest_eval_loss": latest_eval_loss(artifact_key, npc_key),
                "registry_source_kind": registry_entry.get("source_kind"),
            }
        )

    total_raw = sum(row["raw"]["count"] for row in rows)
    notebooklm_rows = sum(1 for row in rows if row.get("registry_source_kind") == "notebooklm_direct")
    trained_rows = sum(1 for row in rows if row.get("latest_eval_loss") is not None)
    weak_coverage = [
        row["npc_key"]
        for row in rows
        if row["raw"]["count"] and len(row["raw"].get("task_distribution", {})) < 2
    ]

    return {
        "summary": {
            "npc_count": len(rows),
            "total_raw_examples": total_raw,
            "notebooklm_direct_datasets": notebooklm_rows,
            "datasets_with_training_reports": trained_rows,
            "single_task_datasets": weak_coverage,
        },
        "datasets": rows,
    }


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Dataset Workflow Audit",
        "",
        "## Summary",
        f"- NPCs audited: {report['summary']['npc_count']}",
        f"- Total raw examples: {report['summary']['total_raw_examples']}",
        f"- NotebookLM-direct datasets: {report['summary']['notebooklm_direct_datasets']}",
        f"- Datasets with training reports: {report['summary']['datasets_with_training_reports']}",
    ]
    weak = report["summary"].get("single_task_datasets") or []
    if weak:
        lines.append(f"- Single-task datasets: {', '.join(weak)}")
    lines.extend(["", "## Datasets", ""])

    for row in report["datasets"]:
        lines.extend(
            [
                f"### {row['npc_key']}",
                f"- Dataset: `{row['dataset_name']}`",
                f"- Raw examples: {row['raw']['count']}",
                f"- Task distribution: `{row['raw']['task_distribution']}`",
                f"- Avg assistant words: {row['raw']['avg_assistant_words']}",
                f"- Duplicate users: {row['raw']['duplicate_user_count']}",
                f"- Duplicate assistants: {row['raw']['duplicate_assistant_count']}",
                f"- Memory slot rate: {row['raw']['memory_slot_rate']}",
                f"- Processed splits: `{row['processed_splits']}`",
                f"- Latest eval loss: {row['latest_eval_loss']}" if row['latest_eval_loss'] is not None else "- Latest eval loss: none",
            ]
        )
        import_report = row.get("import_report") or {}
        if import_report:
            lines.append(f"- Import avg quality: {import_report.get('average_quality', 0.0)}")
            lines.append(f"- Import quality signals: `{import_report.get('quality_signals', {})}`")
        repeated = row["raw"].get("repeated_openings") or {}
        if repeated:
            lines.append(f"- Repeated openings: `{repeated}`")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npc", default=None, help="Audit only one NPC or dataset key.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, default=None, help="Optional output file path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_audit(args.npc)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) if args.format == "json" else to_markdown(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
