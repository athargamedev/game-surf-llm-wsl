#!/usr/bin/env bash
set -euo pipefail

node /usr/local/bin/runtime-configure-studio.js

exec /usr/local/bin/docker-entrypoint.sh "$@"
