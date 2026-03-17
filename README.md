<div align="center">

<img src="frontend/public/icon.svg" alt="Pythinker" width="120" />

# Pythinker

### AI Agent Platform for Research, Code, and Automation

[![CI](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/test-and-lint.yml/badge.svg?branch=main)](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/test-and-lint.yml)
[![Docker](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/docker-build-and-push.yml/badge.svg)](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/docker-build-and-push.yml)
[![Security](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/security-scan.yml/badge.svg)](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/security-scan.yml)
[![GitHub issues](https://img.shields.io/github/issues/mohamed-elkholy95/Pythinker)](https://github.com/mohamed-elkholy95/Pythinker/issues)
[![GitHub stars](https://img.shields.io/github/stars/mohamed-elkholy95/Pythinker)](https://github.com/mohamed-elkholy95/Pythinker/stargazers)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-2496ED.svg)](https://docker.com)
[![Scrapling](https://img.shields.io/badge/Scraping-Scrapling-blue)](https://github.com/D4Vinci/Scrapling)

*An open-source, self-hosted AI agent that can browse the web, write & execute code, search the internet, manage files, and deliver polished research reports — all from a beautiful real-time interface.*

Inspired by [Manus AI](https://manus.im) and built with ideas from [OpenManus](https://github.com/manusai/OpenManus) and [Nanobot](https://github.com/ArcadeAI/nanobot).

**Author:** [Mohamed Elkholy](https://github.com/mohamed-elkholy95)

</div>

---

## What Makes Pythinker Different

| Feature | Description |
|---------|-------------|
| **43+ Built-in Tools** | File, browser, shell, search, code, messaging, automation — the agent picks the right tool for every step |
| **Live Browser Streaming** | Watch the agent browse in real-time via CDP screencast — take over control at any moment |
| **Beautiful Report Generation** | Automatically produces structured, citation-rich research reports with charts and references |
| **Sandboxed Execution** | Every task runs in an isolated Docker container with Chrome, Python, Node.js, and shell access |
| **Multi-Model Support** | Works with any OpenAI-compatible API — GPT-4o, Claude, DeepSeek, Kimi, GLM, local models, and more |
| **Intelligent Web Scraping** | Three-tier scraping with automatic escalation — HTTP, dynamic rendering, stealth browser (powered by Scrapling) |
| **Telegram Integration** | Full-featured Telegram bot gateway with inline buttons, file sharing, and streaming responses |
| **MCP Tool Integration** | Extend capabilities with external Model Context Protocol servers |
| **PlanAct Agent Architecture** | Intelligent planning, execution, reflection, and verification pipeline with 108 agent modules |
| **Hybrid Memory System** | Semantic search over past sessions via Qdrant (BM25 + dense retrieval with RRF fusion) |

---

## Architecture

```
+-----------------------------------------------------------------------+
|                         PYTHINKER PLATFORM                            |
|                                                                       |
|  +----------+   +---------------------------------------------------+ |
|  | Frontend |   |                Backend (FastAPI)                   | |
|  |  Vue 3   |<->|  PlanAct Agent  .  43+ Tools  .  SSE Streaming    | |
|  | TypeScript|   |  Model Router   .  DDD Services . Report Gen     | |
|  +----------+   +--------------+-------------------+----------------+ |
|                                |                   |                  |
|  +----------+   +--------------v--+   +------------v--------------+  |
|  | Telegram |   |    Sandbox(es)  |   |       Data Layer          |  |
|  | Gateway  |   |  Ubuntu Docker  |   |  MongoDB . Redis . Qdrant |  |
|  | (Nanobot)|   |  Chrome . Python|   |  MinIO (Object Storage)   |  |
|  +----------+   +-----------------+   +---------------------------+  |
+-----------------------------------------------------------------------+
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Vue 3, TypeScript, Vite, TipTap, Monaco Editor, xterm.js, Plotly |
| **Backend** | FastAPI, Python 3.12+, Pydantic v2, Beanie ODM, SSE, WebSockets |
| **Agent** | PlanAct pipeline, adaptive model routing, tool efficiency monitoring, reflection & verification |
| **Web Scraping** | [Scrapling](https://github.com/D4Vinci/Scrapling) (tiered: HTTP/TLS impersonation → dynamic rendering → stealth browser), Playwright |
| **Sandbox** | Ubuntu Docker, Chromium, Playwright, Supervisord, CDP screencast |
| **Messaging** | Nanobot multi-channel gateway (Telegram, Slack, Discord, DingTalk, Feishu) |
| **Database** | MongoDB 7.0 (sessions & state), Redis 8 (cache & coordination) |
| **Vector Search** | Qdrant (semantic memory, hybrid BM25 + dense retrieval) |
| **Object Storage** | MinIO (file uploads, artifacts, report assets) |
| **CI/CD** | GitHub Actions (lint, test, security scan, Docker build) |
| **Monitoring** | Prometheus, Grafana, Loki, Promtail |

---

## Tool Categories

The agent has access to **43+ tools** organized into 10 categories:

| Category | Tools | What They Do |
|----------|-------|-------------|
| **File** | read, write, list, search, upload, download | Full filesystem access within the sandbox |
| **Browser** | navigate, click, type, screenshot, scroll, evaluate JS | Headless Chrome with live CDP streaming |
| **Search** | web search, scrape, extract | Internet research with multiple providers (Tavily, Serper, Exa) |
| **Shell** | execute, background, interactive | Full terminal access with real-time output |
| **Message** | ask user, notify, report | Communication and deliverable generation |
| **MCP** | external tool servers | Extensible via Model Context Protocol |
| **Code** | analyze, refactor, test | Code intelligence and manipulation |
| **Plan** | create plan, update step, checkpoint | Structured task planning and tracking |
| **Automation** | batch operations, workflows | Multi-step automated sequences |
| **System** | health, config, diagnostics | Platform management and monitoring |

---

## Quick Start

### Prerequisites

- Docker 20.10+ and Docker Compose
- An LLM API key (any OpenAI-compatible provider)

### 1. Clone & Configure

```bash
git clone https://github.com/mohamed-elkholy95/Pythinker.git
cd Pythinker
cp .env.example .env
```

Edit `.env` with your API credentials:

```env
# LLM Configuration (any OpenAI-compatible API)
LLM_PROVIDER=openai
API_KEY=sk-your-api-key
API_BASE=https://api.openai.com/v1
MODEL_NAME=gpt-4o
TEMPERATURE=0.7
MAX_TOKENS=8192

# Security (required — change these)
SANDBOX_API_SECRET=your-secret-here
JWT_SECRET_KEY=your-jwt-secret
```

### 2. Start

```bash
docker compose up -d
```

### 3. Open

Visit **http://localhost:5174** — log in and start your first research task.

---

## How It Works

### The PlanAct Pipeline

When you send a message, Pythinker's agent follows an intelligent pipeline:

```
User Message
    │
    v
┌──────────────┐    ┌──────────────────┐    ┌────────────────┐    ┌──────────────┐
│   Planning   │───>│    Execution     │───>│   Reflection   │───>│ Verification │
│              │    │                  │    │                │    │              │
│ • Analyze    │    │ • Run tools      │    │ • Evaluate     │    │ • Hallucina- │
│ • Decompose  │    │ • Browse web     │    │   quality      │    │   tion check │
│ • Route model│    │ • Execute code   │    │ • Critic review│    │ • Citation   │
│ • Checkpoint │    │ • Search & scrape│    │ • Self-correct │    │   integrity  │
└──────────────┘    └──────────────────┘    └────────────────┘    └──────────────┘
```

### Agent Architecture Deep Dive

Pythinker's agent is not a simple prompt-and-respond loop. It is a modular, introspective system with **108 specialized modules** across dedicated subsystems:

**Planning** — The Planner decomposes user requests into structured multi-step plans with checkpoints. A complexity assessor routes tasks to the appropriate model tier before planning begins.

**Execution** — The Step Executor runs each plan step, selecting from 43+ tools. A parallel executor can run independent steps concurrently. Tool efficiency is monitored to detect and break analysis paralysis (5+ consecutive reads without writes).

**Reasoning & Reflection** — After execution, a reflection layer evaluates output quality. A critic agent provides adversarial review. Chain-of-verification cross-checks claims against sources.

**Memory** — Conversation context, research traces, and tool results are managed through a sliding-window context system with role-scoped memory. Qdrant provides semantic search over past sessions using hybrid BM25 + dense retrieval with Reciprocal Rank Fusion (RRF).

**Self-Healing** — A stuck detector identifies when the agent is looping. A self-healing loop attempts recovery strategies. Error pattern analysis learns from failures to avoid them in future runs.

**Verification** — Hallucination detection (LLM-as-Judge), citation integrity checking, grounding validation, and output coverage validation ensure the final deliverable is accurate and well-sourced.

**Document Intelligence** — A context-aware document segmenter uses AST-based boundary detection to chunk long documents without splitting mid-function. An implementation tracker validates multi-file code completeness via AST + pattern analysis.

**Security** — Content safety gates, security assessors, and compliance gates run before any output reaches the user.

### Web Scraping Pipeline

Pythinker uses [Scrapling](https://github.com/D4Vinci/Scrapling) as its primary web scraping engine, providing a three-tier escalation strategy that balances speed with stealth:

| Tier | Engine | When Used |
|------|--------|-----------|
| **Tier 1** | HTTP + TLS impersonation (`curl_cffi`) | Default — fast, low overhead |
| **Tier 2** | Dynamic rendering (headless browser) | JavaScript-heavy pages |
| **Tier 3** | Stealth browser (`Patchright`) | Anti-bot protected sites |

The agent's scraper automatically escalates through tiers when a lower tier fails (blocked, empty content, CAPTCHA detected). This is implemented via the domain `Scraper` Protocol with a clean port/adapter boundary — the domain layer never imports Scrapling directly.

### Real-Time Features

- **SSE Event Streaming** — Every agent action streams to the UI in real-time
- **Live Browser View** — Watch the agent browse via CDP screencast; click to take over
- **Live Terminal** — See shell commands execute with real-time output via xterm.js
- **Progress Tracking** — Visual planning bar, step indicators, and tool timeline
- **File Preview** — In-app code viewer with Monaco Editor and syntax highlighting

### Adaptive Model Routing

Pythinker intelligently routes requests to different model tiers based on task complexity:

- **Fast tier** — Simple queries, quick responses (60-70% latency reduction)
- **Balanced tier** — Standard research and coding tasks
- **Powerful tier** — Complex multi-step reasoning and report generation

---

## Telegram Bot

Pythinker includes a multi-channel messaging gateway powered by [Nanobot](https://github.com/ArcadeAI/nanobot):

- Start research tasks from Telegram with `/research`
- Receive streaming responses with inline action buttons
- Upload and download files directly
- Share reports and artifacts as PDF
- Supports Telegram, Slack, Discord, DingTalk, Feishu, and more

Configure in `.env`:

```env
CHANNEL_GATEWAY_ENABLED=true
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHANNEL_ENABLED=true
```

---

## Security

- **Sandboxed execution** — Each task runs in an isolated Docker container with resource limits
- **Security-hardened containers** — `no-new-privileges`, `cap_drop: ALL`, minimal capabilities
- **No direct sandbox access** — All browser/terminal access is proxied through authenticated backend endpoints
- **JWT authentication** — Secure user sessions with configurable auth providers
- **Secret scanning** — TruffleHog + GitHub secret scanning in CI
- **Dependency auditing** — pip-audit and npm audit run automatically
- **Network isolation** — Internal services run on private Docker networks
- **OWASP security headers** — Content-Security-Policy, HSTS, X-Frame-Options on all responses
- **Container scanning** — Trivy vulnerability scanning in CI pipeline

See [SECURITY.md](SECURITY.md) for our vulnerability reporting policy.

---

## Development

### Project Structure

```
Pythinker/
├── frontend/          # Vue 3 + TypeScript + Vite
├── backend/           # FastAPI + Python 3.12 + DDD architecture
│   ├── app/
│   │   ├── core/          # Configuration, settings, lifespan
│   │   ├── domain/        # Models, services, agents (108 modules), tools
│   │   ├── application/   # Use case orchestration, DTOs
│   │   ├── infrastructure/# External integrations (LLM, DB, browser, scraper)
│   │   └── interfaces/    # API routes, WebSocket handlers
│   ├── nanobot/           # Multi-channel messaging gateway (vendored)
│   ├── scripts/           # Utility & migration scripts
│   └── tests/             # 3,800+ tests
├── sandbox/           # Ubuntu Docker sandbox with Chrome
├── grafana/           # Dashboards & monitoring configs
├── scripts/           # Utility scripts
└── docs/              # Architecture docs & guides
```

### Running Locally

```bash
# Development mode with hot reload
docker compose up --watch

# Ports:
#   5174 -> Frontend (Vite dev server)
#   8000 -> Backend API
#   8083 -> Sandbox API (localhost only)
```

### Testing

```bash
# Backend
cd backend
ruff check . && ruff format --check .   # Lint
pytest tests/ -v --tb=short             # Tests

# Frontend
cd frontend
bun install
bun run lint                             # ESLint
bun run type-check                       # TypeScript
bun run test:run                         # Vitest
```

---

## Monitoring

Pythinker ships with a full observability stack:

- **Prometheus** — Metrics collection (SSE connections, sandbox health, API latency, tool efficiency)
- **Grafana** — Pre-configured dashboards
- **Loki + Promtail** — Log aggregation and search

```bash
docker compose -f docker-compose-monitoring.yml up -d
# Grafana: http://localhost:3000
```

---

## Configuration

All configuration is via `.env`. Key sections:

| Category | Variables | Description |
|----------|----------|-------------|
| **LLM** | `API_KEY`, `API_BASE`, `MODEL_NAME` | Primary model configuration |
| **Fast Model** | `FAST_MODEL` | Optional fast-tier model for simple tasks |
| **Search** | `SEARCH_PROVIDER`, `TAVILY_API_KEY` | Web search provider |
| **Auth** | `AUTH_PROVIDER`, `JWT_SECRET_KEY` | Authentication settings |
| **Sandbox** | `SANDBOX_IMAGE`, `SANDBOX_LIFECYCLE_MODE` | Container lifecycle |
| **Telegram** | `TELEGRAM_BOT_TOKEN` | Bot gateway |
| **Storage** | `MINIO_ROOT_USER/PASSWORD` | Object storage |
| **Multi-Key** | `*_API_KEY`, `*_API_KEY_2`, `*_API_KEY_3` | API key rotation with failover |

See [`.env.example`](.env.example) for the complete reference with documentation.

---

## Acknowledgments

Pythinker is inspired by and builds upon ideas from these projects:

- **[Manus AI](https://manus.im)** — The original vision of an AI agent that can browse, code, and deliver research autonomously. Pythinker's PlanAct pipeline and live browser streaming are directly inspired by Manus.
- **[OpenManus](https://github.com/manusai/OpenManus)** — The open-source Manus implementation that demonstrated the feasibility of a self-hosted agent with sandbox isolation.
- **[Nanobot](https://github.com/ArcadeAI/nanobot)** — Multi-channel AI agent framework. Pythinker vendors Nanobot as its Telegram/Slack/Discord messaging gateway, bridging the MessageBus to Pythinker's AgentService.
- **[Scrapling](https://github.com/D4Vinci/Scrapling)** — Intelligent web scraping library with TLS fingerprinting, anti-bot evasion, and tiered fetching. Pythinker uses Scrapling as its primary scraping engine with automatic tier escalation (HTTP → dynamic → stealth).
- **[browser-use](https://github.com/browser-use/browser-use)** — Browser automation library used for autonomous multi-step web workflows.
- **[Playwright](https://playwright.dev)** — Browser control and CDP screencast streaming.
- **[Qdrant](https://qdrant.tech)** — Vector search engine powering Pythinker's hybrid semantic memory system.

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:

- Development setup
- Code style and commit conventions
- Pull request process
- Architecture overview

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

---

## License

Copyright (c) 2024-2026 [Mohamed Elkholy](https://github.com/mohamed-elkholy95)
