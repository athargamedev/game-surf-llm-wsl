<!-- Context: project-intelligence/decisions | Priority: high | Version: 1.0 | Updated: 2025-01-12 -->

# Decisions Log

> Record major architectural and business decisions with full context. This prevents "why was this done?" debates.

## Quick Reference

- **Purpose**: Document decisions so future team members understand context
- **Format**: Each decision as a separate entry
- **Status**: Decided | Pending | Under Review | Deprecated

## Decision Template

```markdown
## [Decision Title]

**Date**: YYYY-MM-DD
**Status**: [Decided/Pending/Under Review/Deprecated]
**Owner**: [Who owns this decision]

### Context
[What situation prompted this decision? What was the problem or opportunity?]

### Decision
[What was decided? Be specific about the choice made.]

### Rationale
[Why this decision? What were the alternatives and why were they rejected?]

### Alternatives Considered
| Alternative | Pros | Cons | Why Rejected? |
|-------------|------|------|---------------|
| [Alt 1] | [Pros] | [Cons] | [Why not chosen] |
| [Alt 2] | [Pros] | [Cons] | [Why not chosen] |

### Impact
**Positive**: [What this enables or improves]
**Negative**: [What trade-offs or limitations this creates]
**Risk**: [What could go wrong]

### Related
- [Links to related decisions, PRs, issues, or documentation]
```

---

## Decision: [Title]

**Date**: YYYY-MM-DD
**Status**: [Status]
**Owner**: [Owner]

### Context
[What was happening? Why did we need to decide?]

### Decision
[What we decided]

### Rationale
[Why this was the right choice]

### Alternatives Considered
| Alternative | Pros | Cons | Why Rejected? |
|-------------|------|------|---------------|
| [Option A] | [Good things] | [Bad things] | [Reason] |
| [Option B] | [Good things] | [Bad things] | [Reason] |

### Impact
- **Positive**: [What we gain]
- **Negative**: [What we trade off]
- **Risk**: [What to watch for]

### Related
- [Link to PR #000]
- [Link to issue #000]
- [Link to documentation]

---

## Decision: Smart Server Port Management

**Date**: 2026-04-22
**Status**: Decided
**Owner**: Agent (LLM_WSL session)

### Context
When multiple agent sessions start servers, they run as direct `nohup &` processes that are invisible to tmux-based `server_manager.py`. The old manager would error ("Port 8000 already in use") without showing who was using it or offering alternatives.

### Decision
Enhanced `scripts/server_manager.py` with three capabilities:
1. **`check` subcommand**: Detects process on any port (pid, cmd, start time)
2. **`--auto` flag**: Scans ports 8000→8002 and 8080→8082, starts on first free
3. **Direct-process detection**: `get_server_status()` now detects both tmux sessions AND processes started outside tmux

### Rationale
- **Visibility first**: Can't manage what you can't see — detecting non-tmux processes was the root issue
- **Graceful collision handling**: Auto-port is safer than manual port selection
- **Minimal surface area change**: Same server, same script, just smarter startup logic

### Alternatives Considered
| Alternative | Pros | Cons | Why Rejected? |
|-------------|------|------|---------------|
| Force-kill on port conflict | Clean slate | Loses in-progress sessions | Unacceptable |
| Lock files (`/tmp/gamesurf.lock`) | Guaranteed single | Needs cleanup, extra file | Over-engineered |
| Env vars for port selection | Flexible | Agents still need to check | Extra coordination |

### Impact
- **Positive**: Agents reliably start/reuse servers across sessions
- **Positive**: `status` command shows full picture (tmux + direct)
- **Negative**: None — purely additive

### Related
- `scripts/server_manager.py`
- `test-workflow.md` — full test infrastructure documented

---

## Decision: 10-Player Memory Stress Test

**Date**: 2026-04-22
**Status**: Decided
**Owner**: Agent (LLM_WSL session)

### Context
Manual testing of the NPC memory pipeline was slow — testing 10+ players across multiple NPCs required repeating session→chat→end manually. No automated stress test existed to validate memory persistence at scale.

### Decision
Built a self-contained browser UI at `GET /test-10-player` embedded in the FastAPI server itself (`llm_integrated_server.py`), backed by `/api/start-test`, `/api/stop-test`, and `/api/test-status` endpoints. A background thread runs real players through the full session lifecycle.

### Architecture
- HTML test page embedded as `HTML_TEST_PAGE` string in server, served at `/test-10-player`
- `run_full_test_thread()` iterates NPCs → players, each in a thread
- `_test_lock` (threading.Lock) protects all `test_state` dict writes
- `last_update` dict carries live status: player, NPC, session_status, last_message, last_response
- 15s hardcoded wait after `/session/end` before memory check
- Sessions with 0 turns → DELETED; sessions with 1+ turns → STATUS=ended + memory trigger

### Fixes Applied (v1.0)
- None session_id crash → guarded slicing
- Missing last_response in UI log → added to last_update + API results
- Race condition on results append → `_test_lock` around all writes
- Duplicate variable declarations in updateUI() → removed
- Session start failure → early return with result appended

### Impact
- **Positive**: Automated multi-player memory stress test, browser-accessible
- **Negative**: 15s memory wait hardcoded; no graceful thread shutdown on stop
- **Risk**: Stop sets `running=False` but thread doesn't actually exit mid-loop

### Related
- `test-workflow.md` — full documentation with diagrams and run commands
- `scripts/llm_integrated_server.py` — HTML_TEST_PAGE, test_state, thread functions

---

## Deprecated Decisions

Decisions that were later overturned (for historical context):

| Decision | Date | Replaced By | Why |
|----------|------|-------------|-----|
| [Old decision] | [Date] | [New decision] | [Reason] |

## Onboarding Checklist

- [ ] Understand the philosophy behind major architectural choices
- [ ] Know why certain technologies were chosen over alternatives
- [ ] Understand trade-offs that were made
- [ ] Know where to find decision context when questions arise
- [ ] Understand what decisions are pending and why

## Related Files

- `technical-domain.md` - Technical implementation affected by these decisions
- `business-tech-bridge.md` - How decisions connect business and technical
- `living-notes.md` - Current open questions that may become decisions
