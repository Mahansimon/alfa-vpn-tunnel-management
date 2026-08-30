#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV="$ROOT/.env"
umask 077
touch "$ENV"
if ! grep -qE '^POSTGRES_PASSWORD=.+' "$ENV"; then
  PW="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 32 || true)"
  [ -n "$PW" ] || PW="$(date +%s)-Alfa-DB"
  printf 'POSTGRES_PASSWORD=%s\n' "$PW" >> "$ENV"
fi
chmod 600 "$ENV"
echo "Environment ready: $ENV"
