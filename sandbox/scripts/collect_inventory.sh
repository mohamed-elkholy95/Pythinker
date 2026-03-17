#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="${1:-/app/artifacts}"
mkdir -p "${OUTPUT_DIR}"

SYSTEM_INFO_FILE="${OUTPUT_DIR}/system_info.txt"
APT_FILE="${OUTPUT_DIR}/apt_packages.txt"
PIP_FILE="${OUTPUT_DIR}/pip_packages.txt"
NPM_FILE="${OUTPUT_DIR}/npm_packages.txt"
ENV_FILE="${OUTPUT_DIR}/env_vars.txt"
BIN_FILE="${OUTPUT_DIR}/bin_list.txt"
CMD_FILE="${OUTPUT_DIR}/cmd_outputs.txt"

{
  uname -a
  echo
  lscpu
  echo
  free -h
  echo
  df -h
  echo
  uptime
} > "${SYSTEM_INFO_FILE}" 2>&1 || true

if command -v dpkg >/dev/null 2>&1; then
  dpkg -l > "${APT_FILE}" 2>&1 || true
fi

if command -v python3 >/dev/null 2>&1; then
  python3 -m pip list --format=columns > "${PIP_FILE}" 2>&1 || true
fi

if command -v pnpm >/dev/null 2>&1; then
  pnpm list -g --depth 0 > "${NPM_FILE}" 2>&1 || true
elif command -v npm >/dev/null 2>&1; then
  npm list -g --depth 0 > "${NPM_FILE}" 2>&1 || true
fi

# Redact sensitive environment values
env | awk -F= '
  {
    key=$1; value="";
    for (i=2; i<=NF; i++) { value = value (i==2?"":"=") $i }
    lower=tolower(key)
    if (lower ~ /key|token|password|secret|dsn|auth|credential/) {
      print key "=REDACTED"
    } else {
      print key "=" value
    }
  }
' > "${ENV_FILE}" 2>/dev/null || true

# List available commands
if command -v compgen >/dev/null 2>&1; then
  compgen -c | sort -u > "${BIN_FILE}" 2>&1 || true
fi

{
  echo "--- Python Version ---"
  python3 --version 2>&1 || true
  echo "--- Node Version ---"
  node --version 2>&1 || true
  echo "--- Git Version ---"
  git --version 2>&1 || true
  echo "--- GH CLI Version ---"
  gh --version 2>&1 || true
  echo "--- Curl Version ---"
  curl --version 2>&1 || true
  echo "--- Chromium Version ---"
  chromium --version 2>&1 || true
} > "${CMD_FILE}" 2>&1 || true

echo "Inventory written to ${OUTPUT_DIR}"
