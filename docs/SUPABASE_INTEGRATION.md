# Game_Surf Supabase Integration

> **Player data, NPC memories, and database schema**

---

## Overview

Supabase provides:
- **Player profiles** - User accounts and preferences
- **NPC memories** - Persistent conversation history per player-NPC pair
- **Dialogue sessions** - Session tracking and metadata
- **Messages** - Individual chat messages

---

## Database Schema

### Tables

#### `players`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| username | TEXT | Player display name |
| preferences | JSONB | Player settings |
| created_at | TIMESTAMPTZ | Account creation |

#### `dialogue_sessions`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| player_id | UUID | Foreign key → players |
| npc_id | TEXT | NPC identifier |
| status | TEXT | 'active' or 'ended' |
| started_at | TIMESTAMPTZ | Session start |
| ended_at | TIMESTAMPTZ | Session end |

#### `messages`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| session_id | UUID | Foreign key → dialogue_sessions |
| role | TEXT | 'player' or 'assistant' |
| content | TEXT | Message content |
| created_at | TIMESTAMPTZ | Timestamp |

#### `npc_memories`
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| player_id | UUID | Foreign key → players |
| npc_id | TEXT | NPC identifier |
| summary | TEXT | Conversation summary |
| session_count | INT | Total sessions |
| key_facts | JSONB | Extracted facts |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Last update |

**UNIQUE constraint**: (player_id, npc_id) - one memory per player-NPC pair

---

## Memory Workflow

```
1. Session Start     → Check npc_memories for prior history
2. Session Active    → Log each turn to messages table
3. Session End       → Trigger: summarize_dialogue_session()
4. Memory Updated   → npc_memories table updated
5. Next Session     → Load memory into system prompt
```

### API Flow

**Start Session**:
```bash
POST /session/start
{
  "player_id": "alice",
  "npc_id": "jazz_historian"
}
```

**Send Message**:
```bash
POST /chat
{
  "player_id": "alice",
  "npc_id": "jazz_historian",
  "message": "Tell me about Miles Davis"
}
```

**End Session** (triggers memory summarization):
```bash
POST /session/end
{
  "session_id": "uuid",
  "player_id": "alice",
  "npc_id": "jazz_historian"
}
```

---

## Database Functions

### `summarize_dialogue_session(session_id, player_id, npc_id)`
- Triggered when session ends
- Summarizes last 10 turns
- Updates/creates memory record
- Increments session_count

### `get_player_npc_memory(player_id, npc_id)`
- Returns latest memory for player-NPC pair
- Includes summary, session count, key facts

---

## Configuration

### Environment Variables
```bash
# .env
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SERVICE_ROLE_KEY=your_key
ENABLE_SUPABASE=true
```

### Server Configuration
The LLM server auto-detects Supabase settings:
```python
SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54321")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ENABLE_SUPABASE = os.environ.get("ENABLE_SUPABASE", "true").lower() == "true"
```

---

## Supabase CLI Commands

```bash
# Start local Supabase
supabase start

# View status
supabase status

# Reset database
supabase db reset

# Push migrations
supabase db push

# Generate types
supabase gen types typescript --local > supabase-types.ts
```

---

## Testing

```bash
# Test memory workflow
cd /root/Game_Surf/Tools/LLM_WSL
python test_memory_workflow.py

# Manual API test
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"player_id": "test_player", "npc_id": "jazz_historian"}'

# Query memories
curl -X GET "http://127.0.0.1:54321/rest/v1/npc_memories?player_id=eq.test_player" \
  -H "Authorization: Bearer YOUR_KEY"
```

---

## URLs

| Service | URL |
|---------|-----|
| Supabase Studio | http://127.0.0.1:54321 |
| REST API | http://127.0.0.1:54321/rest/v1 |
| GraphQL | http://127.0.0.1:54321/graphql/v1 |

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | System architecture |
| [docs/API_REFERENCE.md](API_REFERENCE.md) | Server endpoints |
| [docs/SETUP_GUIDE.md](SETUP_GUIDE.md) | Environment setup |