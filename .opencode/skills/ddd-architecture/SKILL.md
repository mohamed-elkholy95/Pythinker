---
name: ddd-architecture
description: Domain-Driven Design layer discipline for the Pythinker backend — enforces inward-only dependencies, layer boundaries, and correct placement of business logic
---

# DDD Architecture Skill

## When to Use
When creating or modifying backend code, ensure every file lives in the correct DDD layer.

## Layer Structure

```
backend/app/
├── domain/              # Core business logic (ZERO external dependencies)
│   ├── models/          # Pydantic v2 models (AgentSession, ToolResult, Memory)
│   ├── services/        # Domain services (agents/, embeddings/, llm/, tools/, browser/)
│   ├── repositories/    # Abstract repository interfaces (Protocol classes)
│   └── utils/           # Domain utilities (json_repair, etc.)
├── application/         # Use case orchestration
│   ├── services/        # Application services (AgentService, SessionService)
│   └── dtos/            # Data Transfer Objects
├── infrastructure/      # External world adapters
│   ├── repositories/    # MongoDB/Redis/Qdrant implementations
│   ├── adapters/        # LLM adapters, browser adapters, search engines
│   └── middleware/      # Security headers, CORS
├── interfaces/api/      # REST API surface
│   ├── routes/          # FastAPI route handlers
│   └── schemas/         # Request/Response Pydantic models
└── core/                # Configuration & bootstrap
    ├── config.py        # Pydantic Settings (with @computed_field)
    ├── config_llm.py    # LLM-specific config
    └── config_features.py # Feature flags
```

## Dependency Rule (MANDATORY)

```
Interfaces → Infrastructure → Application → Domain
                    ↑ ONLY inward dependencies allowed
```

- **Domain** imports NOTHING from application, infrastructure, or interfaces
- **Application** imports from domain only
- **Infrastructure** imports from domain and application
- **Interfaces** can import from any inner layer

## Checklist

- [ ] New file placed in correct DDD layer
- [ ] No domain imports from infrastructure/interfaces
- [ ] Business logic in domain services, NOT in routes or adapters
- [ ] Abstract repos in domain, concrete implementations in infrastructure
- [ ] DTOs in application layer for cross-layer data transfer
- [ ] Config in core/, not scattered across layers
