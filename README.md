<div align="center">

# 🧠 Pythinker

### AI Agent Platform for Research, Code, and Automation

[![CI](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/test-and-lint.yml/badge.svg)](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/test-and-lint.yml)
[![Docker](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/docker-build-and-push.yml/badge.svg)](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/docker-build-and-push.yml)
[![Security](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/security-scan.yml/badge.svg)](https://github.com/mohamed-elkholy95/Pythinker/actions/workflows/security-scan.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D.svg)](https://vuejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-2496ED.svg)](https://docker.com)

*An open-source, self-hosted AI agent that can browse the web, write & execute code, search the internet, manage files, and deliver polished research reports — all from a beautiful real-time interface.*

**Author:** [Mohamed Elkholy](https://github.com/mohamed-elkholy95)

</div>

---

## ✨ What Makes Pythinker Different

| Feature | Description |
|---------|-------------|
| 🔧 **43+ Built-in Tools** | File, browser, shell, search, code, messaging, automation — the agent picks the right tool for every step |
| 🖥️ **Live Browser Streaming** | Watch the agent browse in real-time via CDP screencast — take over control at any moment |
| 📊 **Beautiful Report Generation** | Automatically produces structured, citation-rich research reports with charts and references |
| 🧪 **Sandboxed Execution** | Every task runs in an isolated Docker container with Chrome, Python, Node.js, and shell access |
| 🤖 **Multi-Model Support** | Works with any OpenAI-compatible API — GPT-4o, Claude, DeepSeek, Kimi, GLM, local models, and more |
| 📱 **Telegram Integration** | Full-featured Telegram bot gateway with inline buttons, file sharing, and streaming responses |
| 🔌 **MCP Tool Integration** | Extend capabilities with external Model Context Protocol servers |
| 🎯 **PlanAct Agent Architecture** | Intelligent planning → execution → summarization pipeline with adaptive model routing |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PYTHINKER PLATFORM                              │
│                                                                         │
│  ┌──────────┐   ┌───────────────────────────────────────────────────┐   │
│  │ Frontend │   │                   Backend (FastAPI)                │   │
│  │  Vue 3   │◄─►│  PlanAct Agent  ·  43+ Tools  ·  SSE Streaming   │   │
│  │  TypeScript│   │  Model Router   ·  DDD Services · Report Gen    │   │
│  └──────────┘   └──────────────┬───────────────────┬────────────────┘   │
│                                │                   │                    │
│  ┌──────────┐   ┌──────────────▼──┐   ┌───────────▼────────────────┐   │
│  │ Telegram │   │    Sandbox(es)   │   │      Data Layer            │   │
│  │ Gateway  │   │  Ubuntu Docker   │   │  MongoDB · Redis · Qdrant  │   │
│  │          │   │  Chrome · Python │   │  MinIO (Object Storage)    │   │
│  │          │   │  Node.js · Shell │   │                            │   │
│  └──────────┘   └─────────────────┘   └────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Vue 3, TypeScript, Vite, TipTap, Monaco Editor, xterm.js, Plotly |
| **Backend** | FastAPI, Python 3.11+, Pydantic v2, Beanie ODM, SSE, WebSockets |
| **Sandbox** | Ubuntu Docker, Chromium/Chrome, Playwright, Supervisord |
| **Database** | MongoDB 7.0 (sessions & state), Redis 8 (cache & coordination) |
| **Vector Search** | Qdrant (RAG, semantic memory, knowledge bases) |
| **Object Storage** | MinIO (file uploads, artifacts, report assets) |
| **Messaging** | Telegram Bot API (polling + webhook modes) |
| **CI/CD** | GitHub Actions (lint, test, security scan, Docker build) |
| **Monitoring** | Prometheus, Grafana, Loki, Promtail |

---

## 🛠️ Tool Categories

The agent has access to **43+ tools** organized into 10 categories:

| Category | Tools | What They Do |
|----------|-------|-------------|
| 📁 **File** | read, write, list, search, upload, download | Full filesystem access within the sandbox |
| 🌐 **Browser** | navigate, click, type, screenshot, scroll, evaluate JS | Headless Chrome with live CDP streaming |
| 🔍 **Search** | web search, scrape, extract | Internet research with multiple providers |
| 💻 **Shell** | execute, background, interactive | Full terminal access with real-time output |
| 💬 **Message** | ask user, notify, report | Communication and deliverable generation |
| 🔌 **MCP** | external tool servers | Extensible via Model Context Protocol |
| 📝 **Code** | analyze, refactor, test | Code intelligence and manipulation |
| 📋 **Plan** | create plan, update step, checkpoint | Structured task planning and tracking |
| ⚡ **Automation** | batch operations, workflows | Multi-step automated sequences |
| ⚙️ **System** | health, config, diagnostics | Platform management and monitoring |

---

## 🚀 Quick Start

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

# Security (required)
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

## 🧠 How It Works

### The PlanAct Pipeline

When you send a message, Pythinker's agent follows an intelligent pipeline:

```
User Message
    │
    ▼
┌──────────────┐    ┌──────────────────┐    ┌────────────────┐
│   Planning   │───►│    Execution     │───►│ Summarization  │
│              │    │                  │    │                │
│ • Analyze    │    │ • Run tools      │    │ • Synthesize   │
│ • Break down │    │ • Browse web     │    │ • Cite sources │
│ • Prioritize │    │ • Execute code   │    │ • Format report│
│ • Checkpoint │    │ • Search & scrape│    │ • Verify facts │
└──────────────┘    └──────────────────┘    └────────────────┘
```

### Real-Time Features

- **SSE Event Streaming** — Every agent action streams to the UI in real-time
- **Live Browser View** — Watch the agent browse via CDP screencast; click to take over
- **Live Terminal** — See shell commands execute with real-time output via xterm.js
- **Progress Tracking** — Visual planning bar, step indicators, and tool timeline
- **File Preview** — In-app code viewer with Monaco Editor and syntax highlighting

### Adaptive Model Routing

Pythinker can intelligently route requests to different model tiers:

- **Fast tier** — Simple queries, quick responses (60-70% latency reduction)
- **Balanced tier** — Standard research and coding tasks
- **Powerful tier** — Complex multi-step reasoning and report generation

---

## 📱 Telegram Bot

Pythinker includes a full-featured Telegram gateway:

- Start research tasks from Telegram with `/research`
- Receive streaming responses with inline action buttons
- Upload and download files directly
- Share reports and artifacts
- Full agent capabilities available via chat

Configure in `.env`:

```env
CHANNEL_GATEWAY_ENABLED=true
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHANNEL_ENABLED=true
```

---

## 🔒 Security

- **Sandboxed execution** — Each task runs in an isolated Docker container with resource limits (2GB RAM, 1 CPU)
- **Security-hardened containers** — `no-new-privileges`, `cap_drop: ALL`, minimal capabilities
- **No direct sandbox access** — All browser/terminal access is proxied through authenticated backend endpoints
- **JWT authentication** — Secure user sessions with configurable auth providers
- **Secret scanning** — TruffleHog + GitHub secret scanning in CI
- **Dependency auditing** — pip-audit and npm audit run automatically
- **Network isolation** — Internal services run on private Docker networks

---

## 🧪 Development

### Project Structure

```
Pythinker/
├── frontend/          # Vue 3 + TypeScript + Vite
├── backend/           # FastAPI + Python 3.11 + DDD architecture
│   ├── app/
│   │   ├── core/          # Configuration, settings
│   │   ├── domain/        # Models, services, agents, tools
│   │   ├── infrastructure/# External integrations, middleware
│   │   └── interfaces/    # API routes, WebSocket handlers
│   └── tests/             # 3,800+ tests
├── sandbox/           # Ubuntu Docker sandbox with Chrome
├── grafana/           # Dashboards & monitoring
├── scripts/           # Utility scripts
└── docs/              # Architecture docs & plans
```

### Running Locally

```bash
# Development mode with hot reload
docker compose -f docker-compose-development.yml up

# Ports:
#   5173 → Frontend (Vite dev server)
#   8000 → Backend API
#   8080 → Sandbox API (localhost only)
```

### Testing

```bash
# Backend
cd backend
ruff check . && ruff format --check .   # Lint
pytest tests/ -v --tb=short             # 3,800+ tests

# Frontend
cd frontend
bun install
bun run lint:check                       # ESLint
bun run type-check                       # TypeScript
bun run test:run                         # Vitest
```

### Run CI Locally

```bash
# Full push-equivalent workflow via act
scripts/run_github_tests_local.sh --event push

# Single job
scripts/run_github_tests_local.sh --job backend-test
```

---

## 📊 Monitoring

Pythinker ships with a full observability stack:

- **Prometheus** — Metrics collection (SSE connections, sandbox health, API latency)
- **Grafana** — Pre-configured dashboards
- **Loki + Promtail** — Log aggregation and search

```bash
# Start with monitoring
docker compose -f docker-compose-monitoring.yml up -d
# Grafana: http://localhost:3000
```

---

## 🔧 Configuration

All configuration is via `.env`. Key sections:

| Category | Variables | Description |
|----------|----------|-------------|
| **LLM** | `API_KEY`, `API_BASE`, `MODEL_NAME` | Primary model configuration |
| **Fast Model** | `FAST_MODEL` | Optional fast-tier model for simple tasks |
| **Search** | `SEARCH_PROVIDER`, `BING_API_KEY` | Web search provider |
| **Auth** | `AUTH_PROVIDER`, `JWT_SECRET_KEY` | Authentication settings |
| **Sandbox** | `SANDBOX_IMAGE`, `SANDBOX_TTL_MINUTES` | Container lifecycle |
| **Telegram** | `TELEGRAM_BOT_TOKEN` | Bot gateway |
| **Storage** | `MINIO_ROOT_USER/PASSWORD` | Object storage |

See [`.env.example`](.env.example) for the complete reference with documentation.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Run the test suite (`scripts/run_github_tests_local.sh --event push`)
4. Commit your changes with [conventional commits](https://www.conventionalcommits.org/)
5. Open a Pull Request

CI will automatically run lint, type-check, tests, and security scans.

---

## 📄 License

MIT License — Copyright (c) 2024 [Mohamed Elkholy](https://github.com/mohamed-elkholy95)
