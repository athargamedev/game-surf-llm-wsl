<!-- Context: project-intelligence/notes | Priority: high | Version: 1.1 | Updated: 2026-04-22 -->

# Living Notes

> Active issues, technical debt, open questions, and insights that don't fit elsewhere. Keep this alive.

## Quick Reference

- **Purpose**: Capture current state, problems, and open questions
- **Update**: Weekly or when status changes
- **Archive**: Move resolved items to bottom with status

## Technical Debt

| Item | Impact | Priority | Mitigation |
|------|--------|----------|------------|
| [Debt item] | [What risk it creates] | [High/Med/Low] | [How to manage] |

### Technical Debt Details

**[Debt Item]**  
*Priority*: [High/Med/Low]  
*Impact*: [What happens if not addressed]  
*Root Cause*: [Why this debt exists]  
*Proposed Solution*: [How to fix it]  
*Effort*: [Small/Medium/Large]  
*Status*: [Acknowledged | Scheduled | In Progress | Deferred]

## Open Questions

| Question | Stakeholders | Status | Next Action |
|----------|--------------|--------|-------------|
| [Question] | [Who needs to decide] | [Open/In Progress] | [What needs to happen] |

### Open Question Details

**[Question]**  
*Context*: [Why this question matters]  
*Stakeholders*: [Who needs to be involved]  
*Options*: [What are the possibilities]  
*Timeline*: [When does this need resolution]  
*Status*: [Open/In Progress/Blocked]

## Known Issues

| Issue | Severity | Workaround | Status |
|-------|----------|------------|--------|
| [Issue] | [Critical/High/Med/Low] | [Temporary fix] | [Known/In Progress/Fixed] |

### Issue Details

**[Issue Title]**  
*Severity*: [Critical/High/Med/Low]  
*Impact*: [Who/what is affected]  
*Reproduction*: [Steps to reproduce if applicable]  
*Workaround*: [Temporary solution if exists]  
*Root Cause*: [If known]  
*Fix Plan*: [How to properly fix]  
*Status*: [Known/In Progress/Fixed in vX.X]

## Insights & Lessons Learned

### What Works Well
- **Chrome DevTools MCP fully functional** — All tools (new_page, navigate_page, take_snapshot, list_network_requests, get_network_request, fill, click, wait_for, close_page) work correctly after Chrome install + MCP config flags (`--headless`, `--isolated`, `--no-sandbox`)
- **Chat startup fix verified** — No eager session on page load. Session only created on NPC selection or first message. Server readiness gating works.
- **Supabase session lifecycle** — Stale sessions with 0 turns are correctly DELETED (not marked ended), preventing junk memories

### What Could Be Better
- **turn_count field in dialogue_sessions** — Updates via DB trigger, which may lag after turn insert. Not a bug, but confusing during live tracing.
- **server_manager.py detection gap** — Non-tmux processes were invisible to manager. Fixed with direct port scanning in v1.3.

### Lessons Learned
- **Always scan ports before starting** — Check existing processes before `nohup &` to avoid duplicate servers. Use `server_manager.py check <port>`.
- **Chrome DevTools recovery** — Transient timeouts recover by navigating to `about:blank`. Never restart the whole MCP.
- **Stale session fix in llm_integrated_server.py** — Sessions with 0 dialogue_turns rows get DELETED, not UPDATEd. This was causing junk `npc_memories` rows.
- **Supabase table is `dialogue_sessions`**, not `npc_sessions` — Query with correct table name when checking session state.

## Patterns & Conventions

### Code Patterns Worth Preserving
- [Pattern 1] - [Where it lives, why it's good]
- [Pattern 2] - [Where it lives, why it's good]

### Gotchas for Maintainers
- [Gotcha 1] - [What to watch out for]
- [Gotcha 2] - [What to watch out for]

## Active Projects

| Project | Goal | Owner | Timeline |
|---------|------|-------|----------|
| [Project] | [What we're doing] | [Who owns it] | [When it matters] |

## Archive (Resolved Items)

Moved here for historical reference. Current team should refer to current notes above.

### Resolved: [Item]
- **Resolved**: [Date]
- **Resolution**: [What was decided/done]
- **Learnings**: [What we learned from this]

## Onboarding Checklist

- [ ] Review known technical debt and understand impact
- [ ] Know what open questions exist and who's involved
- [ ] Understand current issues and workarounds
- [ ] Be aware of patterns and gotchas
- [ ] Know active projects and timelines
- [ ] Understand the team's priorities

## Related Files

- `decisions-log.md` - Past decisions that inform current state
- `business-domain.md` - Business context for current priorities
- `technical-domain.md` - Technical context for current state
- `business-tech-bridge.md` - Context for current trade-offs
