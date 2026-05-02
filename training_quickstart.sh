#!/bin/bash
# Training Quickstart Script for WSL
# Updated paths for WSL2 native execution with verified dataset names

set -e  # Exit on error

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate conda environment
echo "🔧 Activating unsloth_env..."
source /root/miniforge3/bin/activate unsloth_env || {
    echo "❌ Failed to activate conda environment"
    exit 1
}

# Verify datasets exist
echo "✓ Verifying datasets..."
DATASETS=(
    "datasets/personas/brazilian_history_instructor/brazilian_history_dataset.jsonl"
    "datasets/personas/marvel_comics_instructor/marvel_lore_dataset.jsonl"
)

for dataset in "${DATASETS[@]}"; do
    if [ ! -f "$dataset" ]; then
        echo "⚠️  Dataset not found: $dataset"
    else
        echo "✓ Found: $dataset"
    fi
done

# Default to small test
MODE="${1:-small}"

if [ "$MODE" = "small" ]; then
    echo ""
    echo "🚀 Running SMALL DATASET TEST (4 samples, 2 epochs)..."
    echo ""
    python scripts/train_surf_llama.py \
        --datasets brazilian_history_dataset marvel_lore_dataset \
        --model-name unsloth/gemma-4-E4B-it \
        --batch-size 2 \
        --num-train-epochs 1 \
        --small-dataset \
        --output-dir ./exports/training_test \
        --run-name test_run_$(date +%s) \
        --train-sample-limit 4

elif [ "$MODE" = "full" ]; then
    echo ""
    echo "🚀 Running FULL TRAINING (200 samples, 3 epochs)..."
    echo ""
    python scripts/train_surf_llama.py \
        --datasets brazilian_history_dataset marvel_lore_dataset jazz_history_dataset \
        --model-name unsloth/gemma-4-E4B-it \
        --batch-size 2 \
        --num-train-epochs 3 \
        --output-dir ./exports/full_training_$(date +%Y%m%d_%H%M%S) \
        --run-name full_run_$(date +%s) \
        --save-gguf q4_k_m

elif [ "$MODE" = "eval" ]; then
    echo ""
    echo "📊 Running EVALUATION ONLY..."
    echo ""
    python scripts/train_surf_llama.py \
        --datasets brazilian_history_dataset \
        --eval-only \
        --output-dir ./exports/eval_results \
        --resume-from ./exports/training_test/checkpoints/checkpoint-1

elif [ "$MODE" = "help" ]; then
    echo "Usage: ./training_quickstart.sh [mode]"
    echo ""
    echo "Modes:"
    echo "  small (default)  - Quick test with 4 samples, 2 epochs"
    echo "  full             - Full training with 3 epochs"
    echo "  eval             - Evaluation mode only"
    echo "  help             - Show this message"
    echo ""
    echo "Examples:"
    echo "  ./training_quickstart.sh small"
    echo "  ./training_quickstart.sh full"
    echo "  ./training_quickstart.sh eval"

else
    echo "❌ Unknown mode: $MODE"
    echo "Use './training_quickstart.sh help' for usage"
    exit 1
fi

echo ""
echo "✅ Training complete!"
echo "📂 Results saved to exports/"
