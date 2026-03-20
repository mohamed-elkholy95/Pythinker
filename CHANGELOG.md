# Changelog

All notable changes to Pythinker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-03-20

### Added

- **Frontend**: Terminal tool design tokens and CSS variables for consistent terminal theming
- **Frontend**: Live terminal ANSI prompt colorization and xterm theme integration
- **Frontend**: Tool panel terminal stage and timeline chrome styling
- **Frontend**: Floating jump-to-live overlay button for timeline navigation
- **Frontend**: Unified content-title bar with session names and browser URL display
- **Frontend**: Chat/Split/Close panel controls replacing header buttons
- **Frontend**: Manus-style compact step design with dotted timeline
- **Frontend**: BookOpen icon for skill_invoke tool events
- **Frontend**: Data-driven chroma recolor from chroma-render.json for agent cursor overlay
- **Frontend**: macOS Apple-style pointer cursor on all viewer surfaces
- **Frontend**: Forward browser tool events to LiveViewer for agent cursor overlay
- **Skills**: Deal Finder, Design, and Professional Coder official skills
- **Skills**: Skill Creator dialog with Teleport, Radix suppression, and compact layout
- **Skills**: "Create new skill" option in settings dropdown
- **Deploy**: Self-contained full-stack deploy compose package
- **Types**: session_name field and deriveSessionName utility

### Fixed

- **Test**: Handle 429 rate limit retries in integration test helpers
- **Deploy**: Rewrite compose for Dokploy managed Traefik
- **Panel**: Terminal dark mode background alignment and content-title labels
- **Files**: Register all generated files with session and fix tracking pipeline
- **Files**: Remove trailing quote from Content-Disposition filename header
- **Skills**: Fix skill upsert with raw MongoDB update_one
- **Skills**: Fix SkillCreatorDialog z-index and event propagation from settings
- **Skills**: Correct OpenAILLM constructor parameter in draft endpoint
- **Sandbox**: Enable VNC websockify for Take Control feature
- **Agents**: Always emit wall-clock CRITICAL FORCE stop signal
- **LLM**: Record Anthropic key-pool success on key actually used
- **Docker**: Target specific Alpine packages instead of blanket upgrade
- **Docker**: Pin gh CLI to v2.88.1 to fix CRITICAL grpc CVE
- **Docker**: Upgrade Alpine base packages to fix libexpat/zlib CVEs
- **CI**: Install deps before Pyright and make non-blocking
- **CI**: Skip release creation when tag already exists
- **CI**: Ignore unfixable diskcache CVE-2025-69872 in pip-audit

### Changed

- **Panel**: Standardize terminal design tokens and scrollbar CSS
- **Timeline**: Simplify TimelineControls, remove tooltip and unused props
- **Chat**: Polish compact step layout and remove tool chip borders
- **Deploy**: Standardize internal network name across compose files
- **Auth**: Multi-line AuthToken construction for readability

### Security

- **Dependencies**: Bump Pillow and pin authlib/pypdf to fix 12 CVEs
- **Dependencies**: Bump flatted from 3.4.1 to 3.4.2 (frontend)

### Performance

- **Scraper**: Cache lazy __getattr__ exports in module globals

## [1.0.1] - 2026-03-17

### Fixed

- **CI**: Override working-directory on skip steps to prevent workflow failure
- **CI**: Move skip logic to step-level so required status checks always pass
- **CI**: Add workflow_dispatch to Docker build and filter badge URLs
- **Frontend**: Use CSS custom properties for thumbnail space reservation
- **Tests**: Resolve all ruff lint and format errors in test files

### Changed

- **Docker**: Add OCI version labels and build metadata (GIT_VERSION, GIT_SHA, BUILD_DATE) to all Dockerfiles
- **API**: Expose version, git SHA, and build date in health endpoint response
- **Release**: Add automated release script (`scripts/release.sh`) and GitHub Release workflow

### Dependencies

- Bump vitest from 3.2.4 to 4.1.0 (frontend)
- Bump @vitest/coverage-v8 from 3.2.4 to 4.1.0 (frontend)
- Update setuptools requirement from <82 to <83 (backend)
- Update chardet requirement from <6.0.0 to <8.0.0 (backend)
- Bump symspellpy from 6.7.3 to 6.9.0 (backend)
- Bump actions/upload-artifact from 4 to 7
- Bump dorny/paths-filter from 3 to 4
- Bump actions/download-artifact from 6.0.0 to 8.0.1
- Bump docker/setup-buildx-action from 3 to 4
- Bump docker/login-action from 3 to 4

[1.0.1]: https://github.com/mohamed-elkholy95/Pythinker/compare/v1.0.0...v1.0.1

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
