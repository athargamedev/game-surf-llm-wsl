# Maestro Dataset Rollout Plan

## Goal

Improve `maestro_jazz_instructor` chat quality by rerunning the dataset workflow with stricter import/prep gates, retraining the LoRA, and evaluating the candidate against the current baseline in offline and chat-based comparisons.

## Why Maestro First

- Existing audit shows `jazz_history_dataset` is usable but not especially strong.
- Latest recorded eval loss is `2.2922`, weaker than the best current NPCs.
- The audit also flagged repeated assistant openings: `that would be`.
- The subject is narrow enough to run a controlled regeneration and compare behavior clearly.

## Scope

This rollout covers:

1. Re-importing a new or existing NotebookLM batch for `maestro_jazz_instructor`
2. Re-preparing splits with stricter gates
3. Retraining a candidate LoRA
4. Running offline checks
5. Running chat A/B comparisons against the current Maestro model
6. Deciding whether to adopt the candidate recipe

## Baseline

- NPC key: `maestro_jazz_instructor`
- Artifact key: `jazz_history_instructor`
- Dataset: `jazz_history_dataset`
- Baseline raw count: `50`
- Baseline split count: `train=46`, `validation=4`
- Baseline eval loss: `2.2922`

## Success Criteria

Primary:

- Candidate beats baseline on human preference in chat A/B testing
- Candidate reduces repeated openings and generic phrasing
- Candidate preserves concise in-character teaching style

Secondary:

- Equal or lower eval loss than baseline
- Better quiz behavior and memory-aware follow-ups
- No increase in hallucinated jazz facts or off-character responses

## Risks

- Stricter gates may shrink the dataset too much
- NotebookLM batches may still overproduce teaching examples relative to quiz examples
- Lower eval loss may not translate to better live chat behavior
- Candidate may become cleaner but less vivid if filtering is too aggressive

## Runbook

### Phase 1: Refresh Audit And Baseline Snapshot

Purpose: document baseline before making a candidate.

Commands:

```bash
python scripts/audit_dataset_workflow.py --npc maestro_jazz_instructor --format markdown --output docs/maestro_audit_baseline.md
python scripts/import_notebooklm_jsonl.py \
  --npc maestro_jazz_instructor \
  --input datasets/personas/jazz_history_instructor/jazz_history_dataset.jsonl \
  --dry-run
```

Capture:

- raw count
- task distribution
- average quality from dry-run
- repeated opening patterns from the audit

Decision gate:

- If dry-run average quality is already `>= 0.88` and the only issue is phrasing repetition, prefer regenerating narrower topical batches rather than merely reimporting the same data.

### Phase 2: Generate A Candidate Raw Dataset

Preferred approach: use narrower NotebookLM batches instead of one broad batch.

Recommended batch topics:

1. Early New Orleans jazz and Congo Square
2. Swing to Bebop transition
3. Miles Davis, Parker, Coltrane, Ellington, Armstrong
4. Improvisation, blues scale, and II-V-I
5. Jazz and Civil Rights / cultural significance

Suggested prompt-only command for one batch:

```bash
conda run --no-capture-output -n unsloth_env python \
  .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --subject "early New Orleans jazz, Congo Square, Buddy Bolden, King Oliver, Louis Armstrong" \
  --count 20 \
  --batch-id 1 \
  --write-prompt-only
```

Suggested import-and-prepare command after collecting batch files:

```bash
conda run --no-capture-output -n unsloth_env python \
  .opencode/skills/notebooklm-npc-datasets/scripts/notebooklm_dataset_workflow.py \
  --npc maestro_jazz_instructor \
  --input research/maestro_jazz_instructor/notebooklm_batch_*.jsonl \
  --import \
  --prepare \
  --min-quality 0.78 \
  --min-task-examples 8
```

Target:

- `60-90` valid examples after import filtering
- quiz examples at or above `20%`
- no duplicate user prompts
- no duplicate assistant responses

Decision gate:

- If valid count falls below `45`, relax `--min-quality` to `0.75` before regenerating everything.
- If quiz count falls below `8`, regenerate a quiz-focused topical batch instead of broadening all prompts.

### Phase 3: Candidate Prep Validation

Purpose: verify that the prepared dataset is worth training.

Commands:

```bash
python scripts/audit_dataset_workflow.py --npc maestro_jazz_instructor --format markdown --output docs/maestro_candidate_audit.md
python scripts/import_notebooklm_jsonl.py \
  --npc maestro_jazz_instructor \
  --input datasets/personas/jazz_history_instructor/jazz_history_dataset.jsonl \
  --dry-run
```

Checks:

- average import quality is stable or improved vs baseline
- repeated openings are reduced
- prep metadata shows balanced `teaching` / `quiz` coverage
- memory slot rate remains `1.0`

Decision gate:

- Do not train if the candidate still shows strong opening repetition or task imbalance.

### Phase 4: Train Candidate LoRA

Purpose: train a comparable candidate using the improved dataset.

Suggested training command:

```bash
python scripts/run_full_npc_pipeline.py \
  --npc maestro_jazz_instructor \
  --skip-generation \
  --quality-threshold 0.78 \
  --val-split 0.1 \
  --test-split 0.0 \
  --model-name unsloth/Llama-3.2-3B-Instruct \
  --epochs 2 \
  --batch-size 1 \
  --grad-accum 4 \
  --lora-r 16 \
  --lora-alpha 32 \
  --learning-rate 2e-4 \
  --skip-sync
```

Notes:

- Keep training config close to baseline so dataset differences dominate the result.
- Skip Unity sync until the candidate wins evaluation.

Capture:

- `run_config.json`
- `training_report.json`
- latest eval loss

Decision gate:

- If eval loss is materially worse than baseline, only continue to chat A/B if the offline outputs look clearly better qualitatively.

### Phase 5: Offline Eval Pass

Purpose: compare behavior before spending time on live chat review.

Prompt categories:

1. factual teaching
2. short quiz turn
3. memory-aware follow-up
4. misconception correction
5. style consistency under repeated questions
6. off-topic redirect back to jazz

Sample prompts for Maestro:

- `Last time you told me jazz grew out of New Orleans. Why was Congo Square important?`
- `Quick quiz me on the difference between Swing and Bebop.`
- `Was Miles Davis mainly a Bebop player, or is that too simple?`
- `How does a II-V-I progression help improvisation?`
- `Can you explain jazz and the Civil Rights era without getting too long-winded?`
- `Teach me Python instead.`

Evaluation rubric:

- factual correctness
- concise style
- in-character voice
- useful pedagogy
- memory compatibility
- refusal/redirect quality

Decision gate:

- Candidate should win or tie in at least `4/6` prompt categories before chat A/B.

### Phase 6: Chat A/B Evaluation

Purpose: validate real player-facing improvement.

Method:

1. Start the baseline model and record responses to a fixed Maestro prompt set.
2. Switch to the candidate model and repeat the same set.
3. Use the same player memory conditions for both runs.
4. Blind-review outputs if possible.

Suggested chat scenarios:

1. New learner asks what jazz is
2. Returning learner asks about Swing vs Bebop
3. Learner asks for a quick quiz
4. Learner asks a partially wrong claim about Miles Davis
5. Learner asks an off-topic question
6. Learner asks for a short but vivid explanation of improvisation

Human preference questions:

- Which answer would you rather see in the game?
- Which sounds more like the Maestro?
- Which teaches better without sounding scripted?
- Which handles prior-learning context better?

Decision rule:

- Adopt candidate only if it wins clear human preference overall, even if eval loss is only slightly improved.

## Rollback Plan

- Keep the current Maestro model as the active baseline until the candidate wins.
- Do not sync candidate artifacts into Unity until after A/B review.
- Preserve baseline metrics in `docs/maestro_audit_baseline.md` for comparison.

## Recommended Artifacts To Save

- `docs/maestro_audit_baseline.md`
- `docs/maestro_candidate_audit.md`
- candidate import summary output
- candidate `training_report.json`
- A/B notes in `docs/maestro_ab_eval.md`

## Final Decision Template

Adopt the candidate if all are true:

- human A/B preference is better
- repeated openings are reduced
- task coverage is not worse
- factual quality is unchanged or improved

Otherwise:

- keep baseline
- regenerate narrower topical batches
- focus the next attempt on whichever failed first:
  - coverage
  - repetition
  - factual weakness
  - overly flat persona voice
