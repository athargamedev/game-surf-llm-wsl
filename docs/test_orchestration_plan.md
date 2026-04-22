# Test Orchestration Plan: 10-Player NPC Memory Workflow

## Overview

Automated test that simulates 10 new players interacting with NPCs to validate the complete memory workflow and dataflow through the integrated server + Supabase.

## Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                      TEST ORCHESTRATOR                          │
│                   (test_10_player_memory.py)                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              FastAPI Server (port 8000)                         │
│  /session/start → loads prior memories                          │
│  /chat → LLM response + saves dialogue_turns                  │
│  /session/end → triggers async memory embedding               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Local Supabase (port 16433)                        │
│  dialogue_sessions, dialogue_turns, npc_memories              │
│  pgmq queues: memory_embedding_queue, dialogue_graph_queue    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│           GOD Memory Worker (background)                        │
│  Process embedding jobs → generate memory summaries           │
└─────────────────────────────────────────────────────────────────┘
```

## Test Strategy

**Sequential Sessions**: Each player completes a full workflow before the next starts:
1. Player X starts session → loads prior memories (empty for new players)
2. Player X sends 2 chat messages → LLM generates responses
3. Player X ends session → triggers async memory processing
4. Wait for memory worker to process embeddings
5. Verify memory was created in Supabase
6. Move to next player

## Web Interface (test_10_player_memory.html)

A web form allows the user to configure the test before starting:

```html
<!-- Form Fields -->
<form id="testForm">
  <!-- Player Configuration -->
  <label>Player Name:</label>
  <input type="text" id="playerName" placeholder="e.g., Alice" required>

  <!-- NPC Selection (dropdown populated from /npc-models) -->
  <label>Select NPC:</label>
  <select id="npcId" required>
    <option value="">-- Choose NPC --</option>
    <option value="jazz_historian">Jazz Historian</option>
    <option value="marvel_comics_instructor">Marvel Comics Instructor</option>
    <option value="greek_mythology_instructor">Greek Mythology Instructor</option>
  </select>

  <!-- Message 1 -->
  <label>Message 1:</label>
  <textarea id="message1" placeholder="First message to NPC..." required></textarea>

  <!-- Message 2 -->
  <label>Message 2:</label>
  <textarea id="message2" placeholder="Second message to NPC..." required></textarea>

  <!-- Number of players (default 10) -->
  <label>Number of Players:</label>
  <input type="number" id="numPlayers" value="10" min="1" max="20">

  <!-- Start Test Button -->
  <button type="submit" id="startTest">Start Test</button>
</form>

<!-- Progress Display -->
<div id="progress">
  <div id="currentPlayer">Waiting to start...</div>
  <div id="sessionStatus"></div>
  <div id="chatLog"></div>
</div>
```

**User Flow:**
1. Open `test_10_player_memory.html` in browser
2. Fill in: player_name, npc_id (dropdown), message_1, message_2
3. Click "Start Test"
4. Watch real-time progress as each player completes their session

## Timing Requirements

| Operation | Expected Duration | Wait Buffer |
|-----------|------------------|-------------|
| Session start | <1s | 0.5s |
| Chat (LLM inference) | 3-15s | +5s buffer |
| LoRA adapter switch | 2-5s | +3s |
| Session end | <1s | 0.5s |
| Memory embedding queue | <5s | +5s |
| Memory summary creation | 5-10s | +10s |

## Player Configuration

```python
PLAYERS = [
    {"player_id": "player_001", "player_name": "Alice", "npc_id": "jazz_historian"},
    {"player_id": "player_002", "player_name": "Bob", "npc_id": "marvel_comics_instructor"},
    {"player_id": "player_003", "player_name": "Carol", "npc_id": "greek_mythology_instructor"},
    {"player_id": "player_004", "player_name": "David", "npc_id": "jazz_historian"},
    {"player_id": "player_005", "player_name": "Eve", "npc_id": "marvel_comics_instructor"},
    {"player_id": "player_006", "player_name": "Frank", "npc_id": "greek_mythology_instructor"},
    {"player_id": "player_007", "player_name": "Grace", "npc_id": "jazz_historian"},
    {"player_id": "player_008", "player_name": "Henry", "npc_id": "marvel_comics_instructor"},
    {"player_id": "player_009", "player_name": "Iris", "npc_id": "greek_mythology_instructor"},
    {"player_id": "player_010", "player_name": "Jack", "npc_id": "jazz_historian"},
]
```

Each player:
- Unique `player_id` (tests multi-player memory isolation)
- Unique display name (user provides base name, test appends number)
- Assigned to NPC (user selects from dropdown)
- Sends exactly 2 messages (user provides message_1 and message_2)

## Workflow Steps

### Phase 1: Pre-test Setup
1. Verify integrated server is running (`/health` endpoint)
2. Verify Supabase is accessible
3. Verify NPC models are registered (`/npc-models`)
4. Clear any existing test data from previous runs

### Phase 2: Player Session Loop

For each player (1-10):

```python
async def run_player_session(player: PlayerConfig, user_messages: list[str]):
    # Step 1: Start session
    session_resp = await start_session(player)
    assert session_resp.session_id is not None
    # Wait for prior memory retrieval (if returning player)
    await wait(0.5)

    # Step 2: Send 2 chat messages (from user input)
    for i, msg in enumerate(user_messages):
        # Reload NPC adapter if needed
        await reload_npc_model(player.npc_id)

        chat_resp = await send_chat(
            player_id=player.player_id,
            npc_id=player.npc_id,
            message=msg,
            session_id=session_resp.session_id
        )
        assert chat_resp.npc_response is not None
        # Log NPC response to UI

        # Wait for LLM to generate response + DB write
        await wait(5)  # Buffer for inference + Supabase write

    # Step 3: End session (triggers memory embedding)
    end_resp = await end_session(
        session_id=session_resp.session_id,
        player_id=player.player_id,
        npc_id=player.npc_id
    )

    # Step 4: Wait for async memory processing
    await wait_for_memory_processing(player.player_id, player.npc_id)

    # Step 5: Verify memory was created
    memory = await get_memory(player.player_id, player.npc_id)
    assert memory is not None, "Memory should be created after session end"

    return {
        "player_id": player.player_id,
        "session_id": session_resp.session_id,
        "turns": len(user_messages),
        "memory_created": memory is not None
    }
```

### Phase 3: Memory Chain Verification

After all 10 players complete, verify:
1. Each player has memory entry in `npc_memories`
2. Player 004 can retrieve Player 001's memory summary when starting session
3. Verify dialogue turns accumulated correctly in `dialogue_turns`
4. Verify sessions tracked in `dialogue_sessions`

## Key Timing Controls

```python
# Configuration constants
DELAYS = {
    "adapter_switch": 8.0,      # Time for LoRA adapter to load
    "llm_inference": 15.0,      # Max time for LLM to respond
    "db_write": 2.0,             # Time for Supabase writes
    "memory_queue": 10.0,       # Time for embedding job to process
    "memory_summary": 15.0,     # Time for memory summarization
}

async def controlled_wait(delay_type: str):
    """Wait with buffer for operation to complete."""
    await asyncio.sleep(DELAYS[delay_type])
```

## Error Handling

- **LLM timeout**: Retry once with exponential backoff (max 2 retries)
- **Adapter load failure**: Skip to next NPC, log failure
- **Supabase unavailable**: Fail test immediately (critical dependency)
- **Memory not created**: Extended wait (30s) + direct DB query fallback

## Validation Checkpoints

| Checkpoint | Validation Method |
|------------|-------------------|
| Server healthy | GET `/health` returns 200 |
| NPC models loaded | GET `/npc-models` returns list |
| Session created | `dialogue_sessions` has new row |
| Turn recorded | `dialogue_turns` has entries for session |
| Session ended | `dialogue_sessions.status = "ended"` |
| Memory entry | `npc_memories` has entry for player+NPC |
| Memory context | `/session/start` returns prior memory summary |

## File Structure

```
tests/
├── test_10_player_memory.html   # Web interface (form + progress display)
├── test_10_player_memory.py     # Main orchestrator (serves HTML + handles API)
└── test_10_player_memory.json  # Test results/output

# Helper modules (reuse existing)
scripts/
├── llm_integrated_server.py     # Server (already exists)
├── supabase_client.py           # DB client (already exists)
└── god_memory_worker.py         # Memory processor (already exists)
```

## HTML + Python Backend Integration

The test uses a single Python file that serves both the HTML frontend and handles the orchestration:

1. `GET /test` → Serves the HTML form
2. `POST /api/start-test` → Accepts form data, starts orchestration
3. `GET /api/progress` → Returns current player/session status (for UI polling)
4. `WebSocket /ws` → Real-time progress updates to UI

## Expected Test Runtime

- Per player session: ~40-50 seconds
  - Start: 1s
  - 2 chat messages: 20-30s (10-15s each)
  - End + memory wait: 15-20s
- Total: ~7-8 minutes for 10 players

## Success Criteria

1. ✅ All 10 players complete sessions without errors
2. ✅ All 10 memory entries created in `npc_memories`
3. ✅ Returning player (player_004) receives prior memory context on session start
4. ✅ Dialogue turns properly recorded for each session
5. ✅ LoRA adapter switching works (verified by successful NPC responses)
6. ✅ Supabase data integrity (no duplicate sessions, proper status updates)

## Next Steps

1. Create `tests/test_10_player_memory.html` - Web form UI
2. Create `tests/test_10_player_memory.py` - Python backend serving HTML + orchestrating test
3. Access at: `http://127.0.0.1:8000/test-10-player`
4. Fill form with player_name, npc_id, message_1, message_2
5. Click "Start Test" and watch progress in real-time
6. Verify Supabase tables after completion
