# Skill Activation Framework

This document defines how Pythinker activates skills in the backend.

## Policy

- Auto-trigger is **OFF by default**.
- Skills are activated only when explicitly requested by the user:
  - chat-box selected skills
  - slash command invocation (for example `/brainstorm`)
- Runtime policy is controlled by:
  - user setting `skill_auto_trigger_enabled` (from `/settings`)
  - environment fallback `SKILL_AUTO_TRIGGER_ENABLED` (default `false`)

## Backend Flow

1. `AgentService.chat(...)` resolves `auto_trigger_enabled` from user settings (with env fallback).
2. `AgentDomainService.chat(...)` calls `SkillActivationFramework.resolve(...)` with that flag.
3. The framework merges activations from:
   - chat-box selected skills
   - slash command parsing via `CommandRegistry`
   - optional embedded command fallback (`/skill-creator`)
4. The resolved skills are attached to `MessageEvent.skills`.
5. Planner/executor build skill context and apply tool restrictions based on resolved skills.
6. `SkillActivationEvent` is emitted with:
   - `skill_ids`
   - `activation_sources`
   - `command_skill_id`
   - `auto_trigger_enabled`

## Key Files

- Framework: `backend/app/domain/services/skill_activation_framework.py`
- Chat orchestration: `backend/app/domain/services/agent_domain_service.py`
- Skill activation event model: `backend/app/domain/models/event.py`
- SSE mapping: `backend/app/interfaces/schemas/event.py`
