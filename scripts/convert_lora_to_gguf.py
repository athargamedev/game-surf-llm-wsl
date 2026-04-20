#!/usr/bin/env python
"""Convert a PEFT LoRA adapter to the llama.cpp GGUF adapter format.

This project keeps PEFT adapters for training artifacts, but the WSL test
server uses llama.cpp. llama.cpp must load a converted LoRA GGUF file, not the
raw `adapter_model.safetensors` file.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


CONVERTER = Path("/root/.unsloth/llama.cpp/convert_lora_to_gguf.py")


def main() -> int:
    if not CONVERTER.exists():
        print(f"Unsloth llama.cpp converter not found: {CONVERTER}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(CONVERTER.parent))
    sys.argv[0] = str(CONVERTER)
    runpy.run_path(str(CONVERTER), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
