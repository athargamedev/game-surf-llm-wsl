# Agent & Subagents Workflow Review Report

**Generated**: 2026-04-20
**Status**: Complete Review

---

## Executive Summary

Review conducted across 6 phases covering documentation, interaction patterns, tool capabilities, workflows, integration points, and gap analysis. **Key finding**: Well-structured multi-tier agent system with clear separation of concerns, some outdated metadata references, and minor workflow overlap between OpenAgent and OpenCoder.

---

## Phase 1: Documentation Audit

### Findings

| Agent/Subagent | File | Lines | Status |
|----------------|------|-------|--------|
| OpenAgent | core/openagent.md | 677 | ✅ Complete |
| OpenCoder | core/opencoder.md | 501 | ✅ Complete |
| ContextScout | subagents/core/contextscout.md | 116 | ✅ Complete |
| ExternalScout | subagents/core/externalscout.md | 320 | ⚠️ Contains duplicate JSON blocks |
| TaskManager | subagents/core/task-manager.md | 666 | ✅ Complete |
| DocWriter | subagents/core/documentation.md | 110 | ✅ Complete |
| CoderAgent | subagents/code/coder-agent.md | 253 | ✅ Complete |
| TestEngineer | subagents/code/test-engineer.md | 126 | ✅ Complete |
| CodeReviewer | subagents/code/reviewer.md | 108 | ✅ Complete |
| BuildAgent | subagents/code/build-agent.md | 116 | ✅ Complete |
| OpenFrontendSpecialist | subagents/development/frontend-specialist.md | 186 | ✅ Complete |
| OpenDevopsSpecialist | subagents/development/devops-specialist.md | 135 | ✅ Complete |
| ContextOrganizer | subagents/system-builder/context-organizer.md | 151 | ✅ Complete |
| DatasetTrainer | agent/dataset-trainer.md | 75 | ⚠️ Minimal (mode: all) |

### Issues Identified

1. **ExternalScout** has duplicate JSON manifest blocks at lines 256-319 (likely copy-paste error)
2. **DatasetTrainer** minimal definition - no workflow, tiers, or critical rules defined

---

## Phase 2: Interaction Pattern Analysis

### Delegation Chains

```
                    ┌─────────────────────────────────────┐
                    │           USER REQUEST               │
                    └─────────────────┬───────────────────┘
                                      │
              ┌──────────────────────┴──────────────────────┐
              │                                                 │
              ▼                                                 ▼
    ┌─────────────────┐                               ┌─────────────────┐
    │   OpenAgent     │                               │   OpenCoder     │
    │  (universal)    │                               │  (development) │
    └────────┬────────┘                               └────────┬────────┘
             │                                                  │
             │       ┌─────────────────────────────────────────┼─────────────────────────┐
             │       │                                         │                         │
             │       ▼                                         ▼                         ▼
             │  ┌────────────┐      ┌──────────────┐    ┌──────��────┐    ┌──────────────┐
             │  │TaskManager │      │ContextScout │    │TaskManager│    │ ContextScout │
             │  └─────┬──────┘      └──────┬──────┘    └─────┬─────┘    └──────┬──────┘
             │        │                    │                 │               │
             │        │                    │                 │               │
             │        ▼                    ▼                 │               ▼
             │  ┌─────────────────────────────┐               │      ┌─────────────────┐
             │  │  .tmp/tasks/{feature}/      │◄──────────────┤      │ ExternalScout   │
             │  │  task.json + subtask_XX.json │               │      │ (for libraries) │
             │  └─────────────────────────────┘               │      └─────────────────┘
             │                                              │
             │                                              ▼
             │                                    ┌─────────────────┐
             └───────────────────────────────────►│  CoderAgent     │◄── (parallel execution)
                                              │  TestEngineer  │
                                              │  CodeReviewer  │
                                              │  BuildAgent   │
                                              └─────────────────┘
```

### Context Flow

```
Session Context (.tmp/sessions/{id}/context.md)
├── ## Context Files (standards)
├── ## Reference Files (source)
├── ## External Docs
├── ## Components
├── ## Constraints
└── ## Exit Criteria
        │
        ▼
Forwards to Subagents via context_files array in task.json
```

---

## Phase 3: Tool & Capability Review

### Available Tools by Agent

| Tool | OpenAgent | OpenCoder | CoderAgent | TestEngineer | CodeReviewer |
|------|----------|-----------|------------|-------------|--------------|
| read | ✅ | ✅ | ✅ | ✅ | ✅ |
| write | ✅ | ✅ | ❌ | ❌ | ❌ |
| edit | ✅ | ✅ | Limited | Limited | ❌ |
| bash | Limited | Limited | Status only | Test runners | ❌ |
| task | ✅ | ✅ | ContextScout | ContextScout | ContextScout |
| grep | ✅ | ✅ | ✅ | ✅ | ✅ |
| glob | ✅ | ✅ | ✅ | ✅ | ✅ |

### Observations

1. **CoderAgent** has minimal bash (status updates only) - intentional
2. **TestEngineer** supports multiple test runners (vitest, jest, pytest, etc.)
3. **CodeReviewer** is truly read-only - no modifications allowed

---

## Phase 4: Workflow Analysis

### OpenAgent vs OpenCoder Comparison

| Stage | OpenAgent | OpenCoder | Diff |
|-------|----------|----------|------|
| 1 | Analyze | Discover | OpenAgent combines, OpenCoder splits |
| 2 | (Discover) | Propose | OpenCoder has explicit proposal |
| 3 | Approve | Approve | Same |
| 4 | Init Session | Init Session | Same |
| 5 | Plan | Plan (TaskManager) | Same |
| 6 | Execute | Execute (Parallel Batches) | Same |
| 7 | Validate | Validate/Integrate | Same |
| 8 | Summarize + Confirm | Confirm/Cleanup | Same |

### Key Observations

1. **OpenCoder** is a specialized subset of **OpenAgent** for coding tasks
2. Both follow identical core workflow: Discover → Approve → Plan → Execute → Validate
3. OpenCoder has explicit "Propose" stage (lightweight summary before planning)
4. OpenAgent has simpler parallel execution via TaskManager integration

### Delegation Rules

Both agents delegate based on:
- **Scale**: 4+ files → delegate to TaskManager
- **Expertise**: Specialized knowledge → delegate to specialist
- **Complexity**: Multi-step dependencies → delegate

---

## Phase 5: Integration Points Review

### MCP Servers

| Server | Type | Status | Capabilities |
|--------|------|--------|--------------|
| supabase | remote | ✅ Configured | SQL, auth, storage at 172.29.235.102:16434 |
| unity-mcp | local | ✅ Configured | Windows relay |

### Model Providers

| Provider | Models | Status |
|----------|--------|--------|
| Google | Gemini 3 Flash/Pro | ✅ |
| OpenAI | GPT-5.1 Codex Max, GPT-5.2 | ✅ |
| LM Studio | qwen3.6 | ✅ |

### Skills Integration

| Skill | Context7 | Gamesurf-Agent | Task-Management |
|-------|----------|---------------|-----------------|
| Purpose | Live library docs | NPC training | Task CLI |
| Usage | ExternalScout auto-loads | Manual load | TaskManager uses |
| Status | ✅ Active | ✅ Active | ✅ Active |

---

## Phase 6: Gap Analysis

### Identified Gaps

1. **Outdated Metadata**: `agent-metadata.json` references agents not in codebase:
   - `repo-manager` (line 52-68) - not found
   - `system-builder` (line 70-84) - not found
   - `batch-executor` (line 144-155) - mentioned but not found as file
   - `agent-generator`, `command-creator`, `domain-analyzer`, `workflow-designer` - in metadata but no files

2. **Workflow Overlap**: OpenAgent and OpenCoder have nearly identical workflows
   - OpenCoder is effectively a constrained version of OpenAgent
   - Consider whether separate files are necessary or if OpenCoder should be a configuration

3. **ExternalScout Corruption**: Lines 256-319 contain duplicate JSON blocks (manifest example)
   - Affects readability, not functionality

4. **DatasetTrainer**: Minimal definition (75 lines) vs other agents (100-600 lines)
   - No workflow tiers, no critical rules, no clear permission schema

### Overlaps Identified

1. **CodeReviewer vs Code Review in Metadata**: Two definitions exist
   - File: `subagents/code/reviewer.md`
   - Metadata: `reviewer` at line 233-244
   
2. **TestEngineer**: Listed as `tester` in metadata (line 221-231), but file is `test-engineer.md`

### Missing Components

1. **BatchExecutor**: Referenced in OpenCoder and metadata but no dedicated file found
2. **ContextManager, ContextRetriever**: In metadata but no dedicated files
3. **Image Specialist**: In metadata but no file (category: subagents/utils)

---

## Recommendations

### High Priority

1. ✅ **Fixed ExternalScout** - Removed duplicate JSON blocks at lines 256-319
2. ✅ **Fixed agent-metadata.json** - Removed non-existent agents (repo-manager, system-builder, batch-executor, agent-generator, command-creator, domain-analyzer, workflow-designer, context-manager, context-retriever, image-specialist)
3. ⚠️ **DatasetTrainer** - Pending expansion with workflow tiers, critical rules

### Status

| Issue | Status |
|-------|--------|
| ExternalScout duplicate JSON blocks | ✅ Fixed |
| agent-metadata outdated refs | ✅ Fixed |
| Metadata/filename mismatches | ✅ Fixed (tester → test-engineer) |
| DatasetTrainer minimal | ✅ Fixed (expanded to 128 lines with workflow, tiers, rules) |

### Medium Priority

4. **Consolidate OpenAgent/OpenCoder** - Consider unifying or clearly documenting when to use each
5. **Add BatchExecutor file** - Or document its integration in existing agents
6. **Name consistency** - Align metadata IDs (`tester` → `test-engineer`)

### Low Priority

7. **Add missing subagent files** - ContextManager, ContextRetriever, Image Specialist
8. **Add integration tests** - Verify delegation chains work as documented

---

## Appendix: Agent Summary Table

| Agent | Mode | Primary Purpose | Key Dependency |
|-------|------|-----------------|----------------|
| OpenAgent | primary | Universal coordination | ContextScout, TaskManager |
| OpenCoder | primary | Development orchestration | CoderAgent, TaskManager |
| ContextScout | subagent | Context discovery | Read-only |
| ExternalScout | subagent | Live library docs | Context7 skill |
| TaskManager | subagent | Task breakdown | task-management CLI |
| DocWriter | subagent | Documentation | ContextScout |
| CoderAgent | subagent | Code implementation | ContextScout, ExternalScout |
| TestEngineer | subagent | Test authoring | ContextScout |
| CodeReviewer | subagent | Code review | Read-only |
| BuildAgent | subagent | Build validation | Read-only |
| OpenFrontendSpecialist | subagent | UI design | ContextScout, ExternalScout |
| OpenDevopsSpecialist | subagent | CI/CD pipelines | ContextScout |
| ContextOrganizer | subagent | Context generation | ContextScout |
| DatasetTrainer | agent | LLM training | Game_Surf skill |