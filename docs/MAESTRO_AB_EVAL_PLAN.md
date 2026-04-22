# Maestro A/B Eval Plan

## Goal

Compare the current Maestro runtime model against the refreshed candidate model and decide whether the candidate should replace the baseline.

## Models

- Baseline model: `exports/npc_models/maestro_jazz_instructor`
- Candidate model: `exports/npc_models/maestro_jazz_instructor`

## Decision Rule

Promote the candidate only if it wins overall human preference and does not introduce factual regressions.

Recommended threshold:

- candidate wins at least `4/6` scenarios overall
- no major factual miss on core jazz prompts
- no noticeable regression in character voice

## Test Setup

Keep these constant for both runs:

- same prompt list
- same player memory condition
- same generation settings if configurable
- same chat interface path
- same evaluator

Use two conditions:

1. Empty memory context
2. Memory-aware context

## Scenario Set

### 1. New Learner Intro

Prompt:

`What is jazz, in simple terms?`

What to look for:

- concise explanation
- warm Maestro tone
- useful first-contact teaching

### 2. Style Continuity

Prompt:

`Last time you told me jazz grew from New Orleans traditions. Why was Congo Square important?`

What to look for:

- smooth memory-aware continuation
- factual grounding
- no awkward mention of the memory slot

### 3. Quiz Quality

Prompt:

`Give me a quick quiz on the difference between Swing and Bebop.`

What to look for:

- natural quiz behavior
- useful pedagogy
- not overly scripted or repetitive

### 4. Misconception Repair

Prompt:

`Was Miles Davis basically just a Bebop player?`

What to look for:

- corrects the simplification well
- stays concise
- keeps the Maestro voice

### 5. Theory Teaching

Prompt:

`How does a II-V-I progression help improvisation?`

What to look for:

- clarity
- technical accuracy at a beginner-friendly level
- helpful metaphor use when natural

### 6. Off-Topic Redirect

Prompt:

`Teach me Python instead.`

What to look for:

- graceful redirect
- still sounds like Maestro
- not rude, not generic refusal boilerplate

## Memory Condition

Use this memory text for the memory-aware pass:

`The learner previously learned that jazz grew from New Orleans musical traditions and recently asked how Swing and Bebop differ.`

## Scoring Sheet

Score each response `1-5` on:

- factual correctness
- teaching usefulness
- Maestro voice consistency
- conciseness
- naturalness
- memory handling

Add a final binary preference:

- baseline wins
- candidate wins
- tie

## Evaluation Template

Use this table for each scenario.

| Scenario | Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Intro | Baseline |  |  |  |  |  |  |  |
| Intro | Candidate |  |  |  |  |  |  |  |

After both rows, record:

- Preference: baseline / candidate / tie
- Reason:

## Runtime Procedure

1. Start the normal servers.
2. Load or point runtime to the baseline Maestro model.
3. Run the 6 prompts in empty-memory mode.
4. Run the same 6 prompts in memory-aware mode.
5. Save all outputs.
6. Repeat the exact same process with the candidate model.
7. Blind-review the responses if possible.
8. Fill in the scoring sheet.

## What Counts As A Candidate Win

The candidate should show some combination of:

- better factual precision
- fewer repetitive openings
- stronger quiz behavior
- better memory continuity
- same or better Maestro personality

## What Counts As A Candidate Loss

Reject the candidate if it shows any of these clearly:

- more hallucinated jazz facts
- flatter or less recognizable Maestro voice
- more generic assistant phrasing
- weaker redirects
- obvious regressions in memory-aware responses

## Expected Current Risks

Based on the refreshed dataset audit, watch specifically for:

- repeated opening phrasing such as `that would be`
- teaching responses overpowering quiz style
- polished but slightly scripted answers

## Final Record

Write the result summary into:

- `docs/maestro_ab_eval.md`

Include:

- overall winner
- per-scenario winner
- key regressions
- final recommendation: promote / keep baseline / regenerate dataset
