# Game_Surf Setup Guide

> **One-time environment setup** for training NPCs with native WSL2

---

## Prerequisites

| Requirement | Details |
|-------------|---------|
| OS | Windows 10/11 with WSL2 enabled |
| Linux | Ubuntu 22.04 or 24.04 |
| GPU | NVIDIA 8GB+ VRAM (6GB minimum) |
| Driver | Latest NVIDIA Game Ready driver |

---

## Step 1: Enable WSL2

**Windows PowerShell (Admin)**:
```powershell
wsl --install
wsl --set-default-version 2
```

Restart, then open Ubuntu from Start menu.

---

## Step 2: Install Conda & Environment

**Inside WSL (Ubuntu)**:
```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Miniforge
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b
source ~/miniforge3/bin/activate
conda init

# 3. Create environment from file
cd /root/Game_Surf/Tools/LLM_WSL
conda env create -f environment.yml

# 4. Activate
conda activate unsloth_env
```

---

## Step 3: Configure Environment Variables

Create `.env` file in project root:
```bash
cp .env.example .env
```

Edit `.env` with your keys:
- `HF_TOKEN` - Hugging Face token (required for model download)
- `MODEL_PATH` - Path to GGUF model (for inference server)

---

## Step 4: Verify GPU

```bash
# Check NVIDIA drivers (Windows)
nvidia-smi

# Check GPU in WSL
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"
```

Expected output: `True`

---

## Step 5: Run Setup Script

```bash
chmod +x setup_wsl.sh
./setup_wsl.sh
```

Expected output: "WSL Setup Complete!"

---

## Project Location

> [!IMPORTANT]
> **Do NOT run training from `/mnt/d/...`** (Windows drive).
> WSL access to Windows drives uses the slow 9P protocol.

### Recommended Location
```bash
# Copy to WSL home for best performance
cp -r /mnt/d/UnityWorkspaces/Game_Surf/Tools/LLM ~/projects/LLM_WSL
cd ~/projects/LLM_WSL
```

### Alternative: Symlink Only
```bash
# Symlink specific folders (not the whole project)
ln -s /mnt/d/UnityWorkspaces/Game_Surf/Tools/LLM/datasets ./datasets
```

---

## Performance Targets

| Operation | Target Time |
|-----------|-----------|
| Dataset load | < 5s |
| Model init | < 10s |
| 100 steps | ~4 min |
| GGUF export | < 2 min |
| Total pipeline | ~12 min |

---

## Common Commands

```bash
# Activate environment
conda activate unsloth_env

# Run full pipeline
./run_pipeline.sh --npc maestro_jazz_instructor

# With options
./run_pipeline.sh --npc maestro_jazz_instructor --epochs 3 --resume

# Check GPU memory
python -c "import torch; print(torch.cuda.get_device_properties(0).total_memory / 1e9, 'GB')"

# Clear GPU memory
python -c "import torch; torch.cuda.empty_cache()"
```

---

## Troubleshooting

**GPU not detected?**
```bash
# Check Windows drivers
nvidia-smi  # in PowerShell

# Check WSL
nvidia-smi  # in Ubuntu
python -c "import torch; print(torch.cuda.is_available())"
```

**Out of memory?**
```bash
# Close other GPU apps (LM Studio, etc.)
# Clear cache
python -c "import torch; torch.cuda.empty_cache()"
```

**conda not found?**
```bash
# Add to PATH
export PATH="$HOME/miniforge3/bin:$PATH"
source ~/miniforge3/etc/profile/conda.sh
```

---

## Next Steps

1. **Quick Start**: [docs/QUICK_START.md](QUICK_START.md)
2. **Run Pipeline**: `./run_pipeline.sh --npc maestro_jazz_instructor`
3. **Test Chat**: http://127.0.0.1:8080/chat_interface.html