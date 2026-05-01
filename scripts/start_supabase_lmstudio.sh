#!/usr/bin/env bash
set -euo pipefail

CLI="${SUPABASE_LMSTUDIO_CLI:-/mnt/d/GithubRepos/supabasecli/bin/supabase-lmstudio}"

exec "$CLI" start -x storage-api,imgproxy,supavisor
