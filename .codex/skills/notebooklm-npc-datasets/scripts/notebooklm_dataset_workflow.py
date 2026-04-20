#!/usr/bin/env python
"""Automate Game_Surf NotebookLM-direct NPC dataset batches."""

from __future__ import annotations

import argparse
import glob
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
PROFILES_PATH = ROOT / "datasets" / "configs" / "npc_profiles.json"
IMPORTER = ROOT / "scripts" / "import_notebooklm_jsonl.py"
PREPARE = ROOT / "scripts" / "prepare_dataset.py"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout, end="")
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def load_profile(npc_key: str) -> dict[str, Any]:
    data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    if npc_key not in profiles:
        raise SystemExit(f"Unknown NPC '{npc_key}'. Available: {', '.join(sorted(profiles))}")
    return profiles[npc_key]


def format_bullets(items: list[Any], fallback: str, limit: int = 8) -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        values = [fallback]
    return "\n".join(f"- {value}" for value in values[:limit])


def weighted_counts(total: int, weights: list[tuple[str, float]]) -> list[tuple[str, int]]:
    if total <= 0:
        raise SystemExit("--count must be greater than 0")

    raw = [(name, total * weight) for name, weight in weights]
    counts = [(name, int(value)) for name, value in raw]
    assigned = sum(count for _, count in counts)

    remainders = sorted(
        ((raw[index][1] - counts[index][1], index) for index in range(len(counts))),
        reverse=True,
    )
    for _, index in remainders[: total - assigned]:
        name, count = counts[index]
        counts[index] = (name, count + 1)

    if total >= len(counts):
        for index, (name, count) in enumerate(counts):
            if count == 0:
                donor = max(range(len(counts)), key=lambda i: counts[i][1])
                donor_name, donor_count = counts[donor]
                counts[donor] = (donor_name, donor_count - 1)
                counts[index] = (name, 1)

    return counts


def coverage_plan(profile: dict[str, Any], subject: str, count: int) -> str:
    buckets = weighted_counts(
        count,
        [
            ("core teaching answers about the batch subject", 0.30),
            ("specific figures, places, dates, events, or named concepts", 0.20),
            ("short quiz/check-understanding turns", 0.20),
            ("memory-aware follow-ups that refer to previous learning", 0.20),
            ("misconception correction or concrete comparisons", 0.10),
        ],
    )
    bucket_lines = "\n".join(f"- {amount}: {name}" for name, amount in buckets if amount > 0)
    knowledge = format_bullets(
        profile.get("domain_knowledge", []),
        subject,
        limit=10,
    )
    research_queries = format_bullets(
        profile.get("research_queries", []),
        f"What concrete facts should this NPC teach about {subject}?",
        limit=10,
    )
    memory_samples = format_bullets(
        profile.get("memory_context_samples", []),
        "The learner previously studied one concrete fact from this subject.",
        limit=6,
    )
    return f"""Coverage target for exactly {count} examples:
{bucket_lines}

NPC profile knowledge to use when relevant:
{knowledge}

Useful research questions from the project profile:
{research_queries}

Memory-aware user turn patterns:
{memory_samples}
"""


def prompt_for(npc_key: str, profile: dict[str, Any], subject: str, count: int) -> str:
    personality = profile.get("personality", {})
    rules = " ".join(profile.get("voice_rules", [])[:4]) or "Stay concise and in character."
    coverage = coverage_plan(profile, subject, count)
    return f"""Create {count} high-quality NPC fine-tuning examples for Game_Surf.

Use NotebookLM as a source-aware planner before writing:
- Internally inspect the loaded NotebookLM sources, project docs, code/schema notes, and NPC profile details if they are available in this notebook.
- Internally create a coverage plan that satisfies the coverage target below.
- Internally fact-check all names, dates, places, relationships, and claims against the loaded sources.
- If a specific fact is not supported by the sources, omit it instead of guessing.
- Do not output the internal plan or checklist.

Output format:
- JSONL only.
- One valid JSON object per line.
- No Markdown.
- No numbering.
- No explanation before or after.
- Each object must have:
  - messages: an array with exactly 3 messages:
    1. system
    2. user
    3. assistant
  - metadata: an object.

NPC:
- npc_key: {npc_key}
- display name: {profile.get('display_name', npc_key)}
- role: {profile.get('subject_focus') or profile.get('subject') or 'instructor'}
- subject for this batch: {subject}
- tone: {personality.get('tone', 'warm and clear')}
- speaking style: {personality.get('speaking_style', 'concise and in character')}
- answer length: 1-3 sentences
- never mention being an AI, model, dataset, prompt, or training example

{coverage}

Dynamic memory slot:
- Every system message must include exactly this memory slot text:
  [MEMORY_CONTEXT: {{player_memory_summary}}]
- This slot is where runtime Supabase memory will be inserted later.
- Do not fill it with a real memory.
- Do not explain it.

System message template:
You are {profile.get('display_name', npc_key)}. [MEMORY_CONTEXT: {{player_memory_summary}}] Subject: {subject}. Style: {personality.get('tone', 'warm and clear')}; {personality.get('speaking_style', 'concise and in character')}. Rules: {rules} Max 3 sentences. Stay in character.

metadata fields:
- npc_scope: "{profile.get('npc_scope', 'instructor')}"
- task_type: either "teaching" or "quiz"
- source_kind: "notebooklm_direct"
- quality: 0.9
- npc_key: "{npc_key}"

Content requirements:
- Use only facts grounded in the provided NotebookLM sources.
- Use simple, concrete subjects.
- Avoid abstract/generic prompts.
- Avoid duplicate user questions.
- Avoid duplicate assistant answers.
- Include both teaching and quiz examples.
- Include some user questions that refer to previous learning, such as "Last time you told me..."
- Make the assistant answer useful even when the dynamic memory slot is empty.
- Use concrete names, dates, places, and terms from sources when they are relevant.
- Do not invent unsupported people, titles, events, dates, or quotes.

Pre-output checklist:
- Exactly {count} JSON objects.
- Every physical line is one complete parseable JSON object.
- No Markdown, numbering, comments, or prose outside the JSONL.
- Every object has exactly system, user, assistant messages in that order.
- Every system message includes the memory slot exactly once.
- Every metadata object uses only the required metadata fields and values above.
- No duplicate user questions.
- No duplicate assistant answers.
- No assistant text mentions AI, model, dataset, prompt, system prompt, or training example.
- All factual names, dates, places, and claims are grounded in the loaded sources.

Return exactly {count} JSONL lines.
"""


def strip_to_jsonl(text: str) -> str:
    """Recover JSONL objects from NotebookLM CLI output.

    The NotebookLM CLI prints an ``Answer:`` section and wraps long JSON objects
    for terminal display. Those wraps can split JSON strings across physical
    lines, so line-based extraction is too brittle. Scan complete objects by
    brace depth, normalize display newlines inside objects to spaces, then emit
    canonical one-object-per-line JSONL.
    """
    text = text.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("answer"), str):
        text = payload["answer"].strip()
    fence = re.search(r"```(?:jsonl|json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    elif "Answer:" in text:
        text = text.split("Answer:", maxsplit=1)[1]

    objects: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    escaped = False

    for char in text:
        if depth == 0:
            if char != "{":
                continue
            current = ["{"]
            depth = 1
            in_string = False
            escaped = False
            continue

        if char in "\r\n":
            current.append(" ")
            escaped = False
            continue

        current.append(char)

        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = "".join(current)
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    current = []
                    continue
                objects.append(json.dumps(parsed, ensure_ascii=False))
                current = []

    return "\n".join(objects) + ("\n" if objects else "")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npc", required=True)
    parser.add_argument("--subject", default="")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--batch-id", type=int, default=1)
    parser.add_argument("--input", nargs="*", default=[])
    parser.add_argument("--notebook-id", default="")
    parser.add_argument("--run-notebooklm", action="store_true")
    parser.add_argument("--notebooklm-bin", default="notebooklm", help="NotebookLM CLI executable name/path.")
    parser.add_argument("--write-prompt-only", action="store_true")
    parser.add_argument("--import", dest="do_import", action="store_true")
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--smoke-train", action="store_true")
    parser.add_argument("--dry-import", action="store_true", help="Only run importer dry-run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = load_profile(args.npc)
    artifact_key = profile.get("artifact_key", args.npc)
    dataset_name = profile.get("dataset_name", f"{artifact_key}_dataset")
    research_dir = ROOT / "research" / args.npc
    research_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = research_dir / f"notebooklm_batch_{args.batch_id:02d}_prompt.txt"
    raw_response_path = research_dir / f"notebooklm_batch_{args.batch_id:02d}_raw.txt"
    batch_path = research_dir / f"notebooklm_batch_{args.batch_id:02d}.jsonl"

    subject = args.subject or profile.get("subject_focus") or profile.get("subject") or args.npc
    prompt = prompt_for(args.npc, profile, subject, args.count)
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"Prompt written: {prompt_path}")

    inputs = [Path(p) for pattern in args.input for p in glob.glob(pattern)]

    if args.write_prompt_only:
        return 0

    if args.run_notebooklm:
        if not args.notebook_id:
            raise SystemExit("--run-notebooklm requires --notebook-id for deterministic automation.")
        result = run([args.notebooklm_bin, "ask", "--json", "--notebook", args.notebook_id, prompt], check=True)
        raw_response_path.write_text(result.stdout, encoding="utf-8")
        jsonl = strip_to_jsonl(result.stdout)
        if not jsonl:
            raise SystemExit("NotebookLM response did not contain JSONL objects.")
        batch_path.write_text(jsonl, encoding="utf-8")
        print(f"NotebookLM batch written: {batch_path}")
        inputs = [batch_path]

    if not inputs:
        print("No input JSONL files supplied. Use --input, --run-notebooklm, or --write-prompt-only.")
        return 0

    import_cmd = [sys.executable, str(IMPORTER), "--npc", args.npc, "--input", *map(str, inputs)]
    run([*import_cmd, "--dry-run"], check=True)

    if args.dry_import:
        return 0

    if args.do_import:
        run(import_cmd, check=True)

    if args.prepare:
        dataset_path = ROOT / "datasets" / "personas" / artifact_key / f"{dataset_name}.jsonl"
        output_dir = ROOT / "datasets" / "processed" / dataset_name
        run([
            sys.executable,
            str(PREPARE),
            "--input",
            str(dataset_path),
            "--output",
            str(output_dir),
            "--val-split",
            "0.1",
            "--test-split",
            "0.0",
            "--quality-threshold",
            "0.75",
            "--deduplicate",
            "--dedup-by",
            "response",
            "--stratify-by",
            "task_type",
        ], check=True)

    if args.smoke_train:
        run([
            sys.executable,
            "scripts/run_full_npc_pipeline.py",
            "--npc",
            args.npc,
            "--skip-generation",
            "--skip-prep",
            "--target-count",
            str(args.count),
            "--max-steps",
            "2",
            "--epochs",
            "1",
            "--batch-size",
            "1",
            "--grad-accum",
            "1",
            "--skip-sync",
            "--skip-eval",
        ], check=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
