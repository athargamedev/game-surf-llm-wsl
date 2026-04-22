# Task Context: Maestro A/B Evaluation

Session ID: 2026-04-22-maestro-ab-eval
Created: 2026-04-22T00:00:00Z
Status: in_progress

## Current Request
Implement the approved Maestro A/B evaluation workflow, compare the baseline Maestro model against the refreshed candidate model, and record the result.

## Context Files (Standards to Follow)
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/core/standards/code-quality.md
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/core/standards/test-coverage.md
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/project-intelligence/code-standards.md
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/project-intelligence/test-workflow.md
- /root/Game_Surf/Tools/LLM_WSL/.opencode/context/project-intelligence/technical-domain.md

## Reference Files (Source Material to Look At)
- /root/Game_Surf/Tools/LLM_WSL/docs/MAESTRO_AB_EVAL_PLAN.md
- /root/Game_Surf/Tools/LLM_WSL/docs/maestro_ab_eval.md
- /root/Game_Surf/Tools/LLM_WSL/docs/MAESTRO_REFRESH_RESULT.md
- /root/Game_Surf/Tools/LLM_WSL/exports/npc_models/maestro_jazz_instructor/checkpoints/training_report.json
- /root/Game_Surf/Tools/LLM_WSL/exports/npc_models/maestro_jazz_instructor_candidate_20260422/checkpoints/training_report.json
- /root/Game_Surf/Tools/LLM_WSL/scripts/llm_integrated_server.py
- /root/Game_Surf/Tools/LLM_WSL/scripts/server_manager.py
- /root/Game_Surf/Tools/LLM_WSL/chat_interface.html

## External Docs Fetched
- None

## Components
- Runtime server startup
- Baseline Maestro evaluation
- Candidate Maestro evaluation
- Result capture and recommendation

## Constraints
- Keep baseline and candidate comparison fair
- Use the same prompts and memory condition for both runs
- Do not promote candidate unless evaluation supports it

## Exit Criteria
- [ ] Runtime servers are confirmed healthy
- [ ] Baseline Maestro responses are captured for all scenarios
- [ ] Candidate Maestro responses are captured for all scenarios
- [ ] Evaluation sheet is filled with results and recommendation
