#!/bin/sh
set -eu

LOCKFILE="package-lock.json"
STAMPFILE=".deps-lock-sha"

if [ ! -f "$LOCKFILE" ]; then
  echo "Missing $LOCKFILE in /app; cannot verify dependency state."
  exec npx vite --host 0.0.0.0
fi

CURRENT_HASH="$(sha256sum "$LOCKFILE" | awk '{print $1}')"
INSTALLED_HASH=""

if [ -f "$STAMPFILE" ]; then
  INSTALLED_HASH="$(cat "$STAMPFILE")"
fi

if [ ! -d "node_modules" ] || [ "$CURRENT_HASH" != "$INSTALLED_HASH" ]; then
  echo "Installing frontend dependencies (lockfile changed or node_modules missing)..."
  npm ci
  echo "$CURRENT_HASH" > "$STAMPFILE"
fi

exec npx vite --host 0.0.0.0
