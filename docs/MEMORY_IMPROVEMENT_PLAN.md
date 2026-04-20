# Memory Workflow Improvement Plan

## Executive Summary

✅ **Good News:** Memory is being created and stored successfully  
⚠️ **Issue:** Memory is not being loaded when starting new sessions  
🎯 **Root Cause:** Session lifecycle not properly managing memory retrieval

---

## Diagnostic Results

### Current Database State
```
• Dialogue turns recorded:     19 messages
• Sessions created:            17 sessions
• NPC memories generated:      8 memories
• Sessions marked 'ended':     8 sessions
• Sessions still 'active':     9 sessions  ⚠️
• Summarization trigger:       ✓ Installed
```

### Key Findings

1. **✅ Memory Creation Pipeline WORKS**
   - Messages are saved to `dialogue_turns`
   - Sessions trigger memory summarization
   - Summaries stored in `npc_memories` table
   - 8 memories already created from your test conversations

2. **❌ Memory Loading Pipeline BROKEN**
   - `POST /session/start` returns `memory_summary: null`
   - Even though memories exist in database
   - Suggests `load_player_context()` function isn't being called or is failing silently

3. **⚠️ Session Lifecycle Issue**
   - 9 sessions still marked 'active' (not ended)
   - Need to ensure `/session/end` is called before starting new sessions
   - This prevents full memory accumulation

---

## Root Causes & Solutions

### Issue 1: Memory Not Loaded at Session Start

**Problem:** `POST /session/start` doesn't include memory in response

**Root Cause Candidates:**
1. `load_player_context()` not being called in start_session()
2. Supabase query for npc_memories failing silently
3. No error logging to show what's happening

**Solution:**

Add debug logging to identify the exact failure point:

```python
# In scripts/llm_integrated_server.py, in start_session():

# BEFORE: 
memory_summary: str | None = None

# AFTER:
memory_summary: str | None = None
print(f"DEBUG: Starting session for {request.player_id}/{request.npc_id}")

# Then after loading memory:
print(f"DEBUG: Loaded memory_summary: {memory_summary}")
```

Then add to `load_player_context()`:

```python
print(f"DEBUG: load_player_context called for {player_id}/{npc_id}")
# ... existing queries ...
print(f"DEBUG: Found {len(mem_response.data)} memories")
```

### Issue 2: Sessions Not Being Marked as Ended

**Problem:** 9 sessions still have `status='active'`

**Root Cause:** Frontend doesn't call `/session/end` when:
- Switching between NPCs
- Closing the chat
- Refreshing the page

**Solution:**

Ensure `/session/end` is called before `/session/start`:

```javascript
// In chat_interface.html, in setupNpcSelection():

option.addEventListener('click', async function() {
    const previousNpc = currentNpc;
    
    // ✅ MUST: End the current session before switching
    if (currentSessionId) {
        await endCurrentSession(true, previousNpc);  // true = show message
    }
    
    // ... rest of NPC switching code ...
});
```

Also ensure when page loads:

```javascript
// In initialize():
// If there's an active session from a previous page load, end it
if (currentSessionId) {
    await endCurrentSession(false, currentNpc);  // false = silent
}
```

---

## Action Plan

### Phase 1: Add Debug Logging ✅ Ready to Implement

**Goal:** Identify exactly where memory loading is failing

**Steps:**

1. **Modify `llm_integrated_server.py`:**

   Add logging to `start_session()` to show if memory is being fetched:
   ```python
   # Line ~960, in start_session():
   print(f"[MEMORY] Starting session for {request.player_id}/{request.npc_id}")
   
   # Then after memory_summary line:
   print(f"[MEMORY] Loaded summary: {memory_summary}")
   ```

2. **Modify `load_player_context()` to log queries:**
   ```python
   # Line ~446, start of function:
   print(f"[MEMORY] Querying memories for {player_id}/{npc_id}")
   
   # After npc_memories query:
   print(f"[MEMORY] npc_memories query returned: {len(mem_response.data)} rows")
   ```

3. **Restart server and test:**
   ```bash
   # Terminal 1: Start server with debug output
   cd /root/Game_Surf/Tools/LLM_WSL
   PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH python scripts/llm_integrated_server.py
   
   # Terminal 2: Test session start
   curl -X POST http://127.0.0.1:8000/session/start \
     -H "Content-Type: application/json" \
     -d '{
       "player_id": "test_user",
       "npc_id": "maestro_jazz_instructor",
       "player_name": "Test Player"
     }'
   ```

4. **Observe server logs:**
   - Look for `[MEMORY]` lines
   - They'll show exactly where the failure is

### Phase 2: Fix Session Lifecycle ✅ Ready to Implement

**Goal:** Ensure sessions are always properly ended

**Steps:**

1. **Fix NPC switching:**
   - Modify `setupNpcSelection()` in `chat_interface.html`
   - Always call `endCurrentSession()` before switching

2. **Fix page reload:**
   - Add cleanup in `initialize()`
   - End any active sessions from previous page load

3. **Test:** 
   - Send messages
   - Switch NPCs
   - Verify in database that previous session is marked `'ended'`

### Phase 3: Fix Memory Loading 🔧 Implementation Details

**Once debug logs show the problem**, we'll implement one of these:

**Option A: If query is failing**
- Check Supabase permissions on npc_memories table
- Verify schema structure matches assumptions

**Option B: If query returns data but not used**
- Ensure `memory_summary` is passed to response
- Verify it's included in StartSessionResponse model

**Option C: If function not called**
- Ensure `load_player_context()` is called in `start_session()`
- Verify Supabase client is available

### Phase 4: Verify End-to-End Flow ✅ Test Plan

**After fixes, run this test:**

```bash
# 1. Clear test data
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
psql $DATABASE_URL -c "DELETE FROM dialogue_sessions WHERE player_id='e2e_test';"

# 2. Start session
SESSION1=$(curl -s -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"player_id":"e2e_test","npc_id":"maestro_jazz_instructor","player_name":"Test"}' | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)

# 3. Send message
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id":"e2e_test",
    "npc_id":"maestro_jazz_instructor",
    "message":"Tell me about Miles Davis",
    "session_id":"'$SESSION1'"
  }'

# 4. End session
curl -X POST http://127.0.0.1:8000/session/end \
  -H "Content-Type: application/json" \
  -d '{"session_id":"'$SESSION1'","player_id":"e2e_test","npc_id":"maestro_jazz_instructor"}'

sleep 1

# 5. Start NEW session - memory should load
curl -s -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"player_id":"e2e_test","npc_id":"maestro_jazz_instructor","player_name":"Test"}' | python3 -m json.tool

# Expected: memory_summary should contain "Miles Davis"
```

---

## Files to Modify

### 1. `scripts/llm_integrated_server.py`

**Function: `start_session()`** (around line 950)
- Add debug logs for memory retrieval
- Ensure memory_summary is populated

**Function: `load_player_context()`** (around line 446)
- Add debug logs for each query
- Add try/except with logging

### 2. `chat_interface.html`

**Function: `setupNpcSelection()`** (around line 820)
- Ensure `endCurrentSession()` called before switching
- Test that sessions are marked 'ended' in database

**Function: `initialize()`** (around line 700)
- Add cleanup for stale active sessions

---

## Expected Outcome

After implementing these fixes:

✅ Sessions properly ended when switching NPCs  
✅ Memory loaded and shown in `memory_summary` response  
✅ NPC references previous conversations  
✅ No orphaned "active" sessions in database  

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Active sessions | 9 | 0 |
| Ended sessions | 8 | 17+ |
| Memory records | 8 | 17+ |
| Memory loaded | ✗ | ✓ |
| NPC using memory | ✗ | ✓ |

---

## Next Steps

1. **Implement Phase 1 (Debug Logging)**
   - Add print statements
   - Restart server
   - Run test and capture logs

2. **Based on logs, implement Phase 2 or 3**
   - If memory query issue: Fix database query
   - If session lifecycle: Fix NPC switching
   - If not called: Fix calling location

3. **Test full end-to-end flow**
   - Verify memory persists across sessions
   - Verify NPC uses memory in responses

4. **Optimize memory injection** (if needed)
   - Better formatting of memory context
   - Prioritize most relevant memories
   - Add confidence scores

---

## Resources

- **Test Plan:** `docs/MEMORY_WORKFLOW_TEST_PLAN.md`
- **API Reference:** `docs/API_REFERENCE.md`
- **Database Schema:** `supabase/migrations/`
