#!/usr/bin/env python
"""Export an Unsloth LoRA checkpoint into final adapter, merged 16-bit, and GGUF artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from unsloth import FastLanguageModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export an Unsloth checkpoint directory into deployable artifacts."
    )
    parser.add_argument(
        "--checkpoint-dir",
        required=True,
        help="Path to a checkpoint folder containing adapter_config.json and adapter_model.safetensors.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Root output directory for final artifacts.",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=1024,
        help="Sequence length to use when loading the checkpoint.",
    )
    parser.add_argument(
        "--save-merged-16bit",
        action="store_true",
        help="Also export a merged 16-bit model directory.",
    )
    parser.add_argument(
        "--save-gguf",
        default="q4_k_m",
        help="GGUF quantization method. Use empty string to skip GGUF export.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checkpoint_dir = Path(args.checkpoint_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    adapter_dir = output_dir / "lora_adapter"
    merged_dir = output_dir / "merged_16bit"
    gguf_dir = output_dir / "gguf"

    if not checkpoint_dir.exists():
        raise FileNotFoundError(f"Checkpoint directory not found: {checkpoint_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(checkpoint_dir),
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )

    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    if args.save_merged_16bit:
        model.save_pretrained_merged(
            str(merged_dir),
            tokenizer,
            save_method="merged_16bit",
        )

    if args.save_gguf:
        model.save_pretrained_gguf(
            str(gguf_dir),
            tokenizer,
            quantization_method=args.save_gguf,
        )

    summary = {
        "checkpoint_dir": str(checkpoint_dir),
        "output_dir": str(output_dir),
        "adapter_dir": str(adapter_dir),
        "merged_dir": str(merged_dir) if args.save_merged_16bit else None,
        "gguf_dir": str(gguf_dir) if args.save_gguf else None,
        "gguf_quantization": args.save_gguf or None,
        "max_seq_length": args.max_seq_length,
    }
    (output_dir / "export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Adapter export saved to: {adapter_dir}")
    if args.save_merged_16bit:
        print(f"Merged 16-bit model saved to: {merged_dir}")
    if args.save_gguf:
        print(f"GGUF export saved to: {gguf_dir}")


if __name__ == "__main__":
    main()
