#!/usr/bin/env python
"""
Dataset Preparation Pipeline for Game_Surf NPC Dialogue

Converts raw Game_Surf data to professional ChatML format with:
- Metadata schema (npc_scope, task_type, quality, source_kind)
- Quality filtering
- Train/val/test splits
- Export to HuggingFace Hub (optional)

Usage:
    python prepare_dataset.py --input datasets/personas/kai_instructor/kai_instructor_dataset.jsonl
    python prepare_dataset.py --input datasets/ --merge-npc
    python prepare_dataset.py --push-to-hub my-org/surf-npc-dialogue
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from datasets import Dataset, DatasetDict, load_dataset, load_from_disk


# ==============================================================================
# METADATA SCHEMA
# ==============================================================================

METADATA_SCHEMA = {
    "npc_scope": {
        "type": "string",
        "choices": [
            "world",
            "lab_guide",
            "instructor",
            "merchant",
            "rival",
            "guard",
            "shared_role",
        ],
        "description": "NPC role/category",
    },
    "task_type": {
        "type": "string",
        "choices": [
            "mixed",
            "greeting",
            "hint",
            "teaching",
            "refusal",
            "scene_explanation",
            "object_awareness",
            "component_awareness",
            "quiz",
            "redirect",
            "multi_turn",
        ],
        "description": "Dialogue task type",
    },
    "source_kind": {
        "type": "string",
        "choices": ["authored", "playtest", "design_note", "synthetic"],
        "description": "Origin of the data",
    },
    "quality": {
        "type": "float",
        "range": [0.0, 1.0],
        "description": "Quality score for filtering",
    },
}

REQUIRED_FIELDS = ["messages", "metadata"]

# ==============================================================================
# FORMATS
# ==============================================================================


def to_chatml_format(
    instruction: str,
    response: str,
    system: str = "You are a helpful conversational instructor.",
) -> dict:
    """Convert instruction/response to ChatML messages format."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": instruction},
        {"role": "assistant", "content": response},
    ]

    return {
        "messages": messages,
        "metadata": {
            "npc_scope": "world",
            "task_type": "mixed",
            "source_kind": "authored",
            "quality": 1.0,
        },
    }


def to_sharegpt_format(
    instruction: str,
    response: str,
    system: str = "",
) -> dict:
    """Convert to ShareGPT format (conversations array)."""

    conv = []
    if system:
        conv.append({"from": "system", "value": system})
    conv.append({"from": "human", "value": instruction})
    conv.append({"from": "gpt", "value": response})

    return {
        "conversations": conv,
    }


# ==============================================================================
# MAIN PARSER
# ==============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dataset Preparation Pipeline",
    )

    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input file or directory",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="datasets/processed",
        help="Output directory",
    )
    parser.add_argument(
        "--format",
        choices=["jsonl", "json", "alpaca", "sharegpt", "chatml", "auto"],
        default="auto",
        help="Input format",
    )
    parser.add_argument(
        "--add-metadata",
        action="store_true",
        help="Add default metadata if not present",
    )
    parser.add_argument(
        "--npc-scope",
        default="world",
        choices=METADATA_SCHEMA["npc_scope"]["choices"],
        help="Default NPC scope",
    )
    parser.add_argument(
        "--task-type",
        default="mixed",
        choices=METADATA_SCHEMA["task_type"]["choices"],
        help="Default task type",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=0.0,
        help="Filter by minimum quality score",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.1,
        help="Validation split ratio",
    )
    parser.add_argument(
        "--test-split",
        type=float,
        default=0.1,
        help="Test split ratio",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=3407,
        help="Random seed",
    )
    parser.add_argument(
        "--push-to-hub",
        help="Push to HuggingFace Hub (org/dataset)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output",
    )

    # OPTIMIZATION: Stratified splitting
    parser.add_argument(
        "--stratify-by",
        type=str,
        default=None,
        choices=["task_type", "npc_scope", "source_kind"],
        help="Metadata field to stratify splits by (ensures proportional distribution)",
    )

    # OPTIMIZATION: Deduplication
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Remove duplicate examples",
    )
    parser.add_argument(
        "--dedup-by",
        type=str,
        default="content",
        choices=["content", "messages", "response"],
        help="Field to use for deduplication",
    )
    parser.add_argument(
        "--min-task-examples",
        type=int,
        default=0,
        help="Require at least this many examples per task_type after filtering.",
    )

    return parser.parse_args()


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().split())


def build_dataset_report(dataset: Dataset) -> dict[str, Any]:
    task_counter: Counter[str] = Counter()
    scope_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    user_lengths: list[int] = []
    assistant_lengths: list[int] = []
    unique_users: set[str] = set()
    unique_assistants: set[str] = set()
    memory_slot_count = 0

    for example in dataset:
        metadata = example.get("metadata", {}) or {}
        task_counter[str(metadata.get("task_type", "unknown"))] += 1
        scope_counter[str(metadata.get("npc_scope", "unknown"))] += 1
        source_counter[str(metadata.get("source_kind", "unknown"))] += 1

        messages = example.get("messages", []) or []
        system = next((msg.get("content", "") for msg in messages if msg.get("role") == "system"), "")
        user = next((msg.get("content", "") for msg in messages if msg.get("role") == "user"), "")
        assistant = next((msg.get("content", "") for msg in messages if msg.get("role") == "assistant"), "")

        if "[MEMORY_CONTEXT:" in system:
            memory_slot_count += 1
        user_lengths.append(len(user.split()))
        assistant_lengths.append(len(assistant.split()))
        if user:
            unique_users.add(_normalized_text(user))
        if assistant:
            unique_assistants.add(_normalized_text(assistant))

    total = len(dataset)
    return {
        "npc_scope_distribution": dict(sorted(scope_counter.items())),
        "task_distribution": dict(sorted(task_counter.items())),
        "source_distribution": dict(sorted(source_counter.items())),
        "average_user_words": round(sum(user_lengths) / len(user_lengths), 2) if user_lengths else 0.0,
        "average_assistant_words": round(sum(assistant_lengths) / len(assistant_lengths), 2) if assistant_lengths else 0.0,
        "unique_user_count": len(unique_users),
        "unique_assistant_count": len(unique_assistants),
        "memory_slot_rate": round(memory_slot_count / total, 3) if total else 0.0,
    }


def summarize_dataset_metadata(report: dict[str, Any], default_scope: str, default_task: str) -> tuple[str, str]:
    scope_distribution = report.get("npc_scope_distribution", {}) or {}
    task_distribution = report.get("task_distribution", {}) or {}

    if len(scope_distribution) == 1:
        npc_scope = next(iter(scope_distribution))
    else:
        npc_scope = default_scope

    if len(task_distribution) == 1:
        task_type = next(iter(task_distribution))
    elif task_distribution:
        task_type = "mixed"
    else:
        task_type = default_task

    return npc_scope, task_type


def enforce_task_minimums(dataset: Dataset, minimum: int) -> None:
    if minimum <= 0:
        return

    counts: Counter[str] = Counter(
        str((example.get("metadata") or {}).get("task_type", "unknown"))
        for example in dataset
    )
    failing = {task_type: count for task_type, count in counts.items() if count < minimum}
    if failing:
        details = ", ".join(f"{task_type}={count}" for task_type, count in sorted(failing.items()))
        raise ValueError(
            "Task coverage check failed after filtering/deduplication. "
            f"Required >= {minimum} examples per task_type, found: {details}"
        )


def detect_format(path: Path) -> str:
    """Auto-detect input format."""

    if path.is_dir():
        # Check first file
        files = list(path.glob("*.jsonl")) or list(path.glob("*.json"))
        if files:
            path = files[0]

    # Read enough to support both JSONL and pretty-printed JSON manifests.
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline()
        raw_text = first_line
        if first_line.strip() in {"{", "["}:
            raw_text = first_line + f.read()

    try:
        data = json.loads(first_line)
    except json.JSONDecodeError:
        data = json.loads(raw_text)
    if isinstance(data, dict) and isinstance(data.get("datasets"), list):
        raise ValueError(
            "Input appears to be a dataset registry manifest. "
            "Select a raw dataset file or directory, not dataset_registry.json."
        )

    # Detect
    if "messages" in data:
        return "chatml"
    if "conversations" in data:
        return "sharegpt"
    if "instruction" in data and "output" in data:
        return "alpaca"
    if "instruction" in data and "response" in data:
        return "alpaca"
    if "conversations" in data:
        return "sharegpt"
    if "input" in data and "output" in data:
        return "alpaca"

    raise ValueError(
        f"Cannot detect format for '{path}'. "
        "Expected keys: 'messages' (chatml), 'conversations' (sharegpt), "
        "or 'instruction'+'output' (alpaca)."
    )


def load_raw_input(path: str, format: str) -> Dataset:
    """Load raw input data."""

    p = Path(path)

    def load_json_records(file_path: Path) -> list[dict]:
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        if file_path.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]

        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "examples", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        raise ValueError(f"Unsupported JSON root in {file_path}: {type(data).__name__}")

    if p.is_dir():
        files = list(p.glob("*.jsonl")) + list(p.glob("*.json"))
        records: list[dict] = []
        for file_path in sorted(files):
            records.extend(load_json_records(file_path))
        return Dataset.from_list(records)
    elif format == "auto":
        fmt = detect_format(p)
    else:
        fmt = format

    if fmt not in {"jsonl", "json", "alpaca", "sharegpt", "chatml"}:
        raise ValueError(f"Unknown format for {p} (detected: {fmt})")

    return Dataset.from_list(load_json_records(p))


def convert_to_chatml(dataset: Dataset, format: str) -> Dataset:
    """Convert various formats to ChatML."""

    if format == "chatml":
        return dataset  # Already correct

    if format == "sharegpt":
        # Convert from conversations
        def convert(example):
            conv = example.get("conversations", [])
            messages = []
            for turn in conv:
                role = turn.get("from", "")
                if role in ("system", "human", "gpt"):
                    # Map to standard roles
                    role_map = {"system": "system", "human": "user", "gpt": "assistant"}
                    messages.append(
                        {
                            "role": role_map.get(role, role),
                            "content": turn.get("value", ""),
                        }
                    )

            return {"messages": messages}

        return dataset.map(convert, desc="Converting ShareGPT to ChatML")

    if format == "alpaca":
        # Convert from instruction/response
        def convert(example):
            messages = [
                {"role": "system", "content": example.get("system", "")},
                {"role": "user", "content": example.get("instruction", "")},
                {
                    "role": "assistant",
                    "content": example.get("output", example.get("response", "")),
                },
            ]
            return {"messages": messages}

        return dataset.map(convert, desc="Converting Alpaca to ChatML")

    return dataset


def add_default_metadata(dataset: Dataset, npc_scope: str, task_type: str) -> Dataset:
    """Add default metadata to dataset."""

    def add_meta(example):
        meta = example.get("metadata", {})
        meta.setdefault("npc_scope", npc_scope)
        meta.setdefault("task_type", task_type)
        meta.setdefault("source_kind", "authored")
        meta.setdefault("quality", 1.0)
        return {"metadata": meta}

    return dataset.map(add_meta, desc="Adding metadata")


def filter_quality(dataset: Dataset, threshold: float) -> Dataset:
    """Filter by quality score."""

    if threshold <= 0:
        return dataset

    def check_quality(example):
        q = example.get("metadata", {}).get("quality", 1.0)
        return q >= threshold

    return dataset.filter(check_quality, desc=f"Quality >= {threshold}")


def split_dataset(
    dataset: Dataset,
    val_split: float,
    test_split: float,
    seed: int,
) -> DatasetDict:
    """Split into train/val/test."""

    # First split off test
    if test_split > 0:
        split = dataset.train_test_split(test_size=test_split, seed=seed)
        test = split["test"]
        train_val = split["train"]
    else:
        train_val = dataset
        test = None

    # Then split val from train
    if val_split > 0:
        split = train_val.train_test_split(test_size=val_split, seed=seed)
        train = split["train"]
        val = split["test"]
    else:
        train = train_val
        val = None

    if val and test:
        return DatasetDict({"train": train, "validation": val, "test": test})
    elif val:
        return DatasetDict({"train": train, "validation": val})
    else:
        return DatasetDict({"train": train})


# ==============================================================================
# OPTIMIZATION: STRATIFIED SPLITTING & DEDUPLICATION
# ==============================================================================


def stratified_split(
    dataset: Dataset,
    stratify_by: str,
    val_split: float,
    test_split: float,
    seed: int,
) -> DatasetDict:
    """Split dataset stratified by metadata field.

    OPTIMIZATION: Ensures each stratum (task_type, npc_scope) is
    represented in train/val/test splits proportionally.

    Args:
        dataset: Input dataset
        stratify_by: Metadata field to stratify by (e.g., "task_type", "npc_scope")
        val_split: Validation split ratio
        test_split: Test split ratio
        seed: Random seed

    Returns:
        DatasetDict with train/validation/test splits
    """
    from collections import defaultdict
    import random

    # Group by stratify field
    strata_groups: defaultdict[str, list[int]] = defaultdict(list)
    for i, example in enumerate(dataset):
        meta = example.get("metadata") or {}
        label = str(meta.get(stratify_by, "unknown"))
        strata_groups[label].append(i)

    # Distribute each stratum across splits
    train_idx: list[int] = []
    val_idx: list[int] = []
    test_idx: list[int] = []

    rng = random.Random(seed)

    for indices in strata_groups.values():
        rng.shuffle(indices)
        n = len(indices)
        remaining = n

        n_test = int(n * test_split) if test_split > 0 else 0
        if test_split > 0 and n_test == 0 and n >= 3:
            n_test = 1
        n_test = min(n_test, max(0, remaining - 1))
        remaining -= n_test

        n_val = int(n * val_split) if val_split > 0 else 0
        if val_split > 0 and n_val == 0 and remaining >= 2:
            n_val = 1
        n_val = min(n_val, max(0, remaining - 1))

        test_idx.extend(indices[:n_test])
        val_idx.extend(indices[n_test : n_test + n_val])
        train_idx.extend(indices[n_test + n_val :])

    # Build result DatasetDict
    result = {}
    if train_idx:
        result["train"] = dataset.select(train_idx)
    if val_idx:
        result["validation"] = dataset.select(val_idx)
    if test_idx:
        result["test"] = dataset.select(test_idx)

    print(
        f"[STRATIFIED] Split by '{stratify_by}': "
        f"train={len(result.get('train', []))}, "
        f"val={len(result.get('validation', []))}, "
        f"test={len(result.get('test', []))}"
    )

    return DatasetDict(result)


def deduplicate_dataset(
    dataset: Dataset,
    by: str = "content",
    threshold: float = 0.0,
) -> Dataset:
    """Remove duplicate examples from dataset.

    OPTIMIZATION: Uses hash-based exact dedup, removes duplicate
    responses or messages.

    Args:
        dataset: Input dataset
        by: Field to check for duplicates ("content", "messages", "response")
        threshold: For future semantic dedup (not implemented)

    Returns:
        Deduplicated dataset
    """
    seen_hashes: set[str] = set()
    unique_indices: list[int] = []

    for i, example in enumerate(dataset):
        # Compute hash based on selected field
        if by == "content":
            # Hash the full example
            content = json.dumps(example, sort_keys=True, ensure_ascii=False)
        elif by == "response":
            # Hash just the assistant response
            messages = example.get("messages", [])
            response = ""
            for msg in messages:
                if msg.get("role") == "assistant":
                    response = msg.get("content", "")
                    break
            content = response
        else:
            # Hash messages
            messages = example.get("messages", [])
            content = json.dumps(messages, sort_keys=True, ensure_ascii=False)

        # Simple hash
        normalized = " ".join(content.lower().split())
        text_hash = hashlib.md5(normalized.encode()).hexdigest()[:16]

        if text_hash not in seen_hashes:
            seen_hashes.add(text_hash)
            unique_indices.append(i)

    if len(unique_indices) < len(dataset):
        print(
            f"[DEDUP] {len(dataset)} -> {len(unique_indices)} "
            f"({len(dataset) - len(unique_indices)} duplicates removed)"
        )
        return dataset.select(unique_indices)

    return dataset


def save_jsonl(dataset: Dataset, output_dir: Path, name: str = "data") -> None:
    """Save as JSONL."""

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{name}.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for example in dataset:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    print(f"Saved {len(dataset)} examples to {output_path}")


# ==============================================================================
# MAIN
# ==============================================================================


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("Dataset Preparation Pipeline")
    print("=" * 60)
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print("=" * 60)

    # Load
    print("\n[1/4] Loading raw data...")
    raw = load_raw_input(args.input, args.format)
    print(f"Loaded {len(raw)} examples")

    # Detect format
    fmt = args.format
    if fmt == "auto":
        p = Path(args.input)
        if p.is_dir():
            p = (
                list(p.glob("*.jsonl"))[0]
                if list(p.glob("*.jsonl"))
                else list(p.glob("*.json"))[0]
            )
        fmt = detect_format(p)
        print(f"Detected format: {fmt}")

    # Convert to ChatML
    print("\n[2/4] Converting to ChatML...")
    processed = convert_to_chatml(raw, fmt)

    # Add metadata
    if args.add_metadata:
        print("\n[3/4] Adding metadata...")
        processed = add_default_metadata(processed, args.npc_scope, args.task_type)

    # Filter quality
    if args.quality_threshold > 0:
        print(f"\nFiltering by quality >= {args.quality_threshold}...")
        before = len(processed)
        processed = filter_quality(processed, args.quality_threshold)
        after = len(processed)
        pct = (after / before * 100) if before > 0 else 0.0
        print(f"Filtered: {before} -> {after} ({pct:.1f}%)")
        if after == 0:
            raise ValueError(
                f"Quality filter removed all {before} examples. "
                f"Lower --quality-threshold (currently {args.quality_threshold})."
            )

    # OPTIMIZATION: Deduplicate before split (always, if requested)
    if args.deduplicate:
        before_dedup = len(processed)
        processed = deduplicate_dataset(processed, by=args.dedup_by)
        after_dedup = len(processed)
        print(
            f"[DEDUP] {before_dedup} -> {after_dedup} ({before_dedup - after_dedup} duplicates removed)"
        )

    enforce_task_minimums(processed, args.min_task_examples)
    report = build_dataset_report(processed)
    meta_npc_scope, meta_task_type = summarize_dataset_metadata(
        report,
        args.npc_scope,
        args.task_type,
    )
    print(f"[REPORT] Task distribution: {report['task_distribution']}")
    print(
        "[REPORT] Avg words "
        f"user={report['average_user_words']}, assistant={report['average_assistant_words']} "
        f"memory_slot_rate={report['memory_slot_rate']}"
    )

    # Split (use stratified if requested)
    print("\n[4/4] Creating splits...")
    if args.stratify_by:
        print(f"[STRATIFIED] Using stratified split by '{args.stratify_by}'")
        splits = stratified_split(
            processed,
            args.stratify_by,
            args.val_split,
            args.test_split,
            args.seed,
        )
    else:
        splits = split_dataset(
            processed,
            args.val_split,
            args.test_split,
            args.seed,
        )

    output_dir = Path(args.output)

    # Save each split
    for split_name, split_data in splits.items():
        save_jsonl(split_data, output_dir, split_name)

    # Save metadata
    meta_path = output_dir / "metadata.json"
    meta = {
        "format": "chatml",
        "npc_scope": meta_npc_scope,
        "task_type": meta_task_type,
        "total_examples": len(processed),
        "splits": {k: len(v) for k, v in splits.items()},
        "report": report,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nSaved metadata to {meta_path}")

    # Push to Hub
    if args.push_to_hub:
        print(f"\nPushing to Hub: {args.push_to_hub}")
        processed.push_to_hub(args.push_to_hub)
        print("Done!")

    print("\n" + "=" * 60)
    print("PREPARATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
