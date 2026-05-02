#!/usr/bin/env bash
# ============================================================
# run_big_workflow.sh — GameSurf NPC Kit Full Pipeline Run
#
# Reuses imported NotebookLM datasets, trains all LoRA adapters,
# exports GGUFs, runs quality benchmarks, and summarises results.
#
# Usage:
#   ./run_big_workflow.sh                  # retrain all NPCs from prepared NotebookLM data
#   ./run_big_workflow.sh --skip-train     # validation / non-training pass
#   ./run_big_workflow.sh --allow-legacy-generation  # opt in to old local generator
#   ./run_big_workflow.sh --npc supabase_instructor  # single NPC
# ============================================================
set -euo pipefail
export PYTHONUNBUFFERED=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/npc_big_run.log"
START_TIME=$(date +%s)

# ── Colour helpers ────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${RESET} $*" | tee -a "$LOG_FILE"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✅ $*${RESET}" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] ⚠  $*${RESET}" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ❌ $*${RESET}" | tee -a "$LOG_FILE"; }

# ── Args ─────────────────────────────────────────────────────
SKIP_GEN=true
SKIP_TRAIN=false
ALLOW_LEGACY_GENERATION=false
SINGLE_NPC=""
TARGET_COUNT=300
EPOCHS=3

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-gen)    SKIP_GEN=true ;;
        --allow-legacy-generation) ALLOW_LEGACY_GENERATION=true ;;
        --skip-train)  SKIP_TRAIN=true ;;
        --npc)         SINGLE_NPC="$2"; shift ;;
        --count)       TARGET_COUNT="$2"; shift ;;
        --epochs)      EPOCHS="$2"; shift ;;
        *) warn "Unknown arg: $1" ;;
    esac
    shift
done

# ── NPC Execution Order ───────────────────────────────────────
# Ordered: fastest/most-research-first to prevent NotebookLM fatigue
ALL_NPCS=(
    "ai_news_instructor"
    "brazilian_history_instructor"
    "cosmos_instructor"
    "llm_instructor"
    "maestro_jazz_instructor"
    "marvel_comics_instructor"
    "movies_instructor"
    "solar_system_instructor"
    "supabase_instructor"
)

if [[ -n "$SINGLE_NPC" ]]; then
    NPCS=("$SINGLE_NPC")
else
    NPCS=("${ALL_NPCS[@]}")
fi

# ── Tracking ──────────────────────────────────────────────────
declare -A RESULTS  # npc_key -> "gen_ok:train_ok:eval_ok"
FAILED_NPCS=()

# ── Pre-flight checks ─────────────────────────────────────────
log "============================================================"
log "  GameSurf NPC Kit — Big Workflow Run"
log "  NPCs: ${#NPCS[@]} | Count: ${TARGET_COUNT} | Epochs: ${EPOCHS}"
log "  Dataset mode: $( $ALLOW_LEGACY_GENERATION && printf 'legacy local generation enabled' || printf 'NotebookLM-imported datasets only' )"
log "  Log: ${LOG_FILE}"
log "============================================================"

log "Pre-flight: checking VRAM..."
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits 2>/dev/null \
    | awk -F',' '{printf "  GPU VRAM used: %s MB | free: %s MB\n", $1, $2}' | tee -a "$LOG_FILE" \
    || warn "nvidia-smi not available"

log "Pre-flight: checking LMStudio (should be OFF during training)..."
if curl -s --max-time 2 "http://192.168.0.3:1234/v1/models" > /dev/null 2>&1; then
    warn "LMStudio is running. Close it before training if VRAM is tight."
else
    warn "LMStudio not responding. That is fine for NotebookLM-imported dataset training."
fi
echo "" | tee -a "$LOG_FILE"

# ── Phase 1 + 2: Train per NPC from prepared datasets ─────────
for NPC in "${NPCS[@]}"; do
    NPC_START=$(date +%s)
    GEN_OK=false
    TRAIN_OK=false
    EVAL_OK=false

    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "  NPC: ${BOLD}${NPC}${RESET}"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    PIPELINE_ARGS=(
        "--npc" "$NPC"
        "--target-count" "$TARGET_COUNT"
        "--epochs" "$EPOCHS"
        "--lora-r" "16"
        "--lora-alpha" "32"
        "--save-gguf" "q4_k_m"
        "--generation-backend" "auto"
        "--generation-batch-size" "5"
        "--batch-size" "1"
        "--grad-accum" "8"
        "--quality-threshold" "0.75"
        "--val-split" "0.10"
    )

    if $SKIP_GEN; then
        PIPELINE_ARGS+=("--skip-generation")
    fi
    if $ALLOW_LEGACY_GENERATION; then
        PIPELINE_ARGS+=("--allow-legacy-generation")
    fi
    if $SKIP_TRAIN; then
        PIPELINE_ARGS+=("--skip-training" "--skip-sync")
    fi

    if python scripts/run_full_npc_pipeline.py "${PIPELINE_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"; then
        GEN_OK=true
        TRAIN_OK=true
        EVAL_OK=true
        NPC_END=$(date +%s)
        NPC_ELAPSED=$(( (NPC_END - NPC_START) / 60 ))
        ok "Completed ${NPC} in ${NPC_ELAPSED}m"
    else
        err "Pipeline FAILED for ${NPC}"
        FAILED_NPCS+=("$NPC")
    fi

    RESULTS["$NPC"]="${GEN_OK}:${TRAIN_OK}:${EVAL_OK}"

    # Cool-down between NPCs to let VRAM and NotebookLM recover
    if [[ "${NPC}" != "${NPCS[-1]}" ]]; then
        log "Cooling down 30s before next NPC..."
        sleep 30
    fi
done

# ── Phase 4: Benchmarks via HTTP relay server ─────────────────
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "  Phase 4: Benchmark Evaluations (relay server HTTP API)"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

BENCH_RESULTS="/tmp/npc_bench_results.json"

# Run only benchmarks for the NPCs we just trained
if [[ -n "$SINGLE_NPC" ]]; then
    BENCH_FLAGS=("--npc" "$SINGLE_NPC")
else
    BENCH_FLAGS=("--all")
fi

BENCH_PASS=0
BENCH_FAIL=0
if /usr/bin/python3 scripts/run_benchmarks.py \
    "${BENCH_FLAGS[@]}" \
    --output "$BENCH_RESULTS" 2>&1 | tee -a "$LOG_FILE"; then
    BENCH_PASS=$(grep -c '"status": "PASS"' "$BENCH_RESULTS" 2>/dev/null || echo 0)
    BENCH_FAIL=$(grep -c '"status": "FAIL"' "$BENCH_RESULTS" 2>/dev/null || echo 0)
    ok "Benchmarks done: ${BENCH_PASS} passed, ${BENCH_FAIL} failed"
else
    warn "Benchmarks had failures (relay server may not be running)"
    warn "Re-run manually: python3 scripts/run_benchmarks.py --all --output $BENCH_RESULTS"
fi


# ── Phase 5: Final Summary ────────────────────────────────────
TOTAL_END=$(date +%s)
TOTAL_ELAPSED=$(( (TOTAL_END - START_TIME) / 60 ))

log ""
log "════════════════════════════════════════════════════════════"
log "  BIG RUN COMPLETE — Total time: ${TOTAL_ELAPSED}m"
log "════════════════════════════════════════════════════════════"
log ""
log "NPC Results:"
for NPC in "${NPCS[@]}"; do
    r="${RESULTS[$NPC]:-false:false:false}"
    IFS=':' read -r gen train eval_r <<< "$r"
    status=$( [[ "$train" == "true" ]] && echo "✅" || echo "❌")
    log "  ${status} ${NPC}"
done

log ""
log "Benchmarks: ${BENCH_PASS} passed, ${BENCH_FAIL} failed"
log ""

if [[ ${#FAILED_NPCS[@]} -gt 0 ]]; then
    err "FAILED NPCs (retry with --npc <key> --skip-gen):"
    for f in "${FAILED_NPCS[@]}"; do err "  - $f"; done
    exit 1
else
    ok "All NPCs completed successfully!"
fi

log ""
log "  Quick log analysis commands:"
log "  grep 'Average composite' /tmp/npc_big_run.log   # Quality scores"
log "  grep 'CUDA out of memory' /tmp/npc_big_run.log  # VRAM issues"
log "  grep 'benchmark FAIL' /tmp/npc_big_run.log      # Failed evals"
log "  grep 'Phase' /tmp/npc_big_run.log | head -60   # Timeline"
