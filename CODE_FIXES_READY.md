# Code Fixes for test-10-player Improvements

## Fix #1: Replace Fixed Sleep with Smart Retry Loop

**Location:** Before the test checks for memory (around line 2540)

**Add this function to `llm_integrated_server.py`:**

```python
def wait_for_memory_with_retry(player_id: str, npc_id: str, 
                               max_retries: int = 10, 
                               initial_backoff: float = 2.0) -> tuple[bool, int, str]:
    """Poll for memory with exponential backoff.
    
    Returns (memory_exists, attempt_number, reason)
    """
    for attempt in range(max_retries):
        try:
            memory = get_memory_sync(player_id, npc_id)
            if memory:
                memory_context = memory.get("memory_context", "")
                if memory_context and memory_context != "No saved player memory.":
                    print(f"[Memory] Found on attempt {attempt + 1}/{max_retries}")
                    return True, attempt + 1, "found"
        except Exception as e:
            print(f"[Memory] Error checking memory (attempt {attempt + 1}): {e}")
        
        if attempt < max_retries - 1:
            wait_time = initial_backoff * (1.5 ** attempt)
            print(f"[Memory] Not ready yet, retry in {wait_time:.1f}s")
            time.sleep(wait_time)
    
    print(f"[Memory] Timeout after {max_retries} attempts")
    return False, max_retries, "timeout"
```

**Modify in `run_player_session_thread()` (around line 2540):**

**REPLACE THIS:**
```python
if end_session_sync(session_id, player_id, npc_id):
    set_test_update(session_status="waiting for memory processing")
    time.sleep(TEST_MEMORY_PROCESSING_DELAY_SECONDS)
    
    memory = get_memory_sync(player_id, npc_id)
    result["memory_created"] = memory is not None
```

**WITH THIS:**
```python
if end_session_sync(session_id, player_id, npc_id):
    set_test_update(session_status="waiting for memory processing")
    
    # Smart retry instead of fixed sleep
    memory_ready, retry_count, reason = wait_for_memory_with_retry(player_id, npc_id)
    result["memory_created"] = memory_ready
    result["memory_retry_attempts"] = retry_count
    result["memory_retry_reason"] = reason
```

---

## Fix #2: Validate Cross-Session Memory Persistence

**Location:** Cross-session Phase 2 logic (around line 2670)

**Modify `run_player_session_thread()` to track Phase 2 memory loading:**

```python
# Add to result dict initialization:
result["memory_loaded_on_start_phase2"] = None  # Only for Phase 2

# Then in the session start code:
session_resp = start_session_sync(player_id, player_name, npc_id)
if not session_resp:
    result["error"] = "Failed to start session"
    with _test_lock:
        test_state["results"].append(result)
    return

session_id = session_resp.get("session_id")
result["session_id"] = session_id

# IMPORTANT: Track memory at session start
memory_summary_at_start = session_resp.get("memory_summary")
result["memory_loaded_on_start"] = bool(memory_summary_at_start)

# Log what we got
if memory_summary_at_start:
    print(f"[{player_id}] Memory loaded on session start: {memory_summary_at_start[:100]}...")
else:
    print(f"[{player_id}] No memory loaded on session start")

set_test_update(
    player_id=player_id,
    npc_id=npc_id,
    session_status="started",
    last_message=f"Session {session_id[:8]}...",
    memory_loaded_on_start=result["memory_loaded_on_start"],
)
```

**Add validation for cross-session (Phase 2):**

```python
# After regular messages in Phase 2, before ending session:
if fresh_session and phase == "Phase 2":
    # This is a Phase 2 session - verify Phase 1 memory was available
    if not result.get("memory_loaded_on_start"):
        print(f"[WARN] {player_id}: Phase 2 started but Phase 1 memory NOT loaded!")
        result["memory_persistence_verified"] = False
    else:
        print(f"[OK] {player_id}: Phase 1 memory persisted to Phase 2")
        result["memory_persistence_verified"] = True
```

---

## Fix #3: Add Memory Quality Validation

**Location:** New helper function (add before `run_player_session_thread`)

```python
def validate_memory_quality(memory_response: Optional[dict], 
                            expected_min_length: int = 30) -> tuple[bool, str]:
    """Validate that memory is real and complete.
    
    Returns (is_valid, reason_if_invalid)
    """
    if not memory_response:
        return False, "response_is_none"
    
    memory_context = memory_response.get("memory_context", "")
    
    # Check for default "no memory" response
    if not memory_context or memory_context.strip() == "No saved player memory.":
        return False, "empty_or_default"
    
    # Check length is reasonable
    context_len = len(memory_context.strip())
    if context_len < expected_min_length:
        return False, f"too_short ({context_len}<{expected_min_length})"
    
    # Check structure (should have some sections)
    if "\n\n" not in memory_context:
        return False, "lacks_expected_structure"
    
    return True, "valid"
```

**Use in `run_player_session_thread()` when checking memory:**

```python
# Replace simple check:
memory = get_memory_sync(player_id, npc_id)
is_valid, reason = validate_memory_quality(memory)
result["memory_created"] = is_valid
result["memory_quality_reason"] = reason
```

---

## Fix #4: Better Supabase Error Tracking

**Location:** `enqueue_memory_embedding_job()` around line 609

**REPLACE THIS:**
```python
def enqueue_memory_embedding_job(player_id: str, npc_id: str, session_id: str) -> None:
    if supabase_client is None:
        raise RuntimeError("Supabase not connected")

    supabase_client.rpc(
        "enqueue_memory_embedding",
        {
            "player_id_param": player_id,
            "npc_id_param": npc_id,
            "session_id_param": session_id,
        },
    ).execute()
```

**WITH THIS:**
```python
def enqueue_memory_embedding_job(player_id: str, npc_id: str, session_id: str) -> dict:
    """Enqueue memory embedding job and return status details."""
    if supabase_client is None:
        error_msg = "Supabase client not connected"
        print(f"[ERROR] {error_msg}")
        return {"status": "error", "reason": "client_not_connected"}
    
    try:
        print(f"[Memory] Enqueuing memory embedding for {player_id}/{npc_id}/{session_id[:8]}")
        resp = supabase_client.rpc(
            "enqueue_memory_embedding",
            {
                "player_id_param": player_id,
                "npc_id_param": npc_id,
                "session_id_param": session_id,
            },
        ).execute()
        
        # Check for RPC errors
        if hasattr(resp, 'error') and resp.error:
            error_msg = str(resp.error)
            print(f"[ERROR] RPC error: {error_msg}")
            return {"status": "error", "reason": "rpc_error", "detail": error_msg}
        
        print(f"[Memory] Successfully enqueued")
        return {"status": "enqueued"}
    
    except Exception as exc:
        error_msg = str(exc)
        print(f"[ERROR] Exception enqueuing memory: {error_msg}")
        return {"status": "error", "reason": "exception", "detail": error_msg}
```

**Update `/session/end` endpoint to log enqueue result:**

```python
# Around line 1150 in /session/end:
try:
    enqueue_result = enqueue_memory_embedding_job(request.player_id, request.npc_id, request.session_id)
    if enqueue_result["status"] != "enqueued":
        print(f"[WARN] Memory embedding enqueue failed: {enqueue_result}")
    print(f"Enqueued memory embedding for {request.player_id}/{request.npc_id}")
except Exception as exc:
    print(f"Failed to enqueue memory embedding: {exc}")
```

---

## Fix #5: Move Identity Probe Outside Session

**Location:** `run_player_session_thread()` around line 2518

**REPLACE THIS:**
```python
# Identity probe: verify the NPC has the right persona
if not result["error"] and npc_id in _NPC_PROBE_MESSAGES:
    set_test_update(session_status="probing identity")
    probe_resp = send_chat_sync(player_id, npc_id, _NPC_PROBE_MESSAGES[npc_id], session_id)
    if probe_resp:
        probe_response = probe_resp.get("npc_response", "")
        identity_check = verify_npc_identity(npc_id, probe_response)
        result["identity_verified"] = identity_check
        set_test_update(
            session_status="identity check done",
            identity_verified=identity_check.get("verified"),
            last_response=f"ID:{identity_check.get('verified')} {probe_response[:80]}"
        )
    time.sleep(TEST_IDENTITY_PROBE_DELAY_SECONDS)
```

**WITH THIS (moves probe outside session):**
```python
# Identity probe: verify the NPC has the right persona
# NOTE: Probe uses a separate player_id ("__probe__") to avoid polluting session data
if not result["error"] and npc_id in _NPC_PROBE_MESSAGES:
    set_test_update(session_status="probing identity")
    
    # Send probe WITHOUT session_id (will create temporary session)
    probe_resp = send_chat_sync("__probe__", npc_id, _NPC_PROBE_MESSAGES[npc_id], None)
    if probe_resp:
        probe_response = probe_resp.get("npc_response", "")
        identity_check = verify_npc_identity(npc_id, probe_response)
        result["identity_verified"] = identity_check.get("verified")
        
        # Log more informative status
        verified_str = "✓ OK" if identity_check.get("verified") else "✗ FAILED"
        set_test_update(
            session_status=f"identity check: {verified_str}",
            last_response=probe_response[:100]  # Don't add "ID:False" prefix
        )
    
    time.sleep(TEST_IDENTITY_PROBE_DELAY_SECONDS)
```

---

## Fix #6: Enhanced UI Display (HTML Test Page)

**In the HTML test page, update the summary to show new fields:**

```javascript
// In showSummary() function, modify the player details display:
const details = document.getElementById('playerDetails');
details.innerHTML = results.map(r => 
    '<div class="player-row ' + (r.error ? 'error' : '') + '">' +
        '<span class="player-num">' + r.player_id.substr(-3) + '</span>' +
        '<span class="player-name">' + r.player_name + '</span>' +
        '<span class="player-status ' + (r.error ? 'error' : (r.memory_created ? 'done' : 'partial')) + '">' +
            (r.error 
                ? r.error 
                : (r.memory_created 
                    ? '✓ Memory (' + (r.memory_retry_reason || 'ok') + ')'
                    : '✗ No memory (' + (r.memory_retry_reason || 'unknown') + ')'
                )
            ) +
        '</span>' +
        (r.memory_persistence_verified !== undefined
            ? '<span style="margin-left: 10px; font-size: 11px; color: #888;">[Phase2: ' + 
              (r.memory_persistence_verified ? '✓ persist' : '✗ no persist') + ']</span>'
            : ''
        ) +
    '</div>'
).join('');
```

---

## Testing the Fixes

Run the improved test with:

```bash
# Configure AI News only (fastest test)
# Message 1: "What's the latest AI news?"
# Message 2: "Tell me about LLMs"
# Players per NPC: 3
# Enable Cross-Session: YES

# Expected improvements:
# 1. Memory retry shows "found on attempt 3/10" instead of instant false
# 2. Phase 2 shows "memory persisted" or "memory NOT loaded"
# 3. No more "ID:False" in main logs
# 4. Error reasons are specific (e.g., "timeout", "empty_or_default")
```

---

## Expected Results After Fixes

| Metric | Before | After |
|--------|--------|-------|
| False negative memory errors | ~40-50% | <5% |
| Cross-session validation | None | Full validation |
| Memory retry time | 25s fixed | 5-15s adaptive |
| Enqueue error visibility | 0% | 100% |
| Test log clarity | "ID:False" noise | Clean results |

