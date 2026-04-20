# Memory Workflow Test & Diagnosis Plan

## Overview
NPCs aren't remembering previous conversations because the Supabase memory pipeline isn't fully working. This plan diagnosizes the exact failure point and provides solutions.

---

## Architecture Recap

```
Session Start
    ↓
Exchange messages → dialogue_turns table (INSERT)
    ↓
Session End (POST /session/end)
    ↓
Update session status to 'ended' → Trigger fires
    ↓
summarize_dialogue_session() → npc_memories table (INSERT/UPSERT)
    ↓
Next session loads memory from npc_memories → Injected into system prompt
```

---

## Phase 1: Database State Inspection

### Step 1.1 - Check Supabase Connection
```bash
# SSH into terminal or run directly
curl -s http://127.0.0.1:8000/status | python -m json.tool | grep -E "supabase|connected"
```

**Expected Output:**
```
"supabase_enabled": true,
"supabase_connected": true,
```

If `false`, Supabase isn't connected. Check `.env` for `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.

---

### Step 1.2 - Inspect dialogue_turns Table
Check if your test conversations are being recorded:

```bash
# Using Supabase CLI (if installed)
supabase db pull

# Or via psql if you have local Postgres access
psql $DATABASE_URL -c "SELECT COUNT(*) as turn_count FROM dialogue_turns;"
```

**Expected:** Should have rows from your test conversations.

**If empty:** Messages aren't being saved. → Check Step 2.1

---

### Step 1.3 - Inspect dialogue_sessions Table
```bash
psql $DATABASE_URL -c "SELECT session_id, player_id, npc_id, status FROM dialogue_sessions LIMIT 10;"
```

**Expected Output:**
```
             session_id              | player_id  |           npc_id            | status
--------------------------------------+------------+-----------------------------+--------
 12345678-1234-1234-1234-123456789abc | test_user  | maestro_jazz_instructor     | ended
 ...
```

**Check:**
- Do you have sessions marked as `'ended'`? (not still `'active'`)
- Are the player_id and npc_id correct?

**If all active:** Sessions aren't being ended. → Check Step 2.2

---

### Step 1.4 - Inspect npc_memories Table (THE KEY CHECK)
```bash
psql $DATABASE_URL -c "SELECT player_id, npc_id, summary, created_at FROM npc_memories LIMIT 10;"
```

**Expected Output:**
```
 player_id  |           npc_id            |                               summary
------------+-----------------------------+--------------------------------------------------------------------
 test_user  | maestro_jazz_instructor     | Player: Tell me about jazz...NPC: Jazz is...
 ...
```

**This is the critical check:**
- ✅ **If has rows:** Memory is being created! → Skip to Step 3 (frontend issue)
- ❌ **If empty:** Trigger isn't firing or summarization is failing → Go to Step 2.3

---

## Phase 2: Identify the Failure Point

### Step 2.1 - Is dialogue_turns Being Populated?

Add debug logging to `/chat` endpoint. Check server logs after sending a message:

```bash
# Watch the server terminal for this log line:
# "Saved turn for session {session_id}"
```

**If you DON'T see it:**
1. Check if Supabase is enabled: `.env` has `ENABLE_SUPABASE=true`
2. Check the server console for `"Supabase write error: {error}"`
3. **Solution:** Fix error or restart server

**If you DO see it:**
- Verify with Step 1.2 that data is in the database

---

### Step 2.2 - Is /session/end Being Called?

When you close a chat or switch NPCs, check if `/session/end` is called:

**Frontend check:** Open browser dev tools → Network tab → look for POST to `/session/end`

**Backend check:** Watch server console for:
```
Saved turn for session {session_id}
```

**If NOT being called:**
- Issue: Frontend isn't calling `/session/end` when switching NPCs
- **Fix:** See Frontend Issues section below

---

### Step 2.3 - Is the Trigger Firing?

The trigger should automatically summarize when status = 'ended'. Check if it exists:

```bash
psql $DATABASE_URL -c "\dt+ trg_summarize_ended_dialogue_session"
```

**Expected:** Trigger exists and is active

**If missing or error:**
1. Re-apply migrations:
   ```bash
   supabase migration up
   ```
2. Or manually check the migration file:
   ```bash
   cat supabase/migrations/20260418143000_memory_rpc.sql
   ```

---

### Step 2.4 - Manual Trigger Test

Force the trigger to fire:

```bash
# 1. Get a session_id from Step 1.3
SESSION_ID="12345678-1234-1234-1234-123456789abc"

# 2. Check npc_memories BEFORE update
psql $DATABASE_URL -c "SELECT COUNT(*) FROM npc_memories WHERE raw_json->>'session_id' = '$SESSION_ID';"

# 3. Manually update the session to 'ended'
psql $DATABASE_URL -c "UPDATE dialogue_sessions SET status='ended' WHERE session_id='$SESSION_ID'::uuid;"

# 4. Check npc_memories AFTER update
psql $DATABASE_URL -c "SELECT COUNT(*) FROM npc_memories WHERE raw_json->>'session_id' = '$SESSION_ID';"
```

**Expected:**
- Step 2: Count = 0 (not yet summarized)
- Step 4: Count = 1 (trigger created a summary)

**If still 0 after step 4:**
- Trigger isn't executing
- Check trigger permissions:
  ```bash
  psql $DATABASE_URL -c "SELECT trigger_schema, trigger_name, event_object_table, action_statement FROM information_schema.triggers WHERE trigger_name='trg_summarize_ended_dialogue_session';"
  ```

---

## Phase 3: Test Memory Loading

### Step 3.1 - Verify Memory Is Being Retrieved

Send this API request:

```bash
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "test_user",
    "npc_id": "maestro_jazz_instructor",
    "player_name": "TestPlayer"
  }' | python -m json.tool
```

**Expected Output:**
```json
{
  "session_id": "...",
  "player_id": "test_user",
  "npc_id": "maestro_jazz_instructor",
  "memory_summary": "Player: Tell me about jazz\nNPC: Jazz is a beautiful..."  ← THIS SHOULD BE POPULATED
}
```

**If `memory_summary` is `null`:**
- Memory wasn't retrieved
- Check `load_player_context()` in backend (Step 3.2)

---

### Step 3.2 - Debug load_player_context()

Add this to check what's being queried:

```python
# In scripts/llm_integrated_server.py, modify load_player_context() to add:
print(f"DEBUG: Loading context for {player_id}/{npc_id}")
print(f"DEBUG: Supabase client: {supabase_client is not None}")

# After querying npc_memories:
print(f"DEBUG: npc_memories response: {mem_response.data}")
```

**Or check directly via Supabase:**

```bash
# Query what load_player_context() should retrieve:
psql $DATABASE_URL -c "
SELECT player_id, npc_id, summary, created_at 
FROM npc_memories 
WHERE player_id = 'test_user' AND npc_id = 'maestro_jazz_instructor' 
ORDER BY created_at DESC 
LIMIT 5;
"
```

**If data exists but memory_summary is still null:**
- Issue: Backend query is failing silently
- **Fix:** Check exception handling in `load_player_context()`

---

## Phase 4: Full End-to-End Test

Once you've fixed any issues, run this test:

### Setup
```bash
# 1. Clear old test data (optional)
psql $DATABASE_URL -c "DELETE FROM dialogue_sessions WHERE player_id = 'e2e_test_user';"
```

### Test Steps

**Step 4.1: Start Session**
```bash
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor",
    "player_name": "E2E Tester"
  }' | python -m json.tool > session1.json

SESSION_ID=$(cat session1.json | grep session_id | grep -o '[a-f0-9\-]*' | head -1)
echo "Session ID: $SESSION_ID"
```

**Step 4.2: Send 3 Messages**
```bash
# Message 1
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor",
    "message": "Tell me about Miles Davis",
    "session_id": "'$SESSION_ID'"
  }'

# Message 2
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor",
    "message": "What year was he born?",
    "session_id": "'$SESSION_ID'"
  }'

# Message 3
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor",
    "message": "What are some of his famous albums?",
    "session_id": "'$SESSION_ID'"
  }'
```

**Step 4.3: End Session**
```bash
curl -X POST http://127.0.0.1:8000/session/end \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "'$SESSION_ID'",
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor"
  }'

echo "Session ended. Waiting 2 seconds for trigger..."
sleep 2
```

**Step 4.4: Check Memory Was Created**
```bash
psql $DATABASE_URL -c "
SELECT player_id, npc_id, summary 
FROM npc_memories 
WHERE player_id = 'e2e_test_user' 
ORDER BY created_at DESC 
LIMIT 1;
"
```

**Expected:** Should see a summary containing your 3 messages

**Step 4.5: Start New Session & Check Memory Loaded**
```bash
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor",
    "player_name": "E2E Tester"
  }' | python -m json.tool
```

**Expected:** `memory_summary` field should contain your previous conversation

**Step 4.6: Send Follow-up Message**
```bash
# This should demonstrate NPC remembering previous context
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "e2e_test_user",
    "npc_id": "maestro_jazz_instructor",
    "message": "Do you remember what we talked about before?",
    "session_id": "'$SESSION_ID'"
  }'
```

**Expected:** NPC should reference Miles Davis or the previous conversation

---

## Common Issues & Solutions

### Issue 1: "Supabase write error: Insufficient privileges"
**Cause:** Service role key doesn't have write permissions
**Fix:**
1. Check `.env` for correct `SUPABASE_SERVICE_ROLE_KEY`
2. Verify user has INSERT privilege on dialogue_turns, dialogue_sessions, npc_memories
3. Restart server after fixing

### Issue 2: Trigger not firing (npc_memories empty)
**Cause:** Migration not applied
**Fix:**
```bash
# Re-apply all migrations
cd supabase
supabase migration up

# Or manually:
psql $DATABASE_URL < migrations/20260418143000_memory_rpc.sql
```

### Issue 3: Memory loaded but NPC not using it
**Cause:** Memory injected into prompt but prompt format issue
**Fix:** Add debug logging in `apply_memory_slot()`:
```python
print(f"DEBUG: System prompt with memory:\n{system_prompt}")
```

### Issue 4: "Module not found: scripts.supabase_client"
**Cause:** PYTHONPATH not set
**Fix:** Always run server with:
```bash
cd /root/Game_Surf/Tools/LLM_WSL
PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH python scripts/llm_integrated_server.py
```

---

## Monitoring During Testing

Keep these terminals open:

**Terminal 1: Server Logs**
```bash
cd /root/Game_Surf/Tools/LLM_WSL
PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH python scripts/llm_integrated_server.py
```

**Terminal 2: Database Monitor**
```bash
watch -n 1 'psql $DATABASE_URL -c "SELECT COUNT(*) as turns FROM dialogue_turns; SELECT COUNT(*) as sessions FROM dialogue_sessions; SELECT COUNT(*) as memories FROM npc_memories;"'
```

**Terminal 3: Test Commands**
```bash
# Run test steps here
```

---

## Success Criteria

✅ **Full Memory Workflow Successful When:**
1. ✓ Test conversations appear in `dialogue_turns`
2. ✓ Sessions marked as `'ended'` in `dialogue_sessions`
3. ✓ Summaries appear in `npc_memories` after session ends
4. ✓ `memory_summary` field populated in `/session/start` response
5. ✓ NPC references previous conversation in new session

---

## Next Steps After Diagnosis

Once you identify the exact failure point, we can:
1. Fix the root cause with code changes
2. Add better error logging and debugging
3. Improve memory injection into the NPC prompt
4. Test GOD Memory semantic retrieval (if needed)
5. Optimize the memory summarization for better context

Document your findings in the test results section below.
