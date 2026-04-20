# Game_Surf - Quick Start

> **Get started in 30 seconds** - Open the chat, select an NPC, ask questions

---

## 1. Open Chat Interface

```
http://127.0.0.1:8080/chat_interface.html
```

## 2. Select an NPC

| NPC | Knowledge |
|-----|-----------|
| 🎷 Jazz Historian | Jazz history, music theory, improvisation |
| ⚡ Greek Mythology | Greek gods, heroes, myths |
| 🇧🇷 Brazil History | History of Brazil |
| 🦸 Marvel Comics | Marvel Comics lore |

## 3. Ask Questions

Example questions:

```
"Tell me about Miles Davis"
"Who was Achilles?"
"What is bebop?"
"Who is Iron Man?"
```

---

## System Status

| Component | URL | Status |
|-----------|-----|--------|
| Chat Interface | http://127.0.0.1:8080 | Running |
| LLM API | http://127.0.0.1:8000 | Running |
| Knowledge Base | research/ | Ready |

---

## Troubleshooting

**Shows "Server Status: Offline"?**
→ Hard refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)

**Can't connect?**
→ Verify servers are running:
```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/chat_interface.html
```

**Slow responses?**
→ Normal! First message takes 5-10 seconds

---

## Quick Commands

```bash
# Start web server (port 8080)
python run_chat_server.py

# Start LLM server (port 8000)
conda activate unsloth_env
python scripts/llm_integrated_server.py

# Test servers
python test_server.py

# Check GPU
nvidia-smi
```

---

## Documentation

| Document | Purpose |
|-----------|---------|
| [docs/INDEX.md](INDEX.md) | Full documentation index |
| [docs/SETUP_GUIDE.md](SETUP_GUIDE.md) | Environment setup |
| [docs/API_REFERENCE.md](API_REFERENCE.md) | API endpoints |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | System architecture |

---

**Try it now!** → http://127.0.0.1:8080/chat_interface.html