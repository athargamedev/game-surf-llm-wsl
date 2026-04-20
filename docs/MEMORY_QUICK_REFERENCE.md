# Memory Workflow - Quick Reference

## TL;DR: What's Wrong?

✅ **Memory IS being created** (8 memories in database)  
❌ **Memory NOT being loaded** (returns `null` on session start)  
⚠️ **Sessions not ending properly** (9 out of 17 still "active")

---

## The Three Fixes (Priority Order)

### 🔴 Priority 1: Add Debug Logging (5 min)
Helps identify exact issue  
**File:** `scripts/llm_integrated_server.py`  
**See:** `docs/MEMORY_FIX_IMPLEMENTATION.md` → Step 1

```bash
# Test after restart
curl -X POST http://127.0.0.1:8000/session/start ... | grep memory_summary
```

### 🟠 Priority 2: Fix Session Lifecycle (5 min)
Ensure sessions end when switching NPCs  
**File:** `chat_interface.html`  
**See:** `docs/MEMORY_FIX_IMPLEMENTATION.md` → Step 2

```bash
# Verify in database
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
psql $DATABASE_URL -c "SELECT status, COUNT(*) FROM dialogue_sessions GROUP BY status;"
```

### 🟡 Priority 3: Fix Memory Loading (variable)
Based on debug logs from Priority 1  
**File:** `scripts/llm_integrated_server.py` (likely)  
**See:** `docs/MEMORY_FIX_IMPLEMENTATION.md` → Step 3

---

## Diagnostic Commands (Copy-Paste Ready)

### Check Supabase Connection
```bash
curl -s http://127.0.0.1:8000/status | grep -E "supabase"
```

### Full Diagnostic
```bash
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
cd /root/Game_Surf/Tools/LLM_WSL
python3 scripts/diagnose_memory_workflow.py
```

### Check Session Status
```bash
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
psql $DATABASE_URL -t -c "
  SELECT status, COUNT(*) as count 
  FROM dialogue_sessions 
  GROUP BY status;
"
```

### Check Memory Records
```bash
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM npc_memories;"
```

---

## Documentation Map

| Document | Purpose | When to Use |
|----------|---------|------------|
| **MEMORY_WORKFLOW_TEST_PLAN.md** | Detailed test procedures & diagnostics | Need step-by-step guidance |
| **MEMORY_IMPROVEMENT_PLAN.md** | Analysis of findings, root causes, solutions | Understanding the problem |
| **MEMORY_FIX_IMPLEMENTATION.md** | Code changes with examples | Ready to implement fixes |
| **This file** | Quick reference | Need quick answers |

---

## Current Status

```
Database State:
  ✓ Supabase:       Connected
  ✓ Turns:          19 recorded
  ✓ Sessions:       17 recorded
  ✓ Memories:       8 created (trigger working!)
  ⚠ Active:         9 sessions not ended
  ✓ Trigger:        Installed

Issue:
  ✗ memory_summary: null (not loading into new sessions)
```

---

## Quick Wins (Do These First)

### Win 1: Verify Memory Exists
```bash
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
psql $DATABASE_URL -c "SELECT player_id, npc_id, summary FROM npc_memories LIMIT 1 \gx"
```
**Expected:** See summary text from your conversations

### Win 2: Test Direct API
```bash
curl -s -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"player_id":"test","npc_id":"maestro_jazz_instructor"}' | \
  python3 -m json.tool | grep memory_summary
```
**Expected:** Should NOT be `null` after fixes

### Win 3: Check Browser Logs
Open chat interface in browser → Dev Tools → Console  
Look for `[MEMORY]` logs after implementing Priority 1

---

## What Each Component Does

```
┌─ Player sends message
│  ├─ Message saved → dialogue_turns ✓
│  └─ Response shown
│
├─ Player switches NPC or closes
│  ├─ Session status → 'ended' ⚠️ (9 missing)
│  └─ Trigger fires
│     └─ Summarize session
│        └─ Summary saved → npc_memories ✓ (8 created)
│
└─ Player starts new session with same NPC
   ├─ /session/start called
   ├─ load_player_context() runs
   ├─ Query npc_memories ✓ (data exists)
   ├─ Return memory_summary ✗ (returns null)
   └─ NPC never sees previous context
```

The **break** is at the `load_player_context()` → `memory_summary` step.

---

## Server Restart (When Needed)

```bash
# Kill old server
pkill -f llm_integrated_server

# Restart with debug output
cd /root/Game_Surf/Tools/LLM_WSL
export PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH
python scripts/llm_integrated_server.py

# In another terminal, test
curl -X POST http://127.0.0.1:8000/session/start ...
```

---

## Files You Need to Know

```
chat_interface.html          ← Frontend (session lifecycle)
scripts/llm_integrated_server.py  ← Backend (memory loading)
supabase/migrations/20260418143000_memory_rpc.sql  ← Trigger definition
docs/MEMORY_*.md             ← This plan + implementation
```

---

## Success Criteria

After implementation, these should all be `true`:

- [ ] `export DATABASE_URL=...` returns no errors
- [ ] `diagnostic_memory_workflow.py` shows ✓ for all phases
- [ ] `curl /session/start` returns `memory_summary` with text (not null)
- [ ] New session mentions previous conversation (test manually)
- [ ] `psql` shows 0 active sessions, all ended

---

## Stuck?

1. **Check logs first** - run diagnostic script
2. **Read MEMORY_FIX_IMPLEMENTATION.md** - step by step
3. **Check database directly** - verify data exists
4. **Restart server** - might be stale process
5. **Check syntax** - `python3 -m py_compile scripts/llm_integrated_server.py`

---

## Key Command Reference

```bash
# Setup
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
cd /root/Game_Surf/Tools/LLM_WSL

# Diagnostic
python3 scripts/diagnose_memory_workflow.py

# Restart server
pkill -f llm_integrated_server
PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH python scripts/llm_integrated_server.py

# Test API
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"player_id":"test","npc_id":"maestro_jazz_instructor"}'

# Check database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM npc_memories;"
psql $DATABASE_URL -c "SELECT status, COUNT(*) FROM dialogue_sessions GROUP BY status;"
```

---

## Next: Start With Priority 1

👉 **Go to:** `docs/MEMORY_FIX_IMPLEMENTATION.md` → Step 1: Add Debug Logging

This will show exactly where the problem is!
