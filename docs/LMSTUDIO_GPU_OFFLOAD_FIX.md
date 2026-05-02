# LM Studio GPU Offload & Flash Attention Fix

## The Problem: CPU Layer Spillover
You encountered the following error in the LM Studio logs:
```
sched_reserve: layer 24 is assigned to device CPU but the Flash Attention tensor is assigned to device CUDA0
sched_reserve: Flash Attention was auto, set to disabled
```

### Why does this happen?
This is a **package compatibility issue** between LM Studio's execution engine (llama.cpp) and Flash Attention. 
Flash Attention *only* works if **100% of the model layers are loaded onto the GPU (CUDA)**.
When LM Studio realizes your VRAM is running low (e.g., hitting the 6GB limit of your RTX 3060), it automatically spills the remaining layers (like layer 24) to the CPU. Because the model is now split between CPU and GPU, Flash Attention crashes/disables, causing a massive drop in tokens/second.

## The Concise Solution

To ensure **full GPU power** and identify offload maximums, you must explicitly configure LM Studio rather than relying on its "Auto" settings.

### 1. Lock GPU Offload to MAX
Open LM Studio on your host machine:
1. Go to the **Settings (Gear Icon)** -> **Hardware / GPU**.
2. Change **GPU Offload** from `Auto` to `Max`.
   *(If you get an OOM error, it means the model is physically too large for 6GB VRAM, which is better than silently falling back to slow CPU).*

### 2. Force Flash Attention
1. In the right-hand panel of the Chat/Server interface, scroll down to **Advanced Configuration**.
2. Ensure **Flash Attention** is checked `[✓] ON`.

### 3. Use the Correct Quantization (CRITICAL for 6GB VRAM)
Gemma 4 E4B requires ~8GB of VRAM if loaded in `fp16` precision. 
To fit it into your RTX 3060 (6GB), you MUST load the `Q4_K_M` quantized version.
1. Check your loaded model list. If you see `gemma-4-e4b@f16`, **unload it**.
2. Load `gemma-4-e4b@q4_k_m`. This uses only ~2.5GB of VRAM, leaving plenty of room for a large context window without spilling to the CPU.

### 4. Monitor with Watchdog
We have created `scripts/lmstudio_gpu_watchdog.py`. Run this script anytime to benchmark the server. If it detects a massive drop in speed (under 10 tokens/sec), it will warn you that layers have spilled to the CPU and Flash Attention has been disabled.
