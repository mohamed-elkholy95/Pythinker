# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pythinker is an AI Agent system that runs tools (browser, terminal, files, search) in isolated Docker sandbox environments. It uses a FastAPI backend with Domain-Driven Design, a Vue 3 frontend, and Docker containers for task isolation.

## Claude Code Instructions

### Clean Code Summary (TL;DR)

> **Always follow these principles when writing or modifying code:**
>
> 1. **Dependency Rule**: Domain → Application → Infrastructure → Interfaces (inward only)
> 2. **SOLID**: Single responsibility, depend on abstractions, inject dependencies
> 3. **Type Safety**: Full type hints (Python) / strict mode (TypeScript); no `any`
> 4. **Layer Discipline**: Business logic in domain, not in API routes or components
> 5. **Naming**: Python `snake_case` functions / `PascalCase` classes; Vue `PascalCase` components / `useX` composables
> 6. **Error Handling**: Custom domain exceptions; global handlers in infrastructure
> 7. **No Anti-Patterns**: No god classes, no magic strings, no circular dependencies, no leaky abstractions
>
> **Before committing, always validate:**
> - **Frontend**: `cd frontend && bun run lint && bun run type-check`
> - **Backend**: `conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/`

### Development Guidelines

- **Code Search**: Always use TypeScript LSP and Pyright LSP plugins for code searches instead of grep/glob when searching for definitions, references, or type information
- **Python Environment**: Always activate the `pythinker` conda environment before running Python tests or checking Python code:
  ```bash
  conda activate pythinker
  ```
- **Frontend Validation (Before Commit)**: Always run lint and type checks before committing frontend changes:
  ```bash
  cd frontend && bun run lint && bun run type-check
  ```
- **Backend Linting (Before Commit)**: Always run Ruff linter and formatter before committing:
  ```bash
  conda activate pythinker && cd backend && ruff check . && ruff format --check .
  ```
- **Backend Auto-fix**: To automatically fix linting issues:
  ```bash
  conda activate pythinker && cd backend && ruff check --fix . && ruff format .
  ```
- **Backend Testing (Before Commit)**: Always run tests before committing backend changes:
  ```bash
  conda activate pythinker && cd backend && pytest tests/
  ```
- **Plan Execution**: When executing a plan document with multiple phases (P0, P1, P2, P3, etc.):
  - **ALWAYS complete ALL phases** regardless of priority labels - priorities indicate implementation order, not optional phases
  - **NEVER stop early** after completing high-priority phases - continue until every phase is implemented
  - **NEVER delay or defer** lower-priority phases to "later" - implement them in the same session
  - Treat the entire plan as a single atomic unit of work that must be fully completed

---

## Clean Code Architecture Guidelines (Full Reference)

### Core Principles

#### The Dependency Rule
- Dependencies must **strictly point inward** toward core business logic
- High-level policies (domain) should **never depend** on low-level details (infrastructure)
- Outer layers (API, UI) depend on inner layers (application, domain), never the reverse
- Use dependency injection to maintain this direction

#### Separation of Concerns
- Divide the program into distinct sections with **unique responsibilities**
- UI/Web frameworks must be separated from domain logic
- Each module/class should have **one reason to change**

#### SOLID Principles
| Principle | Application |
|-----------|-------------|
| **S**ingle Responsibility | One class = one job |
| **O**pen/Closed | Open for extension, closed for modification |
| **L**iskov Substitution | Subtypes must be substitutable for base types |
| **I**nterface Segregation | Many specific interfaces over one general |
| **D**ependency Inversion | Depend on abstractions, not concretions |

#### Type Safety
- **Python**: Use type hints with Pyright for static analysis; Pydantic for runtime validation; Ruff for linting
- **TypeScript**: Leverage strict mode; avoid `any`; use Zod for runtime validation
- Catch errors at compile-time; ensure predictable data flow

---

### Python (FastAPI) Architecture

#### Layer Structure
```
backend/app/
├── domain/           # Core business logic (NO external dependencies)
│   ├── models/       # Entities, Value Objects, Aggregates
│   ├── services/     # Domain services (pure business logic)
│   └── repositories/ # Abstract interfaces (ABCs)
├── application/      # Use cases, orchestration, DTOs
├── infrastructure/   # External adapters (DB, APIs, messaging)
│   ├── repositories/ # Concrete repository implementations
│   ├── storage/      # Database clients
│   └── external/     # Third-party service adapters
├── interfaces/       # API routes, schemas, presenters
│   ├── api/          # REST endpoints
│   └── schemas/      # Request/Response models (Pydantic)
└── core/             # Cross-cutting concerns (config, DI)
```

#### Naming Conventions (PEP 8)
| Element | Convention | Example |
|---------|------------|---------|
| Functions/Variables | `snake_case` | `get_user_by_id` |
| Classes | `PascalCase` | `UserRepository` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_RETRIES` |
| Modules | `lowercase` | `user_service.py` |
| Private | `_prefix` | `_internal_helper` |

#### Implementation Patterns

**Abstract Base Classes for Dependency Inversion:**
```python
# domain/repositories/user_repository.py
from abc import ABC, abstractmethod
from domain.models.user import User

class UserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...
```

**Concrete Implementation in Infrastructure:**
```python
# infrastructure/repositories/mongodb_user_repository.py
from domain.repositories.user_repository import UserRepository

class MongoDBUserRepository(UserRepository):
    async def get_by_id(self, user_id: str) -> User | None:
        # MongoDB-specific implementation
        ...
```

**Use Cases in Application Layer:**
```python
# application/use_cases/create_user.py
from domain.repositories.user_repository import UserRepository

class CreateUserUseCase:
    def __init__(self, user_repo: UserRepository):
        self._user_repo = user_repo  # Injected abstraction

    async def execute(self, dto: CreateUserDTO) -> User:
        # Business logic orchestration
        ...
```

**Custom Domain Exceptions:**
```python
# domain/exceptions.py
class DomainException(Exception):
    """Base domain exception"""

class UserNotFoundError(DomainException):
    def __init__(self, user_id: str):
        super().__init__(f"User not found: {user_id}")
```

---

### Vue.js (TypeScript) Architecture

#### Layer Structure (Feature-Sliced Design)
```
frontend/src/
├── pages/            # Route-level components (entry points)
├── features/         # Feature modules (self-contained)
│   └── auth/
│       ├── components/
│       ├── composables/
│       ├── types/
│       └── index.ts  # Barrel file (public API)
├── widgets/          # Composite UI blocks
├── shared/           # Reusable utilities
│   ├── api/          # HTTP client, SSE handlers
│   ├── components/   # Base components (BaseButton, BaseInput)
│   ├── composables/  # Shared stateful logic
│   ├── types/        # Global TypeScript definitions
│   └── utils/        # Pure utility functions
└── app/              # App-level setup (router, store, plugins)
```

#### Naming Conventions
| Element | Convention | Example |
|---------|------------|---------|
| Components | `PascalCase` | `ChatMessage.vue` |
| Base Components | `Base` prefix | `BaseButton.vue` |
| Singleton Components | `The` prefix | `TheSidebar.vue` |
| Composables | `use` prefix | `useSession.ts` |
| Types/Interfaces | `PascalCase` | `SessionState` |
| Files/Folders | `kebab-case` | `chat-message.vue` |

#### Implementation Patterns

**Composables for Stateful Logic:**
```typescript
// composables/useSession.ts
import { ref, computed } from 'vue'
import type { Session } from '@/types/session'

export function useSession() {
  const session = ref<Session | null>(null)
  const isActive = computed(() => session.value?.status === 'active')

  async function loadSession(id: string): Promise<void> {
    // Load session logic
  }

  return { session, isActive, loadSession }
}
```

**Type-Safe API Layer:**
```typescript
// api/session.ts
import type { Session, CreateSessionDTO } from '@/types/session'
import { apiClient } from './client'

export const sessionApi = {
  create: (dto: CreateSessionDTO): Promise<Session> =>
    apiClient.put('/sessions', dto),

  getById: (id: string): Promise<Session> =>
    apiClient.get(`/sessions/${id}`),
}
```

**Barrel Files for Encapsulation:**
```typescript
// features/auth/index.ts
export { LoginForm } from './components/LoginForm.vue'
export { useAuth } from './composables/useAuth'
export type { AuthState } from './types'
// Internal implementation details NOT exported
```

---

### Error Handling Strategy

#### Python (FastAPI)
```python
# interfaces/api/exception_handlers.py
from fastapi import Request
from fastapi.responses import JSONResponse
from domain.exceptions import DomainException, UserNotFoundError

async def domain_exception_handler(request: Request, exc: DomainException):
    return JSONResponse(
        status_code=400,
        content={"error": exc.__class__.__name__, "message": str(exc)}
    )

# In main.py
app.add_exception_handler(DomainException, domain_exception_handler)
```

#### TypeScript (Vue)
```typescript
// shared/utils/errors.ts
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly statusCode?: number
  ) {
    super(message)
  }
}

// Global error boundary in App.vue or router guards
```

---

### Code Quality Tools

| Category | Python | TypeScript |
|----------|--------|------------|
| **Linting** | Ruff | ESLint |
| **Formatting** | Ruff | Prettier |
| **Type Checking** | Pyright | tsc --strict |
| **Validation** | Pydantic | Zod |
| **Testing** | Pytest | Vitest, Playwright |
| **Security** | pip-audit | npm audit |
| **Logging** | structlog | - |

---

### Anti-Patterns to Avoid

1. **God Classes**: Split large classes with multiple responsibilities
2. **Anemic Domain Models**: Domain entities should contain behavior, not just data
3. **Leaky Abstractions**: Infrastructure details must not leak into domain
4. **Circular Dependencies**: Maintain strict layer boundaries
5. **Magic Strings/Numbers**: Use enums and constants
6. **Deep Nesting**: Prefer early returns and guard clauses
7. **Implicit Dependencies**: Always inject dependencies explicitly

---

### Refactoring Checklist

Before committing code changes:
- [ ] Dependencies point inward (domain has no external imports)
- [ ] Each class/function has a single responsibility
- [ ] Type hints/annotations are complete
- [ ] Business logic is in domain layer, not in API routes
- [ ] No hardcoded configuration values
- [ ] Custom exceptions used instead of generic ones
- [ ] Unit tests cover business logic
- [ ] No `any` types in TypeScript; no untyped functions in Python
- [ ] Ruff check passes (`ruff check . && ruff format --check .`)
- [ ] ESLint passes (`bun run lint:check`)
- [ ] All tests pass (`pytest tests/`)

## Development Commands

### Full Stack (Docker Compose)
```bash
./dev.sh up -d              # Start dev stack with hot-reload
./dev.sh down -v            # Stop and remove volumes
./dev.sh logs -f backend    # Follow service logs
./run.sh up -d              # Production stack
./build.sh                  # Build images with buildx
```

### Backend
```bash
cd backend
conda activate pythinker              # Use conda environment
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Linting & Formatting (Ruff)
ruff check .                            # Check for issues
ruff check --fix .                      # Auto-fix issues
ruff format .                           # Format code
ruff format --check .                   # Check formatting only

# Testing
pytest tests/                           # All tests (includes coverage)
pytest tests/test_auth_routes.py        # Single file
pytest -v --no-cov                      # Without coverage
pytest -m "not slow"                    # Skip slow tests

# Development dependencies
pip install -r requirements-dev.txt     # Includes ruff, pip-audit
```

### Frontend
```bash
cd frontend
npm install
npm run dev                 # Vite dev server (port 5173)
npm run build              # Production build
npm run type-check         # TypeScript check
npm run lint               # ESLint fix
npm run lint:check         # ESLint check only
npm run test               # Vitest watch mode
npm run test:run           # Single test run
npm run test:coverage      # Coverage report
```

### Sandbox
```bash
cd sandbox
pytest tests/
```

## Architecture

### Backend DDD Structure (`backend/app/`)
- **domain/**: Core business logic
  - `models/`: Domain entities (agent, session, event)
  - `services/agents/`: Agent implementations (Critic, Planner, Executor)
  - `services/flows/`: Workflow orchestration (PlanAct, TreeOfThoughts, Discussion)
  - `services/tools/`: Tool definitions (30+ tools)
  - `services/langgraph/`: LangGraph state management and graph definitions
  - `repositories/`: Abstract data access interfaces
- **application/**: Use case orchestration and DTOs
- **interfaces/api/**: REST routes and request/response schemas
- **infrastructure/**: Technical implementations
  - `repositories/`: MongoDB/Redis implementations
  - `storage/`: Database clients (MongoDB, Redis, Qdrant)
  - `models/documents.py`: MongoDB document schemas (Beanie ODM)
  - `external/`: Third-party service adapters
    - `llm/`: LLM providers (OpenAI, Anthropic, etc.)
    - `search/`: Search engines (SearXNG, Whoogle)
    - `browser/`: Browser automation (Playwright, BrowserUse)
    - `openreplay/`: OpenReplay client for session tracking
- **core/**: System components (`config.py`, `sandbox_manager.py`, `workflow_manager.py`)

### Frontend Structure (`frontend/src/`)
- **pages/**: Route components (ChatPage, HomePage, SessionHistoryPage)
- **components/**: Reusable UI
  - `ChatInput.vue`, `ChatMessage.vue` - Chat interface
  - `ToolPanel*.vue` - Tool execution display
  - `SandboxViewer.vue` - CDP screencast viewer (replaced VNC)
  - `SessionReplayPlayer.vue` - OpenReplay embedded player
  - `ReplayTimeline.vue` - Timeline with event markers
- **composables/**: Shared logic
  - `useChat.ts`, `useSession.ts` - Core session management
  - `useOpenReplay.ts` - Session recording & replay
  - `useAgentEvents.ts` - SSE to OpenReplay event bridge
  - `useSandboxInput.ts` - Input forwarding for takeover
  - `useFilePanel.ts` - File browser logic
- **api/**: Axios HTTP client with SSE support
- **types/**: TypeScript definitions

### Key Patterns
- **Event Sourcing**: Session events stored in MongoDB
- **SSE Streaming**: Real-time event propagation to frontend
- **LangGraph Workflows**: Planning → Execution → Reflection → Verification
- **Sandbox Isolation**: Each task gets its own Docker container with CDP screencast
- **Session Recording**: OpenReplay integration for session replay and live co-browsing

## API Base URL
`/api/v1`

Key endpoints:
- `PUT /sessions` - Create session
- `POST /sessions/{id}/chat` - Chat (SSE stream)
- `GET /sessions/{id}/sandbox-url` - Get CDP screencast URL
- `GET /sessions/{id}/vnc/screenshot` - Capture sandbox screenshot

## Port Mapping (Development)
| Service | Port |
|---------|------|
| Frontend | 5174 |
| Backend | 8000 |
| Sandbox API | 8083 |
| Sandbox Framework | 8082 |
| MongoDB | 27017 |
| Redis | 6379 |
| Qdrant REST | 6333 |
| Qdrant gRPC | 6334 |
| SearXNG | 8888 |
| Whoogle | 5001 |

### OpenReplay Services (Optional)
| Service | Port |
|---------|------|
| OpenReplay Ingest | 9001 |
| OpenReplay API | 8090 |
| OpenReplay Assist | 9003 |
| OpenReplay Assets | 9002 |
| OpenReplay Postgres | 5433 |
| OpenReplay MinIO | 9100 |

## Code Style
- **Python**: 4-space indent, `snake_case` functions, `PascalCase` classes, maintain DDD layers
- **Vue/TypeScript**: 2-space indent, `PascalCase` components, composables named `useX.ts`
- **Linting**: Backend uses Ruff (`backend/pyproject.toml`), Frontend uses ESLint (`frontend/eslint.config.js`)

## Tooling Configuration

### Ruff (Python Linting & Formatting)

Configuration in `backend/pyproject.toml`:
- **Line length**: 120 characters
- **Target**: Python 3.11
- **Lint rules**: E, W, F, I, N, UP, B, C4, LOG, RET, SIM, RUF
- **Ignored**: E501 (line too long), PLR0913 (too many args), PLR2004 (magic values)
- **Per-file ignores**: Tests allow assertions (S101), API routes allow B008

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Check formatting
ruff format --check .

# Apply formatting
ruff format .
```

### Structured Logging (structlog)

The backend uses `structlog` for JSON-formatted logging with correlation ID propagation.

**Key features:**
- JSON output in production, colored console in development
- Automatic correlation IDs: `request_id`, `session_id`, `user_id`, `agent_id`
- Context propagation through async operations via ContextVars

**Usage in code:**
```python
from app.infrastructure.structured_logging import get_logger, set_session_id

logger = get_logger(__name__)

# Set correlation context
set_session_id("session-123")

# Log with automatic context
logger.info("Processing request", user_action="chat", extra_field="value")
```

**Log output (production JSON):**
```json
{"event": "Processing request", "request_id": "abc123", "session_id": "session-123", "level": "INFO", "timestamp": "2024-01-15T10:30:00Z"}
```

### CI/CD Workflows

GitHub Actions workflows in `.github/workflows/`:

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `test-and-lint.yml` | Push/PR to main/develop | backend-lint, backend-test, backend-security, frontend-lint, frontend-typecheck, frontend-test |
| `security-scan.yml` | Weekly + manual + dependency changes | trufflehog-scan, dependency-audit |
| `docker-build-and-push.yml` | Push/PR to main/develop | build-and-push (depends on test-and-lint) |

**CI validation runs:**
- Backend: `ruff check`, `ruff format --check`, `pytest`
- Frontend: `bun run lint:check`, `bun run type-check`, `bun run test:run`
- Security: `pip-audit`, `npm audit`, `trufflehog` (secrets scanning)

## Configuration
- Copy `.env.example` to `.env` for local runs
- MCP integration via `mcp.json.example`
- Docker socket mount required for sandbox creation: `-v /var/run/docker.sock:/var/run/docker.sock`

---

## OpenReplay Integration

Pythinker uses OpenReplay for session recording, replay, and live co-browsing. This replaces the previous VNC-based visualization.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + OpenReplay Tracker)                      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  SandboxViewer (Canvas - CDP Screencast)               │ │
│  │  [Captured by OpenReplay @ 6 FPS]                      │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐   │
│  │ Chat Panel   │ │ Tool Panel   │ │ Timeline + Events  │   │
│  │ [DOM capture]│ │ [DOM capture]│ │ [Agent events]     │   │
│  └──────────────┘ └──────────────┘ └────────────────────┘   │
└────────────────────────────┬────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
    ┌──────────────┐ ┌─────────────┐ ┌─────────────┐
    │ OpenReplay   │ │ Backend     │ │ Sandbox     │
    │ (Optional)   │ │ ────────────│ │ ────────────│
    │ • PostgreSQL │ │ • MongoDB   │ │ • Chrome    │
    │ • Redis      │ │ • Redis     │ │ • CDP 9222  │
    │ • MinIO      │ │ • Qdrant    │ │ • Screencast│
    └──────────────┘ └─────────────┘ └─────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `useOpenReplay` | `frontend/src/composables/useOpenReplay.ts` | Tracker initialization, session recording |
| `useAgentEvents` | `frontend/src/composables/useAgentEvents.ts` | Bridge SSE events to OpenReplay |
| `useSandboxInput` | `frontend/src/composables/useSandboxInput.ts` | Mouse/keyboard forwarding for takeover |
| `SandboxViewer` | `frontend/src/components/SandboxViewer.vue` | CDP screencast canvas viewer |
| `SessionReplayPlayer` | `frontend/src/components/SessionReplayPlayer.vue` | Embedded replay player |
| `ReplayTimeline` | `frontend/src/components/ReplayTimeline.vue` | Timeline with event markers |
| `SessionHistoryPage` | `frontend/src/pages/SessionHistoryPage.vue` | Session history browsing |
| `OpenReplayClient` | `backend/app/infrastructure/external/openreplay/client.py` | Backend OpenReplay integration |

### Environment Variables

```bash
# Frontend (.env)
VITE_OPENREPLAY_PROJECT_KEY=pythinker-dev
VITE_OPENREPLAY_INGEST_URL=http://localhost:9001
VITE_OPENREPLAY_ASSIST_URL=ws://localhost:9003
VITE_OPENREPLAY_CANVAS_QUALITY=medium  # low | medium | high
VITE_OPENREPLAY_CANVAS_FPS=6
VITE_OPENREPLAY_ENABLED=true

# Backend (.env)
OPENREPLAY_PROJECT_KEY=pythinker-dev
OPENREPLAY_API_URL=http://localhost:8090
OPENREPLAY_ENABLED=true
```

### CDP Screencast (Replaced VNC)

The sandbox browser view now uses Chrome DevTools Protocol (CDP) screencast instead of VNC:

- **Lower latency**: Direct frame streaming (10-50ms vs 100-200ms VNC)
- **Better integration**: Captured natively by OpenReplay canvas recording
- **Simpler architecture**: No VNC server/client needed

```typescript
// SandboxViewer connects to CDP screencast
const ws = new WebSocket(`ws://${sandboxHost}:8080/api/v1/screencast/stream`)
ws.onmessage = (event) => {
  const frame = JSON.parse(event.data)
  // Render JPEG frame to canvas
  renderFrame(frame.data)
}
```

### Starting OpenReplay (Optional)

```bash
# Start OpenReplay services alongside dev stack
docker compose -f docker-compose-openreplay.yml up -d

# Or include in main dev stack
docker compose -f docker-compose-development.yml -f docker-compose-openreplay.yml up -d
```

### Session Model Fields

Sessions include OpenReplay tracking:
```python
# backend/app/domain/models/session.py
class Session:
    # ... existing fields ...
    openreplay_session_id: str | None = None
    openreplay_session_url: str | None = None
```

---

## Sandbox Architecture

### CDP Screencast API

The sandbox exposes a screencast WebSocket endpoint for real-time browser view:

```
GET /api/v1/screencast/stream  # WebSocket - continuous JPEG frames
GET /api/v1/screencast/frame   # Single frame capture
```

### Input Forwarding

For interactive takeover, input events are forwarded to the sandbox:

```
POST /api/v1/input/mouse      # { x, y, type, button }
POST /api/v1/input/keyboard   # { key, type, modifiers }
POST /api/v1/input/scroll     # { x, y, deltaX, deltaY }
```

### Container Resources

```yaml
# docker-compose-development.yml sandbox config
shm_size: '2gb'           # Chrome stability
tmpfs:
  - /run:size=100M
  - /tmp:size=500M
deploy:
  resources:
    limits:
      memory: 4G
    reservations:
      memory: 1G
```
