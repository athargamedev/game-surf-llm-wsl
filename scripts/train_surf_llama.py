#!/usr/bin/env python
"""
Enhanced Game_Surf NPC Dialogue Training Pipeline

Professional fine-tuning pipeline for Gemma 4 with:
- Optimized hyperparameters (based on 2024-2025 Unsloth best practices)
- Multi-source dataset loading and blending
- Validation split with loss tracking
- Early stopping support
- Multiple export formats (GGUF, merged)
- Quality filtering
- Per-role LoRA variants support

Usage:
    python train_surf_llama.py --output-dir exports/surf_gemma4
    python train_surf_llama.py --npc-scope lab_guide --epochs 3
    python train_surf_llama.py --eval-only --benchmark benchmarks/npc_eval.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import torch
from unsloth import FastLanguageModel, is_bfloat16_supported, get_chat_template

# Clear CUDA cache before starting
if torch.cuda.is_available():
    torch.cuda.empty_cache()
from datasets import (
    Dataset,
    DatasetDict,
    load_dataset,
    load_from_disk,
)
from transformers import DataCollatorForSeq2Seq, TrainerCallback
from trl import SFTConfig, SFTTrainer
from unsloth.chat_templates import train_on_responses_only
# Ensure scripts/ is in path for local imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from npc_pipeline_contract import build_model_manifest, resolve_npc_spec, write_model_manifest

ROOT_DIR = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT_DIR / "datasets"

# ==============================================================================
# VRAM MANAGER
# ==============================================================================



def check_vram_guard(threshold_gb: float = 3.5) -> None:
    """Check if enough VRAM is free before starting potentially heavy tasks."""
    if not torch.cuda.is_available():
        return

    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info()
        free_gb = free_bytes / (1024**3)
        total_gb = total_bytes / (1024**3)

        print(f"[VRAM] Free: {free_gb:.2f} GB / Total: {total_gb:.2f} GB")

        if free_gb < threshold_gb:
            print(f"!!! WARNING: Low VRAM detected ({free_gb:.2f} GB free) !!!")
            print("Training or GGUF export may fail with OutOfMemory errors.")
            print("Please ensure LM Studio, Docker containers, or other GPU apps are closed.")
            print("Wait 5 seconds to proceed anyway...")
            import time
            time.sleep(5)
    except Exception as e:
        print(f"[VRAM] Could not verify memory: {e}")


@dataclass
class VRAMTier:
    name: str
    min_vram_gb: float
    max_seq_length: int


_VRAM_TIERS = [
    VRAMTier(name="safe",     min_vram_gb=0.0, max_seq_length=1024),
    VRAMTier(name="standard", min_vram_gb=3.5, max_seq_length=1536),
    VRAMTier(name="hd",       min_vram_gb=4.8, max_seq_length=2048),
]


def get_free_vram_gb() -> float:
    """Return free VRAM in GB, or 0.0 if CUDA is unavailable."""
    if not torch.cuda.is_available():
        return 0.0
    try:
        free_mem, _ = torch.cuda.mem_get_info(0)
        return free_mem / (1024 ** 3)
    except Exception:
        return 0.0


def select_max_seq_length(free_vram_gb: float, configured: int) -> int:
    """Select max_seq_length based on available VRAM.

    Tier boundaries:
      < 3.5 GB  → safe     → 1024
      3.5–4.8 GB → standard → 1536
      > 4.8 GB  → hd       → min(2048, configured)
    """
    if free_vram_gb < 3.5:
        return 1024
    elif free_vram_gb < 4.8:
        return 1536
    else:
        return min(2048, configured)


# ==============================================================================
# DEFAULT CONFIGURATION (Optimized from research)
# ==============================================================================

DEFAULT_CONFIG = {
    # Model
    "model_name": "unsloth/gemma-4-E4B-it",  # Gemma 4 E4B for 50% faster inference on RTX 3060
    "max_seq_length": 2048,  # ↑ from 1024 — better multi-turn dialogue context
    # LoRA (Rank-Stabilized) - Optimized for NPC persona capture
    "lora_r": 32,  # ↑ from 16 — richer persona expression
    "lora_alpha": 64,  # ↑ from 32 — 2x rank for stable scaling
    "lora_dropout": 0.05,  # ↑ from 0 — prevent phrase memorization
    "use_rslora": True,  # Rank-stabilized LoRA for higher ranks
    "target_modules": [
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
    # Training (Optimized for consumer GPU)
    "batch_size": 1,
    "gradient_accumulation_steps": 16,  # ↑ from 8 — smoother gradient estimates
    "learning_rate": 1e-4,  # ↓ from 2e-4 — safer with higher rank
    "num_train_epochs": 3,  # ↑ from 2 — solidify character voice
    "warmup_steps": 20,  # ↑ from 10 — prevent early gradient instability
    "weight_decay": 0.03,  # ↑ from 0.01 — better regularization, less "scripted" feel
    "neftune_noise_alpha": 7.5,  # ↑ from 5.0 — better generalization to novel player inputs
    # OPTIMIZATION: Improved LR scheduler (cosine for smoother decay)
    "lr_scheduler_type": "cosine",  # ← from "linear" — smoother late-epoch learning
    "lr_cycles": 0.5,  # Half-cycle cosine for faster convergence
    "lr_min_ratio": 0.05,  # ↓ from 0.1 — decay further at end for clean convergence
    # Packing - pack sequences to max_seq_length for efficiency
    # NOTE: Disable for small datasets (<500 samples) to avoid OOM on 6GB VRAM
    "packing": False,
    "packing_max_seq_length": None,  # Defaults to max_seq_length
    # Data caching is opt-in for prototype runs. Small NPC datasets reformat
    # quickly, and stale formatted caches are more dangerous than useful.
    "use_disk_cache": False,
    "cache_dir": "datasets/.cache",
    # Evaluation
    "eval_strategy": "steps",
    "eval_steps": 50,
    "save_steps": 50,
    "save_total_limit": 2,
    # Early stopping (tighter for better persona consistency)
    "early_stopping_patience": 4,  # ↑ from 3 — NPC dialogue loss can plateau before improving
    "early_stopping_threshold": 0.005,  # ↑ from 0.001 — tighter stopping
    # Optimization
    "optim": "paged_adamw_8bit",  # Perfect for 6GB (pages to RAM if VRAM spikes)
    "use_gradient_checkpointing": "unsloth",
    "seed": 3407,
    # Export
    # NOTE: save_merged_16bit requires downloading the full-precision base model (~6GB)
    # on every export run. Only enable if you need the merged model for non-GGUF inference.
    "save_gguf": "",
    "save_merged_16bit": False,
    # Dataset
    "dataset_mix": "balanced",  # balanced, npc_focus, knowledge_focus
    "val_split": 0.1,
    "quality_threshold": 0.75,
}

# Small-dataset overrides (auto-applied when training samples < 500)
SMALL_DATASET_OVERRIDES = {
    "num_train_epochs": 2,              # ↓ from 3 — prevents memorization
    "warmup_steps": 5,                  # ↓ from 20 — proportional to data size
    "neftune_noise_alpha": 7.0,         # Keep — extra regularization for small data
    "eval_steps": 25,                   # ↓ from 50 — more frequent monitoring
    "save_steps": 25,                   # Match eval frequency
    "early_stopping_patience": 5,       # ↑ from 4 — more patience with tiny data
    "gradient_accumulation_steps": 4,   # ↓ from 16 — more updates per epoch
    "weight_decay": 0.05,               # ↑ from 0.03 — extra regularization
}

# ==============================================================================
# DATASET REGISTRY
# ==============================================================================


def _resolve_local_dataset_path(path_str: str) -> str:
    """Resolve local dataset paths relative to Tools/LLM, not the caller's cwd."""

    candidate = Path(path_str)
    if candidate.is_absolute():
        return str(candidate)

    rooted = ROOT_DIR / candidate
    if rooted.exists():
        return str(rooted)

    if candidate.exists():
        return str(candidate.resolve())

    return str(rooted)


def _discover_dataset_file(dataset_name: str, path_str: str) -> str:
    """Recover from stale registry paths by locating the named JSONL under personas."""

    resolved = Path(_resolve_local_dataset_path(path_str))
    if resolved.exists():
        return str(resolved)

    personas_dir = DATASETS_DIR / "personas"
    if not personas_dir.exists():
        return str(resolved)

    matches: list[Path] = []
    basename = Path(path_str).name if path_str else ""
    if basename:
        matches.extend(personas_dir.glob(f"*/{basename}"))
    if dataset_name:
        matches.extend(personas_dir.glob(f"*/{dataset_name}.jsonl"))

    unique_matches: list[Path] = []
    seen: set[str] = set()
    for match in matches:
        normalized = str(match.resolve())
        if normalized not in seen:
            seen.add(normalized)
            unique_matches.append(match.resolve())

    if len(unique_matches) == 1:
        print(
            f"WARNING: Registry path for '{dataset_name}' was missing; "
            f"using discovered file {unique_matches[0]}"
        )
        return str(unique_matches[0])

    return str(resolved)


def _load_dataset_registry() -> dict:
    """Load AVAILABLE_DATASETS from datasets/configs/dataset_registry.json.

    Falls back to an empty dict if the file doesn't exist.
    Each entry in the registry becomes a key in the returned dict using
    the dataset 'name' field as the key.
    """
    registry_path = Path(__file__).resolve().parents[1] / "datasets" / "configs" / "dataset_registry.json"
    if not registry_path.exists():
        return {}
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        result = {}
        for entry in data.get("datasets", []):
            name = entry.get("name")
            if not name:
                continue
            result[name] = {
                "source": "hub" if entry.get("source") == "hub" else "json",
                "path": _discover_dataset_file(name, entry["path"]),
                "weight": entry.get("weight", 1.0),
                "npc_scope": entry.get("npc_scope", "world"),
            }
        return result
    except Exception as e:
        print(f"WARNING: Could not load dataset registry: {e}")
        return {}


AVAILABLE_DATASETS = _load_dataset_registry()

NPC_SCOPES = [
    "world",  # World knowledge, game mechanics
    "lab_guide",  # Tutorial/mission giver
    "instructor",  # Surf instructor (Kai)
    "merchant",  # Commerce dialogue (Marina)
    "rival",  # Antagonist dialogue (Reef)
    "guard",  # Security/authority (Coral)
    "shared_role",  # Cross-NPC shared behavior
]

TASK_TYPES = [
    "teaching",
    "quiz",
]

# ==============================================================================
# ARGUMENT PARSER
# ==============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enhanced Game_Surf NPC Dialogue Training Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Model
    parser.add_argument(
        "--model-name",
        default=DEFAULT_CONFIG["model_name"],
        help="Base model to finetune",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=DEFAULT_CONFIG["max_seq_length"],
        help="Sequence length",
    )

    # LoRA (Rank-Stabilized)
    parser.add_argument(
        "--lora-r",
        type=int,
        default=DEFAULT_CONFIG["lora_r"],
        help="LoRA rank",
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=DEFAULT_CONFIG["lora_alpha"],
        help="LoRA alpha (use 2x rank for rsLoRA)",
    )
    parser.add_argument(
        "--use-rslora",
        action="store_true",
        default=DEFAULT_CONFIG["use_rslora"],
        help="Use rank-stabilized LoRA",
    )
    parser.add_argument(
        "--target-modules",
        nargs="+",
        default=DEFAULT_CONFIG["target_modules"],
        help="LoRA target modules",
    )

    # Training
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_CONFIG["batch_size"],
        help="Per-device batch size",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=DEFAULT_CONFIG["gradient_accumulation_steps"],
        help="Gradient accumulation steps",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=DEFAULT_CONFIG["learning_rate"],
        help="Learning rate",
    )
    parser.add_argument(
        "--num-train-epochs",
        type=float,
        default=DEFAULT_CONFIG["num_train_epochs"],
        help="Epoch count",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=-1,
        help="Override epochs with fixed step count",
    )
    parser.add_argument(
        "--warmup-steps",
        type=int,
        default=DEFAULT_CONFIG["warmup_steps"],
        help="Warmup steps",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=DEFAULT_CONFIG["weight_decay"],
        help="Weight decay",
    )

    # OPTIMIZATION: Scheduler & packing args
    parser.add_argument(
        "--lr-scheduler",
        type=str,
        default=DEFAULT_CONFIG["lr_scheduler_type"],
        choices=["linear", "cosine", "cosine_with_restarts", "constant"],
        help="Learning rate scheduler",
    )
    parser.add_argument(
        "--lr-min-ratio",
        type=float,
        default=DEFAULT_CONFIG["lr_min_ratio"],
        help="Minimum LR as fraction of max (for cosine)",
    )
    parser.add_argument(
        "--packing",
        action="store_true",
        default=DEFAULT_CONFIG["packing"],
        help="Pack sequences to max_seq_length for efficiency",
    )
    parser.add_argument(
        "--no-packing",
        action="store_true",
        help="Disable packing",
    )
    parser.add_argument(
        "--neftune-noise-alpha",
        type=float,
        default=DEFAULT_CONFIG.get("neftune_noise_alpha"),
        help="Neftune noise alpha for better generalization",
    )

    # Caching & checkpointing
    parser.add_argument(
        "--cache-data",
        action="store_true",
        default=DEFAULT_CONFIG["use_disk_cache"],
        help="Cache processed dataset to disk",
    )
    parser.add_argument(
        "--no-cache-data",
        action="store_false",
        dest="cache_data",
        help="Disable processed dataset cache. Recommended for prototype dataset iteration.",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=DEFAULT_CONFIG["cache_dir"],
        help="Cache directory",
    )
    parser.add_argument(
        "--save-steps",
        type=int,
        default=DEFAULT_CONFIG["save_steps"],
        help="Save checkpoint every N steps",
    )
    parser.add_argument(
        "--save-total-limit",
        type=int,
        default=DEFAULT_CONFIG["save_total_limit"],
        help="Max checkpoints to keep",
    )

    # Evaluation
    parser.add_argument(
        "--eval-steps",
        type=int,
        default=DEFAULT_CONFIG["eval_steps"],
        help="Run evaluation every N steps",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_CONFIG["seed"],
        help="Random seed",
    )

    # Dataset
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["brazilian_history_instructor_dataset"],
        help="Datasets to use (from registry or paths)",
    )
    parser.add_argument(
        "--train-file",
        default=None,
        help="Prepared training split JSONL path",
    )
    parser.add_argument(
        "--val-file",
        default=None,
        help="Prepared validation split JSONL path",
    )
    parser.add_argument(
        "--dataset-weights",
        nargs="+",
        type=float,
        default=None,
        help="Per-dataset weights (must match --datasets)",
    )
    parser.add_argument(
        "--npc-key",
        default=None,
        help="NPC profile key this run belongs to",
    )
    parser.add_argument(
        "--artifact-key",
        default=None,
        help="Stable artifact/storage key for this NPC run",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Canonical dataset name for this run",
    )
    parser.add_argument(
        "--manifest-path",
        default=None,
        help="Optional output manifest path for this run",
    )
    parser.add_argument(
        "--dataset-target-count",
        type=int,
        default=None,
        help="Generation target count used for the linked dataset build",
    )
    parser.add_argument(
        "--prepared-quality-threshold",
        type=float,
        default=None,
        help="Quality threshold used when preparing the linked dataset",
    )
    parser.add_argument(
        "--prepared-val-split",
        type=float,
        default=None,
        help="Validation split used when preparing the linked dataset",
    )
    parser.add_argument(
        "--npc-scope",
        choices=NPC_SCOPES + [None],
        default=None,
        help="Filter by NPC scope",
    )
    parser.add_argument(
        "--task-type",
        choices=TASK_TYPES + [None],
        default=None,
        help="Filter by task type",
    )
    parser.add_argument(
        "--train-sample-limit",
        type=int,
        default=0,
        help="Limit training samples (0=all)",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=DEFAULT_CONFIG["val_split"],
        help="Validation split ratio",
    )
    parser.add_argument(
        "--quality-threshold",
        type=float,
        default=DEFAULT_CONFIG["quality_threshold"],
        help="Filter samples by quality (0.0 = no filter, 0.7 = quality >= 0.7)",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        default="exports/surf_gemma4",
        help="Output directory",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Run name for logging",
    )

    # Export
    parser.add_argument(
        "--save-merged-16bit",
        action="store_true",
        default=DEFAULT_CONFIG["save_merged_16bit"],
        help="Export merged 16-bit model",
    )
    parser.add_argument(
        "--save-gguf",
        default=DEFAULT_CONFIG["save_gguf"],
        help="Optional GGUF quantization (for example q4_k_m). Empty keeps the run as a LoRA adapter.",
    )
    parser.add_argument(
        "--resume-from",
        default=None,
        help="Resume from checkpoint (path to checkpoint folder).",
    )

    # Eval
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Run evaluation only (no training)",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        help="Benchmark JSON file for evaluation",
    )
    parser.add_argument(
        "--early-stopping-patience",
        type=int,
        default=3,
        help="Early stopping patience (0=disabled)",
    )

    # Other
    parser.add_argument(
        "--logging-steps",
        type=int,
        default=10,
        help="Logging interval",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity",
    )
    parser.add_argument(
        "--small-dataset",
        action="store_true",
        help="Apply small-dataset training preset (optimized for <500 samples)",
    )

    return parser.parse_args()


# ==============================================================================
# DATASET LOADING
# ==============================================================================


def load_single_dataset(
    name: str,
    path: str,
    is_hub: bool = False,
    npc_scope: str | None = None,
    task_type: str | None = None,
) -> Dataset:
    """Load a single dataset from local file or HuggingFace Hub."""

    if is_hub:
        raw = load_dataset(path, split="train")
    else:
        # Local JSON/JSONL
        raw = load_dataset(
            "json",
            data_files=_resolve_local_dataset_path(path),
            split="train",
        )

    # Add metadata if not present
    if "metadata" not in raw.column_names:
        # Infer from dataset name
        scope = npc_scope or "world"
        raw = raw.map(
            lambda ex: {
                "metadata": {
                    "npc_scope": scope,
                    "task_type": task_type or "mixed",
                    "source_kind": "raw",
                    "quality": 1.0,
                }
            },
            desc=f"Adding metadata to {name}",
        )

    return raw


def load_datasets(
    dataset_names: list[str],
    weights: list[float] | None = None,
    npc_scope: str | None = None,
    task_type: str | None = None,
    val_split: float = 0.1,
    quality_threshold: float = 0.0,
) -> tuple[Dataset, Dataset]:
    """Load and merge multiple datasets with optional filtering."""

    datasets = []
    total_weight = 0.0

    for i, name in enumerate(dataset_names):
        # Resolve dataset config
        if name in AVAILABLE_DATASETS:
            config = AVAILABLE_DATASETS[name]
            source = config.get("source", "json")
            path = config["path"]
            is_hub = source == "hub"
            weight = config.get("weight", 1.0)
            scope = config.get("npc_scope")
        else:
            # Direct path
            source = "json"
            path = name
            is_hub = False
            weight = 1.0
            scope = None

        # Load
        ds = load_single_dataset(name, path, is_hub, scope or npc_scope, task_type)

        # Filter by scope
        if npc_scope:
            ds = ds.filter(
                lambda x: x.get("metadata", {}).get("npc_scope") == npc_scope,
                desc=f"Filtering {name} by scope={npc_scope}",
            )

        # Filter by task type
        if task_type:
            ds = ds.filter(
                lambda x: x.get("metadata", {}).get("task_type") == task_type,
                desc=f"Filtering {name} by task_type={task_type}",
            )

        # Apply quality threshold filtering
        if quality_threshold > 0:
            ds = ds.filter(
                lambda x: (
                    x.get("metadata", {}).get("quality", 1.0) >= quality_threshold
                ),
                desc=f"Filtering {name} by quality >= {quality_threshold}",
            )

        if len(ds) > 0:
            datasets.append((ds, weight))
            total_weight += weight
            print(f"Loaded {name}: {len(ds)} samples (weight={weight})")
        else:
            print(f"WARNING: {name} filtered to 0 samples, skipping")

    if not datasets:
        raise RuntimeError("No datasets available after loading/filtering")

    # Normalize weights
    if weights:
        # Use provided weights
        if len(weights) != len(datasets):
            raise ValueError("--datasets and --dataset-weights must match")
    else:
        # Normalize to sum to 1
        weights = [w / total_weight for _, w in datasets]

    # Weighted sampling: shuffle each dataset first, then take proportional slice
    from datasets import concatenate_datasets
    import random as _random

    _rng = _random.Random(3407)
    all_samples = []
    total_possible = sum(len(ds) for ds, _ in datasets)
    for (ds, _), w in zip(datasets, weights):
        n = max(1, int(total_possible * w))
        n = min(n, len(ds))
        indices = list(range(len(ds)))
        _rng.shuffle(indices)
        sampled = ds.select(indices[:n])
        all_samples.append(sampled)

    if not all_samples:
        raise RuntimeError("No samples after weighted sampling")

    # Concatenate
    import gc
    gc.collect()
    torch.cuda.empty_cache()
    
    combined = concatenate_datasets(all_samples)
    print(f"Combined dataset: {len(combined)} samples")

    # Shuffle
    combined = combined.shuffle(seed=3407)

    # Split train/val
    if val_split > 0:
        split = combined.train_test_split(test_size=val_split, seed=3407)
        train_ds = split["train"]
        val_ds = split["test"]
        print(f"Train: {len(train_ds)}, Val: {len(val_ds)}")
        return train_ds, val_ds

    return combined, None


# ==============================================================================
# DATA FORMATTING
# ==============================================================================


def detect_format(dataset: Dataset) -> str:
    """Detect dataset format (ChatML, Alpaca, ShareGPT, etc.)."""

    # Check for ChatML
    if "messages" in dataset.column_names:
        return "chatml"

    # Check for Alpaca
    if "instruction" in dataset.column_names and "output" in dataset.column_names:
        return "alpaca"
    if "instruction" in dataset.column_names and "response" in dataset.column_names:
        return "alpaca"

    # Check for ShareGPT
    if "conversations" in dataset.column_names:
        return "sharegpt"

    # Check for standard: instruction/response
    if "instruction" in dataset.column_names:
        return "instruction"

    return "unknown"


def format_to_chatml(examples: dict, tokenizer, chat_template: str) -> dict:
    """Format examples to ChatML for training."""

    output_texts = []

    for i in range(len(examples["messages"])):
        messages = examples["messages"][i]

        # Apply chat template
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
        output_texts.append(text)

    return {"text": output_texts}


def build_text_dataset(
    dataset: Dataset,
    tokenizer,
    format_name: str = "chatml",
) -> Dataset:
    """Convert dataset to training text format."""

    if format_name == "chatml":
        # Already in ChatML format
        def format_row(examples):
            return format_to_chatml(examples, tokenizer, "gemma")

        return dataset.map(
            format_row,
            batched=True,
            remove_columns=dataset.column_names,
            desc="Converting to ChatML",
        )

    elif format_name == "sharegpt":
        # Convert from ShareGPT format (conversations array)
        def format_row(examples):
            texts = []
            for conv in examples["conversations"]:
                messages = []
                for turn in conv:
                    role = turn.get("from", "")
                    if role in ("system", "human", "gpt"):
                        role_map = {
                            "system": "system",
                            "human": "user",
                            "gpt": "assistant",
                        }
                        messages.append(
                            {
                                "role": role_map.get(role, role),
                                "content": turn.get("value", ""),
                            }
                        )
                text = tokenizer.apply_chat_template(messages, tokenize=False)
                texts.append(text)
            return {"text": texts}

        return dataset.map(
            format_row,
            batched=True,
            remove_columns=dataset.column_names,
            desc="Converting ShareGPT to ChatML",
        )

    elif format_name in ("alpaca", "instruction"):
        # Convert from instruction/response
        def format_row(examples):
            texts = []
            for inst, resp in zip(
                examples["instruction"],
                examples.get("response", examples.get("output", [])),
            ):
                messages = [
                    {
                        "role": "system",
                        "content": examples.get("system", [""])[0]
                        if "system" in examples
                        else "",
                    },
                    {"role": "user", "content": inst},
                    {"role": "assistant", "content": resp},
                ]
                text = tokenizer.apply_chat_template(messages, tokenize=False)
                texts.append(text)
            return {"text": texts}

        return dataset.map(
            format_row,
            batched=True,
            remove_columns=dataset.column_names,
            desc="Converting Alpaca to ChatML",
        )

    else:
        raise ValueError(f"Unknown format: {format_name}")


# ==============================================================================
# DATA CACHING (OPTIMIZATION)
# ==============================================================================


def build_cache_suffix(
    max_seq_length: int,
    npc_scope: str | None,
    dataset_identity: str | None = None,
) -> str:
    """Build a cache suffix encoding max_seq_length, npc_scope, and dataset identity.

    Different configs must never share a cache entry:
      build_cache_suffix(1024, None)         → "_formatted_1024"
      build_cache_suffix(1024, "instructor") → "_formatted_1024_instructor"
      build_cache_suffix(1536, "merchant")   → "_formatted_1536_merchant"
    """
    suffix = f"_formatted_{max_seq_length}"
    if npc_scope is not None:
        suffix += f"_{npc_scope}"
    if dataset_identity:
        digest = hashlib.sha1(dataset_identity.encode("utf-8")).hexdigest()[:12]
        suffix += f"_{digest}"
    return suffix


def build_dataset_identity(args: argparse.Namespace) -> str:
    if args.train_file or args.val_file:
        identities: list[str] = []
        for value in [args.train_file, args.val_file]:
            if not value:
                continue
            path = Path(value)
            if path.exists():
                stat = path.stat()
                identities.append(f"{path}:{stat.st_size}:{stat.st_mtime_ns}")
            else:
                identities.append(str(path))
        return "|".join(identities)
    return "|".join(args.datasets or [])


def get_cache_path(cache_dir: Path, suffix: str = "") -> tuple[Path, Path]:
    """Get cache paths for train/val datasets."""
    train_cache = cache_dir / f"train_cache{suffix}"
    val_cache = cache_dir / f"val_cache{suffix}"
    return train_cache, val_cache


def save_dataset_cache(
    train_dataset: Dataset,
    val_dataset: Dataset | None,
    cache_dir: Path,
    suffix: str = "",
) -> None:
    """Save processed datasets to disk cache."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    train_cache, val_cache = get_cache_path(cache_dir, suffix)

    print(f"Caching train dataset to {train_cache}...")
    train_dataset.save_to_disk(str(train_cache))

    if val_dataset is not None:
        print(f"Caching val dataset to {val_cache}...")
        val_dataset.save_to_disk(str(val_cache))


def load_dataset_cache(
    cache_dir: Path,
    suffix: str = "",
) -> tuple[Dataset | None, Dataset | None]:
    """Load cached datasets from disk. Returns (None, None) on any error."""
    cache_dir = Path(cache_dir)
    train_cache, val_cache = get_cache_path(cache_dir, suffix)

    if not train_cache.exists():
        return None, None

    try:
        print(f"Loading cached train from {train_cache}...")
        train_dataset = load_from_disk(str(train_cache))
    except Exception as e:
        print(f"[CACHE] Failed to load train cache: {e}. Rebuilding from source.")
        return None, None

    val_dataset = None
    if val_cache.exists():
        try:
            val_dataset = load_from_disk(str(val_cache))
        except Exception as e:
            print(f"[CACHE] Failed to load val cache: {e}. Proceeding without val cache.")
            val_dataset = None

    return train_dataset, val_dataset


def get_or_build_text_dataset(
    args: argparse.Namespace,
    tokenizer,
    build_fn,
) -> tuple[Dataset, Dataset | None]:
    """Build and optionally cache text-formatted datasets.

    OPTIMIZATION: Cache happens AFTER text formatting so format is preserved.
    """
    cache_dir = Path(args.cache_dir)
    cache_suffix = build_cache_suffix(
        args.max_seq_length,
        args.npc_scope,
        build_dataset_identity(args),
    )

    if args.cache_data:
        # Try loading from cache
        train_ds, val_ds = load_dataset_cache(cache_dir, cache_suffix)
        if train_ds is not None:
            print(f"[CACHE HIT] Using cached formatted datasets")
            return train_ds, val_ds

    # Build from source
    train_ds, val_ds = build_fn()

    # Format to text BEFORE caching
    fmt = detect_format(train_ds)
    print(f"Detected format: {fmt}")

    train_ds = build_text_dataset(train_ds, tokenizer, fmt)
    if val_ds:
        val_ds = build_text_dataset(val_ds, tokenizer, fmt)

    # Cache formatted result
    if args.cache_data:
        save_dataset_cache(train_ds, val_ds, cache_dir, cache_suffix)

    return train_ds, val_ds


# ==============================================================================
# TRAINING
# ==============================================================================


class EarlyStoppingCallback(TrainerCallback):
    """Custom early stopping callback for training."""

    def __init__(self, patience: int = 3, threshold: float = 0.001):
        self.patience = patience
        self.threshold = threshold
        self.best_loss = float("inf")
        self.patience_counter = 0

    def on_evaluate(self, args, state, control, metrics, **kwargs):
        current_loss = metrics.get("eval_loss")
        if current_loss is None:
            return control

        if current_loss < self.best_loss - self.threshold:
            self.best_loss = current_loss
            self.patience_counter = 0
            print(f"[EarlyStopping] New best eval_loss: {current_loss:.4f}")
        else:
            self.patience_counter += 1
            print(
                f"[EarlyStopping] No improvement ({self.patience_counter}/{self.patience})"
            )

        if self.patience_counter >= self.patience:
            print(f"[EarlyStopping] Stopping training at step {state.global_step}")
            control.should_training_stop = True

        return control


class TrainingReportCallback(TrainerCallback):
    """Tracks loss curves and detects overfitting during training.

    Logs train_loss and eval_loss at every eval step, detects overfitting
    (eval_loss rising while train_loss drops), and saves a training_report.json.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.train_losses: list[dict] = []
        self.eval_losses: list[dict] = []
        self.overfitting_detected = False

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        if "loss" in logs:
            self.train_losses.append({
                "step": state.global_step,
                "loss": logs["loss"],
            })

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if metrics is None:
            return
        eval_loss = metrics.get("eval_loss")
        if eval_loss is not None:
            self.eval_losses.append({
                "step": state.global_step,
                "eval_loss": eval_loss,
            })

            # Detect overfitting: eval_loss rising while train_loss dropping
            if len(self.eval_losses) >= 3 and len(self.train_losses) >= 3:
                recent_eval = [e["eval_loss"] for e in self.eval_losses[-3:]]
                recent_train = [t["loss"] for t in self.train_losses[-3:]]
                eval_rising = recent_eval[-1] > recent_eval[0]
                train_dropping = recent_train[-1] < recent_train[0]
                if eval_rising and train_dropping:
                    if not self.overfitting_detected:
                        self.overfitting_detected = True
                        print(
                            f"\n⚠️  OVERFITTING DETECTED at step {state.global_step}: "
                            f"eval_loss rising ({recent_eval[0]:.4f} → {recent_eval[-1]:.4f}) "
                            f"while train_loss dropping ({recent_train[0]:.4f} → {recent_train[-1]:.4f})"
                        )

    def on_train_end(self, args, state, control, **kwargs):
        report = {
            "total_steps": state.global_step,
            "train_losses": self.train_losses,
            "eval_losses": self.eval_losses,
            "overfitting_detected": self.overfitting_detected,
        }
        report_path = self.output_dir / "training_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"\n  Training report saved to {report_path}")
        if self.overfitting_detected:
            print("  ⚠️  Overfitting was detected during training — consider reducing epochs or increasing data.")


def load_model_and_tokenizer(args: argparse.Namespace, max_seq_length: int):
    """Load model and tokenizer with validation and LoRA PEFT setup.
    
    Three-tier fallback strategy for limited VRAM (6GB):
      1. float16 on GPU (5GB limit) - best quality
      2. 4-bit on GPU (4GB limit) - good quality  
      3. 4-bit with CPU offload - maximum compatibility
    """
    import torch
    import gc
    free_vram_gb = get_free_vram_gb()

    # Tier 1: float16 without quantization
    if free_vram_gb >= 5.5:
        print("  [Loading] Tier 1: float16 on GPU (5GB limit)...")
        try:
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=args.model_name,
                max_seq_length=max_seq_length,
                dtype=torch.float16,
                load_in_4bit=False,
                device_map={"": 0},
                max_memory={0: "5GB"},
            )
            print("  [OK] Tier 1 succeeded (float16)")
            return _finish_model_setup(model, tokenizer, args)
        except Exception as e:
            print(f"  [WARN] Tier 1 failed: {e}")
            gc.collect()
            torch.cuda.empty_cache()
    else:
        print(
            f"  [Loading] Skipping Tier 1 float16 because only {free_vram_gb:.2f} GB VRAM is free; "
            "going straight to 4-bit loading."
        )
    
    # Tier 2: 4-bit quantization on GPU
    print("  [Loading] Tier 2: 4-bit on GPU (4GB limit)...")
    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=args.model_name,
            max_seq_length=max_seq_length,
            dtype=torch.float16,
            load_in_4bit=True,
            device_map={"": 0},
            max_memory={0: "4GB"},
        )
        print("  [OK] Tier 2 succeeded (4-bit)")
        return _finish_model_setup(model, tokenizer, args)
    except Exception as e:
        print(f"  [WARN] Tier 2 failed: {e}")
        gc.collect()
        torch.cuda.empty_cache()
    
    # Tier 3: 4-bit with CPU offload (device_map="balanced" spreads across GPU+CPU)
    print("  [Loading] Tier 3: 4-bit with CPU offload (balanced)...")
    try:
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=args.model_name,
            max_seq_length=max_seq_length,
            dtype=torch.float16,
            load_in_4bit=True,
            device_map="balanced",  # Spreads layers across GPU + CPU RAM
            max_memory={0: "2GB", "cpu": "30GB"},  # Keep only 2GB on GPU
            offload_folder="outputs/offload",
            offload_state_dir="outputs/offload",
        )
        print("  [OK] Tier 3 succeeded (4-bit + CPU offload)")
        return _finish_model_setup(model, tokenizer, args)
    except Exception as e:
        print(f"  [ERROR] All tiers failed: {e}")
        raise RuntimeError(
            "Model loading failed on all tiers. Try:\n"
            "  1. Close other GPU apps (LM Studio, Docker, etc.)\n"
            "  2. Reduce max_seq_length\n"
            "  3. Use a smaller base model (e.g., gemma-4-E2B)"
        )


def _finish_model_setup(model, tokenizer, args):
    """Common post-loading model/tokenizer setup."""
    import torch
    from unsloth import get_chat_template
    
    tokenizer = get_chat_template(tokenizer, chat_template="gemma")

    assert tokenizer.pad_token_id is not None, \
        "Tokenizer missing pad_token — set tokenizer.pad_token = tokenizer.eos_token"
    assert tokenizer.eos_token_id is not None, \
        "Tokenizer missing eos_token"
    if tokenizer.pad_token_id == tokenizer.eos_token_id:
        print("WARNING: pad_token and eos_token are the same, reassigning pad_token to unk_token")
        tokenizer.pad_token_id = tokenizer.unk_token_id

    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=args.target_modules,
        lora_alpha=args.lora_alpha,
        lora_dropout=DEFAULT_CONFIG["lora_dropout"],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        use_rslora=args.use_rslora,
        loftq_config=None,
    )

    return model, tokenizer


def load_prepared_datasets(
    train_file: str,
    val_file: str | None = None,
) -> tuple[Dataset, Dataset | None]:
    train_path = _resolve_local_dataset_path(train_file)
    train_dataset = load_dataset("json", data_files=train_path, split="train")

    val_dataset = None
    if val_file:
        val_path = _resolve_local_dataset_path(val_file)
        val_dataset = load_dataset("json", data_files=val_path, split="train")

    return train_dataset, val_dataset


def create_trainer(
    model,
    tokenizer,
    train_dataset: Dataset,
    val_dataset: Dataset | None,
    args: argparse.Namespace,
    output_dir: Path,
):
    """Create and configure SFTTrainer with optimizations."""

    # Determine packing setting
    use_packing = args.packing and not args.no_packing
    model_dtype = None
    for parameter in model.parameters():
        if parameter.is_floating_point() and not parameter.is_meta:
            model_dtype = parameter.dtype
            break

    use_bf16 = model_dtype == torch.bfloat16
    use_fp16 = not use_bf16

    # SFT Config with optimizations
    sft_kwargs = {
        "per_device_train_batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "warmup_steps": args.warmup_steps,
        "learning_rate": args.learning_rate,
        "logging_steps": args.logging_steps,
        "optim": DEFAULT_CONFIG["optim"],
        "weight_decay": args.weight_decay,
        "lr_scheduler_type": args.lr_scheduler,
        "seed": args.seed,
        "output_dir": str(output_dir),
        "report_to": "none",
        "fp16": use_fp16,
        "bf16": use_bf16,
        "max_grad_norm": 1.0,  # Gradient clipping for stability
        # OPTIMIZATION: Checkpointing
        "save_strategy": "steps",
        "save_steps": args.save_steps,
        "save_total_limit": args.save_total_limit,
        "fp16_full_eval": True,  # Memory-efficient evaluation
        "per_device_eval_batch_size": 2,  # Evaluation OOM prevention
        "eval_accumulation_steps": 4,  # Evaluation OOM prevention
    }

    # Eval strategy — only enable when val dataset is present
    # (load_best_model_at_end requires eval_strategy to match save_strategy)
    if val_dataset is not None:
        sft_kwargs["eval_strategy"] = "steps"
        sft_kwargs["eval_steps"] = getattr(
            args, "eval_steps", DEFAULT_CONFIG["eval_steps"]
        )
        sft_kwargs["load_best_model_at_end"] = True
        sft_kwargs["metric_for_best_model"] = "eval_loss"
        sft_kwargs["greater_is_better"] = False

    # Cosine scheduler params - simplified for compatibility
    if "cosine" in args.lr_scheduler:
        # Note: lr_min_ratio not supported in older transformers
        pass

    if args.max_steps > 0:
        sft_kwargs["max_steps"] = args.max_steps
    else:
        sft_kwargs["num_train_epochs"] = args.num_train_epochs

    # Remove keys not supported in this version of transformers/unsloth
    for key in ["early_stopping_patience", "early_stopping_threshold"]:
        sft_kwargs.pop(key, None)

    sft_config = SFTConfig(**sft_kwargs)

    # Data collator - optimize padding for packing
    packing_max_len = args.max_seq_length  # Use max_seq_length for packing
    if use_packing:
        # When using packing, no padding needed - sequences are packed together
        collator = DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            padding=False,  # No padding with packing
            max_length=packing_max_len,
        )
    else:
        # Standard padding for non-packed training
        collator = DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            padding=True,
            max_length=args.max_seq_length,
            pad_to_multiple_of=16,
            return_tensors="pt",
        )

    # OPTIMIZATION: Trainer with packing
    trainer_kwargs = {
        "model": model,
        "train_dataset": train_dataset,
        "eval_dataset": val_dataset,  # Add validation dataset
        "dataset_text_field": "text",
        "max_seq_length": packing_max_len if use_packing else args.max_seq_length,
        "data_collator": collator,
        "packing": use_packing,  # OPTIMIZATION: Enable packing
        "args": sft_config,
    }
    
    # Add optional Neftune noise alpha
    neftune_val = getattr(args, "neftune_noise_alpha", None)
    if neftune_val is not None:
        trainer_kwargs["neftune_noise_alpha"] = neftune_val

    try:
        trainer = SFTTrainer(tokenizer=tokenizer, **trainer_kwargs)
    except TypeError:
        # Fallback for older transformers
        trainer = SFTTrainer(processing_class=tokenizer, **trainer_kwargs)

    # Apply response-only training (learns only from assistant responses)
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|start_header_id|>user<|end_header_id|>\n\n",
        response_part="<|start_header_id|>assistant<|end_header_id|>\n\n",
    )

    # Add early stopping callback if val_dataset is provided and patience > 0
    if val_dataset is not None and args.early_stopping_patience > 0:
        from transformers import EarlyStoppingCallback as TransformersEarlyStoppingCallback
        early_stopping = TransformersEarlyStoppingCallback(
            early_stopping_patience=args.early_stopping_patience,
            early_stopping_threshold=0.001,
        )
        trainer.add_callback(early_stopping)
        print(f"[EarlyStopping] Enabled with patience={args.early_stopping_patience}")

    # Always add training report callback
    trainer.add_callback(TrainingReportCallback(output_dir=output_dir))
    print("[TrainingReport] Loss tracking and overfitting detection enabled")

    return trainer


def _export_gguf(model, tokenizer, gguf_dir: Path, method: str) -> None:
    """Export GGUF with OOM retry at reduced memory usage."""
    print(f"Exporting GGUF ({method})...")
    try:
        model.save_pretrained_gguf(
            str(gguf_dir),
            tokenizer,
            quantization_method=method,
            maximum_memory_usage=0.75,
        )
    except torch.cuda.OutOfMemoryError:
        print("[GGUF] OOM at 0.75 memory usage, retrying at 0.5...")
        torch.cuda.empty_cache()
        try:
            model.save_pretrained_gguf(
                str(gguf_dir),
                tokenizer,
                quantization_method=method,
                maximum_memory_usage=0.5,
            )
        except torch.cuda.OutOfMemoryError:
            print("WARNING: GGUF export failed due to OOM even at 0.5 memory usage. Skipping GGUF export.")
        except Exception as e:
            # Handle the specific case where unsloth might fail during quantization but produce the BF16 file
            print(f"WARNING: GGUF export encountered an error: {e}")
            print("Will attempt to locate any partially generated GGUF files.")


def _make_gguf_name(model_name: str, datasets: list[str], method: str) -> str:
    """Build a descriptive GGUF filename.

    Format: {base_model}-{datasets}-{quant}.gguf
    Example: gemma-4-E4B-kai_instructor-q4_k_m.gguf
    """
    # Shorten model name: keep the last path component, strip unsloth/ prefix
    base = model_name.split("/")[-1].lower()
    # Remove common suffixes that add noise
    for suffix in ["-instruct", "-chat", "-hf"]:
        base = base.replace(suffix, "")

    # Datasets: join with + for multi-dataset runs, truncate if too long
    ds_part = "+".join(datasets)[:40] if datasets else "custom"
    # Sanitize
    ds_part = ds_part.replace("/", "_").replace(" ", "_")

    quant = method.lower().replace(" ", "_")

    return f"{base}-{ds_part}-{quant}.gguf"


def _rename_gguf(output_dir: Path, gguf_dir: Path, new_name: str) -> Path | None:
    """Find the GGUF Unsloth just wrote and move it into the canonical gguf folder.

    Depending on the Unsloth version, the export may land in:
      - output_dir/gguf/*.gguf
      - output_dir/gguf/gguf_gguf/*.gguf
      - output_dir/gguf_gguf/*.gguf
    """
    # Collect all GGUF files recursively
    gguf_files = list(output_dir.rglob("*.gguf"))
    
    # Filter out checkpoints and duplicates
    candidates = []
    for f in gguf_files:
        path_str = f.as_posix().lower()
        if "checkpoint" in path_str:
            continue
        # Prefer the final 4-bit quantization if multiple found
        candidates.append(f)
    
    if not candidates:
        return None
        
    # Pick the most relevant file (prefer largest if multple, or non-BF16)
    candidates.sort(key=lambda x: x.stat().st_size, reverse=True)
    src = candidates[0]
    
    dest = gguf_dir / new_name
    if src != dest:
        # If the file is inside a 'gguf_gguf' folder, we want to move it and then clean up the parent
        parent = src.parent
        src.rename(dest)
        print(f"Finalised GGUF export: {dest.relative_to(output_dir)}")
        
        # Clean up 'gguf_gguf' or other empty-ish export artifacts
        if parent.name == "gguf_gguf" or (parent != gguf_dir and parent.name == "gguf"):
             try:
                 # Only remove if it doesn't contain other important things
                 if not list(parent.glob("*.safetensors")):
                     # Use shutil to be safe or just attempt rmdir if empty
                     import shutil
                     shutil.rmtree(parent)
             except Exception:
                 pass
    return dest


def save_run_config(args: argparse.Namespace, output_dir: Path) -> None:
    """Save run configuration for reproducibility. Serialises all args."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert all args to JSON-serializable form
    config = {}
    for key, value in vars(args).items():
        try:
            json.dumps(value)
            config[key] = value
        except (TypeError, ValueError):
            config[key] = str(value)

    config_path = output_dir / "run_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Saved run config to {config_path}")


def maybe_write_npc_manifest(
    args: argparse.Namespace,
    output_dir: Path,
    adapter_dir: Path,
    gguf_path: Path | None,
) -> Path | None:
    if not args.npc_key:
        return None

    spec = resolve_npc_spec(args.npc_key)
    if args.artifact_key and args.artifact_key != spec.artifact_key:
        raise ValueError(
            f"artifact_key mismatch for {args.npc_key}: expected {spec.artifact_key}, got {args.artifact_key}"
        )
    if args.dataset_name and args.dataset_name != spec.dataset_name:
        raise ValueError(
            f"dataset_name mismatch for {args.npc_key}: expected {spec.dataset_name}, got {args.dataset_name}"
        )

    manifest = build_model_manifest(
        spec,
        base_model=args.model_name,
        target_generation_count=args.dataset_target_count,
        quality_threshold=args.prepared_quality_threshold,
        val_split=args.prepared_val_split,
        epochs=int(args.num_train_epochs) if args.max_steps <= 0 else args.max_steps,
        learning_rate=float(args.learning_rate),
        lora_r=int(args.lora_r),
        lora_alpha=int(args.lora_alpha),
        use_rslora=bool(args.use_rslora),
        save_gguf=args.save_gguf,
        sync_to_unity=None,
        train_file=Path(args.train_file) if args.train_file else None,
        val_file=Path(args.val_file) if args.val_file else None,
        output_dir=output_dir,
        adapter_dir=adapter_dir,
        gguf_path=gguf_path,
    )
    manifest_path = Path(args.manifest_path) if args.manifest_path else spec.manifest_path
    write_model_manifest(manifest_path, manifest)
    print(f"NPC model manifest saved to: {manifest_path}")
    return manifest_path


def build_training_summary(
    batch_size: int,
    grad_accum: int,
    trainer_stats,
    peak_reserved_bytes: int,
) -> dict:
    """Build a training summary dict with key metrics."""
    metrics = trainer_stats.metrics if hasattr(trainer_stats, "metrics") else {}
    return {
        "runtime_seconds": metrics.get("train_runtime", 0.0),
        "effective_batch_size": batch_size * grad_accum,
        "peak_vram_gb": peak_reserved_bytes / (1024 ** 3),
        "train_loss": metrics.get("train_loss", None),
    }


def export_model(model, tokenizer, args: argparse.Namespace, output_dir: Path):
    """Export model in all requested formats."""
    adapter_dir = output_dir / "lora_adapter"
    merged_dir = output_dir / "merged_16bit"
    gguf_dir = output_dir / "gguf"

    # Always save LoRA adapter
    print("Saving LoRA adapter...")
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    _convert_lora_adapter_to_gguf(adapter_dir, args.model_name)

    # Export merged 16-bit
    if args.save_merged_16bit:
        print("Exporting merged 16-bit...")
        model.save_pretrained_merged(
            str(merged_dir),
            tokenizer,
            save_method="merged_16bit",
        )

    # Export GGUF with OOM retry, then rename to descriptive filename
    final_gguf = gguf_dir
    if args.save_gguf:
        _export_gguf(model, tokenizer, gguf_dir, args.save_gguf)
        gguf_name = _make_gguf_name(args.model_name, args.datasets, args.save_gguf)
        renamed = _rename_gguf(output_dir, gguf_dir, gguf_name)
        if renamed:
            final_gguf = renamed

    return adapter_dir, final_gguf


def _find_cached_base_config(model_name: str) -> Path | None:
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    candidates = [
        model_name,
        model_name.replace("gemma-4-E2B-it", "llama-3.2-3b-instruct"),
        "unsloth/gemma-4-e4b-it",
    ]
    for candidate in candidates:
        repo_dir = cache_root / f"models--{candidate.replace('/', '--')}"
        snapshots = repo_dir / "snapshots"
        if not snapshots.exists():
            continue
        for config_path in sorted(snapshots.glob("*/config.json")):
            return config_path.parent
    return None


def _convert_lora_adapter_to_gguf(adapter_dir: Path, model_name: str) -> Path | None:
    """Create the llama.cpp LoRA GGUF used by the WSL test server."""
    output_path = adapter_dir / "adapter_model.gguf"
    converter = Path("/root/.unsloth/gemma.cpp/convert_lora_to_gguf.py")
    if not converter.exists():
        print(f"WARNING: LoRA GGUF converter not found: {converter}")
        return None

    command = [
        sys.executable,
        str(converter),
        str(adapter_dir),
        "--outfile",
        str(output_path),
        "--outtype",
        "f16",
    ]
    base_config_dir = _find_cached_base_config(model_name)
    if base_config_dir:
        command.extend(["--base", str(base_config_dir)])
    else:
        command.extend(["--base-model-id", model_name])

    print("Converting LoRA adapter to gemma.cpp GGUF...")
    result = subprocess.run(command, text=True)
    if result.returncode != 0:
        print("WARNING: LoRA GGUF conversion failed. The PEFT adapter was saved, but llama.cpp runtime selection will skip it.")
        return None
    print(f"LoRA GGUF adapter saved to: {output_path}")
    return output_path


# ==============================================================================
# MAIN
# ==============================================================================


def _apply_small_dataset_overrides(args: argparse.Namespace) -> None:
    """Auto-detect small datasets and apply optimized training parameters.

    When the training dataset has fewer than 500 samples, overfitting is
    the primary risk. This function applies SMALL_DATASET_OVERRIDES to
    reduce epochs, increase regularization, and monitor more frequently.
    """
    # Check if explicitly requested or auto-detect from dataset size
    is_small = getattr(args, "small_dataset", False)

    if not is_small:
        # Try to count samples in the dataset files
        total_samples = 0
        if hasattr(args, "train_file") and args.train_file:
            train_path = Path(args.train_file)
            if train_path.exists():
                total_samples = sum(1 for _ in open(train_path, encoding="utf-8"))
        elif hasattr(args, "datasets") and args.datasets:
            for ds_path in args.datasets:
                p = Path(_resolve_local_dataset_path(ds_path))
                if p.exists():
                    total_samples += sum(1 for _ in open(p, encoding="utf-8"))

        if 0 < total_samples < 500:
            is_small = True
            print(
                f"\n[SmallDataset] Auto-detected {total_samples} samples (<500). "
                f"Applying small-dataset training overrides."
            )

    if is_small:
        for key, value in SMALL_DATASET_OVERRIDES.items():
            if hasattr(args, key):
                old_value = getattr(args, key)
                setattr(args, key, value)
                print(f"  [SmallDataset] {key}: {old_value} → {value}")
            elif hasattr(args, key.replace("-", "_")):
                attr_key = key.replace("-", "_")
                old_value = getattr(args, attr_key)
                setattr(args, attr_key, value)
                print(f"  [SmallDataset] {attr_key}: {old_value} → {value}")


def main() -> None:
    args = parse_args()

    # Setup
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")

    # VRAM Manager: select max_seq_length based on available VRAM
    free_vram = get_free_vram_gb()
    args.max_seq_length = select_max_seq_length(free_vram, args.max_seq_length)
    print(f"[VRAM] Free: {free_vram:.2f} GB → max_seq_length={args.max_seq_length}")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    if not torch.cuda.is_available():
        sys.stderr.write("ERROR: CUDA not available\n")
        sys.exit(1)

    # Output directories
    output_dir = Path(args.output_dir)
    checkpoints_dir = output_dir / "checkpoints"

    # Data cache directory
    cache_dir = Path(args.cache_dir)

    # Create output dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Game_Surf NPC Dialogue Training Pipeline")
    print("=" * 60)
    print(f"Model: {args.model_name}")
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"LoRA: r={args.lora_r}, alpha={args.lora_alpha}, rsLoRA={args.use_rslora}")
    if args.train_file:
        print(f"Prepared train file: {args.train_file}")
        if args.val_file:
            print(f"Prepared val file: {args.val_file}")
    else:
        print(f"Datasets: {args.datasets}")
    print(f"Output: {output_dir}")
    print(f"[OPTIMIZATION] Packing: {args.packing and not args.no_packing}")
    print(f"[OPTIMIZATION] LR Schedule: {args.lr_scheduler}")
    print(f"[OPTIMIZATION] Data Cache: {args.cache_data}")
    print("=" * 60)

    # Small-dataset auto-detection and override
    _apply_small_dataset_overrides(args)

    # Save run config
    save_run_config(args, output_dir)

    # [0/5] VRAM Guard
    check_vram_guard()

    # Load model and tokenizer (with validation and LoRA setup)
    print("\n[1/5] Loading model and configuring LoRA...")
    model, tokenizer = load_model_and_tokenizer(args, args.max_seq_length)

    # OPTIMIZATION: Load/format/cache datasets (tokenizer needed for text conversion)
    print("\n[2/5] Loading datasets (with caching)...")

    def build_datasets():
        if args.train_file:
            return load_prepared_datasets(args.train_file, args.val_file)
        return load_datasets(
            args.datasets,
            args.dataset_weights,
            args.npc_scope,
            args.task_type,
            args.val_split,
            args.quality_threshold,
        )

    # Use cache if enabled (caches AFTER text formatting)
    if args.cache_data:
        train_dataset, val_dataset = get_or_build_text_dataset(
            args, tokenizer, build_datasets
        )
    else:
        train_dataset, val_dataset = build_datasets()
        # Format even without caching
        fmt = detect_format(train_dataset)
        print(f"Detected format: {fmt}")
        train_dataset = build_text_dataset(train_dataset, tokenizer, fmt)
        if val_dataset:
            val_dataset = build_text_dataset(val_dataset, tokenizer, fmt)

    # Sample limit
    if args.train_sample_limit > 0:
        train_dataset = train_dataset.select(
            range(min(args.train_sample_limit, len(train_dataset)))
        )
        print(f"Limited to {args.train_sample_limit} samples")

    # Get trainable params
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(
        f"Trainable: {trainable_params:,} / {total_params:,} ({trainable_params / total_params * 100:.2f}%)"
    )

    # Dataset already formatted above
    print("\n[4/5] Dataset ready...")

    # Create trainer
    trainer = create_trainer(
        model,
        tokenizer,
        train_dataset,
        val_dataset,
        args,
        checkpoints_dir,
    )

    # GPU memory info
    gpu_props = torch.cuda.get_device_properties(0)
    max_memory_gb = gpu_props.total_memory / 1024 / 1024 / 1024
    start_reserved = torch.cuda.max_memory_reserved()
    print(f"Max GPU memory: {max_memory_gb:.2f} GB")

    # Train
    print("\n[5/5] Training...")
    trainer_stats = trainer.train(resume_from_checkpoint=args.resume_from)

    # Zero-loss guard: warn if training loss is 0 after training (not just a resume-skip)
    train_loss = trainer_stats.metrics.get("train_loss", None)
    train_runtime = trainer_stats.metrics.get("train_runtime", 0.0)
    if train_loss is not None and train_loss == 0.0 and train_runtime > 1.0:
        print(
            "WARNING: Training loss is 0. This usually means train_on_responses_only "
            "instruction/response tokens do not match the chat template. "
            "Verify instruction_part and response_part match the Llama 3.x header tokens."
        )

    # Export model (LoRA adapter + optional merged/GGUF)
    adapter_dir, gguf_dir = export_model(model, tokenizer, args, output_dir)
    maybe_write_npc_manifest(
        args,
        output_dir,
        adapter_dir,
        gguf_dir if isinstance(gguf_dir, Path) else None,
    )

    # Memory stats
    peak_reserved = torch.cuda.max_memory_reserved()
    used_gb = peak_reserved / 1024 / 1024 / 1024
    delta_gb = (peak_reserved - start_reserved) / 1024 / 1024 / 1024

    # Build and print training summary
    summary = build_training_summary(
        batch_size=args.batch_size,
        grad_accum=args.gradient_accumulation_steps,
        trainer_stats=trainer_stats,
        peak_reserved_bytes=peak_reserved,
    )

    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())

    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Training finished in {summary['runtime_seconds']:.2f} seconds.")
    print(f"Peak reserved memory: {summary['peak_vram_gb']:.2f} GB ({delta_gb:.2f} GB added during training).")
    print(f"Effective batch size: {summary['effective_batch_size']}")
    print(f"Trainable parameters: {trainable_params:,} / {total_params:,} ({trainable_params / total_params * 100:.2f}%)")
    print(f"LoRA adapter saved to: {adapter_dir}")
    if args.save_gguf:
        print(f"GGUF export saved to: {gguf_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
