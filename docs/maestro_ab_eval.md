# Maestro A/B Evaluation Sheet

## Models

- Baseline: `exports/npc_models/maestro_jazz_instructor`
- Candidate: `exports/npc_models/maestro_jazz_instructor`

## Memory Conditions

- Empty memory
- Memory-aware context:
  - `The learner previously learned that jazz grew from New Orleans musical traditions and recently asked how Swing and Bebop differ.`

Note:

- This pass was executed through the runtime chat API with memory reset between prompts to avoid chat-history contamination.
- The comparison therefore measures prompt-level continuity and runtime response quality, not a fully seeded persisted-memory replay.

## Scoring Scale

- `1` = poor
- `3` = acceptable
- `5` = excellent

## Scenario 1: New Learner Intro

Prompt: `What is jazz, in simple terms?`

| Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 3 | 3 | 4 | 2 | 2 | 2 | Strong Maestro flavor, but response trails off mid-thought and feels less controlled. |
| Candidate | 4 | 4 | 4 | 4 | 4 | 2 | More complete and clearer explanation; still stylized, but much cleaner than baseline. |

Preference: Candidate

Reason: Candidate gives a complete, concise definition while keeping the Maestro voice. Baseline truncates and loses precision.

## Scenario 2: Style Continuity

Prompt: `Last time you told me jazz grew from New Orleans traditions. Why was Congo Square important?`

| Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 4 | 4 | 4 | 3 | 3 | 3 | Good grounding on Congo Square and strong sense of roots, but still cuts off abruptly. |
| Candidate | 3 | 3 | 4 | 2 | 2 | 3 | Similar framing, but weaker factual phrasing and another cutoff near the end. |

Preference: Baseline

Reason: Baseline handles the historical framing more naturally and more convincingly, despite the cutoff.

## Scenario 3: Quiz Quality

Prompt: `Give me a quick quiz on the difference between Swing and Bebop.`

| Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 2 | 2 | 4 | 2 | 2 | 1 | Explains instead of quizzing and ends abruptly. |
| Candidate | 3 | 3 | 4 | 2 | 2 | 1 | Still does not actually quiz, but explains the contrast a bit better than baseline. |

Preference: Candidate

Reason: Both fail the task type, but candidate is slightly more useful and coherent.

## Scenario 4: Misconception Repair

Prompt: `Was Miles Davis basically just a Bebop player?`

| Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 3 | 3 | 4 | 2 | 2 | 1 | Starts well but becomes vague and trails off. |
| Candidate | 4 | 4 | 4 | 4 | 4 | 1 | Better correction, stronger completeness, and more confident structure. |

Preference: Candidate

Reason: Candidate clearly answers the misconception and stays more controlled.

## Scenario 5: Theory Teaching

Prompt: `How does a II-V-I progression help improvisation?`

| Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 4 | 4 | 4 | 4 | 4 | 1 | Good explanation with a useful “backbone” metaphor. |
| Candidate | 4 | 4 | 4 | 4 | 4 | 1 | Also strong, a bit tighter and more polished. |

Preference: Tie

Reason: Both answers are solid. Candidate is slightly cleaner, but not enough to call a decisive win.

## Scenario 6: Off-Topic Redirect

Prompt: `Teach me Python instead.`

| Model | Correctness | Teaching | Voice | Concise | Natural | Memory | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline | 1 | 2 | 3 | 3 | 3 | 1 | Does not redirect back to jazz; instead starts teaching Python. |
| Candidate | 1 | 2 | 3 | 2 | 2 | 1 | Also fails the redirect and leans into Python, with a more generic metaphorical answer. |

Preference: Baseline

Reason: Neither redirects properly, but baseline is slightly less generic and more controlled.

## Summary

Per-scenario winners:

- Scenario 1: Candidate
- Scenario 2: Baseline
- Scenario 3: Candidate
- Scenario 4: Candidate
- Scenario 5: Tie
- Scenario 6: Baseline

Overall winner: Candidate

Recommendation:

- Promote candidate
- Keep baseline
- Regenerate dataset and retry

Key reasons:

- Candidate wins the more important teaching-quality scenarios overall.
- Candidate responses are noticeably more complete and less truncated in several places.
- Candidate preserves Maestro voice while improving factual structure and clarity.
- Baseline still wins one historical-continuity prompt and is slightly better on the failed redirect prompt.
- Both models still need improvement on quiz behavior and off-topic redirect behavior.
