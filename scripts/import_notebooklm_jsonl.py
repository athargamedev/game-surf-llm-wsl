#!/usr/bin/env python
"""Import NotebookLM-authored JSONL examples into the NPC dataset registry."""

from __future__ import annotations

import argparse
from collections import Counter
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
}

MEMORY_SLOT_TEMPLATE = "[MEMORY_CONTEXT: {memory_slot}]"
FORBIDDEN_ASSISTANT_TERMS = [
    "as an ai",
    "language model",
    "training example",
    "dataset",
    "system prompt",
    "prompt engineering",
]
GENERIC_ASSISTANT_OPENERS = (
    "sure",
    "of course",
    "absolutely",
    "certainly",
    "here's",
    "let me",
)


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
    exact_memory_slot = MEMORY_SLOT_TEMPLATE.format(memory_slot=memory_slot)
    if "[MEMORY_CONTEXT:" in system_prompt:
        normalized = re.sub(r"\[MEMORY_CONTEXT:\s*[^\]]*\]", exact_memory_slot, system_prompt)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    display_name = profile.get("display_name", "NPC")
    subject = profile.get("subject", "")
    tone = profile.get("personality", {}).get("tone", "")
    speaking_style = profile.get("personality", {}).get("speaking_style", "")
    rules = " ".join(profile.get("voice_rules", [])[:4])
    return (
        f"You are {display_name}. {exact_memory_slot} "
        f"Subject: {subject}. Style: {tone}; {speaking_style}. "
        f"Rules: {rules} Max 3 sentences. Stay in character."
    )


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).lower()


def count_sentences(text: str) -> int:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    return len(parts)


def opening_ngram(text: str, size: int = 3) -> str:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return " ".join(words[:size])


def contains_memory_reference(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "last time",
        "previously",
        "earlier",
        "before",
        "you told me",
        "we practiced",
        "we talked about",
        "you explained",
    )
    return any(marker in lowered for marker in markers)


def compute_quality_score(
    system_prompt: str,
    user_message: str,
    assistant_response: str,
    task_type: str,
) -> tuple[float, list[str]]:
    score = 0.9
    signals: list[str] = []
    assistant_word_count = len(re.findall(r"\S+", assistant_response))
    user_word_count = len(re.findall(r"\S+", user_message))
    sentence_count = count_sentences(assistant_response)
    normalized_assistant = normalize_text(assistant_response)

    if assistant_word_count < 8:
        score -= 0.12
        signals.append("assistant_too_short")
    if assistant_word_count > 85:
        score -= 0.08
        signals.append("assistant_too_long")
    if sentence_count > 3:
        score -= 0.08
        signals.append("assistant_over_3_sentences")
    if user_word_count < 4:
        score -= 0.08
        signals.append("user_too_short")
    if normalized_assistant.startswith(GENERIC_ASSISTANT_OPENERS):
        score -= 0.05
        signals.append("generic_assistant_opener")
    if assistant_response.count("!") > 2:
        score -= 0.04
        signals.append("excess_exclamation")
    if contains_memory_reference(user_message) and "[MEMORY_CONTEXT:" not in system_prompt:
        score -= 0.1
        signals.append("memory_reference_without_slot")

    return max(0.0, round(score, 2)), signals


def validate_and_normalize(
    record: dict[str, Any],
    profile_key: str,
    profile: dict[str, Any],
    memory_slot: str,
) -> tuple[dict[str, Any] | None, str | None, list[str]]:
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        return None, "messages must contain exactly 3 entries", []

    expected_roles = ["system", "user", "assistant"]
    normalized_messages: list[dict[str, str]] = []
    for index, expected_role in enumerate(expected_roles):
        message = messages[index]
        if not isinstance(message, dict):
            return None, f"message {index + 1} is not an object", []
        if message.get("role") != expected_role:
            return None, f"message {index + 1} role must be {expected_role}", []
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return None, f"message {index + 1} content is empty", []
        normalized_messages.append({"role": expected_role, "content": content.strip()})

    normalized_messages[0]["content"] = normalize_system_prompt(
        normalized_messages[0]["content"],
        profile,
        memory_slot,
    )
    expected_memory_slot = MEMORY_SLOT_TEMPLATE.format(memory_slot=memory_slot)
    system_prompt = normalized_messages[0]["content"]
    if system_prompt.count(expected_memory_slot) != 1:
        return None, "system prompt must contain the exact memory slot exactly once", []

    assistant = normalized_messages[2]["content"].lower()
    if any(term in assistant for term in FORBIDDEN_ASSISTANT_TERMS):
        return None, "assistant response leaks implementation/training language", []

    user_message = normalized_messages[1]["content"]
    assistant_message = normalized_messages[2]["content"]
    if len(re.findall(r"\S+", user_message)) < 3:
        return None, "user message is too short to train useful behavior", []
    if len(re.findall(r"\S+", assistant_message)) < 5:
        return None, "assistant response is too short to train useful behavior", []

    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    metadata = {
        **metadata,
        **REQUIRED_METADATA,
        "npc_key": profile_key,
        "npc_scope": profile.get("npc_scope", "instructor"),
    }
    if metadata.get("task_type") not in {"teaching", "quiz"}:
        metadata["task_type"] = "teaching"
    quality, signals = compute_quality_score(
        normalized_messages[0]["content"],
        user_message,
        assistant_message,
        metadata["task_type"],
    )
    metadata["quality"] = quality

    return {"messages": normalized_messages, "metadata": metadata}, None, signals


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
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.75,
        help="Reject imported examples scored below this heuristic quality threshold.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Optional JSON import report path.",
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
    seen_pairs: set[str] = set()
    seen_users: set[str] = set()
    seen_assistants: set[str] = set()
    duplicates = 0
    duplicate_users = 0
    duplicate_assistants = 0
    quality_signals: Counter[str] = Counter()

    for index, record in enumerate(raw_records, 1):
        normalized, error, signals = validate_and_normalize(record, args.npc, profile, args.memory_slot)
        if error:
            invalid.append(f"record {index}: {error}")
            continue
        assert normalized is not None
        quality = float(normalized.get("metadata", {}).get("quality", 0.0))
        if quality < args.min_quality:
            invalid.append(
                f"record {index}: heuristic quality {quality:.2f} below threshold {args.min_quality:.2f}"
            )
            continue
        pair_key = response_key(normalized)
        user_key = normalize_text(normalized["messages"][1]["content"])
        assistant_key = normalize_text(normalized["messages"][2]["content"])
        if pair_key in seen_pairs:
            duplicates += 1
            continue
        if user_key in seen_users:
            duplicate_users += 1
            invalid.append(f"record {index}: duplicate user message")
            continue
        if assistant_key in seen_assistants:
            duplicate_assistants += 1
            invalid.append(f"record {index}: duplicate assistant response")
            continue
        seen_pairs.add(pair_key)
        seen_users.add(user_key)
        seen_assistants.add(assistant_key)
        quality_signals.update(signals)
        valid.append(normalized)

    task_distribution = Counter(
        record.get("metadata", {}).get("task_type", "unknown")
        for record in valid
    )
    average_quality = round(
        sum(float(record.get("metadata", {}).get("quality", 0.0)) for record in valid) / len(valid),
        3,
    ) if valid else 0.0

    print("NotebookLM JSONL import summary")
    print(f"  Input records: {len(raw_records)}")
    print(f"  Valid unique: {len(valid)}")
    print(f"  Duplicates: {duplicates}")
    print(f"  Duplicate users: {duplicate_users}")
    print(f"  Duplicate assistants: {duplicate_assistants}")
    print(f"  Invalid: {len(invalid)}")
    print(f"  Average quality: {average_quality:.3f}")
    print(f"  Task distribution: {dict(sorted(task_distribution.items()))}")
    if quality_signals:
        print(f"  Quality signals: {dict(sorted(quality_signals.items()))}")
    for error in invalid[:20]:
        print(f"    - {error}")
    if len(invalid) > 20:
        print(f"    ... {len(invalid) - 20} more")

    report = {
        "npc": args.npc,
        "inputs": [str(path) for path in args.input],
        "input_records": len(raw_records),
        "valid_unique": len(valid),
        "duplicates": duplicates,
        "duplicate_users": duplicate_users,
        "duplicate_assistants": duplicate_assistants,
        "invalid": len(invalid),
        "average_quality": average_quality,
        "task_distribution": dict(sorted(task_distribution.items())),
        "quality_signals": dict(sorted(quality_signals.items())),
        "sample_errors": invalid[:20],
    }
    report_path = args.report_json
    if report_path is None and not args.dry_run:
        artifact_key = profile.get("artifact_key", args.npc)
        dataset_name = profile.get("dataset_name", f"{artifact_key}_dataset")
        report_path = PERSONAS_DIR / artifact_key / f"{dataset_name}.import_report.json"

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
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Wrote: {output_path.relative_to(ROOT_DIR).as_posix()}")
    if not args.no_registry:
        print(f"  Updated: {REGISTRY_PATH.relative_to(ROOT_DIR).as_posix()}")
    if report_path is not None:
        print(f"  Report: {report_path.relative_to(ROOT_DIR).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
