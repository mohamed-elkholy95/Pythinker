#!/bin/bash

# Pythinker Container Monitoring Script
# Provides various log monitoring options

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

show_help() {
    cat << 'HELP'
╔════════════════════════════════════════════════════════════════╗
║        PYTHINKER CONTAINER MONITORING - QUICK REFERENCE        ║
╚════════════════════════════════════════════════════════════════╝

USAGE: ./monitor_containers.sh [OPTION]

OPTIONS:
  all               Monitor all containers (default)
  sandbox           Monitor sandbox only
  backend           Monitor backend only
  frontend          Monitor frontend only
  core              Monitor core services (sandbox + backend)
  infra             Monitor infrastructure (mongodb, redis, qdrant)
  stats             Show container statistics
  logs <container>  Show logs for specific container
  tail <container>  Tail logs for specific container
  errors            Show only error messages from all containers
  context           Monitor context generation specifically
  watchdog          Run backend uptime watchdog (auto-recover)
  help              Show this help message

EXAMPLES:
  ./monitor_containers.sh all           # Monitor all containers
  ./monitor_containers.sh sandbox       # Monitor sandbox only
  ./monitor_containers.sh core          # Monitor sandbox + backend
  ./monitor_containers.sh errors        # Show only errors
  ./monitor_containers.sh logs backend  # Show backend logs
  ./monitor_containers.sh tail sandbox  # Tail sandbox logs
  ./monitor_containers.sh context       # Monitor context generation
  ./monitor_containers.sh watchdog      # Auto-recover backend if it stops

KEYBOARD SHORTCUTS:
  Ctrl+C            Stop monitoring
  Ctrl+Z            Pause (resume with 'fg')

COLOR CODING:
  🟢 Green          - Sandbox
  🔵 Blue           - Backend
  🔶 Cyan           - Frontend
  🟡 Yellow         - MongoDB
  🟣 Purple         - Redis
  ⚪ White          - Qdrant
  ⚫ Gray           - Search services

HELP
}

list_container_names() {
    docker ps -a --format "{{.Names}}"
}

service_aliases() {
    case "$1" in
        frontend)
            echo "frontend frontend-dev"
            ;;
        *)
            echo "$1"
            ;;
    esac
}

resolve_container_name() {
    local logical_service="$1"
    local names
    names="$(list_container_names)"

    local service
    for service in $(service_aliases "$logical_service"); do
        local candidate_main="pythinker-main-${service}-1"
        local candidate_legacy="pythinker-${service}-1"
        if echo "$names" | grep -Fxq "$candidate_main"; then
            echo "$candidate_main"
            return 0
        fi
        if echo "$names" | grep -Fxq "$candidate_legacy"; then
            echo "$candidate_legacy"
            return 0
        fi
    done

    for service in $(service_aliases "$logical_service"); do
        local fallback
        fallback="$(echo "$names" | grep -E "(^|-)${service}-1$" | head -n 1)"
        if [ -n "$fallback" ]; then
            echo "$fallback"
            return 0
        fi
    done

    return 1
}

require_container_name() {
    local logical_service="$1"
    local container
    container="$(resolve_container_name "$logical_service")" || {
        echo "No running container found for service '$logical_service'."
        echo "Available containers:"
        docker ps --format "table {{.Names}}\t{{.Status}}"
        return 1
    }
    echo "$container"
}

monitor_all() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║           MONITORING ALL PYTHINKER CONTAINERS                  ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    ./dev.sh logs -f --tail=50
}

monitor_sandbox() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              MONITORING SANDBOX CONTAINER                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    local container
    container="$(require_container_name sandbox)" || return 1

    echo "Container: ${container}"
    echo "Focus: Context generation, CDP/Chrome, supervisord"
    echo ""

    docker logs -f --tail=50 "${container}"
}

monitor_backend() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              MONITORING BACKEND CONTAINER                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    local container
    container="$(require_container_name backend)" || return 1

    echo "Container: ${container}"
    echo "Focus: API requests, context loading, agent execution"
    echo ""

    docker logs -f --tail=50 "${container}"
}

monitor_frontend() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              MONITORING FRONTEND CONTAINER                     ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    local container
    container="$(require_container_name frontend)" || return 1

    echo "Container: ${container}"
    echo "Focus: Vite dev server, HMR, build errors"
    echo ""

    docker logs -f --tail=50 "${container}"
}

monitor_core() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║         MONITORING CORE SERVICES (Sandbox + Backend)          ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    docker-compose -f docker-compose-development.yml logs -f --tail=50 sandbox backend
}

monitor_infra() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║      MONITORING INFRASTRUCTURE (MongoDB, Redis, Qdrant)        ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    docker-compose -f docker-compose-development.yml logs -f --tail=20 mongodb redis qdrant
}

show_stats() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              CONTAINER STATISTICS & STATUS                     ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""

    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}" \
        $(docker ps --filter "name=pythinker" --format "{{.Names}}")

    echo ""
    echo "Container Health:"
    docker ps --filter "name=pythinker" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

monitor_errors() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              MONITORING ERRORS FROM ALL CONTAINERS             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Filtering for: ERROR, error, Exception, CRITICAL, FATAL, Failed"
    echo ""

    ./dev.sh logs -f --tail=100 | grep -iE "(error|exception|critical|fatal|failed|traceback)"
}

monitor_context() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║           MONITORING CONTEXT GENERATION (Sandbox)             ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Filtering for: context, sandbox_context, environment scan"
    echo ""

    local container
    container="$(require_container_name sandbox)" || return 1
    docker logs -f --tail=100 "${container}" | grep -iE "(context|environment|scan|generate|stdlib|builtin)"
}

show_logs() {
    local logical_service="$1"
    local container
    container="$(require_container_name "$logical_service")" || return 1
    echo "Showing logs for: ${container}"
    docker logs "${container}"
}

tail_logs() {
    local logical_service="$1"
    local container
    container="$(require_container_name "$logical_service")" || return 1
    echo "Tailing logs for: ${container}"
    docker logs -f --tail=50 "${container}"
}

run_backend_watchdog() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║             BACKEND UPTIME WATCHDOG (AUTO-RECOVER)            ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Watching: pythinker-backend-1"
    echo "Behavior: auto-start/restart backend on repeated health failures"
    echo "Stop with: Ctrl+C"
    echo ""

    "${SCRIPT_DIR}/scripts/backend_watchdog.sh"
}

# Main script logic
case "${1:-all}" in
    all)
        monitor_all
        ;;
    sandbox)
        monitor_sandbox
        ;;
    backend)
        monitor_backend
        ;;
    frontend)
        monitor_frontend
        ;;
    core)
        monitor_core
        ;;
    infra)
        monitor_infra
        ;;
    stats)
        show_stats
        ;;
    errors)
        monitor_errors
        ;;
    context)
        monitor_context
        ;;
    watchdog)
        run_backend_watchdog
        ;;
    logs)
        show_logs "$2"
        ;;
    tail)
        tail_logs "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown option: $1"
        echo "Run './monitor_containers.sh help' for usage information"
        exit 1
        ;;
esac
