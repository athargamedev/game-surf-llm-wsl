# Dialogue Testing and Tracking Workflow Review

Last updated: 2026-05-01

Scope: runtime dialogue path, `/test-10-player`, `track_workflow_run.py`, Supabase memory persistence, and the evidence loop needed before tuning datasets and training parameters.

## Executive Summary

The current workflow can generate data, train adapters, run live dialogue, and persist Supabase memory. The weakest part is measurement: several tools still prove that requests completed, but not that the NPC gave a high-quality answer, used memory correctly, or improved after a dataset/training change.

Before tuning LoRA hyperparameters or scaling datasets, improve the evaluation layer so every experiment captures:

- response quality
- factual grounding
- persona consistency
- memory creation
- memory retrieval
- memory use in the answer
- regression against previous runs

## Current Dataflow

```text
NotebookLM sources
-> JSONL dataset batches
-> import/prepare gates
-> WSL Unsloth LoRA training
-> adapter manifest/export
-> runtime /reload-model
-> /session/start
-> /chat
-> dialogue_turns insert
-> /session/end
-> dialogue_sessions trigger
-> npc_memories insert
-> Phase 2 /session/start loads memory
-> Phase 2 /chat should use memory
-> /test-10-player and workflow traces record evidence
```

## Findings

### High: `track_workflow_run.py` memory proof is weaker than `/test-10-player`

`scripts/track_workflow_run.py` currently performs only one session: `/session/start` -> `/chat` -> `/session/end` -> history/memories. It does not start a second session to prove recall behavior.

Evidence:
- [track_workflow_run.py](/root/Game_Surf/Tools/LLM_WSL/scripts/track_workflow_run.py:281) starts a single memory probe.
- [track_workflow_run.py](/root/Game_Surf/Tools/LLM_WSL/scripts/track_workflow_run.py:383) marks memory pass from start/end success.
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:3188) exposes `memory_used_in_response`, but the tracker does not consume it.

Impact: a model can pass workflow trace memory checks while still ignoring memory during recall questions.

Recommended fix: add a `--cross-session-memory` mode to `track_workflow_run.py` that mirrors `/test-10-player`: Phase 1 create memory, Phase 2 load memory, ask recall, compute `memory_used_in_response`, and write those fields to `supabase_memory_check.json`.

### High: persistent `test_results` omits the new memory-use fields

The browser status now exposes `memory_used_in_response` and `memory_response_reason`, but `_log_test_result()` does not insert those fields, and the `test_results` table does not have columns for them.

Evidence:
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:2735) inserts `test_results`.
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:3188) returns `memory_used_in_response` only in live status.
- Live table columns currently stop at `duration_seconds` and `created_at`.

Impact: after a restart, the most important memory behavior metric is lost.

Recommended fix: migrate `test_results` with `memory_used_in_response boolean`, `memory_response_reason text`, `run_id text`, `session_id uuid`, `turn_count int`, and short response/message previews.

### High: recall/meta sessions become normal memories and can pollute future context

Ending every session triggers `summarize_dialogue_session()`, including Phase 2 recall sessions. If the NPC says “I don’t recall,” that denial becomes a future memory row.

Evidence:
- Supabase trigger `trg_summarize_ended_dialogue_session` summarizes ended sessions.
- `npc_memories` now contains rows like “Player: Do you remember... NPC: I don't recall...”.
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:809) can detect recall questions, but the DB summary path does not classify them.

Impact: memory context becomes self-referential and may teach future sessions to repeat failed recall behavior.

Recommended fix: add memory classification at write time. Store recall/meta sessions as `raw_json.memory_kind='recall_check'` or skip them from `npc_memories` by default. Keep factual teaching/learning sessions as `memory_kind='learning'`. Retrieval should prioritize learning memories over recall-check memories.

### High: stale active sessions and old zero-turn-count rows distort diagnostics

The live database contained 29 active sessions and 31 ended sessions with `turn_count=0`. Some ended rows had real turns but stale cached `turn_count`.

Evidence:
- Live query showed `active_sessions=29`.
- Live query showed older ended sessions with `actual_turns > 0` and `turn_count=0`.
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:684) now refreshes `turn_count` for Python writes, but older data remains.

Impact: memory/debug reports are noisy, and active sessions can be closed implicitly later in surprising ways.

Recommended fix: add a maintenance command such as `scripts/repair_memory_state.py` that can dry-run and repair stale `turn_count`, end/delete stale active sessions, and report orphaned turns/memories.

### Medium: memory-use scoring is heuristic and can false pass

`response_uses_memory()` currently checks denial phrases and keyword overlap. This catches obvious failures, but it can pass if the response shares generic terms like “Jupiter” without actually using the stored detail.

Evidence:
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:809) computes memory use with keyword overlap.

Impact: useful as a gate, but not sufficient for optimizing final response quality.

Recommended fix: add structured recall probes with expected memory facts. Example: Phase 1 message says “I like Jupiter’s Great Red Spot.” Phase 2 asks “What detail did I ask you about last time?” Expected terms: `Jupiter`, `Great Red Spot`. Score exact entity overlap, not broad keyword overlap.

### Medium: runtime reports do not connect answer quality to dataset/training versions

Training traces record eval loss and dataset split counts, but runtime answer quality is not stored in the same comparable run artifact.

Evidence:
- [track_workflow_run.py](/root/Game_Surf/Tools/LLM_WSL/scripts/track_workflow_run.py:355) records best eval loss.
- [training_metrics.py](/root/Game_Surf/Tools/LLM_WSL/scripts/training_metrics.py:41) focuses on train/eval loss.
- `/test-10-player` results live in process memory and partial DB rows, not in `reports/workflow_runs/<npc>/<run_id>/`.

Impact: after changing a dataset or LoRA parameter, we cannot reliably compare response quality, memory behavior, and training loss in one place.

Recommended fix: create a unified experiment report that includes dataset hash, import report, train config, eval loss, runtime probe answers, memory pass rates, and selected bad examples.

### Medium: identity probes are brittle for educational NPCs

Identity verification relies on expected text fragments. Educational NPCs can answer correctly without saying their name or a known pattern.

Evidence:
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:2443) defines probe messages.
- [llm_integrated_server.py](/root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py:2456) defines expected name patterns.

Impact: identity failures can be false negatives and distract from answer quality.

Recommended fix: split identity checks into two scores: adapter routing proof from `/debug/lora-status/{npc_id}` and content-domain proof from a rubric-based question.

### Medium: response-quality metrics are not yet tied to target behavior

The project has `quality_judge.py` and `evaluate_model.py`, but the operational test focuses on memory mechanics rather than response quality.

Impact: dataset/training tuning can overfit eval loss while producing weak explanations, poor recall, or bland persona.

Recommended fix: define a small fixed benchmark per NPC:

- 5 factual teaching prompts
- 5 quiz/check-understanding prompts
- 5 memory recall prompts
- 3 out-of-domain/refusal prompts
- 2 multi-turn follow-up prompts

Score each answer for factuality, concision, instruction following, persona, memory use, and leakage.

## Recommended Improvement Roadmap

### Phase 1: Measurement Reliability

1. Add cross-session recall proof to `track_workflow_run.py`.
2. Persist `memory_used_in_response`, `memory_response_reason`, `run_id`, session id, and response previews in `test_results`.
3. Add DB maintenance diagnostics for stale active sessions, zero `turn_count`, orphaned turns, and recall-denial memories.
4. Add a stable test-run export file under `reports/workflow_runs/<npc>/<run_id>/automated_memory_test.json`.

### Phase 2: Memory Quality

1. Classify memory rows by kind: `learning`, `recall_check`, `preference`, `profile`, `failed_recall`.
2. Retrieval should prefer `learning`, `preference`, and `profile`, and avoid injecting `failed_recall` unless debugging.
3. Add structured memory probes with expected terms instead of generic “Do you remember?” only.
4. Track memory precision: loaded relevant memory / all loaded memories.

### Phase 3: Response Quality Benchmarks

1. Add per-NPC benchmark files under `benchmarks/npc_dialogue/<npc_id>.json`.
2. Run benchmarks after each dataset/training iteration.
3. Store raw answers and scores with the training run.
4. Require no regression on memory behavior before accepting lower eval loss as an improvement.

### Phase 4: Dataset and Training Tuning Loop

Only after Phases 1-3:

1. Tune dataset composition first: more recall-aware examples, more source-grounded teaching examples, fewer generic persona lines.
2. Tune LoRA parameters second: epochs, LR, LoRA rank, target modules, max steps.
3. Compare against a fixed baseline using the same benchmark and test player setup.
4. Promote a model only if response quality and memory behavior improve together.

## Immediate Next Tasks

1. Done: `track_workflow_run.py --stage memory --cross-session-memory`.
2. Done: `supabase/migrations/20260501000000_dialogue_tracking_improvements.sql` adds durable `test_results` memory-use fields.
3. Done: `scripts/repair_memory_state.py` dry-runs by default and can apply non-destructive metadata repairs.
4. Done: `benchmarks/npc_dialogue/solar_system_instructor.json` covers factual, redirect, and cross-session recall checks.
5. Done: `scripts/run_dialogue_benchmark.py` writes fixed benchmark reports under `reports/dialogue_benchmarks/<npc>/<run_id>/`.

## Implemented Controls

- Workflow trace memory stage can now prove memory creation, memory load on a new session, and memory use in the recall answer.
- Browser automation persists richer test rows and writes JSON report artifacts per run.
- Memory summarization labels recall-probe summaries separately from durable session summaries.
- Runtime memory injection skips `recall_probe` and `empty_session` memories.
- Supabase diagnostics can identify stale active sessions, stale `turn_count`, orphaned memory rows, and untagged recall probes before training comparisons.
