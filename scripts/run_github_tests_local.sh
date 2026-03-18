#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW_PATH=".github/workflows/test-and-lint.yml"
EVENT_NAME="push"
EVENT_PATH=""
CONTAINER_ARCH=""
PLATFORM_IMAGE="${ACT_PLATFORM_IMAGE:-ghcr.io/catthehacker/ubuntu:full-latest}"
FORCE_PULL="${ACT_FORCE_PULL:-true}"
RUNNER_TOOL_CACHE_PATH="${ACT_RUNNER_TOOL_CACHE:-/tmp/act-toolcache}"
DRY_RUN=false
LIST_JOBS=false
REUSE_CONTAINERS=false
RUN_ALL_JOBS=true
declare -a JOBS=()

usage() {
  cat <<'EOF'
Run the GitHub "Test and Lint" workflow locally with act.

Usage:
  scripts/run_github_tests_local.sh [options]

Options:
  --event <push|pull_request>     Event type to simulate (default: push)
  --event-path <file>             Custom event JSON path (default from scripts/ci-events/)
  --job <job-id>                  Run a specific workflow job (can be provided multiple times)
  --list-jobs                     List workflow jobs and exit
  --dry-run                       Show execution plan without running jobs
  --pull                          Always pull runner image(s) before running (default: enabled)
  --no-pull                       Use cached local runner image(s) when available
  --reuse                         Reuse existing act containers
  --container-arch <arch>         Container architecture (default: linux/amd64)
  --runner-tool-cache <path>      Writable tool cache path for setup-python (default: /tmp/act-toolcache)
  --platform-image <image>        Image for ubuntu-latest (default: ghcr.io/catthehacker/ubuntu:full-latest)
  -h, --help                      Show this help message

Examples:
  scripts/run_github_tests_local.sh --event push
  scripts/run_github_tests_local.sh --event pull_request
  scripts/run_github_tests_local.sh --job frontend-test --job backend-lint
  scripts/run_github_tests_local.sh --no-pull --reuse
  scripts/run_github_tests_local.sh --dry-run
EOF
}

ensure_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command not found: $cmd" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --event)
      EVENT_NAME="${2:-}"
      shift 2
      ;;
    --event-path)
      EVENT_PATH="${2:-}"
      shift 2
      ;;
    --job)
      JOBS+=("${2:-}")
      RUN_ALL_JOBS=false
      shift 2
      ;;
    --list-jobs)
      LIST_JOBS=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --pull)
      FORCE_PULL=true
      shift
      ;;
    --no-pull)
      FORCE_PULL=false
      shift
      ;;
    --reuse)
      REUSE_CONTAINERS=true
      shift
      ;;
    --container-arch)
      CONTAINER_ARCH="${2:-}"
      shift 2
      ;;
    --runner-tool-cache)
      RUNNER_TOOL_CACHE_PATH="${2:-}"
      shift 2
      ;;
    --platform-image)
      PLATFORM_IMAGE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ "$EVENT_NAME" != "push" && "$EVENT_NAME" != "pull_request" ]]; then
  echo "Error: --event must be either 'push' or 'pull_request'" >&2
  exit 1
fi

if [[ -z "$CONTAINER_ARCH" ]]; then
  CONTAINER_ARCH="${ACT_CONTAINER_ARCH:-linux/amd64}"
fi

ensure_command act
ensure_command docker

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

if [[ -z "$EVENT_PATH" ]]; then
  EVENT_PATH="$ROOT_DIR/scripts/ci-events/${EVENT_NAME}.json"
fi

if [[ ! -f "$EVENT_PATH" ]]; then
  echo "Error: event file not found: $EVENT_PATH" >&2
  exit 1
fi

ACT_CMD=(
  act
  "$EVENT_NAME"
  -W "$WORKFLOW_PATH"
  --eventpath "$EVENT_PATH"
  "--pull=${FORCE_PULL}"
  -P "ubuntu-latest=${PLATFORM_IMAGE}"
  --env "RUNNER_TOOL_CACHE=${RUNNER_TOOL_CACHE_PATH}"
  --env "AGENT_TOOLSDIRECTORY=${RUNNER_TOOL_CACHE_PATH}"
)

if [[ "$LIST_JOBS" == true ]]; then
  ACT_CMD+=(--list)
fi

if [[ "$DRY_RUN" == true ]]; then
  ACT_CMD+=(-n)
fi

if [[ "$REUSE_CONTAINERS" == true ]]; then
  ACT_CMD+=(--reuse)
fi

ACT_CMD+=(--container-architecture "$CONTAINER_ARCH")

if [[ "$RUN_ALL_JOBS" == false ]]; then
  for job in "${JOBS[@]}"; do
    if [[ -z "$job" ]]; then
      echo "Error: --job requires a non-empty value" >&2
      exit 1
    fi
    ACT_CMD+=(-j "$job")
  done
fi

echo "=== Local GitHub CI Replica ==="
echo "Repository: $ROOT_DIR"
echo "Workflow:   $WORKFLOW_PATH"
echo "Event:      $EVENT_NAME"
echo "Event file: $EVENT_PATH"
echo "Image:      $PLATFORM_IMAGE"
echo "Arch:       $CONTAINER_ARCH"
echo "Pull:       $FORCE_PULL"
echo "Tool cache: $RUNNER_TOOL_CACHE_PATH"
if [[ "$RUN_ALL_JOBS" == false ]]; then
  echo "Jobs:       ${JOBS[*]}"
else
  echo "Jobs:       all"
fi
if [[ "$DRY_RUN" == true ]]; then
  echo "Mode:       dry-run"
fi
echo

(
  cd "$ROOT_DIR"
  "${ACT_CMD[@]}"
)
