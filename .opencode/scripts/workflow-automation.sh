#!/bin/bash
# NPC Training Workflow Automation CLI
# Usage: ./workflow-automation.sh [command] [npc_id] [options]
#
# Commands:
#   run <npc_id>      - Run full 5-phase pipeline
#   gen <npc_id>      - Phase 1: Generate dataset
#   prep <npc_id>    - Phase 2: Prepare dataset
#   train <npc_id>   - Phase 3: Train model
#   export <npc_id>  - Phase 4: Export to GGUF
#   eval <npc_id>    - Phase 5: Evaluate model
#   status <npc_id>  - Check pipeline status
#   list             - List available NPCs
#   help             - Show this help

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
while [ "$(basename "$ROOT_DIR")" != "LLM_WSL" ] && [ "$ROOT_DIR" != "/" ]; do
    ROOT_DIR="$(dirname "$ROOT_DIR")"
done
RESEARCH_DIR="$ROOT_DIR/research"
DATASETS_DIR="$ROOT_DIR/datasets/processed"
EXPORTS_DIR="$ROOT_DIR/exports/npc_models"

# Functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
NPC Training Workflow Automation CLI

Usage: $0 [command] [npc_id] [options]

Commands:
    run <npc_id>       Run full 5-phase pipeline
    gen <npc_id>       Phase 1: Generate dataset
    prep <npc_id>     Phase 2: Prepare dataset  
    train <npc_id>    Phase 3: Train model
    export <npc_id>   Phase 4: Export to GGUF
    eval <npc_id>     Phase 5: Evaluate model
    status <npc_id>   Check pipeline status
    list              List available NPCs
    help              Show this help

Options:
    --target-count N  Number of examples (default: 150)
    --epochs N         Training epochs (default: 2)
    --skip-generation Skip generation phase
    --skip-prep       Skip preparation phase
    --skip-training   Skip training phase
    --skip-sync       Skip Unity sync
    --skip-eval       Skip evaluation
    --resume          Resume from checkpoint

Examples:
    $0 run greek_mythology_instructor
    $0 run movies_instructor --target-count 200
    $0 train jazz_history_instructor --resume
    $0 list

EOF
}

list_npcs() {
    echo "Available NPCs:"
    echo "=============="
    for dir in "$RESEARCH_DIR"/*; do
        if [ -d "$dir" ]; then
            npc_id=$(basename "$dir")
            dataset_file="$DATASETS_DIR/$npc_id/train.jsonl"
            model_dir="$EXPORTS_DIR/$npc_id"
            
            # Check status
            status="❌ No data"
            if [ -f "$dataset_file" ]; then
                count=$(wc -l < "$dataset_file")
                if [ -d "$model_dir/checkpoints" ]; then
                    checkpoints=$(ls -d "$model_dir/checkpoints"/checkpoint-* 2>/dev/null | wc -l)
                    if [ "$checkpoints" -gt 0 ]; then
                        status="✅ Trained ($checkpoints checkpoints)"
                    else
                        status="🟨 Dataset ready ($count examples)"
                    fi
                else
                    status="🟨 Dataset ready ($count examples)"
                fi
            fi
            
            printf "  %-35s %s\n" "$npc_id" "$status"
        fi
    done
}

check_status() {
    local npc_id="$1"
    log_info "Checking status for: $npc_id"
    echo
    
    # Research
    if [ -d "$RESEARCH_DIR/$npc_id" ]; then
        log_info "Research sources:"
        ls -1 "$RESEARCH_DIR/$npc_id"/*.txt "$RESEARCH_DIR/$npc_id"/*.md 2>/dev/null | while read f; do
            echo "  - $(basename "$f")"
        done
    else
        log_error "No research directory found"
        return 1
    fi
    echo
    
    # Dataset
    local dataset_file="$DATASETS_DIR/$npc_id/train.jsonl"
    if [ -f "$dataset_file" ]; then
        local count=$(wc -l < "$dataset_file")
        log_success "Prepared dataset: $count examples"
    else
        log_warn "No prepared dataset"
    fi
    echo
    
    # Model
    local model_dir="$EXPORTS_DIR/$npc_id"
    if [ -d "$model_dir/checkpoints" ]; then
        log_success "Checkpoints:"
        ls -d "$model_dir/checkpoints"/checkpoint-* 2>/dev/null | while read ckpt; do
            echo "  - $(basename "$ckpt")"
        done
    else
        log_warn "No trained checkpoints"
    fi
    
    # GGUF
    if [ -f "$model_dir/gguf/adapter_model.gguf" ]; then
        local size=$(du -h "$model_dir/gguf/adapter_model.gguf" | cut -f1)
        log_success "GGUF export: $size"
    else
        log_warn "No GGUF export"
    fi
    
    # Manifest
    if [ -f "$model_dir/npc_model_manifest.json" ]; then
        log_success "Model manifest exists"
    fi
}

run_phase() {
    local phase="$1"
    local npc_id="$2"
    shift 2
    local options="$@"
    
    log_info "Running phase: $phase for $npc_id"
    
    case "$phase" in
        run)
            python scripts/run_full_npc_pipeline.py --npc "$npc_id" --skip-generation $options
            ;;
        gen)
            conda run --no-capture-output -n unsloth_env python .codex/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py --npc "$npc_id" $options
            ;;
        prep)
            python scripts/prepare_dataset.py --input "$RESEARCH_DIR/$npc_id"/raw.jsonl --output "$DATASETS_DIR/$npc_id"/ $options
            ;;
        train)
            python scripts/train_surf_llama.py --datasets "npc_${npc_id}_dataset" --train-file "$DATASETS_DIR/$npc_id/train.jsonl" $options
            ;;
        export)
            python scripts/convert_lora_to_gguf.py --checkpoint "$EXPORTS_DIR/$npc_id/checkpoints/checkpoint-12" --output "$EXPORTS_DIR/$npc_id/gguf/" $options
            ;;
        eval)
            python scripts/quality_judge.py --input "$RESEARCH_DIR/$npc_id"/raw.jsonl --npc "$npc_id" --report $options
            ;;
        status)
            check_status "$npc_id"
            ;;
        list)
            list_npcs
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            log_error "Unknown command: $phase"
            show_help
            return 1
            ;;
    esac
}

# Main
COMMAND="${1:-help}"
NPC_ID="$2"
OPTIONS="${3:-}"

if [ "$COMMAND" == "help" ] || [ "$COMMAND" == "--help" ] || [ "$COMMAND" == "-h" ]; then
    show_help
    exit 0
fi

if [ "$COMMAND" == "list" ]; then
    list_npcs
    exit 0
fi

if [ -z "$NPC_ID" ]; then
    log_error "NPC ID is required"
    show_help
    exit 1
fi

run_phase "$COMMAND" "$NPC_ID" $OPTIONS
