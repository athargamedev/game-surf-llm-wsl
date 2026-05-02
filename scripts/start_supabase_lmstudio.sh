#!/usr/bin/env bash
set -euo pipefail

CLI="${SUPABASE_LMSTUDIO_CLI:-/mnt/d/GithubRepos/supabasecli/bin/supabase-lmstudio}"
LMSTUDIO_BASE_URL="${STUDIO_OPENAI_BASE_URL:-${OPENAI_BASE_URL:-http://host.docker.internal:1234/v1}}"
LMSTUDIO_MODELS_ENDPOINT="${LMSTUDIO_BASE_URL%/}/models"

export OPENAI_API_KEY="${OPENAI_API_KEY:-lm-studio}"
export STUDIO_OPENAI_BASE_URL="$LMSTUDIO_BASE_URL"
export OPENAI_BASE_URL="$LMSTUDIO_BASE_URL"
export STUDIO_OPENAI_PROMPT_PREFIX="${STUDIO_OPENAI_PROMPT_PREFIX:-You are the Supabase Studio assistant. Follow the requested output format exactly. For SQL tasks, return executable PostgreSQL SQL first, then brief notes only if requested. Prefer safe migrations and avoid destructive operations unless explicitly requested.}"

if [[ -z "${STUDIO_OPENAI_MODELS:-}" ]]; then
  detected_payload="$(
    curl -fsSL "${LMSTUDIO_MODELS_ENDPOINT}" \
      | python3 -c 'import json,os,re,sys
data=json.load(sys.stdin)
all_ids=[]
for item in data.get("data", []):
  if not isinstance(item, dict):
    continue
  model_id=str(item.get("id", "")).strip()
  if model_id and model_id not in all_ids:
    all_ids.append(model_id)

chat_ids=[
  model_id for model_id in all_ids
  if not re.search(r"(text[-_])?embedding|all[-_]?minilm|bge", model_id, flags=re.IGNORECASE)
]
catalog=chat_ids or all_ids

preferred=[
  "qwen2.5-coder-7b-instruct",
  "qwen3-8b",
  "unity-coder-7b-i1",
  "llama-3.2-3b-instruct",
  "meta-llama-3-8b-instruct",
]

def first_token(value: str) -> str:
  return value.split(",", 1)[0].strip()

user_base=first_token(os.getenv("STUDIO_OPENAI_MODEL", ""))
user_adv=first_token(os.getenv("STUDIO_OPENAI_ADVANCED_MODEL", ""))

base=user_base if user_base in catalog else ""
if not base:
  for model_id in preferred:
    if model_id in catalog:
      base=model_id
      break
if not base and catalog:
  base=catalog[0]

ordered_catalog=catalog
if base:
  ordered_catalog=[base] + [model_id for model_id in catalog if model_id != base]

advanced=user_adv if user_adv in ordered_catalog else ""
if not advanced:
  for model_id in preferred:
    if model_id in ordered_catalog and model_id != base:
      advanced=model_id
      break
if not advanced:
  if len(ordered_catalog) > 1:
    advanced=ordered_catalog[1]
  elif ordered_catalog:
    advanced=ordered_catalog[0]

print(",".join(all_ids))
print(",".join(ordered_catalog))
print(base)
print(advanced)' \
      2>/dev/null || true
  )"

  mapfile -t detected_lines <<< "${detected_payload}"
  detected_all_models="${detected_lines[0]:-}"
  detected_catalog_models="${detected_lines[1]:-}"
  detected_base_model="${detected_lines[2]:-}"
  detected_advanced_model="${detected_lines[3]:-}"

  if [[ -n "${detected_catalog_models}" ]]; then
    export STUDIO_OPENAI_MODELS="${detected_catalog_models}"
    export STUDIO_OPENAI_MODEL="${detected_catalog_models}"
    export STUDIO_OPENAI_ADVANCED_MODEL="${detected_advanced_model:-$detected_base_model}"
    echo "[lmstudio] detected all models: ${detected_all_models}"
    echo "[lmstudio] chat model catalog: ${detected_catalog_models}"
    echo "[lmstudio] selected base model: ${detected_base_model}"
    echo "[lmstudio] selected advanced model: ${STUDIO_OPENAI_ADVANCED_MODEL}"
  else
    echo "[lmstudio] warning: unable to detect models from ${LMSTUDIO_MODELS_ENDPOINT}; using configured defaults."
  fi
fi

if [[ -n "${STUDIO_OPENAI_MODELS:-}" && -z "${STUDIO_OPENAI_MODEL:-}" ]]; then
  export STUDIO_OPENAI_MODEL="${STUDIO_OPENAI_MODELS}"
fi

export STUDIO_OPENAI_MODEL="${STUDIO_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export STUDIO_OPENAI_ADVANCED_MODEL="${STUDIO_OPENAI_ADVANCED_MODEL:-qwen3-8b}"

exec "$CLI" start -x storage-api,imgproxy,supavisor
