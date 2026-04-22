<!-- Context: project-intelligence/test-workflow | Priority: high | Version: 1.0 | Updated: 2026-04-22 -->

# Test Workflows

> Test infrastructure for Game_Surf: server API tests, pipeline tests, UI tests, and the 10-player memory stress test.

## Quick Reference

| File | Type | Purpose | Run |
|------|------|---------|-----|
| `tests/test_server.py` | Python unittest | All FastAPI endpoint tests | `python tests/test_server.py` |
| `tests/test_chat_interface.py` | Playwright | Chat UI element tests | `python tests/test_chat_interface.py` |
| `tests/test_pipeline.py` | Phase checks | Dataset/model readiness | `python tests/test_pipeline.py` |
| `tests/run_all.py` | Orchestrator | Runs all suites | `python tests/run_all.py` |
| `test_memory_workflow.py` | Integration | Full session→memory flow | `python test_memory_workflow.py` |
| `/test-10-player` | Browser UI | Stress test at scale | Open via browser |

## Test Server Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Server alive check |
| `/status` | GET | Model, LoRA, Supabase state |
| `/metrics` | GET | Request stats, avg response time |
| `/npc-models` | GET | All registered NPC manifests |
| `/session/start` | POST | Create dialogue session |
| `/session/end` | POST | End session, trigger memory |
| `/chat` | POST | Single NPC chat turn |
| `/chat/stream` | POST | Streaming chat response |
| `/reload-model` | POST | Switch LoRA adapter |
| `/reset-memory` | POST | Clear chat engine cache |
| `/api/start-test` | POST | Start 10-player test |
| `/api/stop-test` | POST | Stop 10-player test |
| `/api/test-status` | GET | Poll live test state |
| `/debug/sessions` | GET | Active session map |
| `/debug/npc-state` | GET | Runtime state snapshot |

## 10-Player Memory Test

Located at `GET /test-10-player` — embedded browser UI served by the FastAPI server itself.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /test-10-player` | Load the HTML test UI |
| `POST /api/start-test` | Spawn test thread, returns immediately |
| `POST /api/stop-test` | Signal stop (sets `running=False`) |
| `GET /api/test-status` | Live snapshot of test state |

### Architecture

```
Browser UI (HTML_TEST_PAGE embedded in llm_integrated_server.py)
    │ poll /api/test-status every 1s
    │
    ├── FastAPI [/api/start-test]
    │     │ Spawns run_full_test_thread() in bg thread
    │     └── Returns immediately
    │
    └── FastAPI [/api/test-status]
          │ Returns snapshot under _test_lock
          │ Fields: running, config, current_player, current_npc,
          │         total_expected, results[], last_update
          │
          └── run_full_test_thread()
                │
                ├── For each enabled NPC
                │     ├── For each player (1..num_players)
                │     │     └── Thread: run_player_session_thread()
                │     │           ├── /session/start
                │     │           ├── /chat (per message)
                │     │           ├── /session/end
                │     │           └── /debug/memory/{player_id} (check memory)
                │     └── sleep(2) between players
                │     └── sleep(3) between NPCs
                │
                └── Sets running=False when done
```

### UI Fields (real-time)

| Field | Source |
|-------|--------|
| `current_npc` | `test_state["current_npc"]` |
| `current_player` | `test_state["current_player"]` |
| `sessionStatus` | `last_update["session_status"]` |
| `log → player message` | `last_update["last_message"]` |
| `log → NPC response` | `last_update["last_response"]` |
| `summary → Memories` | `result["memory_created"]` |

### Thread Safety

All writes to `test_state` are protected by `_test_lock = threading.Lock()`:
- `test_state["results"].append()` — after each player finishes
- `test_state["last_update"]` — set before/after each step (session start, each message, memory check)

### Config Model

```python
class TestConfig(BaseModel):
    player_name: str
    npcs: list[NpcTestConfig]  # [{npc_id, message_1, message_2}]
    num_players: int = 3

class NpcTestConfig(BaseModel):
    npc_id: str
    message_1: str
    message_2: str
```

### Memory Check Timing

After `/session/end`, waits 15 seconds for DB trigger to fire before calling `/debug/memory/`. Configurable timeout planned (currently hardcoded).

### Session Lifecycle

| Turns | Outcome |
|-------|---------|
| 0 | Session DELETED from `dialogue_sessions` |
| 1+ | Session STATUS→ended, memory trigger enqueued |

### Issues & Fixes Applied (v1.0)

| Issue | Fix |
|-------|-----|
| `session_id[:8]` crashes on `None` | Guard: `r["session_id"][:8] if r.get("session_id") else None` |
| `last_response` missing from UI log | Added to `last_update`, returned in API results |
| Race condition on concurrent writes | Added `_test_lock` around all `test_state` writes |
| Duplicate variable declarations | Removed duplicate `results`/`total`/`current` in `updateUI()` |
| Session start fail → no append | Added early `results.append()` before `return` |

## Running Tests

### Local (both servers running)

```bash
# Check server status
python scripts/server_manager.py status

# Run all tests
python tests/run_all.py

# Run server tests only
python tests/test_server.py

# Run pipeline readiness checks
python tests/test_pipeline.py

# Run memory workflow integration test
python test_memory_workflow.py

# Open 10-player test (browser)
# http://127.0.0.1:8080/test-10-player
# OR via server:
# http://127.0.0.1:8000/test-10-player
```

### Playwright UI Tests

```bash
pip install playwright && playwright install chromium
python tests/test_chat_interface.py
```

## Expected Results

| Test | Pass | Failure Means |
|------|------|-------------|
| `/health` | 200 | Server not responding |
| `/status` → `model_loaded` | `true` | Model not loaded |
| `/session/start` → `session_id` | UUID returned | Supabase down or session create failed |
| `/session/end` → `status` | `ended`/`discarded_empty` | Endpoint broken |
| `/chat` → `npc_response` | Non-empty string | LLM not generating |
| `/metrics` → `requests_total` | ≥ 0 | Metrics not tracked |
| 10-player test | All players session→chat→end | Chat or session flow broken |

## Onboarding Checklist

- [ ] Run `python tests/test_server.py` — all endpoints return 200
- [ ] Check `curl http://127.0.0.1:8000/status` — model_loaded, supabase_connected true
- [ ] Open `http://127.0.0.1:8000/test-10-player` — UI loads
- [ ] Start a test with 3 players / 1 NPC — verify log shows messages and responses
- [ ] Run `python tests/test_pipeline.py` — verify dataset/model phases
- [ ] Run `python test_memory_workflow.py` — verify memory persists after session end

## Related Files

- `scripts/llm_integrated_server.py` — server + test thread logic
- `scripts/supabase_client.py` — database client patterns
- `tests/` — all test suites
- `test_memory_workflow.py` — memory integration test
- `decisions-log.md` — architecture decisions
- `technical-domain.md` — server ports, startup commands