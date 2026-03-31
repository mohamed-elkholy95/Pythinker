# Claude Code Inspired Agent Prompt System Implementation Plan
> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Pythinker's agent runtime use a sectioned, cache-aware prompt pipeline with explicit agent roles and controlled skill activation, borrowing the useful Claude Code architecture without copying product-specific complexity.

**Architecture:** Reuse the repo's existing prompt and skill seams instead of introducing a parallel system. The Claude Code backup shows the important ideas to carry over: deterministic system-prompt sections with a cache boundary, prompt-cache observability, progressive skill disclosure, and explicit built-in agent definitions with tool budgets and one-shot specializations. The implementation should keep stable prompt content cacheable, keep runtime/session metadata out of the cacheable core, and expose role/skill provenance through the session APIs and UI.

**Tech Stack:** Python 3.11+ with Pydantic v2 and pytest, TypeScript/Vue 3, Vitest, Vue Test Utils, existing Pythinker domain services and API clients.

---

## Chunk 1: Backend Prompt Contract and Skill Disclosure

This chunk establishes the prompt assembly contract first. The Claude Code backup separates prompt sections, available-skill discovery, and active-skill injection; the plan should do the same using the repo's current `context.py`, `system.py`, `skill_context.py`, and skill registry seams.

### Task 1: Split prompt assembly into stable core, runtime overlay, and active-skill sections

**Files:**
- Modify: `backend/nanobot/agent/context.py`
- Modify: `backend/app/domain/services/prompts/system.py`
- Modify: `backend/app/domain/services/prompts/sandbox_context.py`
- Modify: `backend/app/domain/services/prompts/skill_context.py`
- Test: `backend/tests/domain/services/test_agent_context.py`
- Test: `backend/tests/domain/services/prompts/test_sandbox_context.py`
- Test: `backend/tests/domain/services/prompts/test_skill_context.py`
- Test: `backend/tests/domain/models/test_prompt_profile.py`

- [ ] **Step 1: Write the failing tests**
  - Assert that prompt sections are emitted in a deterministic order.
  - Assert that runtime metadata such as timestamps, channel/chat IDs, and other turn-specific facts live outside the cacheable prompt core.
  - Assert that prompt-profile selection data stays structured metadata instead of being flattened into prose.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_context.py tests/domain/services/prompts/test_sandbox_context.py tests/domain/services/prompts/test_skill_context.py tests/domain/models/test_prompt_profile.py
```

Expected: failures describing the missing section contract, cache boundary, or structured profile fields.

- [ ] **Step 3: Implement the minimal prompt-section refactor**
  - Use explicit helpers for the stable prompt core, runtime overlay, and skill sections instead of one concatenated string.
  - Keep the stable core cacheable and keep session-specific facts out of the cacheable path.
  - Thread `skill_names` through the active-skill path so the caller can distinguish discovery from activation.
  - Reuse the existing `PromptProfile` model for versioned prompt patches instead of inventing a second profile concept.

- [ ] **Step 4: Re-run the targeted tests**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_context.py tests/domain/services/prompts/test_sandbox_context.py tests/domain/services/prompts/test_skill_context.py tests/domain/models/test_prompt_profile.py
```

Expected: pass.

- [ ] **Step 5: Run backend lint on the touched Python files**

```bash
cd backend && ruff check app/domain/services/prompts/system.py app/domain/services/prompts/sandbox_context.py app/domain/services/prompts/skill_context.py nanobot/agent/context.py
```

Expected: pass, or a small number of fixable style errors that can be cleared before moving on.

### Task 2: Make skill discovery progressive and provenance-aware

**Files:**
- Modify: `backend/nanobot/agent/skills.py`
- Modify: `backend/app/domain/services/skill_registry.py`
- Modify: `backend/app/domain/services/skill_loader.py`
- Modify: `backend/app/domain/services/prompts/skill_context.py`
- Test: `backend/tests/domain/services/test_skill_loader.py`
- Test: `backend/tests/domain/services/test_skill_system.py`
- Test: `backend/tests/domain/services/prompts/test_skill_context.py`

- [ ] **Step 1: Write the failing tests**
  - Add coverage for metadata-only discovery versus full-body loading.
  - Add coverage for `always` skills being preloaded into context.
  - Add coverage that the `available_skills` summary stays cheap and factual.
  - Add coverage that dynamic context expansion is allowed only for official/system-owned skills.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_skill_loader.py tests/domain/services/test_skill_system.py tests/domain/services/prompts/test_skill_context.py
```

Expected: failures around missing progressive disclosure, provenance handling, or activation order.

- [ ] **Step 3: Implement the skill-loading split**
  - Keep filesystem/database discovery, summary generation, and full prompt-body loading as separate steps.
  - Reuse `build_available_skills_xml_from_registry()` and `build_skill_context_from_ids()` instead of creating a second discovery path.
  - Keep `expand_dynamic_context()` restricted to official skills only.
  - Preserve tool-restriction computation as a separate output from prompt text so the runtime can inspect it directly.

- [ ] **Step 4: Re-run the targeted tests**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_skill_loader.py tests/domain/services/test_skill_system.py tests/domain/services/prompts/test_skill_context.py
```

Expected: pass.

- [ ] **Step 5: Run backend lint on the touched Python files**

```bash
cd backend && ruff check app/domain/services/skill_loader.py app/domain/services/skill_registry.py app/domain/services/prompts/skill_context.py nanobot/agent/skills.py
```

Expected: pass.

## Chunk 2: Backend Agent Roles, Profile Selection, and Activation

This chunk locks the role model to a small explicit set and makes the runtime route through that set rather than inferring behavior from prompt text. The Claude Code backup's built-in `general-purpose`, `Explore`, `Plan`, and `verification` agents are the design reference here.

### Task 3: Bind explicit agent roles to the existing capability registry and prompt-profile resolver

**Files:**
- Modify: `backend/app/domain/services/agents/registry/capability_registry.py`
- Modify: `backend/app/domain/services/prompt_optimization/profile_resolver.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `backend/app/domain/services/flows/task_orchestrator.py`
- Modify: `backend/app/domain/services/agents/agent_context_factory.py`
- Test: `backend/tests/domain/models/test_prompt_profile.py`
- Test: `backend/tests/domain/services/agents/test_agent_task_factory.py`
- Test: `backend/tests/domain/services/flows/test_task_orchestrator.py`
- Test: `backend/tests/domain/services/test_agent_domain_service_reactivation_context.py`

- [ ] **Step 1: Write the failing tests**
  - Add coverage for a minimal role set: general-purpose, explorer, planner, verifier.
  - Add coverage that the verifier role is read-only and cannot self-approve its own work.
  - Add coverage that explorer/planner roles use narrower tool budgets or tighter allowed-tool sets than the general role.
  - Add coverage that profile selection remains a separate overlay on top of the base role definition.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/models/test_prompt_profile.py tests/domain/services/agents/test_agent_task_factory.py tests/domain/services/flows/test_task_orchestrator.py tests/domain/services/test_agent_domain_service_reactivation_context.py
```

Expected: failures around missing role metadata, selection context, or tool-budget rules.

- [ ] **Step 3: Implement the role/profile wiring**
  - Reuse the existing capability registry as the source of truth for role-level tool and capability boundaries.
  - Keep prompt profiles as versioned overlays applied after role selection.
  - Keep built-in role definitions small and explicit; do not infer role identity from free-form prompt text.
  - Preserve one-shot specializations for roles that should stop after producing a report.

- [ ] **Step 4: Re-run the targeted tests**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/models/test_prompt_profile.py tests/domain/services/agents/test_agent_task_factory.py tests/domain/services/flows/test_task_orchestrator.py tests/domain/services/test_agent_domain_service_reactivation_context.py
```

Expected: pass.

### Task 4: Tighten skill activation precedence and routing

**Files:**
- Modify: `backend/app/domain/services/skill_activation_framework.py`
- Modify: `backend/app/domain/services/skill_registry.py`
- Modify: `backend/app/domain/services/agents/execution.py`
- Modify: `backend/app/domain/services/tools/skill_invoke.py`
- Test: `backend/tests/domain/services/test_skill_activation_framework.py`
- Test: `backend/tests/domain/services/test_agent_domain_service_skill_activation_policy.py`
- Test: `backend/tests/domain/services/test_agent_domain_service_reactivation_context.py`

- [ ] **Step 1: Write the failing tests**
  - Add coverage that explicit chat-box selection wins over auto-triggered matches.
  - Add coverage that slash-command invocation wins over auto-triggering.
  - Add coverage that auto-triggering stays opt-in and can be disabled without affecting explicit selection.
  - Add coverage that embedded command fallbacks remain compatibility-only, not the preferred path.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_skill_activation_framework.py tests/domain/services/test_agent_domain_service_skill_activation_policy.py tests/domain/services/test_agent_domain_service_reactivation_context.py
```

Expected: failures around precedence, routing, or missing provenance.

- [ ] **Step 3: Implement explicit activation precedence and session provenance**
  - Keep `build_available_skills_xml_from_registry()` as discovery only.
  - Keep `build_skill_context_from_ids()` as the activation path.
  - Thread the resolved activation source into session/turn context so downstream code can report why a skill was active.
  - Keep the activation policy factual and narrow: explicit selection first, slash command second, auto-trigger third.

- [ ] **Step 4: Re-run the targeted tests**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_skill_activation_framework.py tests/domain/services/test_agent_domain_service_skill_activation_policy.py tests/domain/services/test_agent_domain_service_reactivation_context.py
```

Expected: pass.

- [ ] **Step 5: Run backend lint on the touched Python files**

```bash
cd backend && ruff check app/domain/services/skill_activation_framework.py app/domain/services/skill_registry.py app/domain/services/tools/skill_invoke.py app/domain/services/agents/execution.py
```

Expected: pass.

## Chunk 3: API Contract, UI State, and Observability

The final chunk exposes the new role and skill metadata to the frontend without inventing a separate contract. The UI should show the same factual metadata the backend uses, and the session history should preserve enough provenance to debug prompt changes and cache behavior.

### Task 5: Extend the session, skill, and prompt-profile API contracts

**Files:**
- Modify: `backend/app/interfaces/schemas/session.py`
- Modify: `backend/app/interfaces/api/session_routes.py`
- Modify: `backend/app/interfaces/schemas/skill.py`
- Modify: `backend/app/interfaces/api/skills_routes.py`
- Modify: `backend/app/interfaces/schemas/prompt_optimization.py`
- Modify: `backend/app/interfaces/api/prompt_optimization_routes.py`
- Modify: `frontend/src/contracts/agent.schema.ts`
- Modify: `frontend/src/api/agent.ts`
- Modify: `frontend/src/api/skills.ts`
- Test: `backend/tests/interfaces/api/test_session_routes.py`
- Test: `backend/tests/interfaces/api/test_prompt_optimization_routes.py`
- Test: `backend/tests/domain/services/test_skill_system.py`
- Test: `frontend/src/api/__tests__/agent-chat.test.ts`

- [ ] **Step 1: Write the failing tests**
  - Add coverage for session create/get payloads that include the chosen agent role and active skill list.
  - Add coverage for prompt-profile selection metadata staying structured in API responses.
  - Add coverage that skill metadata exposed to the frontend matches the backend's factual schema.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py tests/interfaces/api/test_prompt_optimization_routes.py tests/domain/services/test_skill_system.py
```

and

```bash
cd frontend && bun run test:run -- frontend/src/api/__tests__/agent-chat.test.ts
```

Expected: failures until the new response fields and serialization paths are wired through.

- [ ] **Step 3: Update the API contracts**
  - Extend the session response schema with selected role, active skills, and activation provenance.
  - Extend prompt-profile responses with the minimum selection metadata the UI needs.
  - Keep the skill response shape narrow and factual; do not duplicate backend enums if an existing schema already exists.
  - Keep the frontend contract as a mirror of the backend schema, not a new source of truth.

- [ ] **Step 4: Re-run the targeted tests and frontend checks**

```bash
cd backend && pytest -p no:cov -o addopts= tests/interfaces/api/test_session_routes.py tests/interfaces/api/test_prompt_optimization_routes.py tests/domain/services/test_skill_system.py
```

and

```bash
cd frontend && bun run test:run -- frontend/src/api/__tests__/agent-chat.test.ts && bun run lint:check && bun run type-check
```

Expected: pass.

### Task 6: Surface role and skill state in the session UI

**Files:**
- Modify: `frontend/src/components/SkillPicker.vue`
- Modify: `frontend/src/pages/HomePage.vue`
- Modify: `frontend/src/pages/ChatPage.vue`
- Create: `frontend/src/components/__tests__/SkillPicker.spec.ts`
- Create: `frontend/src/pages/__tests__/HomePage.spec.ts`
- Create: `frontend/src/pages/__tests__/ChatPage.spec.ts`
- Test: `frontend/src/utils/__tests__/sessionHistory.spec.ts`

- [ ] **Step 1: Write the failing tests**
  - Add coverage that the skill picker shows source/provenance and the important capability metadata.
  - Add coverage that the home and chat flows preserve the selected role and skills across session creation and resume.
  - Add coverage that the UI does not silently drop session-level skill state on reload.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd frontend && bun run test:run -- frontend/src/components/__tests__/SkillPicker.spec.ts frontend/src/pages/__tests__/HomePage.spec.ts frontend/src/pages/__tests__/ChatPage.spec.ts frontend/src/utils/__tests__/sessionHistory.spec.ts
```

Expected: failures around missing UI fields or session-state plumbing.

- [ ] **Step 3: Implement the UI updates**
  - Keep `SkillPicker` as a thin presentation layer over richer skill metadata.
  - Make session creation and resume pass the chosen role and skill set explicitly.
  - Keep the home-page quick actions and chat-page bootstrap aligned so the first message and later turns use the same contract.
  - Show only factual metadata in the UI; do not invent derived state that the backend did not send.

- [ ] **Step 4: Re-run the targeted tests and frontend checks**

```bash
cd frontend && bun run test:run -- frontend/src/components/__tests__/SkillPicker.spec.ts frontend/src/pages/__tests__/HomePage.spec.ts frontend/src/pages/__tests__/ChatPage.spec.ts frontend/src/utils/__tests__/sessionHistory.spec.ts && bun run lint:check && bun run type-check
```

Expected: pass.

### Task 7: Add prompt and role observability surfaces

**Files:**
- Modify: `backend/nanobot/agent/context.py`
- Modify: `backend/app/domain/services/prompt_optimization/profile_resolver.py`
- Modify: `backend/app/domain/services/agent_domain_service.py`
- Modify: `frontend/src/pages/ChatPage.vue`
- Test: `backend/tests/domain/services/test_agent_context.py`
- Test: `frontend/src/utils/__tests__/sessionHistory.spec.ts`

- [ ] **Step 1: Write the failing tests**
  - Add coverage for prompt-section metadata being emitted by the backend.
  - Add coverage that the frontend can surface which role/profile and skills were active for a session.
  - Add coverage that observability data remains factual and does not invent state.

- [ ] **Step 2: Run the targeted tests to verify they fail**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_context.py
```

and

```bash
cd frontend && bun run test:run -- frontend/src/utils/__tests__/sessionHistory.spec.ts
```

Expected: failures until the observability payloads are wired through.

- [ ] **Step 3: Implement the observability plumbing**
  - Add a minimal prompt-section summary to the backend response or session metadata.
  - Surface that summary in the chat/session UI where it helps debugging.
  - Keep the output factual and compact.
  - Reuse existing session-history and telemetry surfaces before adding anything new.

- [ ] **Step 4: Re-run the targeted tests and frontend checks**

```bash
cd backend && pytest -p no:cov -o addopts= tests/domain/services/test_agent_context.py && cd ../frontend && bun run test:run -- frontend/src/utils/__tests__/sessionHistory.spec.ts && bun run lint:check && bun run type-check
```

Expected: pass.

---

### Critical Files for Implementation
- `backend/nanobot/agent/context.py`
- `backend/nanobot/agent/skills.py`
- `backend/app/domain/services/prompts/system.py`
- `backend/app/domain/services/prompts/skill_context.py`
- `backend/app/domain/services/skill_registry.py`
- `backend/app/domain/services/skill_activation_framework.py`
- `backend/app/domain/services/agents/registry/capability_registry.py`
- `backend/app/domain/services/prompt_optimization/profile_resolver.py`
- `backend/app/interfaces/schemas/session.py`
- `backend/app/interfaces/api/session_routes.py`
- `frontend/src/contracts/agent.schema.ts`
- `frontend/src/api/agent.ts`
- `frontend/src/components/SkillPicker.vue`
