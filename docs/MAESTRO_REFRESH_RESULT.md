# Maestro Refresh Result

## Outcome

The `maestro_jazz_instructor` dataset refresh and candidate retrain completed successfully.

## Dataset Changes

- Baseline raw dataset: `50` examples
- Refreshed raw dataset: `111` examples
- Source batches imported: `4`
- Import average quality: `0.899`
- Import rejects: `3`
- Duplicate assistant responses removed during import: `2`

## Prepared Dataset

- Train split: `100`
- Validation split: `11`
- Task distribution: `teaching=81`, `quiz=30`
- Memory slot coverage: `1.0`
- Unique user prompts: `111`
- Unique assistant responses: `111`

## Model Comparison

- Baseline model dir: `exports/npc_models/maestro_jazz_instructor`
- Candidate model dir: `exports/npc_models/maestro_jazz_instructor`
- Baseline eval loss: `2.2922`
- Candidate eval loss at step 25: `2.0331`
- Candidate eval loss at step 50: `2.1082`

## Notes

- The candidate improved over the baseline eval loss.
- The candidate required training at `--max-seq-length 1024` on this RTX 3060 6GB setup.
- The refresh also exposed and fixed several pipeline issues in `train_surf_llama.py`:
  - trainer precision mismatch for float16-loaded models
  - incompatible `device_map='auto'` training path
  - stale 4-bit loader kwargs for the installed Unsloth/Transformers versions
  - over-aggressive float16 loading on low free VRAM
- The refreshed dataset still shows repeated opening phrasing, especially `that would be`, so the next iteration should target prompt diversity rather than raw count.

## Artifacts

- Candidate manifest: `exports/npc_models/maestro_jazz_instructor/npc_model_manifest.json`
- Candidate training report: `exports/npc_models/maestro_jazz_instructor/checkpoints/training_report.json`
- Candidate adapter: `exports/npc_models/maestro_jazz_instructor/lora_adapter/adapter_model.safetensors`
- Candidate GGUF adapter: `exports/npc_models/maestro_jazz_instructor/lora_adapter/adapter_model.gguf`
- Candidate dataset audit: `docs/maestro_candidate_audit.md`

## A/B Evaluation Outcome

- Evaluation sheet: `docs/maestro_ab_eval.md`
- Overall winner: candidate
- Scenario wins:
  - Candidate: 3
  - Baseline: 2
  - Tie: 1

## Promotion State

- The candidate has been promoted for runtime Maestro selection.
- Active Maestro adapter path now resolves to:
  - `exports/npc_models/maestro_jazz_instructor/lora_adapter/adapter_model.gguf`
- The old baseline artifacts were moved to a legacy rollback directory:
  - `exports/npc_models/maestro_jazz_instructor_legacy_baseline_20260422`
- The old baseline artifacts remain on disk and are also preserved in backup.
