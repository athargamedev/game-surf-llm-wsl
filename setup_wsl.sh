#!/bin/bash
set -e

echo "============================================================"
echo "Game_Surf NPC LLM Tooling - WSL Native Setup"
echo "============================================================"

# 1. Check for Conda/Mamba
if ! command -v conda &> /dev/null; then
    echo "[!] Conda not found. Installing Miniforge..."
    curl -L https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -o miniforge.sh
    bash miniforge.sh -b -p $HOME/miniforge3
    source "$HOME/miniforge3/bin/activate"
    conda init
    echo "[OK] Miniforge installed. PLEASE RESTART YOUR TERMINAL and run this script again."
    exit 0
fi

echo "[1/4] Creating Conda environment: unsloth_env"
# Use environment.yml if it exists, otherwise manual
if [ -f "environment.yml" ]; then
    conda env create -f environment.yml -y || conda env update -f environment.yml
else
    conda create --name unsloth_env python=3.11 -y
fi

echo "[2/4] Installing Unsloth and GPU dependencies"
conda run -n unsloth_env pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
conda run -n unsloth_env pip install --no-deps "xformers<0.0.28" "trl<0.9.0" peft accelerate bitsandbytes
conda run -n unsloth_env pip install datasets huggingface_hub hf_transfer transformers openai

echo "[3/4] Setting up directories"
mkdir -p exports/npc_models
mkdir -p datasets/processed
mkdir -p logs

echo "[4/4] Configuring environment"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "[INFO] Created .env from example. Please edit it with your HuggingFace token if needed."
fi

echo "============================================================"
echo "[SUCCESS] WSL Setup Complete!"
echo "To start training, run: ./run_pipeline.sh --npc <npc_key>"
echo "Or activate manually: conda activate unsloth_env"
echo "============================================================"
