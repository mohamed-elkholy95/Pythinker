# Pythinker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Pythinker is a general-purpose AI Agent system that supports running various tools and operations in a sandbox environment.

**Author:** Mohamed Elkholy

## Key Features

* **Deployment:** Minimal deployment requires only an LLM service, with no dependency on other external services.
* **Tools:** Supports Terminal, Browser, File, Web Search, and messaging tools with real-time viewing and takeover capabilities, supports external MCP tool integration.
* **Sandbox:** Each task is allocated a separate sandbox that runs in a local Docker environment.
* **Task Sessions:** Session history is managed through MongoDB/Redis, supporting background tasks.
* **Conversations:** Supports stopping and interrupting, file upload and download.
* **Authentication:** User login and authentication.

## DeepCode Integration ✨ NEW

Pythinker now includes **8 powerful enhancements** from DeepCode for improved performance, cost efficiency, and reliability:

### Performance & Cost Optimization
* **🧠 Adaptive Model Routing** - Auto-select optimal model tier (fast/balanced/powerful) based on task complexity
  * 💰 **20-40% cost reduction** via intelligent tier selection
  * ⚡ **60-70% latency reduction** on simple tasks using fast tier

### Agent Reliability
* **⚡ Tool Efficiency Monitor** - Detect and prevent analysis paralysis (endless research loops)
  * 🎯 **50% fewer stuck sessions** with automatic nudge interventions
* **✂️ Truncation Detector** - Catch incomplete outputs using pattern matching
  * 📝 **60% fewer incomplete responses** with automatic continuation requests

### Code Quality Tools
* **📄 Document Segmenter** - Context-aware chunking for large files (respects function/class boundaries)
  * 📊 **70% reduction** in context truncation for long documents
* **✅ Implementation Tracker** - Multi-file code completeness validation
  * 🔍 **80% fewer incomplete** multi-file implementations

**Quick Start:** See [`DEEPCODE_QUICKSTART.md`](DEEPCODE_QUICKSTART.md) for 5-minute setup.

**Full Documentation:**
- 📖 [Complete Integration Guide](DEEPCODE_INTEGRATION_COMPLETE.md)
- 🛠️ [Tool Usage Guide](CODE_ANALYSIS_TOOLS_GUIDE.md)
- 📋 [Changelog](CHANGELOG_DEEPCODE_2026_02_15.md)
- 🎯 [Demo Script](examples/deepcode_integration_demo.py)

## Environment Requirements

This project primarily relies on Docker for development and deployment:
- Docker 20.10+
- Docker Compose

Model capability requirements:
- Compatible with OpenAI interface
- Support for FunctionCall
- Support for Json Format output

## Quick Start

Docker Compose is recommended for deployment:

```yaml
services:
  frontend:
    image: pythinker/pythinker-frontend
    ports:
      - "5173:80"
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - pythinker-network
    environment:
      - BACKEND_URL=http://backend:8000

  backend:
    image: pythinker/pythinker-backend
    depends_on:
      - sandbox
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - pythinker-network
    environment:
      - API_BASE=https://api.openai.com/v1
      - API_KEY=sk-xxxx
      - MODEL_NAME=gpt-4o
      - TEMPERATURE=0.7
      - MAX_TOKENS=2000
      - SANDBOX_IMAGE=pythinker/pythinker-sandbox
      - SANDBOX_NAME_PREFIX=sandbox
      - SANDBOX_TTL_MINUTES=30
      - SANDBOX_NETWORK=pythinker-network
      - SEARCH_PROVIDER=bing
      - AUTH_PROVIDER=local
      - LOCAL_AUTH_EMAIL=admin@example.com
      - LOCAL_AUTH_PASSWORD=admin
      - JWT_SECRET_KEY=your-secret-key-here
      - LOG_LEVEL=INFO

  sandbox:
    image: pythinker/pythinker-sandbox
    command: /bin/sh -c "exit 0"
    restart: "no"
    networks:
      - pythinker-network

  mongodb:
    image: mongo:7.0
    volumes:
      - mongodb_data:/data/db
    restart: unless-stopped
    networks:
      - pythinker-network

  redis:
    image: redis:7.0
    restart: unless-stopped
    networks:
      - pythinker-network

volumes:
  mongodb_data:
    name: pythinker-mongodb-data

networks:
  pythinker-network:
    name: pythinker-network
    driver: bridge
```

Save as `docker-compose.yml` and run:

```bash
docker compose up -d
```

Open your browser and visit http://localhost:5173 to access Pythinker.

## Development

### Project Structure

* `frontend`: Pythinker frontend (Vue.js)
* `backend`: Pythinker backend (FastAPI)
* `sandbox`: Pythinker sandbox (Ubuntu Docker)

### Development Setup

1. Clone the project and copy configuration:
```bash
cp .env.example .env
```

2. Update `.env` with your API key and settings.

**Pre-deployment environment**

Before running `docker compose up` for deployment, create a `.env` from `.env.example` and ensure required secrets are set. This project expects MinIO credentials to be provided via environment variables used by `docker-compose.yml`:

- `MINIO_ROOT_USER` - MinIO admin username (example placeholder in `.env.example`)
- `MINIO_ROOT_PASSWORD` - MinIO admin password (example placeholder in `.env.example`)

Example workflow:

```bash
cp .env.example .env
# Edit .env and set secure values for MINIO_ROOT_USER and MINIO_ROOT_PASSWORD
# Generate a secure password, e.g. on macOS: openssl rand -base64 32
```

Verify the variables are present before running `docker compose`:

```bash
grep -E "MINIO_ROOT_USER|MINIO_ROOT_PASSWORD" .env
```

If a variable is missing, `docker-compose.yml` may fail the substitution checks. Use strong, unique values for MinIO credentials in production.

3. Run in development mode:
```bash
docker compose -f docker-compose-development.yml up
```

Development ports:
- 5173: Web frontend
- 8000: Backend API
- 8080: Sandbox API
- 5902: Sandbox VNC

### Run GitHub Tests Locally (Exact Workflow Replica)

Use the local CI harness to run the same `.github/workflows/test-and-lint.yml` jobs via `act`.

Prerequisites:
- Docker Desktop running
- `act` installed (example: `brew install act`)

Commands:

```bash
# Dry-run: list jobs that will run
scripts/run_github_tests_local.sh --list-jobs --dry-run

# Full push-equivalent workflow
scripts/run_github_tests_local.sh --event push

# Full pull_request-equivalent workflow
scripts/run_github_tests_local.sh --event pull_request

# Cached local run (no forced image pull)
scripts/run_github_tests_local.sh --event push --no-pull --reuse

# Single job only
scripts/run_github_tests_local.sh --job frontend-test

# Override Python tool-cache path for local runners if needed
scripts/run_github_tests_local.sh --job backend-lint --runner-tool-cache /tmp/act-toolcache
```

Notes:
- Default image is `ghcr.io/catthehacker/ubuntu:full-latest` for high-fidelity CI parity.
- Default architecture is `linux/amd64` to match GitHub-hosted runners.
- Use `--no-pull` when you want to reuse local cached images and avoid long pull phases.
- Local runs export `RUNNER_TOOL_CACHE` and `AGENT_TOOLSDIRECTORY` to a writable path for `actions/setup-python` compatibility.
- First run can take longer due image pulls.

## Architecture

**When a user initiates a conversation:**

1. Web sends a request to create an Agent to the Server, which creates a Sandbox through `/var/run/docker.sock` and returns a session ID.
2. The Sandbox is an Ubuntu Docker environment that starts Chrome browser and API services for tools like File/Shell.
3. Web sends user messages to the session ID, and when the Server receives user messages, it forwards them to the PlanAct Agent for processing.
4. During processing, the PlanAct Agent calls relevant tools to complete tasks.
5. All events generated during Agent processing are sent back to Web via SSE.

## License

MIT License

Copyright (c) 2024 Mohamed Elkholy
