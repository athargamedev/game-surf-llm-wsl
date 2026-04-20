# Game_Surf API Reference

> **Server endpoints, testing, and curl examples**

---

## Base URLs

| Service | URL |
|---------|-----|
| LLM API | http://127.0.0.1:8000 |
| Web UI | http://127.0.0.1:8080 |
| Chat UI | http://127.0.0.1:8080/chat_interface.html |

---

## Endpoints

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server health check |
| `/status` | GET | Model/index status |

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok"}

curl http://127.0.0.1:8000/status
# {"model_loaded": true, "index_loaded": true, ...}
```

### Session Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/start` | POST | Start new session |
| `/session/end` | POST | End session |
| `/session/history/{player_id}/{npc_id}` | GET | Get session history |

```bash
# Start session
curl -X POST http://127.0.0.1:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"player_id": "player_001", "npc_id": "jazz_historian"}'

# End session
curl -X POST http://127.0.0.1:8000/session/end \
  -H "Content-Type: application/json" \
  -d '{"session_id": "uuid", "player_id": "player_001", "npc_id": "jazz_historian"}'

# Get history
curl http://127.0.0.1:8000/session/history/player_001/jazz_historian
```

### Chat

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Send message, get response |

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "player_id": "player_001",
    "npc_id": "jazz_historian",
    "message": "Tell me about Miles Davis"
  }'
```

**Response**:
```json
{
  "npc_response": "Miles Davis was a legendary...",
  "session_id": "uuid"
}
```

### Utilities

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/reload-model` | POST | Reload LLM model |
| `/reload-index` | POST | Rebuild vector index |
| `/reset-memory` | POST | Clear player memory |

```bash
# Reload model
curl -X POST http://127.0.0.1:8000/reload-model

# Reload index (after adding lore files)
curl -X POST http://127.0.0.1:8000/reload-index

# Reset memory
curl -X POST http://127.0.0.1:8000/reset-memory \
  -H "Content-Type: application/json" \
  -d '{"player_id": "player_001"}'
```

### Player Memories

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/players/{player_id}/memories` | GET | Get player memories |

```bash
curl http://127.0.0.1:8000/players/player_001/memories
```

---

## Available NPCs

| npc_id | Display Name |
|--------|--------------|
| `jazz_historian` | Jazz Historian |
| `greek_mythology` | Greek Mythology |
| `brazilian_history` | Brazil History |
| `marvel_comics` | Marvel Comics |

---

## Testing

### Automated Test Suite

```bash
python test_server.py
```

**Expected output**:
```
✅ All tests passed!
   health: ✅ PASS
   status: ✅ PASS
   session_start: ✅ PASS
   chat: ✅ PASS
```

### Memory Workflow Test

```bash
python test_memory_workflow.py
```

---

## Model Information

| Property | Value |
|----------|-------|
| Model | llama-3.2-3b-instruct |
| Quantization | Q4_K_M (4-bit) |
| Engine | llama.cpp via llama-index |
| Framework | FastAPI |

---

## Performance

| Metric | Value |
|-------|-------|
| First inference | 5-10 seconds |
| Subsequent | 2-5 seconds |
| VRAM usage | 2-3GB |

---

## Unity Integration

### C# Example

```csharp
using UnityEngine;
using System.Collections;

public class NPCDialogueManager : MonoBehaviour 
{
    public IEnumerator SendChatMessage(string npcId, string message)
    {
        var request = new UnityWebRequest("http://127.0.0.1:8000/chat", "POST");
        var body = JsonUtility.ToJson(new ChatRequest {
            player_id = "unity_player",
            npc_id = npcId,
            message = message
        });
        
        request.uploadHandler = new UploadHandlerRaw(System.Text.Encoding.UTF8.GetBytes(body));
        request.downloadHandler = new DownloadHandlerBuffer();
        request.SetRequestHeader("Content-Type", "application/json");
        
        yield return request.SendWebRequest();
        
        if (request.result == UnityWebRequest.Result.Success)
        {
            var response = JsonUtility.FromJson<ChatResponse>(
                request.downloadHandler.text
            );
            DisplayNPCDialogue(response.npc_response);
        }
    }
}
```

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [docs/QUICK_START.md](QUICK_START.md) | Quick start |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | Architecture |
| [docs/SUPABASE_INTEGRATION.md](SUPABASE_INTEGRATION.md) | Supabase |