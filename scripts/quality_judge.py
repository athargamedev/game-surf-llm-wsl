#!/usr/bin/env python
"""
Quality Judge — LLM-as-Judge Post-Generation Quality Scoring

Evaluates generated NPC dialogue examples on 4 dimensions:
  1. Persona Adherence (0.0-1.0) — uses correct slang, tone, stays in character
  2. Conciseness (0.0-1.0)       — response is 1-3 sentences unless detail requested
  3. Factual Accuracy (0.0-1.0)  — domain knowledge is correct
  4. Game Awareness (0.0-1.0)    — references game context when appropriate

Can be used standalone or integrated into generate_npc_dataset.py.

Usage:
    # Score a single dataset file
    python quality_judge.py --input datasets/personas/jazz_history_instructor/jazz_history_dataset.jsonl

    # Score and filter (keep only quality >= threshold)
    python quality_judge.py --input dataset.jsonl --output filtered.jsonl --threshold 0.6

    # Score with custom LLM endpoint
    python quality_judge.py --input dataset.jsonl --llm-url http://127.0.0.1:1234
"""

from __future__ import annotations

import argparse
import json
import sys
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    from openai import AsyncOpenAI
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False

ROOT_DIR = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT_DIR / "datasets" / "configs" / "npc_profiles.json"


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================


@dataclass
class QualityScore:
    """Multi-dimensional quality score for a single example."""

    persona_adherence: float
    conciseness: float
    factual_accuracy: float
    game_awareness: float
    rationale: str = ""

    @property
    def composite(self) -> float:
        """Weighted composite score."""
        return (
            self.persona_adherence * 0.30
            + self.conciseness * 0.25
            + self.factual_accuracy * 0.25
            + self.game_awareness * 0.20
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona_adherence": round(self.persona_adherence, 2),
            "conciseness": round(self.conciseness, 2),
            "factual_accuracy": round(self.factual_accuracy, 2),
            "game_awareness": round(self.game_awareness, 2),
            "composite": round(self.composite, 2),
            "rationale": self.rationale,
        }


# ==============================================================================
# PROFILE LOADING
# ==============================================================================


def load_profile_summary(npc_key: str) -> dict[str, Any] | None:
    """Load minimal profile info needed for judging."""
    if not PROFILES_PATH.exists():
        return None
    data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    profile = profiles.get(npc_key)
    if not profile:
        return None
    return {
        "display_name": profile.get("display_name", npc_key),
        "tone": profile.get("personality", {}).get("tone", ""),
        "speaking_style": profile.get("personality", {}).get("speaking_style", ""),
        "catchphrases": profile.get("personality", {}).get("catchphrases", []),
        "refusal_style": profile.get("personality", {}).get("refusal_style", ""),
        "voice_rules": profile.get("voice_rules", []),
        "domain_knowledge": profile.get("domain_knowledge", []),
        "subject": profile.get("subject", ""),
    }


# ==============================================================================
# JUDGE PROMPT CONSTRUCTION
# ==============================================================================


def build_judge_prompt(
    profile_summary: dict[str, Any],
    system_prompt: str,
    user_message: str,
    assistant_response: str,
    task_type: str = "unknown",
) -> tuple[str, str]:
    """Build the system and user prompts for the LLM judge.

    Returns (judge_system, judge_user) prompt pair.
    """
    voice_rules = "\n".join(f"  - {r}" for r in profile_summary.get("voice_rules", []))
    catchphrases = ", ".join(profile_summary.get("catchphrases", []))
    domain_topics = "\n".join(
        f"  - {t}" for t in profile_summary.get("domain_knowledge", [])
    )

    judge_system = (
        "You are an expert evaluator for NPC dialogue quality in a surfing game called Game_Surf.\n"
        "You score dialogue exchanges on a 0.0-1.0 scale across 4 dimensions.\n"
        "Be strict but fair. A score of 0.7+ means good quality. 0.5-0.7 is acceptable. Below 0.5 is poor.\n\n"
        "You MUST respond with ONLY valid JSON. No explanation text outside the JSON."
    )

    judge_user = (
        f"== NPC PERSONA PROFILE ==\n"
        f"Name: {profile_summary.get('display_name', 'Unknown')}\n"
        f"Subject: {profile_summary.get('subject', 'Unknown')}\n"
        f"Tone: {profile_summary.get('tone', 'Unknown')}\n"
        f"Speaking Style: {profile_summary.get('speaking_style', 'Unknown')}\n"
        f"Catchphrases: {catchphrases}\n"
        f"Voice Rules:\n{voice_rules}\n"
        f"Domain Knowledge:\n{domain_topics}\n\n"
        f"== DIALOGUE TO EVALUATE ==\n"
        f"Task type: {task_type}\n"
        f"System prompt: {system_prompt[:200]}...\n"
        f"User: {user_message}\n"
        f"Assistant: {assistant_response}\n\n"
        f"== SCORING RUBRIC ==\n"
        f"Score each dimension 0.0-1.0:\n\n"
        f"1. persona_adherence: Does the response match the defined personality?\n"
        f"   - Uses the correct slang, tone, and catchphrases?\n"
        f"   - Stays in character throughout?\n"
        f"   - Matches the speaking style described?\n\n"
        f"2. conciseness: Is the response appropriately brief?\n"
        f"   - 1-3 sentences for most responses (as per voice rules)?\n"
        f"   - Not overly verbose or padded?\n"
        f"   - Information-dense without filler?\n\n"
        f"3. factual_accuracy: Is the domain information correct?\n"
        f"   - No hallucinated dates, names, or facts?\n"
        f"   - Accurate within the NPC's domain knowledge?\n"
        f"   - (Score 0.7 if the task doesn't require domain facts, e.g. greetings)\n\n"
        f"4. game_awareness: Does the response acknowledge the game context?\n"
        f"   - References Game_Surf, surfing, or game elements when natural?\n"
        f"   - Acknowledges being an NPC when appropriate?\n"
        f"   - (Score 0.7 if the task doesn't warrant game references)\n\n"
        f'Return JSON: {{"persona_adherence": X, "conciseness": X, '
        f'"factual_accuracy": X, "game_awareness": X, "rationale": "brief explanation"}}'
    )

    return judge_system, judge_user


# ==============================================================================
# LLM CALL
# ==============================================================================


def call_judge_llm(
    base_url: str,
    system: str,
    user: str,
    temperature: float = 0.1,
    max_tokens: int = 300,
) -> str | None:
    """Call the LLM to judge quality. Uses low temperature for consistency."""
    payload = {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        req = request.Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"    Judge LLM call failed: {exc}")
        return None


async def call_judge_llm_async(
    base_url: str,
    system: str,
    user: str,
    temperature: float = 0.1,
    max_tokens: int = 300,
) -> str | None:
    """Async call to the LLM to judge quality."""
    if not ASYNC_AVAILABLE:
        return call_judge_llm(base_url, system, user, temperature, max_tokens)

    try:
        client = AsyncOpenAI(base_url=f"{base_url}/v1", api_key="dummy")
        response = await client.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as exc:
        print(f"    Async judge LLM call failed: {exc}")
        return None


# ==============================================================================
# SCORING
# ==============================================================================


def parse_judge_response(response: str) -> QualityScore | None:
    """Parse the JSON response from the judge LLM into a QualityScore."""
    try:
        # Try to extract JSON from possible markdown wrapping
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        data = json.loads(text)

        return QualityScore(
            persona_adherence=_clamp(float(data.get("persona_adherence", 0.5))),
            conciseness=_clamp(float(data.get("conciseness", 0.5))),
            factual_accuracy=_clamp(float(data.get("factual_accuracy", 0.5))),
            game_awareness=_clamp(float(data.get("game_awareness", 0.5))),
            rationale=str(data.get("rationale", "")),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"    Failed to parse judge response: {exc}")
        print(f"    Raw response: {response[:200]}")
        return None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def score_example(
    messages: list[dict[str, str]],
    metadata: dict[str, Any],
    profile_summary: dict[str, Any],
    base_url: str = "http://127.0.0.1:1234",
) -> QualityScore | None:
    """Score a single training example.

    Args:
        messages: ChatML messages list [system, user, assistant]
        metadata: Example metadata dict
        profile_summary: Loaded profile summary dict
        base_url: LLM server URL

    Returns:
        QualityScore or None if scoring failed
    """
    # Extract messages
    system_prompt = ""
    user_message = ""
    assistant_response = ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        elif role == "user":
            user_message = content
        elif role == "assistant":
            assistant_response = content

    # Handle Alpaca format (instruction/response)
    if not user_message and not assistant_response:
        # Try alpaca keys
        if isinstance(messages, dict):
            user_message = messages.get("instruction", "")
            assistant_response = messages.get("response", "")
            system_prompt = messages.get("system", "")

    if not user_message or not assistant_response:
        return None

    task_type = metadata.get("task_type", "unknown")

    # Build judge prompt
    judge_system, judge_user = build_judge_prompt(
        profile_summary, system_prompt, user_message, assistant_response, task_type
    )

    # Call judge
    response = call_judge_llm(base_url, judge_system, judge_user)
    if not response:
        return None

    return parse_judge_response(response)


def score_dataset(
    input_path: Path,
    profile_summary: dict[str, Any],
    base_url: str = "http://127.0.0.1:1234",
    max_examples: int | None = None,
) -> list[tuple[dict[str, Any], QualityScore | None]]:
    """Score all examples in a JSONL dataset file.

    Returns list of (original_row, score) tuples.
    """
    results: list[tuple[dict[str, Any], QualityScore | None]] = []

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total = len(lines)
    if max_examples:
        lines = lines[:max_examples]

    print(f"  Scoring {len(lines)}/{total} examples from {input_path.name}...")

    for i, line in enumerate(lines):
        try:
            row = json.loads(line.strip())
        except json.JSONDecodeError:
            results.append(({}, None))
            continue

        messages = row.get("messages", row)  # Handle both ChatML and flat formats
        metadata = row.get("metadata", {})

        print(f"  [{i + 1}/{len(lines)}] Scoring...", end=" ")
        score = score_example(messages, metadata, profile_summary, base_url)

        if score:
            print(f"composite={score.composite:.2f}")
        else:
            print("FAILED")

        results.append((row, score))

    return results


async def score_dataset_async(
    input_path: Path,
    profile_summary: dict[str, Any],
    base_url: str = "http://127.0.0.1:1234",
    max_examples: int | None = None,
    batch_size: int = 10,
) -> list[tuple[dict[str, Any], QualityScore | None]]:
    """Score dataset in parallel batches."""
    results_map: dict[int, tuple[dict[str, Any], QualityScore | None]] = {}

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total = len(lines)
    if max_examples:
        lines = lines[:max_examples]

    print(f"  [ASYNC] Scoring {len(lines)}/{total} examples in batches of {batch_size}...")

    async def score_indexed_row(idx: int, line: str):
        try:
            row = json.loads(line.strip())
        except json.JSONDecodeError:
            results_map[idx] = ({}, None)
            return

        messages = row.get("messages", row)
        metadata = row.get("metadata", {})
        task_type = metadata.get("task_type", "unknown")

        judge_system, judge_user = build_judge_prompt(
            profile_summary, "", "", "", task_type
        )
        # Re-extracting from row properly
        sys_p = ""
        u_m = ""
        a_r = ""
        msgs = row.get("messages", [])
        if not msgs and isinstance(row, dict):
             # Try alpaca
             u_m = row.get("instruction", "")
             a_r = row.get("response", "")
             sys_p = row.get("system", "")
        else:
            for m in msgs:
                if m["role"] == "system": sys_p = m["content"]
                elif m["role"] == "user": u_m = m["content"]
                elif m["role"] == "assistant": a_r = m["content"]

        judge_system, judge_user = build_judge_prompt(
            profile_summary, sys_p, u_m, a_r, task_type
        )

        resp = await call_judge_llm_async(base_url, judge_system, judge_user)
        score = parse_judge_response(resp) if resp else None
        results_map[idx] = (row, score)

    # Process in batches to avoid overwhelming the local LLM
    for i in range(0, len(lines), batch_size):
        batch = lines[i : i + batch_size]
        tasks = [score_indexed_row(i + j, line) for j, line in enumerate(batch)]
        await asyncio.gather(*tasks)
        print(f"  [ASYNC] Progress: {min(i + batch_size, len(lines))}/{len(lines)}")

    # Sort back to original order
    return [results_map[i] for i in range(len(lines))]


def filter_by_quality(
    scored_results: list[tuple[dict[str, Any], QualityScore | None]],
    threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Filter scored results, keeping only examples above threshold.

    Updates the metadata.quality field with the composite score.
    """
    filtered = []
    for row, score in scored_results:
        if score is None:
            continue
        if score.composite >= threshold:
            # Update quality in metadata
            if "metadata" in row:
                row["metadata"]["quality"] = score.composite
                row["metadata"]["quality_breakdown"] = score.to_dict()
            filtered.append(row)

    return filtered


# ==============================================================================
# INTEGRATION API (for generate_npc_dataset.py)
# ==============================================================================


def judge_and_retry(
    messages: list[dict[str, str]],
    metadata: dict[str, Any],
    profile_summary: dict[str, Any],
    regenerate_fn: Any | None = None,
    base_url: str = "http://127.0.0.1:1234",
    threshold: float = 0.6,
    max_retries: int = 2,
) -> tuple[list[dict[str, str]], dict[str, Any], QualityScore | None]:
    """Score an example and optionally retry if below threshold.

    Args:
        messages: ChatML messages
        metadata: Example metadata
        profile_summary: Profile summary dict
        regenerate_fn: Optional callable() -> (messages, metadata) for retry
        base_url: LLM server URL
        threshold: Minimum composite score
        max_retries: Max regeneration attempts

    Returns:
        (messages, metadata, score) — best version after retries
    """
    best_score: QualityScore | None = None
    best_messages = messages
    best_metadata = metadata

    for attempt in range(max_retries + 1):
        score = score_example(
            messages if attempt == 0 else best_messages,
            metadata if attempt == 0 else best_metadata,
            profile_summary,
            base_url,
        )

        if score is None:
            break

        if best_score is None or score.composite > best_score.composite:
            best_score = score
            best_messages = messages
            best_metadata = metadata

        if score.composite >= threshold:
            break

        # Retry with regeneration if available
        if regenerate_fn and attempt < max_retries:
            print(
                f"    Quality {score.composite:.2f} < {threshold}, "
                f"retrying ({attempt + 1}/{max_retries})..."
            )
            try:
                messages, metadata = regenerate_fn()
            except Exception as exc:
                print(f"    Regeneration failed: {exc}")
                break

    # Update metadata with final score
    if best_score:
        best_metadata["quality"] = best_score.composite
        best_metadata["quality_breakdown"] = best_score.to_dict()

    return best_messages, best_metadata, best_score


# ==============================================================================
# CLI
# ==============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score NPC dialogue quality using LLM-as-Judge",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSONL dataset file to score",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSONL file for filtered results (optional)",
    )
    parser.add_argument(
        "--npc",
        default=None,
        help="NPC profile key for persona-aware scoring",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.6,
        help="Minimum composite quality score to keep",
    )
    parser.add_argument(
        "--llm-url",
        default="http://127.0.0.1:1234",
        help="Local LLM server URL",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Max examples to score (for quick testing)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print detailed quality report",
    )
    parser.add_argument(
        "--async-batch",
        action="store_true",
        help="Use async batch scoring",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for async scoring",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    # Auto-detect NPC key from file path if not provided
    npc_key = args.npc
    if not npc_key:
        # Try to infer from path: datasets/personas/{npc_key}/...
        parts = input_path.parts
        if "personas" in parts:
            idx = parts.index("personas")
            if idx + 1 < len(parts):
                npc_key = parts[idx + 1]
                print(f"  Auto-detected NPC key: {npc_key}")

    # Load profile
    profile_summary = None
    if npc_key:
        profile_summary = load_profile_summary(npc_key)
        if not profile_summary:
            # Try with artifact_key mapping
            data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
            for key, profile in data.get("profiles", {}).items():
                if profile.get("artifact_key") == npc_key:
                    profile_summary = load_profile_summary(key)
                    break

    if not profile_summary:
        print(
            "WARNING: No profile found. Using generic scoring "
            "(persona_adherence will be less accurate)."
        )
        profile_summary = {
            "display_name": "Unknown NPC",
            "tone": "friendly",
            "speaking_style": "casual",
            "catchphrases": [],
            "voice_rules": ["Speak in 1-3 sentences"],
            "domain_knowledge": [],
            "subject": "general",
        }

    # Score dataset
    if args.async_batch and ASYNC_AVAILABLE:
        results = asyncio.run(
            score_dataset_async(
                input_path,
                profile_summary,
                args.llm_url,
                args.max_examples,
                args.batch_size,
            )
        )
    else:
        results = score_dataset(
            input_path, profile_summary, args.llm_url, args.max_examples
        )

    # Report
    scored = [(row, score) for row, score in results if score is not None]
    if not scored:
        print("\nERROR: No examples could be scored.")
        sys.exit(1)

    composites = [s.composite for _, s in scored]
    avg = sum(composites) / len(composites)
    above_threshold = sum(1 for c in composites if c >= args.threshold)

    print(f"\n{'=' * 50}")
    print(f"QUALITY REPORT: {input_path.name}")
    print(f"{'=' * 50}")
    print(f"  Examples scored: {len(scored)}/{len(results)}")
    print(f"  Average composite: {avg:.3f}")
    print(f"  Above threshold ({args.threshold}): {above_threshold}/{len(scored)}")
    print(f"  Min: {min(composites):.3f}")
    print(f"  Max: {max(composites):.3f}")

    if args.report:
        # Per-dimension averages
        dims = {
            "persona_adherence": [],
            "conciseness": [],
            "factual_accuracy": [],
            "game_awareness": [],
        }
        for _, score in scored:
            dims["persona_adherence"].append(score.persona_adherence)
            dims["conciseness"].append(score.conciseness)
            dims["factual_accuracy"].append(score.factual_accuracy)
            dims["game_awareness"].append(score.game_awareness)

        print(f"\n  Per-dimension averages:")
        for dim, vals in dims.items():
            print(f"    {dim}: {sum(vals) / len(vals):.3f}")

        # Show lowest-scoring examples
        sorted_results = sorted(scored, key=lambda x: x[1].composite)
        print(f"\n  Lowest-scoring examples:")
        for row, score in sorted_results[:3]:
            msgs = row.get("messages", [])
            user_msg = next(
                (m["content"] for m in msgs if m.get("role") == "user"), "?"
            )
            print(f"    [{score.composite:.2f}] User: {user_msg[:60]}...")
            print(f"             Rationale: {score.rationale[:80]}...")

    # Filter and save
    if args.output:
        filtered = filter_by_quality(results, args.threshold)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for row in filtered:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"\n  Saved {len(filtered)} filtered examples to {output_path}")

    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
