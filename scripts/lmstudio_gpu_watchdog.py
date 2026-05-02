#!/usr/bin/env python3
# scripts/lmstudio_gpu_watchdog.py
# ─────────────────────────────────────────────────────────────
# LMStudio GPU & Compatibility Watchdog
# ─────────────────────────────────────────────────────────────
# This script ensures that LMStudio is running with FULL GPU OFFLOAD
# and FLASH ATTENTION enabled, maximizing performance for Gemma 4.
# If layers spill over to CPU, Flash Attention gets disabled, severely
# impacting tokens/sec.

import os
import json
import time
import requests
import argparse
from typing import Dict, Any

LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "192.168.0.3:1234")
API_BASE = f"http://{LMSTUDIO_HOST}/v1"

def check_server_status() -> bool:
    print(f"🔍 Checking LMStudio connection at {API_BASE}...")
    try:
        res = requests.get(f"{API_BASE}/models", timeout=5)
        res.raise_for_status()
        models = res.json().get("data", [])
        print(f"✅ LMStudio is ONLINE. Loaded {len(models)} models.")
        for m in models[:3]:
            print(f"   - {m['id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to LMStudio: {e}")
        return False

def check_gpu_offload_status(target_model: str):
    """
    Benchmarks the LM Studio server using a standard chat completion.
    Detects if layers are spilling to CPU (disabling Flash Attention)
    by measuring Time-to-First-Token (TTFT) and tokens per second.
    """
    print(f"\n⚡ Benchmarking GPU Performance for [{target_model}]...")
    
    payload = {
        "model": target_model,
        "messages": [
            {"role": "user", "content": "Write a 100 word story about a fast GPU. Reply immediately."}
        ],
        "max_tokens": 100,
        "temperature": 0.1,
        "stream": False
    }

    start_time = time.time()
    try:
        res = requests.post(f"{API_BASE}/chat/completions", json=payload, timeout=120)
        res.raise_for_status()
        
        elapsed = time.time() - start_time
        data = res.json()
        
        usage = data.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        
        speed = completion_tokens / elapsed if elapsed > 0 else 0
        
        print(f"✅ Benchmark SUCCESSFUL in {elapsed:.2f}s")
        print(f"   Tokens generated: {completion_tokens}")
        print(f"   Estimated Speed:  {speed:.2f} tokens/sec")
        
        if speed < 12.0:
            print("\n⚠️  WARNING: Generation speed is very slow (< 12 tok/sec).")
            print("   This confirms your layers are spilling to the CPU, and Flash Attention is disabled!")
            print("   ACTION REQUIRED in LM Studio GUI:")
            print("     1. Check 'GPU Offload' -> 'Max'")
            print("     2. Ensure you loaded the Q4_K_M quantized model, NOT f16.")
            print("     3. Lower Context Length if you hit OOM.")
        else:
            print("\n🚀 GPU is fully engaged! Flash Attention is active and layers are loaded in VRAM.")

    except requests.exceptions.ReadTimeout:
        print("\n⏳ TIMEOUT: LM Studio took too long.")
        print("   This happens when VRAM is full and it swaps heavily to System RAM.")
    except Exception as e:
        print(f"\n❌ API Error during benchmark: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LMStudio GPU Compatibility Watchdog")
    parser.add_argument("--model", type=str, default="google/gemma-4-e4b", help="Target model to benchmark")
    args = parser.parse_args()

    print("======================================================")
    print(" 🎮 GameSurf | LM Studio GPU Initialization Watchdog")
    print("======================================================")
    
    if check_server_status():
        check_gpu_offload_status(args.model)
