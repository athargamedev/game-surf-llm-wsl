# Skills Catalog (Machine-Readable)

## Skills (Loadable by Agent)

```yaml
- name: notebooklm
  path: /root/.claude/skills/notebooklm/SKILL.md
  triggers:
    - /notebooklm
    - use notebooklm
    - notebooklm (tool name mention)
  loadable_by_agent: true
  scope: global
  capabilities:
    - create_notebooks
    - add_sources
    - chat_with_content
    - generate_artifacts
    - download_artifacts
    - web_search

- name: notebooklm-npc-datasets
  path: /root/.claude/skills/notebooklm-npc-datasets/SKILL.md
  triggers:
    - notebooklm-npc-datasets
    - NotebookLM direct JSONL batches
  loadable_by_agent: true
  scope: global
  capabilities:
    - generate_notebooklm_prompts
    - import_jsonl_batches
    - validate_dedup_splits
    - run_lora_smoke_training

- name: notebooklm-npc-datasets
  path: /root/Game_Surf/Tools/LLM_WSL/.codex/skills/notebooklm-npc-datasets/SKILL.md
  triggers:
    - notebooklm-npc-datasets
    - NotebookLM direct JSONL batches
  loadable_by_agent: true
  scope: project
  capabilities:
    - generate_notebooklm_prompts
    - import_jsonl_batches
    - validate_dedup_splits
    - run_lora_smoke_training

- name: npc-model-tuning
  path: /root/Game_Surf/Tools/LLM_WSL/.codex/skills/npc-model-tuning/SKILL.md
  triggers:
    - npc-model-tuning
    - NPC Model Tuning
    - local LLM training workflow
  loadable_by_agent: true
  scope: project
  capabilities:
    - manage_lm_studio
    - tune_npc_generation
    - generate_npc_dataset
    - run_unsloth_finetuning
    - evaluate_outputs
    - sync_to_unity

- name: notebooklm
  path: /root/.claude/skills/notebooklm/SKILL.md
  triggers:
    - notebooklm
    - /notebooklm
  loadable_by_agent: true
  scope: global
  capabilities:
    - create_notebooks
    - add_sources
    - chat_with_content
    - generate_artifacts
```

## Activate Command Reference

To activate a skill in conversation:
- Say "load skill notebooklm" or use trigger phrase
- Skills inject their full instructions into context

## Scope Definitions

- `global`: Available for all projects
- `project`: Specific to Game_Surf/LLM_WSL