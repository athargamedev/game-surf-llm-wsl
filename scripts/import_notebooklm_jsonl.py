#!/usr/bin/env python
"""Import NotebookLM-authored JSONL examples into the NPC dataset registry."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT_DIR / "datasets" / "configs" / "npc_profiles.json"
REGISTRY_PATH = ROOT_DIR / "datasets" / "configs" / "dataset_registry.json"
PERSONAS_DIR = ROOT_DIR / "datasets" / "personas"

REQUIRED_METADATA = {
    "source_kind": "notebooklm_direct",
    "quality": 0.9,
}


def load_profiles() -> dict[str, dict[str, Any]]:
    data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    return data.get("profiles", {})


def load_jsonl(paths: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in paths:
        for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path}:{line_no}: invalid JSON: {exc}")
                continue
            if not isinstance(data, dict):
                errors.append(f"{path}:{line_no}: expected JSON object")
                continue
            records.append(data)

    return records, errors


def normalize_system_prompt(system_prompt: str, profile: dict[str, Any], memory_slot: str) -> str:
    if "[MEMORY_CONTEXT:" in system_prompt:
        return system_prompt

    display_name = profile.get("display_name", "NPC")
    subject = profile.get("subject", "")
    tone = profile.get("personality", {}).get("tone", "")
    speaking_style = profile.get("personality", {}).get("speaking_style", "")
    rules = " ".join(profile.get("voice_rules", [])[:4])
    return (
        f"You are {display_name}. [MEMORY_CONTEXT: {memory_slot}] "
        f"Subject: {subject}. Style: {tone}; {speaking_style}. "
        f"Rules: {rules} Max 3 sentences. Stay in character."
    )


def validate_and_normalize(
    record: dict[str, Any],
    profile_key: str,
    profile: dict[str, Any],
    memory_slot: str,
) -> tuple[dict[str, Any] | None, str | None]:
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        return None, "messages must contain exactly 3 entries"

    expected_roles = ["system", "user", "assistant"]
    normalized_messages: list[dict[str, str]] = []
    for index, expected_role in enumerate(expected_roles):
        message = messages[index]
        if not isinstance(message, dict):
            return None, f"message {index + 1} is not an object"
        if message.get("role") != expected_role:
            return None, f"message {index + 1} role must be {expected_role}"
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None, f"message {index + 1} content is empty"
        normalized_messages.append({"role": expected_role, "content": content.strip()})

    normalized_messages[0]["content"] = normalize_system_prompt(
        normalized_messages[0]["content"],
        profile,
        memory_slot,
    )

    assistant = normalized_messages[2]["content"].lower()
    forbidden = ["as an ai", "language model", "training example", "dataset", "system prompt"]
    if any(term in assistant for term in forbidden):
        return None, "assistant response leaks implementation/training language"

    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    metadata = {
        **metadata,
        **REQUIRED_METADATA,
        "npc_key": profile_key,
        "npc_scope": profile.get("npc_scope", "instructor"),
    }
    if metadata.get("task_type") not in {"teaching", "quiz"}:
        metadata["task_type"] = "teaching"

    return {"messages": normalized_messages, "metadata": metadata}, None


def response_key(record: dict[str, Any]) -> str:
    user = record["messages"][1]["content"]
    assistant = record["messages"][2]["content"]
    text = f"{user}\n{assistant}".lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def update_registry(profile: dict[str, Any], dataset_path: Path, sample_count: int) -> None:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    datasets = registry.setdefault("datasets", [])
    dataset_name = profile.get("dataset_name")
    rel_path = dataset_path.relative_to(ROOT_DIR).as_posix()

    entry = {
        "name": dataset_name,
        "path": rel_path,
        "task_type": "mixed",
        "npc_scope": profile.get("npc_scope", "instructor"),
        "format": "chatml",
        "sample_count": sample_count,
        "weight": 1.0,
        "source_kind": "notebooklm_direct",
        "_note": f"Imported from NotebookLM direct JSONL - {profile.get('display_name', dataset_name)}",
    }

    for index, current in enumerate(datasets):
        if current.get("name") == dataset_name:
            datasets[index] = entry
            break
    else:
        datasets.append(entry)

    registry["_updated"] = "auto-generated by import_notebooklm_jsonl.py"
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import NotebookLM JSONL examples for one NPC.")
    parser.add_argument("--npc", required=True, help="NPC profile key from npc_profiles.json.")
    parser.add_argument("--input", nargs="+", required=True, type=Path, help="NotebookLM JSONL batch files.")
    parser.add_argument("--output", type=Path, default=None, help="Optional output JSONL path.")
    parser.add_argument(
        "--memory-slot",
        default="{player_memory_summary}",
        help="Dynamic memory slot to enforce in system prompts.",
    )
    parser.add_argument("--no-registry", action="store_true", help="Write output without updating dataset_registry.json.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profiles = load_profiles()
    if args.npc not in profiles:
        raise SystemExit(f"Unknown NPC '{args.npc}'. Available: {', '.join(sorted(profiles))}")

    profile = profiles[args.npc]
    artifact_key = profile.get("artifact_key", args.npc)
    dataset_name = profile.get("dataset_name", f"{artifact_key}_dataset")
    output_path = args.output or PERSONAS_DIR / artifact_key / f"{dataset_name}.jsonl"

    raw_records, parse_errors = load_jsonl(args.input)
    valid: list[dict[str, Any]] = []
    invalid: list[str] = list(parse_errors)
    seen: set[str] = set()
    duplicates = 0

    for index, record in enumerate(raw_records, 1):
        normalized, error = validate_and_normalize(record, args.npc, profile, args.memory_slot)
        if error:
            invalid.append(f"record {index}: {error}")
            continue
        assert normalized is not None
        key = response_key(normalized)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        valid.append(normalized)

    print("NotebookLM JSONL import summary")
    print(f"  Input records: {len(raw_records)}")
    print(f"  Valid unique: {len(valid)}")
    print(f"  Duplicates: {duplicates}")
    print(f"  Invalid: {len(invalid)}")
    for error in invalid[:20]:
        print(f"    - {error}")
    if len(invalid) > 20:
        print(f"    ... {len(invalid) - 20} more")

    if args.dry_run:
        return 0 if valid else 1

    if not valid:
        raise SystemExit("No valid records to write.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in valid) + "\n",
        encoding="utf-8",
    )
    if not args.no_registry:
        update_registry(profile, output_path, len(valid))
    print(f"  Wrote: {output_path.relative_to(ROOT_DIR).as_posix()}")
    if not args.no_registry:
        print(f"  Updated: {REGISTRY_PATH.relative_to(ROOT_DIR).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
