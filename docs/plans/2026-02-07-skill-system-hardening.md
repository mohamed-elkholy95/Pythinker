# Skill System Hardening Plan

**Date**: 2026-02-07
**Scope**: End-to-end skill activation, creation UX, and agent integration
**Reference**: `@system/skills/` (SKILL.md, init_skill.py, quick_validate.py, workflows.md, output-patterns.md, progressive-disclosure-patterns.md)

---

## Executive Summary

After thorough analysis of the skill system, I identified **13 concrete issues** spanning the full stack. The most critical is that **skills activated in chat are cleared after every message**, so the agent loses skill context in multi-turn conversations. The `/skill-creator` command is detected but never actually injects the skill's `system_prompt_addition` into the agent context. The "Build with Pythinker" button only works from the HomePage (not from ChatPage).

The infrastructure for skill injection IS present — `execution.py` and `planner.py` both call `registry.build_context()` and inject into the system prompt. The gap is in how skills **get onto `message.skills`** and how they **persist across messages**.

---

## Issues Found

### Priority 1 — Critical (Skills don't work correctly)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 1 | **Per-message skills cleared** — `clearSelectedSkills()` runs after every send, so skills vanish on follow-up messages | `ChatPage.vue:1270`, `useSkills.ts:194` | Agent loses skill context mid-conversation |
| 2 | **Missing command registry entry** — "skill-creator" not in `SUPERPOWERS_COMMANDS`, so `/skill-creator` never maps to a skill ID | `command_registry.py` | `/skill-creator` command doesn't inject skill |
| 3 | **`_extract_skill_creator_command()` doesn't add skill to message.skills** — only emits tool events, never injects `system_prompt_addition` | `plan_act.py:427-463` | Skill creator instructions never reach agent |
| 4 | **Missing tool/prompt restore in execution.py** — original tools and system_prompt saved but never restored after step, causing stale tool list on non-skill steps | `execution.py:136-186` | Tool list permanently filtered if any step had skills |

### Priority 2 — High (Skill creation UX broken)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 5 | **"Build with Pythinker" only works from HomePage** — `pythinker:insert-chat-message` event listener only on `HomePage.vue`, not `ChatPage.vue` | `SettingsDialog.vue:157`, `HomePage.vue:269` | Button fails if user is in active chat |
| 6 | **init_skill.py hardcoded to `/home/ubuntu/skills`** — doesn't match Pythinker sandbox paths | `system/skills/init_skill.py:195` | Skill init fails in Pythinker sandbox |
| 7 | **quick_validate.py hardcoded to `/home/ubuntu/skills`** — same issue | `system/skills/quick_validate.py:21` | Validation fails in Pythinker sandbox |
| 8 | **skill-creator seed references wrong file path** — `file_read(path="/workspace/skills/skill-creator/SKILL.md")` in `system_prompt_addition` | `skills_seed.py:516` | Agent can't load creation guide |

### Priority 3 — Medium (Quality and hardening)

| # | Issue | File(s) | Impact |
|---|-------|---------|--------|
| 9 | **No session-level skill persistence** — even if we fix per-message clearing, returning users still lose skill context | `agent_domain_service.py`, `useSkills.ts` | Multi-turn skill workflows broken |
| 10 | **Manus branding in system/skills docs** — SKILL.md says "Manus" in several places | `system/skills/SKILL.md` | Branding inconsistency |
| 11 | **No active skill indicator in chat** — user has no visual feedback of which skills are active during the session | `ChatPage.vue`, `ChatBox.vue` | Confusing UX |
| 12 | **Skill picker doesn't auto-select when "/command" typed** — typing `/skill-creator` in chat doesn't auto-select the skill in the picker | `ChatBox.vue`, `SkillPicker.vue` | Inconsistent UX |
| 13 | **Skill creation process references wrong sandbox paths** — the `skill-creator` skill's instructions reference Manus paths | `skills_seed.py:505-599` | Agent follows wrong paths during creation |

---

## Implementation Plan

### Phase 1: Command Registry & Skill Injection Fix (Critical)

**Goal**: Make `/skill-creator` command actually activate the skill and inject its context.

#### Step 1.1: Add "skill-creator" to command registry
**File**: `backend/app/domain/services/command_registry.py`

Add a new `CommandMapping`:
```python
CommandMapping(
    command="skill-creator",
    skill_id="skill-creator",
    description="Create new skills through guided conversation",
    aliases=["create-skill-guided"],
),
```

This ensures `/skill-creator` at the START of a message maps to the "skill-creator" skill ID.

#### Step 1.2: Fix `_parse_command()` to handle embedded commands
**File**: `backend/app/domain/services/agent_domain_service.py`

Currently the regex `r"^/([a-zA-Z0-9_-]+)(?:\s+(.*))?$"` requires the command at the START. The "Build with Pythinker" message starts with "Help me create..." not "/skill-creator".

Solution: Add a fallback check for embedded `/skill-creator` specifically:
```python
command_skill_id, _message_without_command = self._parse_command(message)
if not command_skill_id:
    # Fallback: check for embedded /skill-creator command
    if "/skill-creator" in message.lower():
        command_skill_id = "skill-creator"
```

#### Step 1.3: Remove redundant `_extract_skill_creator_command()` in plan_act.py
**File**: `backend/app/domain/services/flows/plan_act.py`

Since the command registry now handles `/skill-creator`, the separate extraction in `_run_with_trace()` (line 1762-1766) is redundant. Keep the acknowledgment logic in `_generate_acknowledgment()` but remove the tool event emission — the skill's `system_prompt_addition` handles the guidance.

#### Step 1.4: Add tool/prompt restore in execution.py
**File**: `backend/app/domain/services/agents/execution.py`

Wrap the step execution in a `try/finally` to restore original tools and system_prompt:
```python
original_tools = list(self.tools)
original_system_prompt = self.system_prompt
try:
    if message.skills:
        # ... inject skill context
    # ... execute step
    async for event in self._execute_step_impl(plan, step, message):
        yield event
finally:
    self.tools = original_tools
    self.system_prompt = original_system_prompt
```

---

### Phase 2: Skill Persistence Across Messages (Critical)

**Goal**: Skills selected by user persist for the entire session, not just one message.

#### Step 2.1: Add session-level skill persistence in useSkills.ts
**File**: `frontend/src/composables/useSkills.ts`

Add `sessionSkillIds` alongside `selectedSkillIds`:
```typescript
// Session-level persistent skills (persist across messages)
const sessionSkillIds = ref<string[]>([]);

// Lock skills for the session (called when skills are first activated)
function lockSkillsForSession(skillIds: string[]): void {
  sessionSkillIds.value = [...new Set([...sessionSkillIds.value, ...skillIds])];
}

// Clear session skills (called when session changes)
function clearSessionSkills(): void {
  sessionSkillIds.value = [];
}

// Get combined skill IDs (session + per-message selection)
function getEffectiveSkillIds(): string[] {
  return [...new Set([...sessionSkillIds.value, ...selectedSkillIds.value])];
}
```

#### Step 2.2: Update ChatPage.vue to use session skills
**File**: `frontend/src/pages/ChatPage.vue`

- Replace `getSelectedSkillIds()` with `getEffectiveSkillIds()` at line 1295
- Only clear `selectedSkillIds` after send (per-message picks), NOT `sessionSkillIds`
- When `skill_activation` SSE event arrives, call `lockSkillsForSession(data.skill_ids)` to persist for the session
- Clear `sessionSkillIds` when `sessionId` changes (new session)

#### Step 2.3: Show active session skills in ChatBox
**File**: `frontend/src/components/ChatBox.vue` or new sub-component

Add a small chip/tag row above the input showing persistent session skills:
```
[🧩 Skill Creator ×] [🧩 Research ×]
```
Users can dismiss individual session skills by clicking ×.

---

### Phase 3: "Build with Pythinker" End-to-End Fix (High)

**Goal**: Button works from any page and correctly activates the skill-creator flow.

#### Step 3.1: Listen for insert event on ChatPage.vue
**File**: `frontend/src/pages/ChatPage.vue`

Add the same `pythinker:insert-chat-message` event listener:
```typescript
const handleInsertMessage = (event: CustomEvent<{ message: string }>) => {
  inputMessage.value = event.detail.message;
};

onMounted(() => {
  window.addEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);
});

onUnmounted(() => {
  window.removeEventListener('pythinker:insert-chat-message', handleInsertMessage as EventListener);
});
```

#### Step 3.2: Auto-select skill-creator skill when message inserted
**File**: `frontend/src/pages/ChatPage.vue` (or `HomePage.vue`)

When the "Build with Pythinker" message is inserted, also auto-select the skill:
```typescript
const handleInsertMessage = (event: CustomEvent<{ message: string; skillId?: string }>) => {
  inputMessage.value = event.detail.message;
  if (event.detail.skillId) {
    selectSkill(event.detail.skillId);
  }
};
```

Update `SettingsDialog.vue` to include skillId in the event:
```typescript
window.dispatchEvent(new CustomEvent('pythinker:insert-chat-message', {
  detail: { message: skillCreationMessage, skillId: 'skill-creator' }
}));
```

---

### Phase 4: Skill Creation Path Fixes (High)

**Goal**: Fix hardcoded paths and branding to match Pythinker sandbox environment.

#### Step 4.1: Update init_skill.py for Pythinker
**File**: `system/skills/init_skill.py`

Change `SKILLS_BASE_PATH` from `/home/ubuntu/skills` to `/home/user/skills` (Pythinker sandbox user dir).

#### Step 4.2: Update quick_validate.py
**File**: `system/skills/quick_validate.py`

Same path change.

#### Step 4.3: Fix skill-creator seed paths
**File**: `backend/app/infrastructure/seeds/skills_seed.py`

Update the `system_prompt_addition` for skill-creator:
- Change `file_read(path="/workspace/skills/skill-creator/SKILL.md")` → `file_read(path="/home/user/skills/skill-creator/SKILL.md")`
- Reference correct paths for `init_skill.py` and `quick_validate.py`

#### Step 4.4: Update SKILL.md branding
**File**: `system/skills/SKILL.md`

Replace remaining "Manus" references with "Pythinker". The skill-creator skill's `system_prompt_addition` in the seed already uses "Pythinker" but the reference SKILL.md in `system/skills/` still says "Manus" in the description field.

---

### Phase 5: Active Skill Indicator & Auto-Detection (Medium)

**Goal**: Users see what skills are active and `/command` text auto-selects skills.

#### Step 5.1: Add active skills indicator in ChatBox
**File**: `frontend/src/components/ChatBox.vue`

Show a row of skill chips when `sessionSkillIds` is non-empty. Each chip has skill name + dismiss button. Style: subtle, below attachment row, above input.

#### Step 5.2: Auto-detect /commands in chat input
**File**: `frontend/src/components/ChatBox.vue`

Watch the input text for `/skill-creator` or other command patterns. When detected, auto-select the corresponding skill in the picker AND show a subtle toast: "Skill Creator will be activated".

Map commands to skill IDs using a frontend constant derived from the same data as command_registry.py.

---

### Phase 6: Enhance Skill Creation Quality (Medium)

**Goal**: Improve the skill creation flow using `@system/skills/` best practices.

#### Step 6.1: Enhance skill-creator system_prompt_addition
**File**: `backend/app/infrastructure/seeds/skills_seed.py`

Improve the skill-creator's `system_prompt_addition` to reference the progressive disclosure patterns and output patterns from the reference docs:

1. Add explicit instructions for the agent to use `progressive-disclosure-patterns.md` when the skill is complex
2. Reference `workflows.md` for sequential skill creation steps
3. Reference `output-patterns.md` for output format guidance
4. Add validation step that runs `quick_validate.py` before delivery
5. Add a "skill testing" step where agent tests the skill in a dry-run

#### Step 6.2: Copy system/skills reference docs to sandbox
**File**: `backend/app/domain/services/agent_task_runner.py` (or sandbox init)

When the skill-creator skill is active, ensure the reference files from `system/skills/` are available in the sandbox at `/home/user/skills/skill-creator/`:
- `SKILL.md` (creation guide)
- `references/workflows.md`
- `references/output-patterns.md`
- `references/progressive-disclosure-patterns.md`
- `scripts/init_skill.py`
- `scripts/quick_validate.py`

---

## Files to Modify

| File | Phase | Changes |
|------|-------|---------|
| `backend/app/domain/services/command_registry.py` | 1 | Add "skill-creator" command mapping |
| `backend/app/domain/services/agent_domain_service.py` | 1 | Embedded /skill-creator detection fallback |
| `backend/app/domain/services/flows/plan_act.py` | 1 | Remove redundant skill-creator extraction, keep acknowledgment |
| `backend/app/domain/services/agents/execution.py` | 1 | Add try/finally for tool/prompt restore |
| `frontend/src/composables/useSkills.ts` | 2 | Add session-level skill persistence |
| `frontend/src/pages/ChatPage.vue` | 2,3 | Use effective skills, listen for insert event, lock session skills |
| `frontend/src/pages/HomePage.vue` | 3 | Pass skillId in insert event |
| `frontend/src/components/settings/SettingsDialog.vue` | 3 | Include skillId in custom event |
| `frontend/src/components/ChatBox.vue` | 5 | Active skills indicator, auto-detect commands |
| `system/skills/init_skill.py` | 4 | Fix path to `/home/user/skills` |
| `system/skills/quick_validate.py` | 4 | Fix path to `/home/user/skills` |
| `system/skills/SKILL.md` | 4 | Fix Manus→Pythinker branding |
| `backend/app/infrastructure/seeds/skills_seed.py` | 4,6 | Fix paths, enhance skill-creator prompt |

## New Files

| File | Phase | Purpose |
|------|-------|---------|
| `frontend/src/components/ActiveSkillChips.vue` | 5 | Chip row showing active session skills |

---

## Test Plan

### Backend Tests
- [ ] `test_command_registry_skill_creator` — `/skill-creator` maps to "skill-creator" skill ID
- [ ] `test_embedded_skill_creator_detection` — "Help me create... /skill-creator" detected
- [ ] `test_execution_step_tool_restore` — tools and system_prompt restored after each step
- [ ] `test_skill_context_injected_per_step` — each step gets skill context from message.skills
- [ ] `test_skill_creator_system_prompt` — skill-creator's system_prompt_addition injected properly

### Frontend Tests
- [ ] `test_session_skill_persistence` — skills persist across messages within session
- [ ] `test_clear_session_skills_on_change` — session skills clear when sessionId changes
- [ ] `test_build_with_pythinker_from_chat` — button works from ChatPage
- [ ] `test_auto_select_skill_on_command` — typing /skill-creator auto-selects skill

### Integration Tests
- [ ] End-to-end: "Build with Pythinker" → message inserted → skill activated → agent has skill context
- [ ] End-to-end: Select skill in picker → send message → send follow-up → agent still has skill context
- [ ] End-to-end: `/skill-creator MySkill` → agent guides through 6-step creation process

---

## Execution Order

1. **Phase 1** (Critical fixes) — must be done first
2. **Phase 2** (Persistence) — depends on Phase 1
3. **Phase 3** (Build with Pythinker) — can parallel with Phase 2
4. **Phase 4** (Path fixes) — independent, can parallel
5. **Phase 5** (UI indicators) — depends on Phase 2
6. **Phase 6** (Enhancement) — depends on Phase 4
