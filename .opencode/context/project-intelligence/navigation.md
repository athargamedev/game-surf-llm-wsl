<!-- Context: project-intelligence/nav | Priority: critical | Version: 1.4 | Updated: 2026-04-22 -->

# Project Intelligence

> Start here for quick project understanding. These files bridge business and technical domains.

## Structure

```
.opencode/context/project-intelligence/
├── navigation.md              # This file - quick overview
├── business-domain.md         # Business context and problem statement
├── technical-domain.md        # Stack, architecture, technical decisions
├── code-standards.md          # Python patterns, naming, security
├── supabase-patterns.md       # Database patterns, memory workflow
├── business-tech-bridge.md    # How business needs map to solutions
├── decisions-log.md           # Major decisions with rationale
├── living-notes.md            # Active issues, debt, open questions
└── test-workflow.md           # Test suites and 10-player stress test
```

## Quick Routes

| File | Description | Priority |
|------|-------------|----------|
| `business-domain.md` | Problem, users, value proposition | high |
| `technical-domain.md` | Stack, architecture, integrations | **critical** |
| `code-standards.md` | Python patterns, naming, security | **critical** |
| `supabase-patterns.md` | Database patterns, memory workflow | high |
| `test-workflow.md` | Test suites, 10-player stress test | **high** |
| `business-tech-bridge.md` | Business → technical mapping | high |
| `decisions-log.md` | Why decisions were made | medium |
| `living-notes.md` | Active issues and open questions | medium |

## Developer Commands

```bash
# Start servers (auto-finds free port)
python scripts/server_manager.py start --auto

# Check what process owns a port
python scripts/server_manager.py check 8000

# Check all servers
python scripts/server_manager.py status

# Kill process on port
python scripts/server_manager.py kill-port 8000
```

## Usage

**New Team Member / Agent**:
1. Start with `navigation.md` (this file)
2. Read all files in order for complete understanding
3. Follow onboarding checklist in each file

**Quick Reference**:
- Business focus → `business-domain.md`
- Technical focus → `technical-domain.md`
- Decision context → `decisions-log.md`

## Integration

This folder is referenced from:
- `.opencode/context/core/standards/project-intelligence.md` (standards and patterns)
- `.opencode/context/core/system/context-guide.md` (context loading)

See `.opencode/context/core/context-system.md` for the broader context architecture.

## Maintenance

Keep this folder current:
- Update when business direction changes
- Document decisions as they're made
- Review `living-notes.md` regularly
- Archive resolved items from decisions-log.md

**Management Guide**: See `.opencode/context/core/standards/project-intelligence-management.md` for complete lifecycle management including:
- How to update, add, and remove files
- How to create new subfolders
- Version tracking and frontmatter standards
- Quality checklists and anti-patterns
- Governance and ownership

See `.opencode/context/core/standards/project-intelligence.md` for the standard itself.
