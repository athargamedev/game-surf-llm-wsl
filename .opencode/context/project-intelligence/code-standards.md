<!-- Context: project-intelligence/standards | Priority: critical | Version: 1.0 | Updated: 2026-04-20 -->

# Code Standards & Patterns

> Python coding standards, naming conventions, and security requirements.

## Quick Reference

- **Purpose**: Enforce consistent code patterns across all agents
- **Update When**: New patterns adopted, standards change
- **Audience**: Developers, AI agents

---

## Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files (Python) | snake_case | `train_surf_llama.py` |
| Files (Scripts) | snake_case | `run_full_npc_pipeline.py` |
| NPC IDs | kebab-case | `maestro_jazz_instructor` |
| Classes | PascalCase | `SupabaseClient`, `PlayerProfile` |
| Functions | snake_case | `get_player_profile()` |
| Constants | UPPER_SNAKE | `MAX_EPOCHS`, `DEFAULT_BATCH_SIZE` |
| DB Tables | snake_case | `player_profiles`, `dialogue_sessions` |
| DB Columns | snake_case | `player_id`, `npc_id`, `started_at` |

---

## Python Standards

**Required**:
- PEP 8 compliance (use Black formatter)
- Type hints for all function signatures
- Dataclasses for data structures
- Docstrings for public functions
- `from __future__ import annotations`

**Required Imports**:
```python
from __future__ import annotations
from pathlib import Path
from typing import Any, Optional
```

---

## Core Patterns

### Dataclass Pattern
```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class PlayerProfile:
    player_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime
```

### Singleton Client Pattern
```python
from supabase import Client, create_client
from typing import Optional

class SupabaseClient:
    _instance: Optional[Client] = None
    _url: str = ""
    _key: str = ""

    @classmethod
    def get_instance(cls) -> Optional[Client]:
        if cls._instance is not None:
            return cls._instance
        # ... lazy initialization
        cls._instance = create_client(cls._url, cls._key)
        return cls._instance
```

### VRAM Guard Pattern
```python
import torch

def check_vram_guard(threshold_gb: float = 3.5) -> None:
    """Check if enough VRAM is free before heavy tasks."""
    if not torch.cuda.is_available():
        return
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    free_gb = free_bytes / (1024**3)
    if free_gb < threshold_gb:
        print(f"WARNING: Low VRAM ({free_gb:.2f} GB)")
```

---

## Security Requirements

| Requirement | Implementation |
|-------------|----------------|
| API Keys | Environment variables only, never hardcoded |
| Auth | Service role key (server), anon key (client) |
| Validation | Validate before DB operations |
| Queries | Parameterized via Supabase client |
| Secrets | Add to `.gitignore` immediately |

### Environment Variable Pattern
```python
import os
from pathlib import Path

def get_config() -> tuple[str, str, bool]:
    ROOT = Path(__file__).resolve().parent.parent
    env = {}
    # Load from .env file
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')

    url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL", "http://127.0.0.1:16433")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    enabled = os.environ.get("ENABLE_SUPABASE", "true").lower() == "true"
    return url, key, enabled
```

### Required .gitignore Entries
```
.env
*.gguf
exports/
datasets/processed/
__pycache__/
*.pyc
```

---

## 📂 Codebase References

- Implementation: `scripts/supabase_client.py` - All patterns above
- Training: `scripts/train_surf_llama.py` - VRAM guard, dataclasses
- Pipeline: `scripts/run_full_npc_pipeline.py` - Standard structure

---

## Related Files

- `technical-domain.md` - Full tech stack and architecture
- `decisions-log.md` - Why these standards were chosen