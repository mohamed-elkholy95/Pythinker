#!/bin/bash

# Pythinker Container Monitoring Script
# Provides various log monitoring options

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
  help              Show this help message

EXAMPLES:
  ./monitor_containers.sh all           # Monitor all containers
  ./monitor_containers.sh sandbox       # Monitor sandbox only
  ./monitor_containers.sh core          # Monitor sandbox + backend
  ./monitor_containers.sh errors        # Show only errors
  ./monitor_containers.sh logs backend  # Show backend logs
  ./monitor_containers.sh tail sandbox  # Tail sandbox logs
  ./monitor_containers.sh context       # Monitor context generation

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
    echo "Container: pythinker-sandbox-1"
    echo "Focus: Context generation, VNC, Chrome, supervisord"
    echo ""

    docker logs -f --tail=50 pythinker-sandbox-1
}

monitor_backend() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              MONITORING BACKEND CONTAINER                      ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Container: pythinker-backend-1"
    echo "Focus: API requests, context loading, agent execution"
    echo ""

    docker logs -f --tail=50 pythinker-backend-1
}

monitor_frontend() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║              MONITORING FRONTEND CONTAINER                     ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Container: pythinker-frontend-dev-1"
    echo "Focus: Vite dev server, HMR, build errors"
    echo ""

    docker logs -f --tail=50 pythinker-frontend-dev-1
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

    docker logs -f --tail=100 pythinker-sandbox-1 | grep -iE "(context|environment|scan|generate|stdlib|builtin)"
}

show_logs() {
    local container=$1
    echo "Showing logs for: pythinker-${container}-1"
    docker logs pythinker-${container}-1
}

tail_logs() {
    local container=$1
    echo "Tailing logs for: pythinker-${container}-1"
    docker logs -f --tail=50 pythinker-${container}-1
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
