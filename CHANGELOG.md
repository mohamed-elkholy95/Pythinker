# Changelog

All notable changes to Pythinker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-16

### Added

- **AI Agent Platform** — Full-stack AI agent with planning, execution, reflection, and verification pipeline (PlanAct flow)
- **Multi-Provider LLM Routing** — Support for OpenAI, Anthropic, DeepSeek, Kimi, GLM, OpenRouter with adaptive model selection and automatic failover
- **Tool System** — Browser automation (Playwright + CDP), terminal execution, file management, web search (Serper, Tavily, Exa, Jina), and MCP integration
- **Research Pipeline** — Multi-step research with parallel query execution, auto-enrichment, citation tracking, and polished report generation (Markdown/PDF)
- **Real-Time Streaming** — Server-Sent Events (SSE) for live agent progress, tool execution, and streaming responses
- **Docker Sandbox Isolation** — Each task runs in an isolated Ubuntu container with browser automation, file system access, and CDP screencast
- **Vue 3 Frontend** — Modern SPA with real-time chat, sandbox viewer, tool panel, phase timeline, and responsive design
- **FastAPI Backend (DDD)** — Domain-Driven Design architecture with clean layer separation (domain, application, infrastructure, interfaces)
- **Memory System** — Hybrid retrieval with MongoDB (document storage) + Qdrant (vector search) using dense embeddings + BM25 sparse vectors
- **Multi-API Key Management** — Key pool with failover/round-robin strategies, circuit breaking, and automatic recovery
- **DeepCode Integration** — Adaptive model routing, tool efficiency monitoring, truncation detection, document segmentation, and implementation tracking
- **Telegram Bot** — Full agent access via Telegram with PDF report delivery
- **Agent Reliability** — Delivery integrity gates, hallucination grounding, analysis paralysis detection, and cooperative cancellation
- **Observability** — Prometheus metrics, structured logging, and health monitoring
- **Security** — OWASP-compliant headers, JWT authentication, sandbox API secrets, and multi-stage Docker builds
- **CI/CD** — GitHub Actions for linting (Ruff, ESLint), testing (pytest, Vitest), security scanning (CodeQL, Trivy), and Docker builds

### Security

- MIT License for open-source distribution
- Secret scanning and push protection enabled
- Dependabot automated dependency updates configured

[1.0.0]: https://github.com/mohamed-elkholy95/Pythinker/releases/tag/v1.0.0
