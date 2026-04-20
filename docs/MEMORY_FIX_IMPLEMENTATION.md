# Memory Workflow Fix - Implementation Guide

Quick step-by-step guide to fix the memory system.

---

## Step 1: Add Debug Logging (5 minutes)

### File: `scripts/llm_integrated_server.py`

#### Change 1: Add logs to `start_session()` (around line 950)

Find this section:
```python
@app.post("/session/start", response_model=StartSessionResponse)
def start_session(request: StartSessionRequest) -> StartSessionResponse:
    """Create a new dialogue session and load prior memory for this player+NPC."""
    session_id: str | None = None
    memory_summary: str | None = None
```

Add logging:
```python
@app.post("/session/start", response_model=StartSessionResponse)
def start_session(request: StartSessionRequest) -> StartSessionResponse:
    """Create a new dialogue session and load prior memory for this player+NPC."""
    print(f"[MEMORY] Starting session for {request.player_id}/{request.npc_id}")
    session_id: str | None = None
    memory_summary: str | None = None
```

Then find where memory is loaded:
```python
            # Load latest memory summary
            mem_resp = (
                supabase_client.table("npc_memories")
                .select("summary")
                .match({"player_id": request.player_id, "npc_id": request.npc_id})
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            if mem_resp.data:
                memory_summary = mem_resp.data[0]["summary"]
```

Change to:
```python
            # Load latest memory summary
            print(f"[MEMORY] Querying npc_memories for {request.player_id}/{request.npc_id}")
            mem_resp = (
                supabase_client.table("npc_memories")
                .select("summary")
                .match({"player_id": request.player_id, "npc_id": request.npc_id})
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            print(f"[MEMORY] Query returned: {len(mem_resp.data) if mem_resp.data else 0} rows")
            if mem_resp.data:
                memory_summary = mem_resp.data[0]["summary"]
                print(f"[MEMORY] Loaded memory: {memory_summary[:100]}...")
            else:
                print(f"[MEMORY] No memories found")
```

#### Change 2: Add logs to `load_player_context()` (around line 446)

Find:
```python
def load_player_context(player_id: str, npc_id: str, current_message: str = "") -> str:
    profile_lines: list[str] = []
    memory_lines: list[str] = []
    term_lines: list[str] = []
    if supabase_client is None:
        return "No saved player memory."
```

Add:
```python
def load_player_context(player_id: str, npc_id: str, current_message: str = "") -> str:
    print(f"[MEMORY] load_player_context called for {player_id}/{npc_id}")
    profile_lines: list[str] = []
    memory_lines: list[str] = []
    term_lines: list[str] = []
    if supabase_client is None:
        print(f"[MEMORY] Supabase client is None!")
        return "No saved player memory."
```

Then find the npc_memories query:
```python
        mem_response = (
            supabase_client.table("npc_memories")
            .select("summary, created_at, raw_json")
            .match({"player_id": player_id, "npc_id": npc_id})
            .order("created_at", desc=True)
            .limit(mem_limit)
            .execute()
        )
        if mem_response.data:
```

Change to:
```python
        print(f"[MEMORY] Querying npc_memories table...")
        mem_response = (
            supabase_client.table("npc_memories")
            .select("summary, created_at, raw_json")
            .match({"player_id": player_id, "npc_id": npc_id})
            .order("created_at", desc=True)
            .limit(mem_limit)
            .execute()
        )
        print(f"[MEMORY] Query returned {len(mem_response.data) if mem_response.data else 0} rows")
        if mem_response.data:
```

### Restart Server & Test

```bash
# Kill old server
pkill -f llm_integrated_server

# Restart with debug output visible
cd /root/Game_Surf/Tools/LLM_WSL
PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH python scripts/llm_integrated_server.py

# In another terminal, test:
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "test_user",
    "npc_id": "maestro_jazz_instructor",
    "player_name": "Test Player"
  }'
```

**What to look for in server logs:**
- `[MEMORY] Starting session for ...`
- `[MEMORY] Querying npc_memories table...`
- `[MEMORY] Query returned X rows`
- `[MEMORY] Loaded memory: ...` OR `[MEMORY] No memories found`

---

## Step 2: Fix Session Lifecycle Issues (10 minutes)

### File: `chat_interface.html`

#### Change 1: Ensure sessions end before switching NPCs

Find `setupNpcSelection()` function (around line 820), locate this block:

```javascript
option.addEventListener('click', async function() {
    const previousNpc = currentNpc;
    const originalText = this.textContent;
    this.textContent = '⏳ Loading...';
    this.style.pointerEvents = 'none';
    
    try {
        await endCurrentSession(false, previousNpc);  // ← Already there
        document.querySelectorAll('.npc-option').forEach(o => o.classList.remove('active'));
        this.classList.add('active');
        currentNpc = this.dataset.npc;
        updateDatasetInfo();
        await selectNpcAdapter();
        await startNewSession();
    }
```

**Good news:** This is already doing the right thing! It calls `endCurrentSession()` before starting a new one.

**But we need to verify** the `endCurrentSession()` actually marks sessions as 'ended'. Check the function around line 950:

```javascript
async function endCurrentSession(showMessage = true, npcId = currentNpc) {
    if (!currentSessionId) return;
    const endingSessionId = currentSessionId;
    currentSessionId = null;
    try {
        await fetch(`${API_BASE}/session/end`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: endingSessionId,
                player_id: currentPlayerId,
                npc_id: npcId
            })
        });
        if (showMessage) addSystemMessage(`Ended session ${endingSessionId}`);
    } catch (error) {
        console.warn('Unable to end session:', error);
    }
}
```

**Verify this is being called** by adding a log:

```javascript
async function endCurrentSession(showMessage = true, npcId = currentNpc) {
    console.log(`[MEMORY] Ending session ${currentSessionId} for NPC: ${npcId}`);  // ← Add this
    if (!currentSessionId) return;
    const endingSessionId = currentSessionId;
    currentSessionId = null;
```

#### Change 2: Ensure cleanup on page load

Find `initialize()` function (around line 700):

```javascript
async function initialize() {
    // Initialize Supabase realtime first
    initSupabase();
    
    setupNpcSelection();
```

Add cleanup:

```javascript
async function initialize() {
    // Clean up any stale session from previous page load
    if (currentSessionId) {
        console.log(`[MEMORY] Cleaning up stale session from previous load`);
        await endCurrentSession(false, currentNpc);
    }
    
    // Initialize Supabase realtime first
    initSupabase();
    
    setupNpcSelection();
```

### Test Session Lifecycle

```bash
# 1. Open chat interface in browser
# 2. Set a player name
# 3. Send a message
# 4. Switch to a different NPC
# 5. Open database and check:

export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
psql $DATABASE_URL -c "
SELECT player_id, npc_id, status, created_at 
FROM dialogue_sessions 
ORDER BY created_at DESC 
LIMIT 10;
"
```

**Expected:** Recent sessions should show `status='ended'` when switched

---

## Step 3: Diagnose Memory Loading (Based on Logs)

Run the diagnostic script again after logging:

```bash
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"
cd /root/Game_Surf/Tools/LLM_WSL
python3 scripts/diagnose_memory_workflow.py
```

### Scenario A: Logs show "Supabase client is None!"
**Problem:** Supabase not initializing  
**Fix:** Check `.env` has `ENABLE_SUPABASE=true`

### Scenario B: Logs show "Query returned 0 rows"
**Problem:** Query not finding memories even though they exist  
**Fix:** Check query filters (player_id, npc_id match exactly)

```bash
# Debug: Check what player_ids are in the database
psql $DATABASE_URL -c "SELECT DISTINCT player_id FROM npc_memories;"
```

### Scenario C: Logs show "Query returned X rows" but still no memory_summary
**Problem:** Query works but result not returned in response  
**Fix:** Verify `StartSessionResponse` model has memory_summary field

Check in `scripts/llm_integrated_server.py`:
```python
class StartSessionResponse(BaseModel):
    session_id: str
    player_id: str
    npc_id: str
    memory_summary: str | None = None  # ← Should be here
```

---

## Step 4: Test End-to-End (5 minutes)

After implementing fixes above:

```bash
# 1. Restart server (with debug logs)
pkill -f llm_integrated_server
cd /root/Game_Surf/Tools/LLM_WSL
PYTHONPATH=/root/Game_Surf/Tools/LLM_WSL:$PYTHONPATH python scripts/llm_integrated_server.py

# 2. In another terminal, run test:
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:15433/postgres"

# Clear test data
psql $DATABASE_URL -c "DELETE FROM dialogue_sessions WHERE player_id='final_test';"

# Start session 1
SESSION1=$(curl -s -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_id":"final_test",
    "npc_id":"maestro_jazz_instructor",
    "player_name":"Test"
  }' | grep -o '"session_id":"[^"]*' | cut -d'"' -f4)

echo "Session 1: $SESSION1"

# Send message
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id":"final_test",
    "npc_id":"maestro_jazz_instructor",
    "message":"Tell me about jazz history",
    "session_id":"'$SESSION1'"
  }' | head -20

# End session
curl -s -X POST http://127.0.0.1:8000/session/end \
  -H "Content-Type: application/json" \
  -d '{"session_id":"'$SESSION1'","player_id":"final_test","npc_id":"maestro_jazz_instructor"}'

sleep 2

# Start session 2 - CHECK FOR MEMORY!
echo -e "\n=== Session 2 (should have memory) ==="
curl -s -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_id":"final_test",
    "npc_id":"maestro_jazz_instructor",
    "player_name":"Test"
  }' | python3 -m json.tool | grep -A 2 "memory_summary"
```

**Expected Output:**
```json
"memory_summary": "Player: Tell me about jazz history\nNPC: [NPC's response about jazz]..."
```

---

## Checklist

- [ ] Added debug logs to `start_session()`
- [ ] Added debug logs to `load_player_context()`
- [ ] Restarted server and verified logs appear
- [ ] Verified `endCurrentSession()` is called when switching NPCs
- [ ] Added cleanup in `initialize()`
- [ ] Ran end-to-end test
- [ ] Confirmed `memory_summary` is populated in session start response
- [ ] NPCs now remember previous conversations ✅

---

## Troubleshooting

| Error | Solution |
|-------|----------|
| `[MEMORY] Supabase client is None!` | Enable Supabase: `ENABLE_SUPABASE=true` in .env |
| `[MEMORY] Query returned 0 rows` | Check player_id/npc_id match exactly in database |
| `memory_summary: null` | Check logs, add more debugging, verify query works |
| Server crashes | Check Python syntax, run `python3 -m py_compile scripts/llm_integrated_server.py` |
| No `[MEMORY]` logs | Restart server, check for typos in log statements |

---

## Once Working

After memory loading is fixed:

1. **Optional: Improve memory formatting**
   - Better summarization
   - Relevance scoring
   - Context injection quality

2. **Optional: Use GOD Memory**
   - Start `scripts/god_memory_worker.py`
   - Use semantic search for memories
   - Implement `/memory/god` endpoint

3. **Monitor performance**
   - Check memory loading time
   - Verify no duplicate memories
   - Tune query limits
