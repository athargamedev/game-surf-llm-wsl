<!-- Context: project-intelligence/supabase-patterns | Priority: high | Version: 1.0 | Updated: 2026-04-20 -->

# Supabase Patterns

> Database client patterns, table operations, and memory workflow for Game_Surf.

## Quick Reference

- **Purpose**: How to interact with Supabase for player data and NPC memories
- **Update When**: Schema changes, new RPCs, pattern updates
- **Audience**: Developers, AI agents

---

## Client Initialization

```python
from scripts.supabase_client import SupabaseClient

# Initialize (loads from .env)
SupabaseClient.initialize()

# Get singleton instance
client = SupabaseClient.get_instance()
```

**Environment Variables**:
- `SUPABASE_URL` - Database URL (default: `http://127.0.0.1:16433`)
- `SUPABASE_SERVICE_ROLE_KEY` - Service role key for admin operations
- `ENABLE_SUPABASE` - Enable/disable (default: `true`)

---

## Data Models

### PlayerProfile
```python
@dataclass
class PlayerProfile:
    player_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime
```

### NPCProfile
```python
@dataclass
class NPCProfile:
    npc_id: str
    display_name: str
    npc_scope: str
    subject: Optional[str] = None
    personality: dict = field(default_factory=dict)
```

### DialogueSession
```python
@dataclass
class DialogueSession:
    session_id: uuid.UUID
    player_id: str
    npc_id: str
    status: str  # 'active' or 'ended'
    started_at: datetime
    ended_at: Optional[datetime] = None
```

### NPCMemory
```python
@dataclass
class NPCMemory:
    memory_id: int
    player_id: str
    npc_id: str
    summary: str
    session_count: int
    key_facts: dict  # JSONB
    created_at: datetime
```

---

## Common Operations

### Get Player Profile
```python
def get_player_profile(player_id: str) -> Optional[PlayerProfile]:
    client = SupabaseClient.get_instance()
    resp = client.table("player_profiles").select("*").eq("player_id", player_id).limit(1).execute()
    if not resp.data:
        return None
    return PlayerProfile(**resp.data[0])
```

### Create/Update Player
```python
def upsert_player_profile(player_id: str, display_name: str) -> None:
    client = SupabaseClient.get_instance()
    client.table("player_profiles").upsert({
        "player_id": player_id,
        "display_name": display_name,
        "updated_at": datetime.utcnow().isoformat()
    }).execute()
```

### Get NPC Memory
```python
def get_npc_memory(player_id: str, npc_id: str) -> Optional[NPCMemory]:
    client = SupabaseClient.get_instance()
    resp = client.table("npc_memories").select("*").eq("player_id", player_id).eq("npc_id", npc_id).limit(1).execute()
    if not resp.data:
        return None
    return NPCMemory(**resp.data[0])
```

### Store Dialogue Turn
```python
def store_dialogue_turn(session_id: uuid.UUID, role: str, content: str) -> None:
    client = SupabaseClient.get_instance()
    client.table("messages").insert({
        "session_id": str(session_id),
        "role": role,
        "content": content
    }).execute()
```

---

## Memory Workflow

```
Session Start → get_npc_memory() → Load into system prompt
     ↓
Session Active → store_dialogue_turn() → Log each message
     ↓
Session End → summarize_dialogue_session() RPC → Update memory
     ↓
Next Session → Repeat
```

---

## RPC Functions

### summarize_dialogue_session(session_id, player_id, npc_id)
- Triggered when session ends
- Summarizes last 10 turns
- Updates/creates npc_memories record
- Increments session_count

### get_player_npc_memory(player_id, npc_id)
- Returns latest memory for player-NPC pair

---

## Query Patterns

**Filter by player**:
```python
client.table("dialogue_sessions").select("*").eq("player_id", player_id).execute()
```

**Filter by NPC**:
```python
client.table("npc_memories").select("*").eq("npc_id", npc_id).execute()
```

**Filter + order**:
```python
client.table("messages").select("*").eq("session_id", session_id).order("created_at").execute()
```

**Limit results**:
```python
client.table("npc_memories").select("*").limit(10).execute()
```

---

## 📂 Codebase References

- **Client Implementation**: `scripts/supabase_client.py` (419 lines)
- **Server Integration**: `scripts/llm_integrated_server.py` - Session management
- **Memory Worker**: `scripts/god_memory_worker.py` - Memory processing
- **Tests**: `test_memory_workflow.py`
- **Docs**: `docs/SUPABASE_INTEGRATION.md`

---

## Related Files

- `technical-domain.md` - Full tech stack
- `code-standards.md` - Python patterns
- `docs/SUPABASE_INTEGRATION.md` - Full database schema