# Project Context Intelligence

Last updated: 2026-05-01 (updated with workflow improvements)

This file records durable workflow lessons for Game_Surf NPC dataset generation, WSL Unsloth training, runtime validation, and Supabase memory testing.

## Canonical Workflow

- **Single Entry Point:** Use `./run_pipeline.sh --npc <npc_id>` or `python scripts/run_full_npc_pipeline.py --npc <npc_id>` for ALL pipeline runs.
- **NotebookLM CLI is `notebooklm`, not `nlm`** (verified: `which notebooklm` works, `nlm` does NOT exist).
- New NPCs should use NotebookLM-backed source slices, then import/prepare, then WSL-native Unsloth LoRA training.
- Runtime validation uses the shared base GGUF plus per-NPC LoRA adapters.
- Use `npc_id` for `/chat`, `/reload-model`, `/session/start`, `/session/end`, and memory/debug endpoints.
- Add every trained NPC to both `chat_interface.html` and `/test-10-player` before considering it ready for user testing.
- Use `docs/GAMESURF_WORKFLOW_SKILL_GRAPH.mmd` as the visual agent handoff map; it connects skills, workflow stages, validation gates, fallback paths, reports, and the dataset/prompt/memory/training feedback loop.

## Workflow Improvements (2026-05-01)

### Critical Fixes Applied
1. **CLI Command Standardization:** All scripts now use `notebooklm` (not `nlm`). Files fixed: `setup_dataset_pipeline.py`, `generate_npc_dataset.py`.
2. **Import Path Fix:** `npc_pipeline_contract.py` now imports correctly by adding `scripts/` to `sys.path` in `run_full_npc_pipeline.py` and `train_surf_llama.py`.
3. **Function Consistency:** Renamed `_run_nlm_command` → `_run_notebooklm_command` in `generate_npc_dataset.py`.

### High-Priority Cleanup Completed
1. **Legacy LM Studio Removal:** Removed `check_legacy_local_llm()` from `setup_dataset_pipeline.py`. Hidden `--llm-url` and `--llm-model` args (SUPPRESS) in pipeline scripts.
2. **Path Standardization:** Updated all `.codex/skills/` references to `.opencode/skills/` in 5 doc files (NOTEBOOKLM_DATASET_WORKFLOW.md, PIPELINE_REFERENCE.md, NPC_TRAINING_WORKFLOW.md, gamesurf-agent SKILL.md, MAESTRO_DATASET_ROLLOUT_PLAN.md).
3. **Directory Structure Fix:** Fixed `REQUIRED_DIRS` in `setup_dataset_pipeline.py` (`datasets/world` → `benchmarks`, `datasets/evals` → `benchmarks`).
4. **Backend Cleanup:** Removed `local` from backend choices in `generate_npc_dataset.py` and `run_full_npc_pipeline.py`.

### Consolidation Improvements
1. **Single Entry Point:** `run_full_npc_pipeline.py` is now the canonical entry point. Updated NPC_TRAINING_WORKFLOW.md to reference `./run_pipeline.sh` instead of direct script calls.
2. **VRAM Pre-flight:** Consolidated `check_vram_guard()` into `run_full_npc_pipeline.py` (lines 19-44). Individual scripts no longer need separate VRAM checks at startup.
3. **NPC ID Standardization:** Updated docs with all 10 NPCs. Note: `kosmos_instructor` (NPC key) → `greek_mythology_instructor` (artifact_key) is INTENTIONAL (artifact_key matches Supabase ID).

### Efficiency Gains
- **Dead Code Removed:** Legacy LM Studio support completely removed from setup script.
- **Consolidated Checks:** VRAM check happens once in orchestrator, not duplicated across scripts.
- **Clear Path Resolution:** `npc_pipeline_contract.py` resolves all paths from NPC profiles (never hardcode paths).

## NotebookLM Dataset Lessons

- Smaller 10-example NotebookLM asks are more reliable than broad 50-example asks when the CLI or notebook response stalls.
- Prompts should require strict JSONL only, no wrapper JSON, no citations, and no explanatory text.
- Every system prompt must preserve the literal slot:

```text
[MEMORY_CONTEXT: {player_memory_summary}]
```

- Source slices should be concrete and narrow. For `solar_system_instructor`, the reliable slices were structure, small bodies, planets, dwarf planets/distant regions, and scale/motion.
- Import only validated batches. Do not blindly glob old or failed batches if a previous NotebookLM response produced wrapper JSON or empty answers.

## Training Runtime Lessons

- Train inside this WSL instance with `unsloth_env`; do not route training through LM Studio.
- If Triton cannot find the conda compiler, set `CC` and `CXX` inside the `conda run ... bash -lc` command, not only in the parent shell.
- Start browser-visible servers outside the Codex sandbox when the user needs to test in their browser:

```bash
bash scripts/start_servers.sh
```

- After code changes to `scripts/llm_integrated_server.py`, restart the backend before validating `/test-10-player`.

## `/test-10-player` Memory Test Lessons

- Cross-session mode validates per-player/per-NPC persistence:
  - Phase 1 starts a session, sends message 1, ends the session, and waits for memory.
  - Phase 2 starts a new session with the same `player_id` and `npc_id`, sends message 2, and checks whether memory loaded.
- A test pass must prove both:
  - memory exists and loaded at session start
  - the NPC answer actually used that memory
- `memory_loaded_on_start=true` alone is not enough. The model can still deny recall even when Supabase returned a valid memory row.
- The test now reports `memory_used_in_response` and `memory_response_reason` so ignored memory is visible.
- Test player IDs must include a unique run id. Reusing `TestPlayer_<npc>_001` can load old memory from previous runs and contaminate results.
- Keep slower pacing for LoRA swaps and memory processing:
  - message delay: 5s
  - identity probe delay: 4s
  - player delay: 4s
  - NPC switch delay: 8s
  - phase memory delay: 35s

## Dialogue Workflow Review Priorities

- Do not tune datasets or LoRA parameters against eval loss alone. First make sure runtime tracking captures answer quality and memory behavior.
- `track_workflow_run.py --stage memory --cross-session-memory` mirrors `/test-10-player` with Phase 1 memory creation and Phase 2 recall proof.
- `test_results` now has migration support for `memory_used_in_response`, `memory_response_reason`, `run_id`, session id, turn count, and response/message previews.
- `/test-10-player` writes durable reports to `reports/workflow_runs/test-10-player/<run_id>/automated_memory_test.json` and per-NPC report folders.
- Recall/meta sessions are classified with `raw_json.memory_kind='recall_probe'` and skipped by runtime memory injection so they do not crowd out learning memories.
- Use `scripts/repair_memory_state.py --json` for dry-run diagnostics on stale active sessions, stale `turn_count`, orphaned memory rows, and untagged recall-probe memories.
- Build and run fixed per-NPC dialogue benchmarks before training-parameter tuning. Benchmarks should cover factual teaching, quiz, memory recall, refusal, and multi-turn follow-up prompts.
- First benchmark: `benchmarks/npc_dialogue/solar_system_instructor.json`; run with `python scripts/run_dialogue_benchmark.py --npc solar_system_instructor`.

## Supabase Memory Contract

- Browser/test flow:
  - `POST /session/start` with `player_id`, `player_name`, `npc_id`
  - `POST /chat` with `player_id`, `npc_id`, `message`, `session_id`
  - `POST /session/end` with `session_id`, `player_id`, `npc_id`
- Core tables:
  - `player_profiles(player_id, display_name)`
  - `dialogue_sessions(session_id, player_id, npc_id, status, started_at, ended_at, raw_json, turn_count)`
  - `dialogue_turns(turn_id, session_id, player_message, npc_response, raw_json, created_at)`
  - `npc_memories(memory_id, player_id, npc_id, summary, created_at, raw_json)`
- Python `/chat` writes `dialogue_turns`; keep `dialogue_sessions.turn_count` synchronized for diagnostics and Edge-function parity.
- Memory summarization is triggered by ending a dialogue session. Do not add a second direct summarizer unless duplicate `npc_memories` has been ruled out.

## Local Supabase Customization

- Use `LLM_WSL/supabase` as the source of truth for Game_Surf schema, Edge Functions, memory migrations, and local runtime config.
- Use the Supabase CLI fork at `/mnt/d/GithubRepos/supabasecli` only for local stack orchestration improvements such as image pins, custom Studio image support, and extra Studio env wiring.
- The current documented Studio AI config only exposes `studio.openai_api_key`; local research found no built-in `openai_base_url` or model override in the CLI fork.
- Redirecting the Supabase Studio integrated assistant to LM Studio requires a Studio image/provider patch or a local OpenAI-compatible proxy. A CLI-only patch can pass env vars, but it cannot change assistant behavior if the Studio image ignores them.
- LM Studio is reachable from WSL/Docker at `http://host.docker.internal:1234/v1`; use that instead of `127.0.0.1:1234` for Dockerized Supabase services.
- Preferred local Studio assistant defaults:
  - `OPENAI_API_KEY=lm-studio`
  - `STUDIO_OPENAI_BASE_URL=http://host.docker.internal:1234/v1`
  - `STUDIO_OPENAI_MODEL=qwen2.5-coder-7b-instruct`
  - `STUDIO_OPENAI_ADVANCED_MODEL=qwen3-8b`
- Game_Surf local `supabase/config.toml` can declare these values directly plus `custom_image = "localhost/gamesurf/supabase-studio:lmstudio-local"`; keep optional Studio AI fields out of the upstream CLI default template unless golden diff fixtures are updated.
- Current local integration uses `/mnt/d/GithubRepos/supabasecli/bin/supabase-lmstudio` and `scripts/start_supabase_lmstudio.sh`; start with `-x storage-api,imgproxy,supavisor`, not `pooler`, on the latest CLI fork.
- Verified integration means the Studio SQL assistant route returns `200 OK` through LM Studio. Structured-output routes still need local-model prompt/model tuning because they can fail with unparseable object responses.
- Full research and implementation path: `docs/LOCAL_SUPABASE_CUSTOMIZATION_RESEARCH.md`.

## Solar System Run Snapshot

- NPC: `solar_system_instructor`
- Display: `Professor Sol`
- NotebookLM notebook: `Solar_System_Instructor`
- Imported examples after repair batches: 78
- Prepared split after repair batches: 71 train / 7 validation
- Current repair training: 24 steps, eval loss 1.7759336233139038, no overfitting flag
- Adapter: `exports/npc_models/solar_system_instructor/lora_adapter/adapter_model.gguf`
- Final dialogue benchmark: `reports/dialogue_benchmarks/solar_system_instructor/20260501_075829/summary.md` passed 5/5.
- Final cross-session workflow trace: `reports/workflow_runs/solar_system_instructor/20260501_075926/summary.md` passed memory gate with `memory_loaded_on_start=true` and `memory_used_in_response=true`.
- The winning changes were:
  - add targeted redirect and memory-continuation examples;
  - add factual repair examples for rocky inner planets and hot inner Solar System formation;
  - include subject boundary, refusal style, and memory-continuation rule in the runtime system prompt.
