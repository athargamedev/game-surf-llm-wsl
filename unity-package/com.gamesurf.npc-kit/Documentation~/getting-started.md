# GameSurf NPC Kit — Getting Started

## Prerequisites

- Unity 2022.3 or later
- A GGUF base model (3GB): `llama-3.2-3b-instruct.Q4_K_M.gguf`
- GPU with 4GB+ VRAM (CPU fallback available, slower)
- Python 3.10+ for training (optional)

## Installation

### Via Git URL (recommended)

1. Open **Window > Package Manager**
2. Click **+** > **Add package from git URL**
3. Enter: `https://github.com/AtharvGameDev/gamesurf-npc-kit.git`

### Via Local Folder

1. Clone or copy the `com.gamesurf.npc-kit` folder to your project's `Packages/` directory

## Quick Setup

### 1. Configure Supabase

1. Go to **Project Settings > GameSurf NPC Kit**
2. Create a Supabase Config: **Assets > Create > GameSurf > Supabase Config**
3. Enter your Supabase URL and API key
4. Apply the database schema (see `Documentation~/supabase-setup.md`)

### 2. Create an NPC Profile

1. **Assets > Create > GameSurf > NPC Profile**
2. Fill in:
   - **NPC ID**: `my_custom_npc` (kebab_case)
   - **Display Name**: `Professor Nova`
   - **Subject**: `Space Exploration`
   - **Personality > Tone**: `enthusiastic and knowledgeable`
3. Add voice rules (short behavior constraints)

### 3. Add to Scene

1. Create an empty GameObject (or use your NPC character)
2. Add the **NpcDialogueController** component
3. Assign your NPC Profile and Supabase Config
4. Choose **Remote Server** mode for development

### 4. Connect UI

```csharp
using GameSurf.NpcKit;
using UnityEngine;
using UnityEngine.UI;

public class SimpleChatUI : MonoBehaviour
{
    public NpcDialogueController npc;
    public InputField inputField;
    public Text responseText;

    private async void Start()
    {
        await npc.StartSession("player_001", "PlayerName");
    }

    public async void OnSendClicked()
    {
        string response = await npc.SendMessage(inputField.text);
        responseText.text = response;
        inputField.text = "";
    }

    private async void OnDestroy()
    {
        await npc.EndSession();
    }
}
```

### 5. Train a Custom LoRA (Optional)

```bash
pip install gamesurf-train
gamesurf-train pipeline --npc my_custom_npc --research ./research/
gamesurf-train sync --npc my_custom_npc --unity-project /path/to/unity/
```

## Development Mode vs Production

| Feature | Dev Mode (Remote Server) | Production (Local Inference) |
|---------|-------------------------|------------------------------|
| Inference | LLM WSL server at :8000 | llama.cpp via P/Invoke |
| Setup | `bash scripts/start_servers.sh` | GGUF in StreamingAssets |
| Hot-reload | Instant model changes | Requires restart |
| Best for | Iteration, testing | Deployed builds |

## Next Steps

- [Training Guide](training-guide.md) — Create custom NPC personalities
- [Supabase Setup](supabase-setup.md) — Database schema and configuration
- [API Reference](index.md) — Full API documentation
