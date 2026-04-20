# On Task Completion

## Before Declaring Done
1. Run lint/typecheck if available (no formal linter configured)
2. Test the change works with real data if possible
3. If training script: run `./run_pipeline.sh --npc <name>` and verify `.gguf` export
4. If server: run `python test_server.py` and verify all tests pass

## Verify Checklist
- [ ] Code builds/runs without errors
- [ ] Tests pass (if applicable)
- [ ] Exported model works in chat interface
- [ ] No secrets or keys committed

## Project Structure
```
LLM_WSL/
├── scripts/          # Training & server scripts
├── research/         # NPC knowledge bases
├── exports/          # Trained models (.gguf)
├── datasets/         # Training datasets
├── chat_interface.html  # Web UI
├── run_chat_server.py  # Web server (8080)
├── run_pipeline.sh   # Training entrypoint
├── environment.yml    # Conda environment
└── .env            # Config (not committed)
```