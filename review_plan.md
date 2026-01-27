# PyThinker Agent Workflow Enhancement Plan

---

## Executive Summary

This plan enhances the existing **PyThinker** implementation based on a gap analysis between `review_plan.md` and the current codebase.

Key finding: the system is **more mature than expected**. Most components already exist but are **not fully wired together**. The focus therefore shifts from building new systems to **integration, validation, and wiring**.

---

## Current State Assessment

### What’s Already Implemented (No Changes Needed)

| Component              | Status     | Location / Notes                                                  |
| ---------------------- | ---------- | ----------------------------------------------------------------- |
| Error Handler          | ✅ Complete | `error_handler.py` – classification, backoff, retry by error type |
| Memory Manager         | ✅ Complete | `memory_manager.py` – smart compaction, pressure levels, archival |
| Token Manager          | ✅ Complete | `token_manager.py` – accurate counting, trimming                  |
| Verification System    | ✅ Complete | `verifier.py` – structured feedback, PASS / REVISE / FAIL         |
| Plan Model             | ✅ Complete | `plan.py` – dependencies, cascade blocking, status helpers        |
| Error Pattern Analyzer | ✅ Complete | `error_pattern_analyzer.py` – stuck detection                     |
| Agent Registry         | ✅ Complete | `agent_types.py` – 12 agent types, capability scoring             |
| Agent Factory          | ✅ Complete | `agent_factory.py` – creates agents from specs                    |

---

### Critical Gaps (Focus of This Plan)

| Gap                                        | Impact | Effort |
| ------------------------------------------ | ------ | ------ |
| State fragmentation (3+ overlapping enums) | HIGH   | Medium |
| TaskStateManager not wired into flow       | HIGH   | Low    |
| Multi-agent dispatch not integrated        | MEDIUM | Medium |
| No plan validation before execution        | MEDIUM | Medium |
| Fixed step constraints (MIN=3, MAX=6)      | LOW    | Low    |
| Output compliance gates missing            | MEDIUM | High   |

---

## Recommended Changes (Prioritized)

---

## Phase 1: Critical Bug Fixes & Integration (Week 1)

### 1.1 Fix TaskStateManager Sandbox Method Name (BUG)

**Location**
`backend/app/domain/services/agents/task_state_manager.py:286`

**Problem**
Uses `write_file()` but the Sandbox protocol defines `file_write()` → runtime failure.

**Fix**

```python
# Current (broken)
await self._sandbox.write_file(self._file_path, content)

# Fixed
await self._sandbox.file_write(self._file_path, content)
```

---

### 1.2 Fix Step Completion Status Always Marked "completed" (BUG)

**Location**
`backend/app/domain/services/flows/plan_act.py:855`

**Problem**
Steps are always marked `completed`, even on failure.

**Fix**

```python
if step.success:
    self._task_state_manager.update_step_status(str(step.id), "completed")
else:
    self._task_state_manager.update_step_status(str(step.id), "failed")
```

---

### 1.3 Persist TaskState to Sandbox (MISSING)

**Location**
`backend/app/domain/services/flows/plan_act.py`

**Problem**
TaskState updates are never persisted to sandbox storage.

**Add Call (after step completion)**

```python
self._background_save_task_state()
```

**New Method**

```python
def _background_save_task_state(self) -> None:
    async def _save():
        try:
            await self._task_state_manager.save_to_sandbox()
            logger.debug(f"Agent {self._agent_id} task state saved")
        except Exception as e:
            logger.warning(f"Task state save failed: {e}")

    task = asyncio.create_task(_save())
    self._background_tasks.add(task)
    task.add_done_callback(self._background_tasks.discard)
```

**Files to Modify**

* `task_state_manager.py:286`
* `plan_act.py:855`
* `plan_act.py:~470` (new method)
* `plan_act.py:~870` (call method)

---

### 1.4 Integrate Multi-Agent Dispatch

**Location**
`backend/app/domain/services/flows/plan_act.py:332–401`

**Problem**
`AgentRegistry` exists but `_get_executor_for_step()` does not use it.

**Changes**

1. Use `agent_registry.select_for_task(step.description, context)`
2. Retrieve best-matched agent spec
3. Instantiate via `agent_factory.create_agent()`
4. Cache agents for reuse

**Additional**

* Enable `enable_multi_agent = True` by default

---

### 1.5 Add Plan Validation Before Execution

**Location**
`backend/app/domain/models/plan.py`

**Problem**
No pre-execution validation (only runtime dependency checks).

**New Method**

```python
def validate_plan(self) -> ValidationResult:
    """Pre-execution plan validation

    Checks:
    - Circular dependencies
    - Orphan steps
    - Empty or invalid steps
    """
```

**Integration**

* Call before EXECUTING transition in `plan_act.py:753–759`

---

## Phase 2: State Model Unification (Week 1–2)

### 2.1 Add Unified State Transition Validator

**New File**
`backend/app/domain/models/state_model.py`

**Problem**
Three overlapping state systems without transition validation.

**Solution**

```python
VALID_TRANSITIONS = {
    AgentStatus.IDLE: [AgentStatus.PLANNING],
    AgentStatus.PLANNING: [AgentStatus.VERIFYING, AgentStatus.EXECUTING, AgentStatus.ERROR],
    AgentStatus.VERIFYING: [AgentStatus.EXECUTING, AgentStatus.PLANNING, AgentStatus.SUMMARIZING, AgentStatus.ERROR],
    AgentStatus.EXECUTING: [AgentStatus.UPDATING, AgentStatus.SUMMARIZING, AgentStatus.ERROR],
    AgentStatus.UPDATING: [AgentStatus.EXECUTING, AgentStatus.ERROR],
    AgentStatus.SUMMARIZING: [AgentStatus.COMPLETED, AgentStatus.ERROR],
    AgentStatus.COMPLETED: [AgentStatus.IDLE],
    AgentStatus.ERROR: [AgentStatus.PLANNING, AgentStatus.EXECUTING, AgentStatus.IDLE],
}
```

---

## Phase 3: Adaptive Planning (Week 2)

### 3.1 Adaptive Step Constraints

**Current**
`MIN_PLAN_STEPS = 3`, `MAX_PLAN_STEPS = 6`

**Proposed**

```python
MIN_PLAN_STEPS = 1
MAX_PLAN_STEPS = 12
```

```python
def get_task_complexity(message: str, tools: list) -> str:
    return 'simple' | 'medium' | 'complex'


def get_step_limits(complexity: str) -> tuple[int, int]:
    return {
        'simple': (1, 3),
        'medium': (3, 6),
        'complex': (5, 12),
    }[complexity]
```

---

### 3.2 Preserve Merged Step Details

**Problem**
Original step details are lost during merges.

**Change**

```python
class Step(BaseModel):
    metadata: Optional[Dict[str, Any]] = None
```

Used to store:

* merged step IDs
* original descriptions

---

## Phase 4: Proactive Error Prevention (Week 2–3)

### 4.1 Inject Error Pattern Signals Before Execution

**Location**
`backend/app/domain/services/agents/execution.py`

**Change**

```python
pattern_signals = error_pattern_analyzer.get_proactive_signals(
    likely_tools=self._infer_tools_from_step(step.description)
)

if pattern_signals:
    execution_message += f"\n\nCAUTION: {pattern_signals}"
```

---

## Phase 5: Output Quality Gates (Week 3)

### 5.1 Compliance Gate System

**New File**
`backend/app/domain/services/agents/compliance_gates.py`

**Purpose**
Block final output if quality issues are detected.

**Gates**

```python
class ComplianceGates:
    def check_artifact_hygiene(self, artifacts):
        pass

    def check_command_context(self, content):
        pass

    def check_source_labeling(self, sources):
        pass
```

**Integration Point**
`plan_act.py` — during `SUMMARIZING` → `COMPLETED` transition

---

## Implementation Order

### Week 1

* Wire TaskStateManager (2h)
* Multi-agent dispatch (3h)
* Plan validation (2h)
* State transition validator (2h)

### Week 2

* Adaptive step constraints (2h)
* Preserve merged step metadata (1h)
* Proactive error signals (2h)

### Week 3

* Compliance gates (4h)

---

## What NOT to Change

These systems are solid and should remain untouched:

1. Error Handler
2. Memory Manager
3. Verification System
4. Token Manager
5. Main PlanActFlow loop

---

## Decision

**Enhanced Plan Recommended**

This plan:

* Avoids rebuilding what already works
* Fixes critical bugs first
* Focuses on integration and wiring
* Provides exact file paths and line numbers
* Reduces scope from rebuild → integration

**Estimated effort reduced from 8–12 weeks to ~3 weeks.**
