# Skill System Fixes Implementation Plan

**Date:** 2026-02-07
**Scope:** 34 findings from deep code analysis of skill system
**Strategy:** Fix in priority order, parallel where independent

---

## Phase 1: Critical Security Fixes (P0)

### 1.1 Environment variable leak in dynamic context execution
- **File:** `backend/app/domain/services/prompts/skill_context.py`
- **Fix:** Change `env=None` to `env={}` or curated minimal dict
- **Fix:** Remove `env`/`printenv` from `ALLOWED_COMMANDS`
- **Fix:** Add `-c` to `BLOCKED_SUBCOMMANDS` for python

### 1.2 Path traversal in SkillLoader
- **File:** `backend/app/domain/services/skill_loader.py`
- **Fix:** Add path traversal check in `load_resource()` — resolve path and verify it's under skill directory

### 1.3 Path traversal in SkillInitializer
- **File:** `backend/app/domain/services/skills/init_skill.py`
- **Fix:** Validate `skill_name` contains no path separators or `..`

### 1.4 ReDoS protection for trigger patterns
- **File:** `backend/app/domain/services/skill_trigger_matcher.py`
- **Fix:** Add regex compile timeout or complexity limit (use `re.compile` with a length cap + try/except for catastrophic patterns)

### 1.5 `sanitize_prompt()` dead code
- **File:** `backend/app/domain/services/skill_validator.py`
- **Fix:** Either wire it into `validate()` or remove it

---

## Phase 2: Critical Bug Fixes (P0)

### 2.1 Frontend SSE event handlers for skill_delivery and skill_activation
- **File:** `frontend/src/pages/ChatPage.vue`
- **Fix:** Add event handlers for `skill_delivery` and `skill_activation` in `handleEvent()`

### 2.2 Skills never sent with chat messages
- **File:** `frontend/src/pages/ChatPage.vue`
- **Fix:** Pass `getSelectedSkillIds()` instead of `undefined` for skills parameter

### 2.3 SkillDocument timestamp bug
- **File:** `backend/app/infrastructure/models/documents.py`
- **Fix:** Change `created_at`/`updated_at` defaults to `default_factory=lambda: datetime.now(UTC)`

### 2.4 Context cache TTL never enforced
- **File:** `backend/app/domain/services/skill_registry.py`
- **Fix:** Add TTL check in context cache lookup

### 2.5 Registry marks initialized on failure
- **File:** `backend/app/domain/services/skill_registry.py`, `skill_trigger_matcher.py`
- **Fix:** Only set `_initialized = True` on success; add retry logic

---

## Phase 3: Architecture Fixes (P1)

### 3.1 Rename conflicting SkillValidator classes
- `domain/services/skill_validator.py` → rename class to `CustomSkillValidator`
- `domain/services/skills/skill_validator.py` → rename class to `SkillFileValidator`

### 3.2 Fix SkillService DDD violation
- **File:** `backend/app/application/services/skill_service.py`
- **Fix:** Depend on `SkillRepository` Protocol, inject implementation

### 3.3 Fix Superpowers tool name mapping
- **File:** `backend/app/infrastructure/seeds/superpowers_tool_mapping.py`
- **Fix:** Update tool names to match actual ALLOWED_TOOLS

### 3.4 Fix marketplace routes bypassing service layer
- **File:** `backend/app/interfaces/api/skills_routes.py`
- **Fix:** Use `SkillService` instead of direct `MongoSkillRepository()` instantiation

---

## Phase 4: Dead Code & Quality Fixes (P2)

### 4.1 Remove unused `configurations` field from Skill model
### 4.2 Remove decorative `version` field or implement version checking
### 4.3 Fix untyped dict in UserSkillConfig
### 4.4 Fix Manus branding in SkillsSettings.vue
### 4.5 Fix shared loading state race condition in useSkills.ts
### 4.6 Fix `any` types in frontend constants
### 4.7 Fix SkillListTool naming collision

---

## Phase 5: Test Coverage (P1 - parallel with fixes)

### 5.1 Add tests for CustomSkillValidator (prompt injection, tool allowlist)
### 5.2 Add tests for path traversal prevention
### 5.3 Add tests for ReDoS protection

---

## Execution Strategy

- Phases 1 + 2: Execute in parallel (security + bugs are independent)
- Phase 3: Execute after phases 1+2 (renames affect imports)
- Phase 4: Execute in parallel with phase 3
- Phase 5: Tests written alongside fixes
