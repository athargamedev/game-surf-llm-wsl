# Task Context: Project-Wide Naming Convention Review & Standardization

Session ID: 2026-05-02-naming-convention-review
Created: 2026-05-02T00:00:00Z
Status: in_progress

## Current Request
Review all files and folders naming to make sure all paths are consistent and follow our patterns. Clean all previously generated data, fix naming inconsistencies, and regenerate datasets with optimized workflow (200 examples each, respecting NotebookLM timing/limits).

## Context Files (Standards to Follow)
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/core/standards/code-quality.md
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/project-intelligence/code-standards.md

## Reference Files (Source Material to Look At)
- /root/Game_Surf/Tools/LLM_WSL/AGENTS.md (NPC ID conventions: kebab-case + _instructor suffix)
- /root/Game_Surf/Tools/LLM_WSL/datasets/configs/npc_profiles.json
- /root/Game_Surf/Tools/LLM_WSL/datasets/configs/dataset_registry.json
- /root/Game_Surf/Tools/LLM_WSL/scripts/run_full_npc_pipeline.py

## External Docs Fetched
N/A (using internal project standards)

## Components

### Phase 1: Clean Slate - Remove All Generated Data
- Delete contents of datasets/processed/*_dataset/ (keep structure)
- Delete contents of exports/npc_models/<npc_id>/ (except .gitkeep)
- Clear reports/workflow_runs/ and reports/dialogue_benchmarks/
- Remove world_lore/ from research/, datasets/personas/, configs
- Move legacy backups to backups/

### Phase 2: Fix Naming Inconsistencies
**research/ renames:**
- `brazilian_history/` → `brazilian_history_instructor/`
- `kosmos_instructor/` → `cosmos_instructor/` (typo fix)
- Delete `world_lore/`

**datasets/personas/ renames:**
- `jazz_history_instructor/` → `maestro_jazz_instructor/`

**datasets/processed/ renames (remove duplicates):**
- Delete `greek_mythology_dataset/` (keep `greek_mythology_instructor_dataset/`)
- Delete `jazz_history_dataset/` (keep `jazz_history_instructor_dataset/`)
- `marvel_lore_dataset/` → `marvel_comics_instructor_dataset/`
- `brazilian_history_dataset/` → `brazilian_history_instructor_dataset/`
- `solar_system_dataset/` → `solar_system_instructor_dataset/`

**datasets/configs/ updates:**
- Update npc_profiles.json: remove world_lore, fix kosmos→cosmos
- Update dataset_registry.json: same fixes

### Phase 3: Update Script References
- Grep and replace old NPC IDs in all Python scripts
- Update AGENTS.md examples if needed

### Phase 4: Regenerate Datasets
- Generate 200 examples per NPC (8 batches × 25 examples)
- Respect NotebookLM rate limits with delays between calls
- Output to research/<npc_id>/notebooklm_batch_*.jsonl

### Phase 5: Verification
- Test pipeline with --skip-generation --resume for each NPC
- Verify all paths in npc_model_manifest.json files

## Constraints
- NPC IDs must follow: kebab-case + `_instructor` suffix
- Clean all previous generated data before regeneration
- 200 examples per NPC maximum (NotebookLM limits)
- Batch size: 25 examples per NotebookLM call
- Add delays between batches to respect rate limits
- Remove world_lore entirely (dissonant config)
- Move legacy backups to backups/ folder

## Exit Criteria
- [ ] All folders follow kebab-case + _instructor suffix pattern
- [ ] No duplicate dataset folders in datasets/processed/
- [ ] world_lore removed from all configs and directories
- [ ] kosmos_instructor renamed to cosmos_instructor
- [ ] All script references updated (grep confirms no old names)
- [ ] datasets/processed/ contains clean (empty) folders ready for regeneration
- [ ] exports/npc_models/ cleaned (ready for new training)
- [ ] Legacy backups moved to backups/
- [ ] npc_profiles.json and dataset_registry.json updated
- [ ] Pipeline test passes for at least one NPC with --skip-generation --resume
