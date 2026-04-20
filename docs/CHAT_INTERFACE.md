# Game_Surf Chat Interface

> **Web UI usage guide**

---

## Access

**URL**: http://127.0.0.1:8080/chat_interface.html

---

## Features

### 1. NPC Selection (Sidebar Left)
Choose an NPC to chat with:

| NPC | Knowledge |
|-----|-----------|
| 🎷 Jazz Historian | Jazz history, music theory |
| ⚡ Greek Mythology | Greek gods, heroes, myths |
| 🇧🇷 Brazil History | History of Brazil |
| 🦸 Marvel Comics | Marvel Comics lore |

### 2. Chat Area (Main)
- Type messages
- View responses
- See typing indicator during processing
- Conversation history

### 3. Server Status (Top)
- Shows connectivity
- Model/index status
- Auto-refreshes every 30 seconds

### 4. Controls (Bottom)
- Clear Chat
- Reset Memory

---

## Usage Examples

### Jazz History
1. Select "Jazz Historian"
2. Ask: "Who was Miles Davis?"
3. Follow up: "What is bebop?"

### Greek Mythology
1. Select "Greek Mythology"
2. Ask: "Tell me about the 12 Olympians"
3. Ask: "Who was Achilles?"

---

## Troubleshooting

**Shows "Server Offline"?**
→ Hard refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)

**Slow responses?**
→ Normal! First message takes 5-10 seconds

**Can't connect?**
```bash
# Check servers
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/chat_interface.html
```

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [docs/QUICK_START.md](QUICK_START.md) | Quick start |
| [docs/API_REFERENCE.md](API_REFERENCE.md) | API endpoints |