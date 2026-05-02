#!/usr/bin/env python
"""Compatibility wrapper for the canonical NotebookLM workflow script."""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[4]
    target = root / ".codex" / "skills" / "notebooklm-npc-datasets" / "scripts" / "notebooklm_dataset_workflow.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
