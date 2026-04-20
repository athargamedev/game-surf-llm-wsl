#!/usr/bin/env python3
"""
Training Metrics Tracker

Tracks NPC training runs over time to measure improvement.
Run this after each training to log metrics.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
METRICS_FILE = ROOT / ".training_metrics.jsonl"


def get_training_metrics(npc_id: str) -> Optional[dict]:
    """Extract metrics from training report."""
    report_path = ROOT / "exports" / "npc_models" / npc_id / "checkpoints" / "training_report.json"
    config_path = ROOT / "exports" / "npc_models" / npc_id / "run_config.json"
    
    if not report_path.exists():
        return None
    
    report = json.loads(report_path.read_text())
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    
    # Find best train loss
    train_losses = report.get("train_losses", [])
    best_train_loss = min(train_losses, key=lambda x: x["loss"])["loss"] if train_losses else None
    
    # Find best eval loss
    eval_losses = report.get("eval_losses", [])
    best_eval_loss = min(eval_losses, key=lambda x: x["eval_loss"])["eval_loss"] if eval_losses else None
    
    return {
        "npc_id": npc_id,
        "timestamp": datetime.now().isoformat(),
        "training": {
            "total_steps": report.get("total_steps", 0),
            "best_train_loss": best_train_loss,
            "best_eval_loss": best_eval_loss,
            "overfitting_detected": report.get("overfitting_detected", False),
        },
        "config": {
            "dataset_size": config.get("datasets", [{}])[0] if config.get("datasets") else "unknown",
            "num_epochs": config.get("num_train_epochs"),
            "learning_rate": config.get("learning_rate"),
            "lora_r": config.get("lora_r"),
        },
        "dataset": {
            "train_samples": _count_lines(ROOT / "datasets/processed" / f"{npc_id}_dataset" / "train.jsonl"),
            "val_samples": _count_lines(ROOT / "datasets/processed" / f"{npc_id}_dataset" / "validation.jsonl"),
        }
    }


def _count_lines(path: Optional[Path]) -> int:
    if path and path.exists():
        return len(path.read_text().strip().split("\n"))
    return 0


def log_training(npc_id: str) -> dict:
    """Log training metrics for an NPC."""
    metrics = get_training_metrics(npc_id)
    
    if not metrics:
        print(f"No training data found for {npc_id}")
        return {}
    
    # Read existing metrics
    existing = []
    if METRICS_FILE.exists():
        for line in METRICS_FILE.read_text().strip().split("\n"):
            if line:
                existing.append(json.loads(line))
    
    # Add new metrics
    existing.append(metrics)
    
    # Write back
    METRICS_FILE.write_text("\n".join(json.dumps(m) for m in existing) + "\n")
    
    return metrics


def show_history(npc_id: Optional[str] = None) -> None:
    """Show training history."""
    if not METRICS_FILE.exists():
        print("No training history found.")
        return
    
    print("=" * 70)
    print("TRAINING METRICS HISTORY")
    print("=" * 70)
    
    runs = []
    for line in METRICS_FILE.read_text().strip().split("\n"):
        if line:
            runs.append(json.loads(line))
    
    if not runs:
        print("No training history found.")
        return
    
    # Filter by NPC if specified
    if npc_id:
        runs = [r for r in runs if r.get("npc_id") == npc_id]
    
    # Group by NPC
    by_npc = {}
    for r in runs:
        npc = r.get("npc_id", "unknown")
        if npc not in by_npc:
            by_npc[npc] = []
        by_npc[npc].append(r)
    
    for npc, npc_runs in sorted(by_npc.items()):
        print(f"\n🤖 {npc}")
        print("-" * 50)
        
        for i, run in enumerate(npc_runs):
            ts = run.get("timestamp", "")[:19].replace("T", " ")
            train_loss = run.get("training", {}).get("best_train_loss")
            eval_loss = run.get("training", {}).get("best_eval_loss")
            overfit = run.get("training", {}).get("overfitting_detected")
            steps = run.get("training", {}).get("total_steps", 0)
            
            print(f"  Run {i+1} | {ts}")
            print(f"    Steps: {steps}")
            if train_loss:
                print(f"    Train Loss: {train_loss:.4f}")
            if eval_loss:
                print(f"    Eval Loss:  {eval_loss:.4f}")
            if overfit:
                print(f"    ⚠️  Overfitting detected!")
        
        # Show trend
        if len(npc_runs) > 1:
            print(f"\n  📈 Trend (last 3 runs):")
            recent = npc_runs[-3:]
            for i, run in enumerate(recent):
                eval_loss = run.get("training", {}).get("best_eval_loss")
                if eval_loss:
                    arrow = ""
                    if i > 0:
                        prev = recent[i-1].get("training", {}).get("best_eval_loss")
                        if prev:
                            if eval_loss < prev:
                                arrow = " ↓"
                            elif eval_loss > prev:
                                arrow = " ↑"
                    print(f"    {eval_loss:.4f}{arrow}")


def compare(npc_id: str) -> None:
    """Compare current vs previous run for an NPC."""
    if not METRICS_FILE.exists():
        print("No training history.")
        return
    
    runs = []
    for line in METRICS_FILE.read_text().strip().split("\n"):
        if line:
            runs.append(json.loads(line))
    
    npc_runs = [r for r in runs if r.get("npc_id") == npc_id]
    
    if len(npc_runs) < 2:
        print(f"Need at least 2 runs to compare. Found: {len(npc_runs)}")
        return
    
    current = npc_runs[-1]
    previous = npc_runs[-2]
    
    print("=" * 60)
    print(f"COMPARISON: {npc_id}")
    print("=" * 60)
    
    # Training metrics
    curr_train = current.get("training", {})
    prev_train = previous.get("training", {})
    
    print(f"\nTraining:")
    print(f"  Train Loss: {prev_train.get('best_train_loss', 'N/A'):.4f} → {curr_train.get('best_train_loss', 'N/A'):.4f}")
    print(f"  Eval Loss:  {prev_train.get('best_eval_loss', 'N/A'):.4f} → {curr_train.get('best_eval_loss', 'N/A'):.4f}")
    
    # Dataset size
    curr_data = current.get("dataset", {})
    prev_data = previous.get("dataset", {})
    
    print(f"\nDataset:")
    print(f"  Train: {prev_data.get('train_samples', '?')} → {curr_data.get('train_samples', '?')}")
    
    # Summary
    curr_eval = curr_train.get("best_eval_loss")
    prev_eval = prev_train.get("best_eval_loss")
    
    if curr_eval and prev_eval:
        diff = ((curr_eval - prev_eval) / prev_eval) * 100
        print(f"\n📊 Eval Loss Change: {diff:+.1f}%")
        if diff < -5:
            print("   ✅ Significant improvement!")
        elif diff < 0:
            print("   ↗️  Slight improvement")
        elif diff < 5:
            print("   ↘️  Slight regression")
        else:
            print("   ❌ Significant regression")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/training_metrics.py log <npc_id>   # Log training run")
        print("  python scripts/training_metrics.py history        # Show all history")
        print("  python scripts/training_metrics.py history <npc>  # Show NPC history")
        print("  python scripts/training_metrics.py compare <npc>  # Compare last 2 runs")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "log" and len(sys.argv) > 2:
        metrics = log_training(sys.argv[2])
        print(f"Logged: {sys.argv[2]}")
        print(f"  Eval Loss: {metrics.get('training',{}).get('best_eval_loss')}")
    elif cmd == "history":
        npc_id = sys.argv[2] if len(sys.argv) > 2 else None
        show_history(npc_id)
    elif cmd == "compare" and len(sys.argv) > 2:
        compare(sys.argv[2])
    else:
        print("Unknown command")