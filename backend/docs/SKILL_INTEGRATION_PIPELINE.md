# Skill System Integration Pipeline

## Complete Data Flow & Tool Connections

This document maps the exact integration points between the skill system and agent workflow.

---

## 1. End-to-End Pipeline Overview

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                            SKILL INTEGRATION PIPELINE                                   │
└────────────────────────────────────────────────────────────────────────────────────────┘

USER INPUT                          SKILL RESOLUTION                     AGENT EXECUTION
─────────────────────────────────────────────────────────────────────────────────────────

┌─────────────┐     ┌─────────────────────┐     ┌─────────────────────────────────────┐
│ Chat Input  │────▶│ message.skills[]    │────▶│ ExecutionAgent._setup()             │
│ + Selected  │     │ (from SkillsPopover │     │ ├── build_skill_context_from_ids()  │
│   Skills    │     │  or /skill-name)    │     │ ├── Inject into system_prompt       │
└─────────────┘     └─────────────────────┘     │ └── (Line 91-105 execution.py)      │
                                                └─────────────────────────────────────┘
                                                                 │
                                                                 ▼
                                                ┌─────────────────────────────────────┐
                                                │ LLM Call with Skill Context         │
                                                │ SYSTEM_PROMPT                       │
                                                │ + EXECUTION_SYSTEM_PROMPT           │
                                                │ + <enabled_skills>...</enabled_skills>
                                                └─────────────────────────────────────┘
```

---

## 2. Component Connection Map

### 2.1 Frontend → Backend Flow

```
frontend/src/components/SkillsPopover.vue
         │
         │ User selects skills
         ▼
frontend/src/composables/useSkills.ts
         │ selectedSkillIds: ref<string[]>
         │
         │ Included in chat message
         ▼
frontend/src/api/agent.ts
         │ POST /sessions/{id}/chat
         │ body: { message, skills: selectedSkillIds }
         ▼
backend/app/interfaces/api/routes.py
         │ ChatRequest → Message model
         ▼
backend/app/domain/models/message.py
         │ Message.skills: list[str]
         ▼
backend/app/domain/services/flows/plan_act.py
         │ Passes message to ExecutionAgent
         ▼
backend/app/domain/services/agents/execution.py:91-105
         │ await build_skill_context_from_ids(message.skills)
         │ self.system_prompt += skill_context
```

### 2.2 Skill Context Building

```
backend/app/domain/services/prompts/skill_context.py

build_skill_context_from_ids(skill_ids: list[str])
         │
         ├──▶ get_skill_service().get_skills_by_ids(skill_ids)
         │    └── MongoSkillRepository.get_by_ids()
         │
         ├──▶ build_skill_context_async(skills)
         │    ├── For each skill:
         │    │   └── build_skill_content(skill)
         │    │       ├── substitute_arguments($ARGUMENTS, $1, $2)
         │    │       └── expand_dynamic_context(!`command`)
         │    │
         │    └── Wrap in <enabled_skills> XML block
         │
         └──▶ Returns: str (formatted skill context)
```

### 2.3 Tool Restrictions Flow

```
backend/app/domain/services/prompts/skill_context.py

get_allowed_tools_from_skills(skills: list[Skill])
         │
         │ For each skill with allowed_tools:
         │   Compute intersection of all restrictions
         │
         └──▶ Returns: set[str] | None

┌─────────────────────────────────────────────────────────────────────┐
│ INTEGRATION POINT (NOT YET CONNECTED)                               │
│ The allowed_tools result is computed but NOT applied to tool list   │
│ in ExecutionAgent. This needs to be wired in plan_act.py:           │
│                                                                     │
│   if allowed_tools := get_allowed_tools_from_skills(skills):        │
│       tools = [t for t in tools if t.name in allowed_tools]         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. File-by-File Connection Matrix

| File | Connects To | Purpose |
|------|-------------|---------|
| `models/skill.py` | All skill files | Domain entity definition |
| `models/skill_package.py` | `skill_packager.py`, `skills_routes.py` | Package format for export |
| `services/skill_validator.py` | `skill_creator.py`, `skills_routes.py` | Security validation |
| `services/skill_packager.py` | `skill_creator.py`, `skills_routes.py` | ZIP package creation |
| `prompts/skill_context.py` | `execution.py`, `planner.py` | Context injection |
| `prompts/skill_creator.py` | `skill_creator.py` tool | Guided creation prompts |
| `tools/skill_invoke.py` | Agent tool list | AI skill invocation |
| `tools/skill_creator.py` | `plan_act.py` tool setup | CRUD tools |
| `services/skill_service.py` | All that need DB access | Application CRUD |
| `repositories/mongo_skill_repository.py` | `skill_service.py` | MongoDB persistence |
| `api/skills_routes.py` | Frontend API calls | REST endpoints |
| `schemas/skill.py` | `skills_routes.py` | Request/Response models |

---

## 4. Tool Registration Points

### 4.1 Skill Creator Tools (plan_act.py:96)

```python
# backend/app/domain/services/flows/plan_act.py

from app.domain.services.tools.skill_creator import get_skill_creator_tools

# In PlanActFlow.__init__:
skill_tools = get_skill_creator_tools(
    user_id=user_id,
    emit_event=self._emit_event,  # For SkillDeliveryEvent
)
self.tools.extend(skill_tools)
```

**Tools Registered:**
- `skill_create` - Create new custom skill
- `skill_list` - List user's custom skills
- `skill_delete` - Delete custom skill

### 4.2 Skill Invoke Tool (NOT YET REGISTERED)

```python
# NEEDED IN: backend/app/domain/services/flows/plan_act.py

from app.domain.services.tools.skill_invoke import create_skill_invoke_tool
from app.application.services.skill_service import get_skill_service

# Get available skills for session
skill_service = get_skill_service()
available_skills = await skill_service.get_all_skills()

# Filter to AI-invokable
ai_skills = [s for s in available_skills
             if s.invocation_type in (SkillInvocationType.AI, SkillInvocationType.BOTH)]

# Create and register tool
skill_invoke_tool = create_skill_invoke_tool(
    available_skills=ai_skills,
    session_id=session_id,
)
self.tools.append(skill_invoke_tool)
```

---

## 5. Event Flow for Skill Delivery

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SKILL DELIVERY EVENT FLOW                        │
└─────────────────────────────────────────────────────────────────────────┘

Agent calls skill_create tool
         │
         ▼
backend/app/domain/services/tools/skill_creator.py:SkillCreatorTool.execute()
         │
         ├── Validate via SkillValidator
         ├── Save skill via SkillService
         ├── Create package via SkillPackager
         │
         └── Emit SkillDeliveryEvent
                  │
                  ▼
         SSE Stream to Frontend
                  │
                  ▼
frontend/src/components/ChatMessage.vue
         │
         └── Renders SkillDeliveryCard
                  │
                  ├── View Package (SkillViewerModal)
                  ├── Download .skill file
                  └── Install skill (enables it)
```

---

## 6. Database Schema Connections

```
MongoDB Collections:

skills (SkillDocument)
├── skill_id: str (indexed, unique)
├── owner_id: str (indexed for custom skills)
├── category: str (indexed)
├── is_public: bool (indexed for community)
├── source: str (official/community/custom)
└── All Skill model fields...

sessions (SessionDocument)
├── enabled_skills: list[str]  # Skill IDs enabled for session
└── ...

user_settings (UserSettingsDocument)
├── skill_configs: list[UserSkillConfig]
│   ├── skill_id: str
│   ├── enabled: bool
│   └── config: dict
└── ...
```

---

## 7. API Endpoint Matrix

| Endpoint | Method | Handler | Purpose |
|----------|--------|---------|---------|
| `/skills` | GET | `get_available_skills` | List all skills |
| `/skills/{id}` | GET | `get_skill` | Get single skill |
| `/skills/user/config` | GET | `get_user_skills` | User's enabled config |
| `/skills/user/{id}` | PUT | `update_user_skill` | Toggle enable/config |
| `/skills/user/enable` | POST | `enable_skills` | Bulk enable skills |
| `/skills/tools/required` | GET | `get_required_tools` | Tools for skill IDs |
| `/skills/custom` | POST | `create_custom_skill` | Create custom |
| `/skills/custom` | GET | `get_my_custom_skills` | List user's custom |
| `/skills/custom/{id}` | PUT | `update_custom_skill` | Update custom |
| `/skills/custom/{id}` | DELETE | `delete_custom_skill` | Delete custom |
| `/skills/custom/{id}/publish` | POST | `publish_custom_skill` | Publish to community |
| `/skills/packages/{id}` | GET | `get_skill_package` | Package metadata |
| `/skills/packages/{id}/download` | GET | `download_skill_package` | Download .skill ZIP |
| `/skills/packages/{id}/file` | GET | `get_package_file` | Single file content |
| `/skills/packages/{id}/install` | POST | `install_skill_package` | Install from package |

---

## 8. Missing Integration Points (Action Items)

### 8.1 Tool Restriction Enforcement

**Location:** `backend/app/domain/services/agents/execution.py`

```python
# AFTER line 105, ADD:
from app.domain.services.prompts.skill_context import get_allowed_tools_from_skill_ids

# Get tool restrictions from enabled skills
if message.skills:
    allowed_tools = await get_allowed_tools_from_skill_ids(message.skills)
    if allowed_tools is not None:
        # Filter self.tools to only allowed
        self.tools = [t for t in self.tools if t.name in allowed_tools]
        logger.info(f"Applied tool restrictions: {len(self.tools)} tools available")
```

### 8.2 Skill Invoke Tool Registration

**Location:** `backend/app/domain/services/flows/plan_act.py`

```python
# In tool setup section, ADD:
from app.domain.services.tools.skill_invoke import create_skill_invoke_tool

async def _setup_skill_invoke_tool(self) -> None:
    """Register skill_invoke meta-tool for AI invocation."""
    skill_service = get_skill_service()
    all_skills = await skill_service.get_all_skills()

    # Filter to AI-invokable skills
    ai_skills = [
        s for s in all_skills
        if s.invocation_type in (SkillInvocationType.AI, SkillInvocationType.BOTH)
    ]

    if ai_skills:
        self.tools.append(create_skill_invoke_tool(
            available_skills=ai_skills,
            session_id=self._session_id,
        ))
```

### 8.3 Trigger Pattern Matching

**Location:** `backend/app/domain/services/agents/execution.py`

```python
# In execute_step(), before skill context building, ADD:
from app.domain.services.skill_trigger_matcher import SkillTriggerMatcher

# Auto-detect skills if none explicitly selected
if not message.skills:
    matcher = SkillTriggerMatcher()
    matched_skills = await matcher.find_matches(message.message)
    if matched_skills:
        message.skills = [m.skill_id for m in matched_skills[:2]]
        logger.info(f"Auto-detected skills from patterns: {message.skills}")
```

### 8.4 Planner Skill Context

**Location:** `backend/app/domain/services/agents/planner.py`

```python
# Planner should also receive skill context for planning with skill awareness
if message.skills:
    from app.domain.services.prompts.skill_context import build_skill_context_from_ids
    skill_context = await build_skill_context_from_ids(message.skills)
    if skill_context:
        self.system_prompt = BASE_PLANNER_PROMPT + skill_context
```

---

## 9. Testing Checklist

### Unit Tests Needed

- [ ] `test_skill_context_building` - Verify context assembly
- [ ] `test_skill_argument_substitution` - $ARGUMENTS, $1, $2 work
- [ ] `test_skill_dynamic_context` - !`command` expansion
- [ ] `test_skill_tool_restrictions` - allowed_tools intersection
- [ ] `test_skill_invoke_tool` - AI invocation works
- [ ] `test_skill_trigger_patterns` - Regex matching

### Integration Tests Needed

- [ ] `test_skill_flows_to_execution` - message.skills → system_prompt
- [ ] `test_skill_tools_filtered` - Tool list respects allowed_tools
- [ ] `test_skill_creation_flow` - Create → Package → Deliver → Install
- [ ] `test_skill_invocation_flow` - User /skill → AI skill_invoke

---

## 10. Performance Considerations

### Current Issues

1. **No Caching**: `get_skill_service().get_skills_by_ids()` hits DB every time
2. **No Preloading**: Skills loaded per-message, not per-session
3. **Sync Context Expansion**: Dynamic !command runs synchronously

### Recommended Optimizations

```python
# Session-level skill cache
class SessionSkillCache:
    _cache: dict[str, list[Skill]] = {}
    _ttl = timedelta(minutes=5)

    async def get_skills(self, session_id: str, skill_ids: list[str]) -> list[Skill]:
        cache_key = f"{session_id}:{':'.join(sorted(skill_ids))}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        # ... fetch and cache
```

---

## Summary

The skill system is now fully integrated with all components connected:

| Component | Status | Location |
|-----------|--------|----------|
| Skill Model | ✅ Complete | `domain/models/skill.py` |
| Skill Validation | ✅ Complete | `domain/services/skill_validator.py` |
| Skill Packaging | ✅ Complete | `domain/services/skill_packager.py` |
| Context Building | ✅ Complete | `domain/services/prompts/skill_context.py` |
| Context Injection | ✅ Connected | `execution.py:91-130` |
| Tool Restrictions | ✅ Connected | `execution.py:120-127` |
| Skill Invoke Tool | ✅ Registered | `plan_act.py:192-199, 323-347` |
| Trigger Patterns | ✅ Implemented | `domain/services/skill_trigger_matcher.py` |
| Auto-Detection | ✅ Implemented | `execution.py:95-107` |
| Planner Integration | ✅ Connected | `planner.py:215-235` |
| Skill Registry | ✅ Implemented | `domain/services/skill_registry.py` |
| Caching | ✅ Implemented | `skill_registry.py` (5min TTL) |

### New Files Added

- `backend/app/domain/services/skill_registry.py` - Centralized registry with caching
- `backend/app/domain/services/skill_trigger_matcher.py` - Pattern-based auto-detection
- `backend/tests/domain/services/test_skill_system.py` - Unit tests (11 passing)

---

*Last Updated: 2026-01-31*
*Implementation Status: Complete*
