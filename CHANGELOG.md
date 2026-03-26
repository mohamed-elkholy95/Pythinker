# Changelog

All notable changes to Pythinker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-03-26

### Added

- **Monitoring**: Grafana dashboards, alert contact points, and Loki alerting rules
- **Monitoring**: Promtail JSON log parsing, multi-format level detection, and pipeline stages
- **Monitoring**: Prometheus instrumentation for LLM calls, tool calls, and active sessions
- **Monitoring**: Container resource telemetry with cAdvisor
- **Backend**: Configurable log format (auto/json/plain) for Docker-friendly structured output
- **Backend**: Hallucination correction feedback loop in output verification
- **Backend**: MiniMax M2.7 LLM provider support
- **Backend**: LLM-powered chart analysis replacing heuristic pipeline
- **Backend**: Domain-level URL failure blocking with cross-session cache
- **Backend**: Search query and browser navigation deduplication per step
- **Backend**: Expected tools on Step model for declarative action audit
- **Backend**: Middleware lifecycle hooks for per-step state reset
- **Backend**: Search evidence fed to output verifier for grounding
- **Backend**: Blocked-domains context injection from URL failure guard
- **Backend**: Configurable context cap with deep_research override
- **Backend**: Higher search and browser budgets for deep_research mode
- **Frontend**: Plan presentation and streaming tool display
- **Frontend**: Markdown preview and syntax-highlighted code view in editor
- **Frontend**: Inline chart/image previews for assistant attachments
- **Frontend**: Google Drive-style FileTypeIcon redesign
- **Frontend**: ThinkingIndicator component replacing static SVGs
- **Frontend**: Negative caching for auth status during backend restarts
- **Frontend**: Progress toast with rich layout and session notifications
- **Frontend**: TaskCompletedFooter with phased rating flow
- **Sandbox**: Parameterized resource limits with env-driven defaults
- **Browser**: Playwright tools and browser lifecycle metrics
- **VNC**: Pre-flight websockify check and improved error handling
- **Agent**: Improved stuck detection and tightened context limits
- **Agent**: Report quality improvements with source grounding and delivery fallbacks
- **Email**: BIMI SVG Tiny PS logo for Gmail brand display
- **Config**: Default rating notification email setting
- **Tests**: 4,500+ new tests across 120+ test files covering domain models, services, tools, and infrastructure

### Fixed

- **Models**: Add missing RUNNING and FINISHED members to PlanStatus enum
- **Auth**: Skip server logout when token is already cleared
- **Config**: Raise deep_research context cap and planning budget
- **Agents**: Suppress stuck detector false positive during research steps
- **UI**: Guard sandbox connection init against completed sessions
- **UI**: Fix scoped CSS dark mode selectors and transparent text leak
- **SSE**: Prevent UUID resume cursor from causing full event replay
- **Sandbox**: Allow /tmp paths in file service and harden X11 cleanup
- **Sandbox**: Handle ProcessLookupError race in X11 screencast process cleanup
- **Charts**: Resolve chart attachment filename mismatch in reports
- **Browser**: Prevent Playwright route handler cascade on page close
- **Browser**: Catch PlaywrightError in route_handler to prevent TargetClosedError tracebacks
- **Context Manager**: Guard against None result in InsightSynthesizer
- **Monitoring**: Remove high-cardinality event label from Promtail
- **Prometheus**: Add missing rule_files references for recording rules
- **Loki**: Add retention config and reduce compactor workers for dev
- **Alerts**: Correct misleading annotation in ToolFailureRateHigh alert
- **Alerts**: Use changes() instead of increase() for container restart detection
- **Metrics**: Log partial ImportError instead of silently swallowing
- **MongoDB**: Raise wiredTiger cacheSizeGB to 0.25 (min required by Mongo 7.0.31)
- **Tools**: Reduce false-positive traceback_in_success anomalies in result analyzer

### Changed

- **Metrics**: Prefix agent metrics with pythinker_ namespace
- **Verification**: Replace magic strings with ClaimVerdict constants
- **Session**: Use TakeoverReason enum for type-safe takeover handling
- **Agent**: Extract step action audit into StepExecutionContext
- **UI**: Extract useFavicon composable with persistent localStorage cache

### Performance

- **Config**: Enable Qdrant quantization and semantic cache by default
- **Docker**: Add BuildKit cache mounts for apt, uv, and npm
- **Docker**: Create lightweight gateway Dockerfile without browser deps
- **Docker**: Make gateway and VNC opt-in services
- **Sandbox**: Tune CDP screencast everyNthFrame from 1 to 3
- **Sandbox**: Remove addon packages from default runtime requirements
- **Backend**: Add GC tuning after startup initialization
- **Compose**: Add backend and MinIO resource limits to dev compose
- **Observability**: Cap in-memory trace retention
- **Metrics**: Replace unbounded histogram observations with bucket aggregation
- **Infra**: Right-size connection pools and production memory limits
- **Agent**: Per-step context compaction to prevent 130K accumulation
- **Agent**: Hard context cap and recovery truncation to prevent 60s+ LLM calls
- **Browser**: HEAD pre-check to skip dead URLs before full navigation

### Security

- **Auth**: Block AUTH_PROVIDER=none in production environment
- **Security**: Use proper URL hostname validation and bump vulnerable deps
- **Metrics**: Suppress METRICS_PASSWORD warning in development mode

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
