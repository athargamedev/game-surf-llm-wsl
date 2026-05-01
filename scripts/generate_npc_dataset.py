#!/usr/bin/env python
"""
NPC LoRA Dataset Generator — NotebookLM Research → Training Data Pipeline

Automated workflow that:
  1. Creates a NotebookLM notebook for a chosen NPC subject
  2. Adds source URLs and queries the notebook for domain knowledge
  3. Transforms research into structured ChatML training examples
  4. Outputs JSONL files matching the Game_Surf dataset schema

Supports two research backends:
    - "notebooklm" : Uses notebooklm CLI to query a NotebookLM notebook
  - "local"      : Uses a local LLM (LM Studio / llama.cpp) to generate
                    research and dialogue from the profile alone

Usage:
    # Full pipeline with NotebookLM research
    python generate_npc_dataset.py --npc kai_instructor

    # Local-only mode (no NotebookLM required)
    python generate_npc_dataset.py --npc kai_instructor --backend local

    # Generate for all NPCs
    python generate_npc_dataset.py --all

    # Dry run (show what would be generated)
    python generate_npc_dataset.py --npc kai_instructor --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

# OPTIMIZATION: Async LLM support
try:
    from openai import AsyncOpenAI

    ASYNC_LLM_AVAILABLE = True
except ImportError:
    ASYNC_LLM_AVAILABLE = False

# ==============================================================================
# PATHS & CONSTANTS
# ==============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]  # Tools/LLM
CONFIGS_DIR = ROOT_DIR / "datasets" / "configs"
DATASETS_DIR = ROOT_DIR / "datasets"
RESEARCH_DIR = ROOT_DIR / "research"
PROFILES_PATH = CONFIGS_DIR / "npc_profiles.json"

TASK_TYPES = [
    "teaching",
    "quiz",
]

# Prompt templates for each task type
TASK_PROMPTS = {
    "teaching": [
        "Who was involved in {topic}?",
        "What happened during {topic}?",
        "Why is {topic} important?",
        "Can you explain {topic} for a student?",
        "What should I remember about {topic}?",
        "How does {topic} connect to the main subject?",
        "What is the simplest way to understand {topic}?",
        "Can you give me a factual summary of {topic}?",
    ],
    "quiz": [
        "Can you quiz me on {topic}?",
        "Ask me one question about {topic}.",
        "Give me a quick study question about {topic}.",
        "Test whether I understood {topic}.",
    ],
}

# Follow-up prompts for multi-turn conversations
FOLLOWUP_PROMPTS = [
    "Tell me more about that",
    "Wait, can you explain that again?",
    "That's cool! What else should I know?",
    "How does that connect to the bigger picture?",
    "I didn't understand that, can you simplify?",
    "What's the most important thing you just said?",
    "Really? Why is that?",
    "Can you give me an example?",
    "Who else was involved in that?",
    "What happened next?",
]

# ==============================================================================
# DATA STRUCTURES
# ==============================================================================


@dataclass
class NpcProfile:
    """Loaded NPC profile from datasets/configs/npc_profiles.json."""

    key: str
    display_name: str
    npc_scope: str
    subject: str
    personality: dict[str, Any]
    voice_rules: list[str]
    domain_knowledge: list[str]
    notebooklm_sources: list[str]
    research_queries: list[str]
    task_type_distribution: dict[str, float]
    artifact_key: str | None = None
    dataset_name: str | None = None
    dataset_mode: str = "educational_roleplay"
    subject_focus: str | None = None
    memory_context_samples: list[str] = field(default_factory=list)
    generation_defaults: dict[str, Any] = field(default_factory=dict)

    @property
    def storage_key(self) -> str:
        return self.artifact_key or self.key

    @property
    def output_dataset_name(self) -> str:
        return self.dataset_name or f"{self.storage_key}_dataset"


@dataclass
class ResearchNote:
    """A single piece of research from NotebookLM or local generation."""

    query: str
    answer: str
    source: str  # "notebooklm" or "local"
    topics: list[str] = field(default_factory=list)


@dataclass
class TrainingExample:
    """A single training example in ChatML format."""

    messages: list[dict[str, str]]
    metadata: dict[str, Any]


# ==============================================================================
# PROFILE LOADING
# ==============================================================================


def load_profiles(path: Path = PROFILES_PATH) -> dict[str, NpcProfile]:
    """Load all NPC profiles from config file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = data.get("generation_defaults", {})
    profiles = {}

    for key, profile_data in data.get("profiles", {}).items():
        generation_defaults = {
            **defaults,
            **profile_data.get("generation_defaults", {}),
        }
        profiles[key] = NpcProfile(
            key=key,
            display_name=profile_data["display_name"],
            npc_scope=profile_data["npc_scope"],
            subject=profile_data["subject"],
            personality=profile_data["personality"],
            voice_rules=profile_data["voice_rules"],
            domain_knowledge=profile_data["domain_knowledge"],
            notebooklm_sources=profile_data.get("notebooklm_sources", []),
            research_queries=profile_data.get("research_queries", []),
            task_type_distribution=profile_data.get("task_type_distribution", {}),
            artifact_key=profile_data.get("artifact_key"),
            dataset_name=profile_data.get("dataset_name"),
            dataset_mode=profile_data.get("dataset_mode", "educational_roleplay"),
            subject_focus=profile_data.get("subject_focus"),
            memory_context_samples=profile_data.get("memory_context_samples", []),
            generation_defaults=generation_defaults,
        )

    return profiles


# ==============================================================================
# RESEARCH BACKENDS
# ==============================================================================


def research_via_notebooklm(
    profile: NpcProfile,
    notebook_id: str | None = None,
) -> list[ResearchNote]:
    """
    Use notebooklm CLI to research the NPC's subject domain.

    Workflow:
      1. Create notebook (or reuse existing)
      2. Add source URLs
      3. Query for each research question
      4. Collect structured answers
    """
    notes: list[ResearchNote] = []

    # Step 1: Create or select notebook
    if not notebook_id:
        print(f"  Creating NotebookLM notebook: '{profile.display_name} Research'...")
        result = _run_notebooklm_command(
            [
                "notebooklm",
                "notebook",
                "create",
                f"Research: {profile.display_name}",
            ]
        )
        # Parse notebook ID from output
        notebook_id = _parse_notebook_id(result)
        if not notebook_id:
            print("  WARNING: Could not create notebook, falling back to report-based generation")
            return research_via_report(profile, Path("dummy"), "") if args.report_path else []

    # Step 2: Add source URLs
    for url in profile.notebooklm_sources:
        print(f"  Adding source: {url}")
        _run_notebooklm_command(
            [
                "notebooklm",
                "source",
                "add",
                notebook_id,
                "--url",
                url,
                "--wait",
            ]
        )
        time.sleep(2)  # Rate limiting

    # Step 3: Query for domain knowledge
    for query in profile.research_queries:
        print(f"  Querying: {query[:60]}...")
        result = _run_notebooklm_command(
            [
                "notebooklm",
                "notebook",
                "query",
                notebook_id,
                query,
            ]
        )
        if result:
            notes.append(
                ResearchNote(
                    query=query,
                    answer=result.strip(),
                    source="notebooklm",
                    topics=_extract_topics(query, profile.domain_knowledge),
                )
            )
        time.sleep(3)  # Rate limiting

    return notes


def research_via_local(
    profile: NpcProfile,
    base_url: str = "http://127.0.0.1:1234",
) -> list[ResearchNote]:
    """
    Use local LLM (LM Studio) to generate research answers.
    This is the fallback when NotebookLM is unavailable.
    """
    notes: list[ResearchNote] = []

    research_system = (
        f"You are a knowledgeable research assistant specializing in: "
        f"{profile.subject}. "
        f"Provide detailed, factual answers. "
        f"Focus on practical knowledge that would be useful for a conversational "
        f"instructor who teaches learners about these topics. "
        f"Keep each answer to 2-4 paragraphs of substantive information."
    )

    for query in profile.research_queries:
        print(f"  Researching: {query[:60]}...")
        answer = _call_local_llm(
            base_url,
            system=research_system,
            user=query,
            temperature=0.4,
            max_tokens=500,
        )
        if answer:
            notes.append(
                ResearchNote(
                    query=query,
                    answer=answer.strip(),
                    source="local",
                    topics=_extract_topics(query, profile.domain_knowledge),
                )
            )

    return notes


def research_via_report(
    profile: NpcProfile,
    report_path: Path,
    base_url: str = "http://127.0.0.1:1234",
) -> list[ResearchNote]:
    """
    Ingest a high-quality Markdown report (e.g. from Deep Research)
    and extract structured ResearchNotes.
    """
    print(f"  Ingesting research report from: {report_path}")
    content = report_path.read_text(encoding="utf-8")

    # Use LLM to split the report into logical chunks (ResearchNotes)
    extractor_system = (
        "Extract 5-8 distinct, high-quality research notes from the provided report. "
        "Each note should cover a specific sub-topic (e.g. 'Safety', 'Technique'). "
        "Return the notes as a JSON array of objects, each with 'query' (the topic name) "
        "and 'answer' (the 2-4 paragraph detailed summary for that topic). "
        "Focus on technical accuracy for a conversational instructor dataset."
    )

    result = _call_local_llm(
        base_url,
        system=extractor_system,
        user=f"REPORT CONTENT:\n\n{content}",
        temperature=0.3,
        max_tokens=3000,
    )

    notes: list[ResearchNote] = []
    if result:
        try:
            # Clean JSON from markdown blocks if present
            json_text = result.strip()
            if "```json" in json_text:
                json_text = json_text.split("```json")[1].split("```")[0].strip()
            elif "```" in json_text:
                json_text = json_text.split("```")[1].split("```")[0].strip()
            
            items = json.loads(json_text)
            for item in items:
                notes.append(
                    ResearchNote(
                        query=item["query"],
                        answer=item["answer"],
                        source="notebooklm_deep",
                        topics=_extract_topics(item["query"], profile.domain_knowledge),
                    )
                )
        except Exception as e:
            print(f"  ERROR parsing report extraction: {e}")

    return notes


# ==============================================================================
# DATASET GENERATION
# ==============================================================================


def generate_dataset(
    profile: NpcProfile,
    research_notes: list[ResearchNote],
    target_count: int = 200,
    base_url: str = "http://127.0.0.1:1234",
    model_id: str = "local-model"
) -> list[TrainingExample]:
    """
    Generate training examples from research notes + NPC profile.

    Uses the local LLM to transform research into in-character NPC dialogue.
    """
    examples: list[TrainingExample] = []

    # Calculate per-task-type targets
    task_targets = {}
    for task_type, weight in profile.task_type_distribution.items():
        task_targets[task_type] = max(
            profile.generation_defaults.get("min_examples_per_task_type", 5),
            int(target_count * weight),
        )

    print(f"\n  Task type targets: {task_targets}")

    # ── Phase 1: Generate from research notes ────────────────────────────
    # Each research note produces teaching/hint examples
    research_topics = [note.answer for note in research_notes]

    for note in research_notes:
        # Extract key facts from the research
        facts = _extract_key_facts(note.answer, base_url)

        for fact in facts:
            # Generate a teaching example
            if task_targets.get("teaching", 0) > 0:
                ex = _generate_example_from_fact(
                    profile, fact, "teaching", base_url
                )
                if ex:
                    examples.append(ex)
                    task_targets["teaching"] = task_targets.get("teaching", 0) - 1

            # Generate a hint example
            if task_targets.get("hint", 0) > 0:
                ex = _generate_example_from_fact(
                    profile, fact, "hint", base_url
                )
                if ex:
                    examples.append(ex)
                    task_targets["hint"] = task_targets.get("hint", 0) - 1

    # ── Phase 2: Generate task-specific examples ─────────────────────────
    for task_type, remaining in task_targets.items():
        if remaining <= 0 or task_type == "multi_turn":
            continue

        print(f"  Generating {remaining} more '{task_type}' examples...")
        prompts = TASK_PROMPTS.get(task_type, ["Tell me something"])

        for i in range(remaining):
            prompt_template = random.choice(prompts)

            # Fill in template variables
            prompt = _fill_prompt_template(prompt_template, profile)

            # Generate NPC response
            npc_system = _build_npc_system_prompt(profile)
            response = _generate_npc_response(
                profile, npc_system, prompt, task_type, base_url
            )
            if response:
                examples.append(
                    TrainingExample(
                        messages=[
                            {"role": "system", "content": npc_system},
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": response},
                        ],
                        metadata={
                            "npc_scope": profile.npc_scope,
                            "task_type": task_type,
                            "source_kind": "synthetic",
                            "quality": 0.8,
                            "npc_key": profile.key,
                            "generated_by": "generate_npc_dataset.py",
                        },
                    )
                )

    # ── Phase 3: Generate multi-turn conversations (~20% of target) ──────
    multi_turn_count = task_targets.get("multi_turn", 0)
    if multi_turn_count > 0:
        print(f"  Generating {multi_turn_count} multi-turn conversations...")
    for i in range(multi_turn_count):
        npc_system = _build_npc_system_prompt(profile)
        mt_example = _generate_multi_turn_example(
            profile, npc_system, base_url, num_turns=random.randint(2, 4)
        )
        if mt_example:
            examples.append(mt_example)

    print(f"  Total examples generated: {len(examples)}")
    return examples


# ==============================================================================
# OPTIMIZED: ASYNC BATCH GENERATION
# ==============================================================================


async def generate_dataset_async(
    profile: NpcProfile,
    research_notes: list[ResearchNote],
    target_count: int = 200,
    base_url: str = "http://127.0.0.1:1234",
    batch_size: int = 5,
    model_id: str = "local-model"
) -> list[TrainingExample]:
    """
    OPTIMIZED: Async batch generation for faster dataset creation.

    Generates multiple examples concurrently instead of sequentially.
    This is ~batch_size times faster than sequential generation.
    """
    examples: list[TrainingExample] = []
    # Calculate per-task-type targets
    # Scale the minimum per task type so we can do small tests
    min_per_type = profile.generation_defaults.get("min_examples_per_task_type", 5)
    if target_count < len(profile.task_type_distribution) * min_per_type:
        min_per_type = 1

    task_targets = {}
    for task_type, weight in profile.task_type_distribution.items():
        task_targets[task_type] = max(
            min_per_type,
            int(target_count * weight),
        )

    print(f"\n  [ASYNC] Task type targets: {task_targets}")
    print(f"  [ASYNC] Batch size: {batch_size}")

    # ── Phase 1: Extract facts from research (sequential for stability) ────────
    all_facts: list[tuple[str, str]] = []  # (fact, topic)
    facts_cache_path = RESEARCH_DIR / profile.key / "extracted_facts.json"
    
    if facts_cache_path.exists():
        try:
            cached_facts = json.loads(facts_cache_path.read_text(encoding="utf-8"))
            all_facts = [
                (item["fact"], item.get("topic", "general"))
                for item in cached_facts
                if item.get("fact")
            ]
            print(f"  [ASYNC] Loaded {len(all_facts)} cached extracted facts")
        except Exception as exc:
            print(f"  [ASYNC] Could not load fact cache: {exc}")
            all_facts = []

    if research_notes and not all_facts:
        print(f"  [ASYNC] Extracting facts from {len(research_notes)} research notes (sequential)...")
        for i, note in enumerate(research_notes):
            if not note.answer or len(note.answer.strip()) < 10:
                print(f"    - Skipping empty note {i+1}")
                continue
            try:
                print(f"    - Processing note {i+1}/{len(research_notes)}...", end="", flush=True)
                facts_text = await _call_async_llm(
                    base_url,
                    system="Pick 3-5 distinct facts from the text. Return each fact on a new line. NO OTHER TEXT.",
                    user=note.answer,
                    model_id=model_id,
                    temperature=0.3,
                    max_tokens=200
                )
                if facts_text:
                    facts_lines = [
                        re.sub(r"^\s*[-*]?\s*\d+[\).\s-]*", "", line).strip()
                        for line in facts_text.strip().split("\n")
                        if line.strip()
                    ]
                    topics = _extract_topics(note.query, profile.domain_knowledge)
                    for fact in facts_lines[:3]:
                        all_facts.append((fact, random.choice(topics)))
                    print(f" done ({len(facts_lines)} facts found)")
                else:
                    print(" no facts returned.")
            except Exception as e:
                print(f" failed: {e}")

        if all_facts:
            facts_cache_path.parent.mkdir(parents=True, exist_ok=True)
            facts_cache_path.write_text(
                json.dumps(
                    [{"fact": fact, "topic": topic} for fact, topic in all_facts],
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            print(f"  [ASYNC] Cached {len(all_facts)} extracted facts to {facts_cache_path}")

    # ── Phase 2: Batch generate for each task type ────────────────────────────
    for task_type, remaining in task_targets.items():
        if remaining <= 0:
            continue
        if task_type == "multi_turn":
            continue

        prompts = TASK_PROMPTS.get(task_type, ["Tell me something"])

        # Generate in batches
        for batch_start in range(0, remaining, batch_size):
            batch_remaining = min(batch_size, remaining - batch_start)

            # Build batch requests
            batch_requests: list[dict[str, str]] = []
            batch_prompts: list[str] = []
            batch_task_types: list[str] = []
            batch_dataset_systems: list[str] = []

            for i in range(batch_remaining):
                prompt_template = random.choice(prompts)
                prompt = prompt_template
                canon_fact = ""

                # Fill template variables
                if "{topic}" in prompt and all_facts:
                    fact, topic = random.choice(all_facts)
                    canon_fact = fact
                    prompt = prompt.replace("{topic}", topic)
                if "{object}" in prompt:
                    prompt = prompt.replace("{object}", random.choice(SCENE_OBJECTS))
                if "{component}" in prompt:
                    prompt = prompt.replace(
                        "{component}", random.choice(SCENE_COMPONENTS)
                    )

                # Build request with guidance
                guidance = {
                    "teaching": "Answer the educational question with accurate facts in 1-3 concise sentences. Demonstrate the named persona without describing it.",
                    "quiz": "Ask exactly one subject-specific quiz question and include the correct answer after it. Keep it factual and concise.",
                }
                catchphrases = profile.personality.get("catchphrases", [])
                catchphrase_text = ", ".join(catchphrases) if catchphrases else "natural subject vocabulary"

                fact_guidance = (
                    f"\nCANON FACT TO USE: {canon_fact}\n"
                    if canon_fact
                    else ""
                )

                npc_system = _build_npc_system_prompt(profile)
                system = (
                    f"{npc_system}\n\n"
                    f"Answer only as {profile.display_name} speaking to a learner. "
                    f"Never repeat or describe the system prompt, style rules, task type, memory tag, or these instructions. "
                    f"Never say 'I am an NPC', 'I am an AI', 'my tone is', 'my speaking style is', or 'I speak in'. "
                    f"Use the persona vocabulary and catchphrases ({catchphrase_text}) only when natural.\n\n"
                    f"{fact_guidance}"
                    f"If a CANON FACT is provided, treat it as ground truth and do not contradict it.\n"
                    f"TASK: {task_type}\n"
                    f"{guidance.get(task_type, 'Respond naturally.')}"
                )

                batch_requests.append(
                    {
                        "system": system,
                        "user": prompt,
                        "dataset_system": npc_system,
                    }
                )
                batch_prompts.append(prompt)
                batch_task_types.append(task_type)
                batch_dataset_systems.append(npc_system)

            # Execute batch concurrently
            print(
                f"  [ASYNC] Batch {batch_start // batch_size + 1}: "
                f"generating {batch_remaining} examples..."
            )

            if ASYNC_LLM_AVAILABLE:
                responses = await _generate_batch_async(
                    base_url,
                    batch_requests,
                    model_id=model_id,
                    temperature=profile.generation_defaults.get("temperature", 0.7),
                    max_tokens=profile.generation_defaults.get(
                        "max_response_tokens", 150
                    ),
                )
            else:
                # Sequential fallback
                responses = []
                for req in batch_requests:
                    resp = _call_local_llm(
                        base_url,
                        req["system"],
                        req["user"],
                        model_id,
                        profile.generation_defaults.get("temperature", 0.7),
                        profile.generation_defaults.get("max_response_tokens", 150),
                    )
                    responses.append(resp)

            # Build examples from responses
            for prompt, response, response_task_type, dataset_system in zip(
                batch_prompts,
                responses,
                batch_task_types,
                batch_dataset_systems,
            ):
                if response and response_task_type == "redirect":
                    response = _normalize_redirect_response(profile, response)

                if response and not _looks_like_prompt_leak(response):
                    response = _clean_response(response)
                    examples.append(
                        TrainingExample(
                            messages=[
                                {"role": "system", "content": dataset_system},
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": response},
                            ],
                            metadata={
                                "npc_scope": profile.npc_scope,
                                "task_type": task_type,
                                "source_kind": "synthetic",
                                "quality": 0.8,
                                "npc_key": profile.key,
                                "generated_by": "generate_npc_dataset.py (async)",
                            },
                        )
                    )
                elif response:
                    print("    Skipped response that appeared to leak prompt instructions.")

    # ── Phase 3: Generate real multi-turn examples sequentially ───────────────
    multi_turn_count = task_targets.get("multi_turn", 0)
    if multi_turn_count > 0:
        print(f"  [ASYNC] Generating {multi_turn_count} multi-turn conversations...")
    for _ in range(multi_turn_count):
        mt_example = await _generate_multi_turn_example_async(
            profile,
            _build_npc_system_prompt(profile),
            base_url,
            model_id=model_id,
            num_turns=random.randint(2, 4),
        )
        if mt_example:
            examples.append(mt_example)

    print(f"  [ASYNC] Total examples generated: {len(examples)}")
    return examples


# ==============================================================================
# GENERATION HELPERS
# ==============================================================================


def _fill_prompt_template(prompt_template: str, profile: NpcProfile) -> str:
    """Fill template variables in a prompt string.

    Supported variables: {topic}, {subject_short}, {npc_role}
    """
    prompt = prompt_template

    if "{topic}" in prompt:
        topic = random.choice(profile.domain_knowledge)
        prompt = prompt.replace("{topic}", topic)
    if "{subject_short}" in prompt:
        # Extract first part of subject for natural phrasing
        subject_short = profile.subject.split(",")[0].strip()
        prompt = prompt.replace("{subject_short}", subject_short)
    if "{npc_role}" in prompt:
        prompt = prompt.replace("{npc_role}", profile.display_name)

    return prompt


def _looks_like_prompt_leak(response: str) -> bool:
    """Detect responses that repeated generation instructions instead of roleplaying."""
    leaked_markers = [
        "voice rules",
        "system prompt",
        "memory_context",
        "[memory_context",
        "task:",
        "task type",
        "critical:",
        "i must strictly follow",
        "generation guidance",
        "these instructions",
        "i am an npc",
        "i'm an npc",
        "i am a non-player character",
        "i am an ai",
        "i'm an ai",
        "my tone is",
        "my speaking style is",
        "i speak in",
        "as an npc",
        "as an ai",
    ]
    response_lower = response.lower()
    return any(marker in response_lower for marker in leaked_markers)


def _clean_response(response: str) -> str:
    """Remove common synthetic-generation artifacts from assistant text."""
    cleaned = response.strip()
    cleaned = re.sub(
        r"^\s*[A-Za-z][A-Za-z0-9 _-]{0,40}\s+to\s+[A-Za-z][A-Za-z0-9 _-]{0,40}\s*:\s*",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"^\s*(assistant|npc|teacher|instructor)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _synthetic_memory_context(profile: NpcProfile) -> str:
    """Create a short synthetic memory hook for Unity/Supabase replacement tests."""
    if profile.memory_context_samples:
        return random.choice(profile.memory_context_samples)

    topic = random.choice(profile.domain_knowledge or [profile.subject])
    templates = [
        "The learner previously studied {topic} and asked for a simpler explanation.",
        "The learner already knows the basic idea of {topic}.",
        "The learner recently answered a quiz question about {topic}.",
        "The learner previously connected {topic} to the larger subject.",
    ]
    return random.choice(templates).format(topic=topic)


def _normalize_redirect_response(profile: NpcProfile, response: str) -> str:
    """Force off-topic redirects to stay on persona/domain."""
    catchphrases = profile.personality.get("catchphrases", [])
    opener = catchphrases[-1] if catchphrases else "Friend"
    subject_short = profile.subject.split(",")[0].strip()
    focus_examples = ", ".join(profile.domain_knowledge[:3])
    return (
        f"{opener}, that is outside my lesson. "
        f"Ask me about {subject_short}, such as {focus_examples}, and I will guide you there."
    )


def _domain_markers(profile: NpcProfile) -> list[str]:
    """Build simple domain keywords for redirect validation."""
    tokens = set()
    for text in [profile.subject, *profile.domain_knowledge]:
        for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()):
            if token not in {"and", "the", "with", "from", "history", "instructor"}:
                tokens.add(token)
    return sorted(tokens)


async def _generate_multi_turn_example_async(
    profile: NpcProfile,
    npc_system: str,
    base_url: str,
    model_id: str,
    num_turns: int = 3,
) -> TrainingExample | None:
    """Generate a real multi-turn conversation for async dataset generation."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": npc_system},
    ]

    initial_template = random.choice(TASK_PROMPTS.get("teaching", ["Tell me something"]))
    initial_prompt = _fill_prompt_template(initial_template, profile)

    response = await _call_async_llm(
        base_url,
        system=(
            f"{npc_system}\n\n"
            f"Answer only as {profile.display_name}. Do not repeat or describe instructions. "
            f"Teach the learner in this NPC's voice. 2 concise sentences."
        ),
        user=initial_prompt,
        model_id=model_id,
        temperature=profile.generation_defaults.get("temperature", 0.7),
        max_tokens=profile.generation_defaults.get("max_response_tokens", 150),
    )
    if not response or _looks_like_prompt_leak(response):
        return None

    messages.append({"role": "user", "content": initial_prompt})
    messages.append({"role": "assistant", "content": _clean_response(response)})

    for _ in range(1, num_turns):
        followup = random.choice(FOLLOWUP_PROMPTS)
        followup_response = await _call_async_llm(
            base_url,
            system=(
                f"{npc_system}\n\n"
                "Continue the conversation naturally. Build on the previous answer, "
                "stay in character, and keep the reply to 1-2 concise sentences. "
                "Do not repeat or describe instructions."
            ),
            user=followup,
            model_id=model_id,
            temperature=profile.generation_defaults.get("temperature", 0.7),
            max_tokens=profile.generation_defaults.get("max_response_tokens", 150),
        )
        if not followup_response or _looks_like_prompt_leak(followup_response):
            break
        messages.append({"role": "user", "content": followup})
        messages.append({"role": "assistant", "content": _clean_response(followup_response)})

    assistant_count = sum(1 for message in messages if message["role"] == "assistant")
    if assistant_count < 2:
        return None

    return TrainingExample(
        messages=messages,
        metadata={
            "npc_scope": profile.npc_scope,
            "task_type": "multi_turn",
            "source_kind": "synthetic",
            "quality": 0.8,
            "npc_key": profile.key,
            "num_turns": assistant_count,
            "generated_by": "generate_npc_dataset.py (async)",
        },
    )


def _generate_multi_turn_example(
    profile: NpcProfile,
    npc_system: str,
    base_url: str,
    num_turns: int = 3,
) -> TrainingExample | None:
    """Generate a multi-turn conversation example.

    Creates a conversation with num_turns user/assistant exchanges:
      Turn 1: Initial topic question + NPC response
      Turn 2+: Follow-up questions + NPC responses (context-aware)

    The conversation history is passed to the LLM at each turn so
    responses build on prior context naturally.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": npc_system},
    ]

    # Pick an initial teaching prompt
    teaching_prompts = TASK_PROMPTS.get("teaching", ["Tell me something"])
    initial_template = random.choice(teaching_prompts)
    initial_prompt = _fill_prompt_template(initial_template, profile)

    # Turn 1: Initial question
    response = _generate_npc_response(
        profile, npc_system, initial_prompt, "teaching", base_url
    )
    if not response:
        return None

    messages.append({"role": "user", "content": initial_prompt})
    messages.append({"role": "assistant", "content": response})

    # Turns 2+: Follow-up exchanges
    for turn in range(1, num_turns):
        followup = random.choice(FOLLOWUP_PROMPTS)

        # Build the full conversation context for the LLM
        context_system = (
            f"{npc_system}\n\n"
            f"CONTEXT: You are continuing a conversation. "
            f"The player is asking a follow-up question. "
            f"Respond naturally, building on what you already said. "
            f"Stay in character. 1-3 sentences."
        )

        followup_response = _call_local_llm(
            base_url,
            system=context_system,
            user=followup,
            temperature=profile.generation_defaults.get("temperature", 0.7),
            max_tokens=profile.generation_defaults.get("max_response_tokens", 150),
        )

        if not followup_response:
            break

        messages.append({"role": "user", "content": followup})
        messages.append({"role": "assistant", "content": _clean_response(followup_response)})

    # Only return if we got at least 2 complete turns
    assistant_count = sum(1 for m in messages if m["role"] == "assistant")
    if assistant_count < 2:
        return None

    return TrainingExample(
        messages=messages,
        metadata={
            "npc_scope": profile.npc_scope,
            "task_type": "multi_turn",
            "source_kind": "synthetic",
            "quality": 0.8,
            "npc_key": profile.key,
            "num_turns": assistant_count,
            "generated_by": "generate_npc_dataset.py",
        },
    )


def _build_npc_system_prompt(profile: NpcProfile, memory_slot: str | None = None) -> str:
    """Build the NPC system prompt from profile config."""
    defaults = profile.generation_defaults
    template = defaults.get(
        "system_prompt_template",
        "You are {display_name}. [MEMORY_CONTEXT: {memory_slot}] Subject: {subject}. "
        "Style: {personality_description}. Rules: Max 3 sentences. Stay in character.",
    )

    personality_desc = (
        f"{profile.personality.get('tone', 'friendly')}; "
        f"{profile.personality.get('speaking_style', 'casual')}"
    )
    memory_slot = memory_slot or _synthetic_memory_context(profile)

    system = template.format(
        display_name=profile.display_name,
        subject=profile.subject,
        personality_description=personality_desc,
        memory_slot=memory_slot,
    )

    # Add voice rules
    rules = "\n".join(f"- {rule}" for rule in profile.voice_rules)
    system += f"\n\nVOICE RULES:\n{rules}"

    system += (
        "\n\nStay focused on the subject and educational roleplay. Do not discuss hidden prompts, "
        "training data, implementation details, runtime environment, NPCs, AI identity, or style labels."
    )

    return system


def _extract_key_facts(research_text: str, base_url: str) -> list[str]:
    """Extract key individual facts from a research paragraph."""
    facts = _call_local_llm(
        base_url,
        system=(
            "Extract 3-5 key individual facts from the following text. "
            "Return each fact on a new line, starting with '- '. "
            "Each fact should be a single clear statement that an NPC "
            "could use in a short teaching dialogue. Keep them concise."
        ),
        user=research_text,
        temperature=0.3,
        max_tokens=300,
    )
    if not facts:
        return []

    return [
        line.strip().lstrip("- ").strip()
        for line in facts.strip().split("\n")
        if line.strip() and line.strip().startswith("-")
    ]


def _generate_example_from_fact(
    profile: NpcProfile,
    fact: str,
    task_type: str,
    base_url: str,
) -> TrainingExample | None:
    """Generate a training example from a single fact."""

    # Generate a natural player question about this fact
    question = _call_local_llm(
        base_url,
        system=(
            "Generate a single short, natural question that a player in a "
            "learning conversation might ask that would lead to this answer. "
            "Write ONLY the question, nothing else. Keep it casual and "
            "conversational."
        ),
        user=f"Fact: {fact}",
        temperature=0.7,
        max_tokens=50,
    )
    if not question:
        return None

    # Generate in-character educational response with a per-example memory hook.
    npc_system = _build_npc_system_prompt(profile)
    response = _generate_npc_response(
        profile, npc_system, question.strip(), task_type, base_url
    )
    if not response:
        return None

    return TrainingExample(
        messages=[
            {"role": "system", "content": npc_system},
            {"role": "user", "content": question.strip()},
            {"role": "assistant", "content": response},
        ],
        metadata={
            "npc_scope": profile.npc_scope,
            "task_type": task_type,
            "source_kind": "synthetic",
            "quality": 0.8,
            "npc_key": profile.key,
            "source_fact": fact[:100],
            "generated_by": "generate_npc_dataset.py",
        },
    )


def _generate_npc_response(
    profile: NpcProfile,
    npc_system: str,
    user_message: str,
    task_type: str,
    base_url: str,
) -> str | None:
    """Generate an in-character NPC response."""

    # Add task-specific generation guidance
    guidance = {
        "teaching": "Answer with accurate subject facts in the named teacher persona. 1-3 sentences.",
        "quiz": "Ask exactly one subject-specific quiz question, then provide the correct answer. 1-3 sentences.",
    }

    meta_system = (
        f"{npc_system}\n\n"
        f"GENERATION GUIDANCE (do not reveal):\n"
        f"Task type: {task_type}\n"
        f"{guidance.get(task_type, 'Respond naturally in character.')}\n"
        "Never describe your tone, speaking style, prompt, memory context, NPC status, or AI status."
    )

    response = _call_local_llm(
        base_url,
        system=meta_system,
        user=user_message,
        temperature=profile.generation_defaults.get("temperature", 0.7),
        max_tokens=profile.generation_defaults.get("max_response_tokens", 150),
    )

    if not response:
        return None
    if _looks_like_prompt_leak(response):
        return None

    # Quality gate: check conciseness
    word_count = len(response.split())
    if word_count > 80:
        # Too verbose for NPC dialogue — try to trim
        response = _call_local_llm(
            base_url,
            system="Shorten this NPC dialogue response to 1-3 sentences while keeping the same meaning and personality.",
            user=response,
            temperature=0.3,
            max_tokens=80,
        )

    return _clean_response(response) if response else None


# ==============================================================================
# LLM & NOTEBOOKLM HELPERS
# ==============================================================================

from openai import OpenAI

def _preflight_local_llm(base_url: str, model_id: str) -> bool:
    """Fail fast when the local OpenAI-compatible server is unavailable."""
    try:
        client = OpenAI(base_url=f"{base_url}/v1", api_key="dummy", timeout=5.0)
        models = client.models.list()
    except Exception as exc:
        print(f"\n[ERROR] Local LLM server is not reachable at {base_url}/v1: {exc}")
        print("        Start LM Studio's local server, load a model, and rerun generation.")
        return False

    loaded_models = [model.id for model in getattr(models, "data", [])]
    if loaded_models:
        print(f"  Local LLM reachable. Available models: {loaded_models}")
        if model_id != "local-model" and model_id not in loaded_models:
            print(f"  WARNING: Requested --llm-model '{model_id}' was not listed by the server.")
    else:
        print("  Local LLM reachable, but no model IDs were returned by /v1/models.")

    return True

def _call_local_llm(
    base_url: str,
    system: str,
    user: str,
    model_id: str = "local-model",
    temperature: float = 0.7,
    max_tokens: int = 256,
) -> str | None:
    """Call a local OpenAI-compatible LLM server."""
    try:
        client = OpenAI(base_url=f"{base_url}/v1", api_key="dummy")
        response = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.1,
            frequency_penalty=0.5,
            stream=False,
        )
        return response.choices[0].message.content
    except Exception as exc:
        print(f"    LLM call failed: {exc}")
        return None


# ==============================================================================
# OPTIMIZATION: ASYNC BATCH LLM CALLS
# ==============================================================================


async def _call_async_llm(
    base_url: str,
    system: str,
    user: str,
    model_id: str = "local-model",
    temperature: float = 0.7,
    max_tokens: int = 256,
) -> str | None:
    """Async call to local LLM server."""
    if not ASYNC_LLM_AVAILABLE:
        return _call_local_llm(base_url, system, user, model_id, temperature, max_tokens)

    try:
        # Create client once per request or reuse? Let's add timeout
        client = AsyncOpenAI(base_url=f"{base_url}/v1", api_key="dummy", timeout=120.0)
        response = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=0.1,
            frequency_penalty=0.5,
            stream=False,
        )
        content = response.choices[0].message.content
        if content:
            print(".", end="", flush=True)
        return content
    except Exception as exc:
        print(f"    Async LLM call failed: {exc}")
        return None


async def _generate_batch_async(
    base_url: str,
    requests: list[dict[str, str]],
    model_id: str = "local-model",
    temperature: float = 0.7,
    max_tokens: int = 256,
) -> list[str | None]:
    """Generate multiple responses concurrently.

    OPTIMIZATION: Batch generate N examples in 1 API call instead of N sequential calls.
    This is ~N times faster for generation.
    """
    if not ASYNC_LLM_AVAILABLE:
        # Fallback to sequential if async not available
        results = []
        for req in requests:
            result = _call_local_llm(
                base_url, req["system"], req["user"], model_id, temperature, max_tokens
            )
            results.append(result)
        return results

    async def single_call(req: dict[str, str]) -> str | None:
        return await _call_async_llm(
            base_url, req["system"], req["user"], model_id, temperature, max_tokens
        )

    # Run all concurrently - much faster than sequential
    tasks = [single_call(req) for req in requests]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Convert exceptions to None
    return [r if isinstance(r, str) else None for r in results]


# ==============================================================================
# OPTIMIZATION: SEMANTIC DEDUPLICATION
# ==============================================================================


def _compute_text_hash(text: str) -> str:
    """Compute simple hash for deduplication."""
    normalized = " ".join(text.lower().split())
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def _deduplicate_examples(
    examples: list[TrainingExample],
    max_examples: int | None = None,
) -> list[TrainingExample]:
    """Remove duplicate examples based on response content.

    OPTIMIZATION: Uses hash-based exact dedup, removes duplicate responses.
    """
    seen_hashes: set[str] = set()
    unique_examples: list[TrainingExample] = []

    for ex in examples:
        # Get response content for hashing
        response = ""
        for msg in ex.messages:
            if msg.get("role") == "assistant":
                response = msg.get("content", "")
                break

        if not response:
            continue

        text_hash = _compute_text_hash(response)

        if text_hash not in seen_hashes:
            seen_hashes.add(text_hash)
            unique_examples.append(ex)

            if max_examples and len(unique_examples) >= max_examples:
                break

    if len(examples) - len(unique_examples) > 0:
        print(
            f"  Deduplicated: {len(examples)} -> {len(unique_examples)} "
            f"({len(examples) - len(unique_examples)} duplicates removed)"
        )

    return unique_examples


def _is_strict_chatml_example(example: TrainingExample) -> bool:
    """Validate strict ChatML role structure and educational roleplay guardrails."""
    messages = example.messages
    if len(messages) < 3:
        return False

    roles = [message.get("role") for message in messages]
    if roles[0] != "system":
        return False
    if any(role not in {"system", "user", "assistant"} for role in roles):
        return False
    if "user" not in roles or "assistant" not in roles:
        return False

    system_content = messages[0].get("content", "")
    if "[MEMORY_CONTEXT:" not in system_content:
        return False

    for message in messages:
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return False
        if message.get("role") == "assistant" and _looks_like_prompt_leak(content):
            return False

    return True


def _filter_valid_examples(examples: list[TrainingExample]) -> list[TrainingExample]:
    """Drop malformed or fourth-wall examples before writing JSONL."""
    valid = [example for example in examples if _is_strict_chatml_example(example)]
    dropped = len(examples) - len(valid)
    if dropped:
        print(f"  Validation dropped {dropped} malformed or fourth-wall examples")
    return valid


def _run_notebooklm_command(args: list[str]) -> str:
    """Run a notebooklm command and return output."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"    notebooklm command failed: {result.stderr[:200]}")
            return ""
        return result.stdout
    except FileNotFoundError:
        print(
            "    ERROR: 'notebooklm' command not found. Install: pip install notebooklm-py"
        )
        return ""
    except subprocess.TimeoutExpired:
        print("    ERROR: notebooklm command timed out (120s)")
        return ""


def _parse_notebook_id(output: str) -> str | None:
    """Parse notebook ID from notebooklm create output."""
    # notebooklm typically outputs JSON or structured text with the notebook ID
    try:
        data = json.loads(output)
        return data.get("id") or data.get("notebook_id")
    except (json.JSONDecodeError, AttributeError):
        pass
    # Try to find an ID-like string
    for line in output.strip().split("\n"):
        line = line.strip()
        if len(line) > 10 and not line.startswith("#"):
            return line
    return None


def _extract_topics(query: str, domain_knowledge: list[str]) -> list[str]:
    """Find which domain knowledge topics match a query."""
    stopwords = {
        "a", "an", "and", "are", "briefly", "can", "describe", "does", "explain",
        "how", "in", "is", "of", "the", "to", "what", "who", "work",
    }

    def tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token not in stopwords and len(token) > 2
        }

    query_tokens = tokens(query)
    matches = []
    for topic in domain_knowledge:
        topic_tokens = tokens(topic)
        if query_tokens & topic_tokens:
            matches.append(topic)

    return matches or domain_knowledge[:1]


# ==============================================================================
# OUTPUT
# ==============================================================================


def save_dataset(
    examples: list[TrainingExample],
    profile: NpcProfile,
    output_dir: Path,
) -> Path:
    """Save examples as JSONL in the project dataset structure.

    Output path: datasets/personas/{storage_key}/{dataset_name}.jsonl
    Each persona gets its own folder. Also registers the dataset in
    datasets/configs/dataset_registry.json.
    """
    examples = _filter_valid_examples(examples)
    if not examples:
        raise ValueError("No valid strict ChatML examples to save.")

    # Each persona gets its own folder: personas/{storage_key}/
    persona_dir = output_dir / profile.storage_key
    persona_dir.mkdir(parents=True, exist_ok=True)

    output_path = persona_dir / f"{profile.output_dataset_name}.jsonl"

    with open(output_path, "w", encoding="utf-8") as f:
        for ex in examples:
            row = {
                "messages": ex.messages,
                "metadata": ex.metadata,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n  Saved {len(examples)} examples to {output_path}")

    # Register in dataset_registry.json
    _register_dataset(profile, output_path, len(examples))

    return output_path


def _register_dataset(profile: NpcProfile, output_path: Path, sample_count: int) -> None:
    """Add or update this dataset's entry in datasets/configs/dataset_registry.json."""
    registry_path = ROOT_DIR / "datasets" / "configs" / "dataset_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing registry
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"datasets": []}
    else:
        data = {"datasets": []}

    # Relative path from ROOT_DIR (for portability inside Docker)
    try:
        rel_path = output_path.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        rel_path = str(output_path)

    dataset_name = profile.output_dataset_name
    match_names = {
        dataset_name,
        f"{profile.key}_dataset",
        f"{profile.key}_generated",
    }
    if profile.storage_key != profile.key:
        match_names.add(f"{profile.storage_key}_dataset")
        match_names.add(f"{profile.storage_key}_generated")

    # Update or insert
    existing = next(
        (
            d
            for d in data["datasets"]
            if d.get("name") in match_names
        ),
        None,
    )
    entry = {
        "name": dataset_name,
        "path": rel_path,
        "task_type": "mixed",
        "npc_scope": profile.npc_scope,
        "format": "chatml",
        "sample_count": sample_count,
        "weight": 1.0,
        "source_kind": "synthetic",
        "_note": f"Auto-generated by generate_npc_dataset.py — {profile.display_name}",
    }
    if existing:
        existing.update(entry)
    else:
        data["datasets"].append(entry)

    data["_updated"] = "auto-generated by generate_npc_dataset.py"
    registry_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Registered '{dataset_name}' in dataset_registry.json")


def save_research_notes(
    notes: list[ResearchNote],
    profile: NpcProfile,
) -> Path:
    """Save research notes for inspection and reuse."""
    research_dir = RESEARCH_DIR / profile.key
    research_dir.mkdir(parents=True, exist_ok=True)

    output_path = research_dir / "research_notes.json"

    data = [
        {
            "query": note.query,
            "answer": note.answer,
            "source": note.source,
            "topics": note.topics,
        }
        for note in notes
    ]

    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  Saved {len(notes)} research notes to {output_path}")
    return output_path


def generate_summary(
    profile: NpcProfile,
    examples: list[TrainingExample],
    research_notes: list[ResearchNote],
) -> dict[str, Any]:
    """Generate a summary report of the dataset generation."""
    task_counts = {}
    for ex in examples:
        tt = ex.metadata.get("task_type", "unknown")
        task_counts[tt] = task_counts.get(tt, 0) + 1

    return {
        "npc_key": profile.key,
        "display_name": profile.display_name,
        "npc_scope": profile.npc_scope,
        "total_examples": len(examples),
        "research_notes": len(research_notes),
        "task_type_breakdown": task_counts,
        "avg_quality": sum(ex.metadata.get("quality", 0) for ex in examples)
        / max(len(examples), 1),
        "research_sources": [n.source for n in research_notes],
    }


# ==============================================================================
# MAIN
# ==============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NPC LoRA Dataset Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--npc",
        help="NPC profile key (e.g., kai_instructor, marina_merchant)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate datasets for all NPC profiles",
    )
    parser.add_argument(
        "--backend",
        choices=["notebooklm", "auto"],
        default="auto",
        help="Research backend (notebooklm recommended, auto-detects)",
    )
    parser.add_argument(
        "--notebook-id",
        default=None,
        help="Reuse existing NotebookLM notebook by ID",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=200,
        help="Target number of examples per NPC",
    )
    parser.add_argument(
        "--subject",
        default=None,
        help="Override the profile subject for a focused educational-roleplay test dataset.",
    )
    parser.add_argument(
        "--llm-url",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output-dir",
        default=str(DATASETS_DIR / "personas"),
        help="Output directory for generated datasets",
    )
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip research phase, use existing research notes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without actually generating",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=3407,
        help="Random seed for reproducibility",
    )

    # OPTIMIZATION: Async batch generation
    parser.add_argument(
        "--async-batch",
        action="store_true",
        help="Use async batch generation (faster)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Batch size for async generation",
    )

    # OPTIMIZATION: Deduplication
    parser.add_argument(
        "--deduplicate",
        action="store_true",
        help="Remove duplicate examples after generation",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=None,
        help="Max unique examples after dedup",
    )

    parser.add_argument(
        "--report-path",
        default=None,
        help="Path to a Markdown research report (from NotebookLM Deep Research)",
    )

    return parser.parse_args()


def run_for_profile(
    profile: NpcProfile,
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Run the full pipeline for a single NPC profile."""

    if args.subject:
        subject = args.subject.strip()
        profile.subject = subject
        profile.subject_focus = subject
        profile.domain_knowledge = [subject]
        wiki_slug = re.sub(r"\s+", "_", subject.strip())
        profile.notebooklm_sources = [f"https://en.wikipedia.org/wiki/{wiki_slug}"]
        if not args.skip_research:
            profile.research_queries = [
                f"What are the most important facts a beginner should learn about {subject}?",
                f"Explain {subject} clearly for an educational roleplay tutor.",
                f"What quiz questions best test understanding of {subject}?",
            ]
        if not profile.memory_context_samples:
            profile.memory_context_samples = [
                f"The learner previously asked for a simple overview of {subject}.",
                f"The learner already knows one basic fact about {subject}.",
                f"The learner recently practiced a quiz question about {subject}.",
            ]

    print("=" * 60)
    print(f"NPC Dataset Generation: {profile.display_name}")
    print(f"  Scope: {profile.npc_scope}")
    print(f"  Subject: {profile.subject}")
    print(f"  Target: {args.target_count} examples")
    print("=" * 60)

    if args.dry_run:
        min_per_type = profile.generation_defaults.get("min_examples_per_task_type", 5)
        if args.async_batch and args.target_count < len(profile.task_type_distribution) * min_per_type:
            min_per_type = 1
        task_targets = {}
        for task_type, weight in profile.task_type_distribution.items():
            task_targets[task_type] = max(min_per_type, int(args.target_count * weight))
        print(f"\n  [DRY RUN] Would generate:")
        print(f"    Research queries: {len(profile.research_queries)}")
        print(f"    NotebookLM sources: {len(profile.notebooklm_sources)}")
        print(f"    Task targets: {task_targets}")
        print(f"    Total target: ~{sum(task_targets.values())} examples")
        return None

    if not _preflight_local_llm(args.llm_url, args.llm_model):
        print("  WARNING: Local LLM check failed, continuing anyway...")

    # ── Step 1: Research ──────────────────────────────────────────────
    research_notes: list[ResearchNote] = []

    if args.skip_research:
        # Load existing research notes
        notes_path = RESEARCH_DIR / profile.key / "research_notes.json"
        if notes_path.exists():
            raw = json.loads(notes_path.read_text(encoding="utf-8"))
            research_notes = [ResearchNote(**n) for n in raw]
            print(f"\n[1/3] Loaded {len(research_notes)} existing research notes")
        else:
            print(f"\n[1/3] No existing research found at {notes_path}")
    else:
        print(f"\n[1/3] Researching '{profile.subject}'...")
        backend = args.backend

        if backend == "auto":
            # Try NotebookLM first
            try:
                result = subprocess.run(
                    ["notebooklm", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    backend = "notebooklm"
                else:
                    print("  WARNING: notebooklm not available, falling back to report if available")
                    backend = "notebooklm"  # Will fail gracefully in research_via_notebooklm
            except (FileNotFoundError, subprocess.TimeoutExpired):
                print("  WARNING: notebooklm not found, falling back to report if available")
                backend = "notebooklm"  # Will fail gracefully in research_via_notebooklm
            print(f"  Auto-detected backend: {backend}")

        if args.report_path:
            report_path = Path(args.report_path)
            if report_path.exists():
                research_notes = research_via_report(profile, report_path, args.llm_url)
            else:
                print(f"  ERROR: Report not found at {report_path}")
                research_notes = []

        if not research_notes:
            research_notes = research_via_notebooklm(profile, args.notebook_id)

        # Save research for reuse
        if research_notes:
            save_research_notes(research_notes, profile)

    if not research_notes:
        print("  WARNING: No research notes available. Generating from profile only.")

    # ── Step 2: Generate dataset ──────────────────────────────────────
    print(f"\n[2/3] Generating training examples...")

    if args.async_batch and ASYNC_LLM_AVAILABLE:
        print(
            f"[OPTIMIZATION] Using async batch generation (batch_size={args.batch_size})"
        )
        examples = asyncio.run(
            generate_dataset_async(
                profile,
                research_notes,
                target_count=args.target_count,
                base_url=args.llm_url,
                batch_size=args.batch_size,
                model_id=args.llm_model
            )
        )
    else:
        examples = generate_dataset(
            profile,
            research_notes,
            target_count=args.target_count,
            base_url=args.llm_url,
            model_id=args.llm_model
        )

    # OPTIMIZATION: Deduplicate if requested
    if args.deduplicate and examples:
        print(f"[OPTIMIZATION] Deduplicating examples...")
        examples = _deduplicate_examples(examples, args.max_examples)

    if not examples:
        print("\n[ERROR] No examples were generated. Check that the local LLM server is running and reachable.")
        print("        Refusing to save an empty dataset or update dataset_registry.json.")
        sys.exit(1)

    # ── Step 3: Save output ───────────────────────────────────────────
    print(f"\n[3/3] Saving dataset...")
    output_dir = Path(args.output_dir)
    save_dataset(examples, profile, output_dir)

    # Summary
    summary = generate_summary(profile, examples, research_notes)

    summary_path = RESEARCH_DIR / profile.key / "generation_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print(f"COMPLETE: {profile.display_name}")
    print(f"  Examples: {summary['total_examples']}")
    print(f"  Task breakdown: {summary['task_type_breakdown']}")
    print(f"  Avg quality: {summary['avg_quality']:.2f}")
    print(f"{'=' * 60}")

    return summary


def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    # Load profiles
    profiles = load_profiles()

    if not profiles:
        print("ERROR: No NPC profiles found. Check datasets/configs/npc_profiles.json")
        sys.exit(1)

    print(f"Available NPC profiles: {list(profiles.keys())}")

    # Determine which profiles to process
    selected: list[NpcProfile] = []

    if args.all:
        selected = list(profiles.values())
    elif args.npc:
        if args.npc not in profiles:
            print(
                f"ERROR: Unknown NPC '{args.npc}'. Available: {list(profiles.keys())}"
            )
            sys.exit(1)
        selected = [profiles[args.npc]]
    else:
        print("ERROR: Specify --npc <key> or --all")
        print(f"Available NPCs: {list(profiles.keys())}")
        sys.exit(1)

    # Process each profile
    summaries = []
    for profile in selected:
        summary = run_for_profile(profile, args)
        if summary:
            summaries.append(summary)

    # Overall summary
    if summaries:
        print(f"\n{'=' * 60}")
        print("ALL GENERATION COMPLETE")
        print(f"{'=' * 60}")
        total = sum(s["total_examples"] for s in summaries)
        print(f"  NPCs processed: {len(summaries)}")
        print(f"  Total examples: {total}")
        for s in summaries:
            print(f"    {s['display_name']}: {s['total_examples']} examples")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
