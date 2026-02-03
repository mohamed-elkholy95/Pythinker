# Pythinker Agent Enhancement - Implementation Guide

**Version:** 1.0
**Date:** 2026-01-31
**Status:** Ready for Implementation

---

## Overview

This guide provides step-by-step instructions for implementing enhanced agent prompts in Pythinker, based on comprehensive analysis of 30+ AI coding assistants and industry best practices.

### What's Included

1. **Enhanced Prompts Documentation** (`enhanced_prompts.md`)
   - Comprehensive analysis of all enhancements
   - Expected improvements and metrics
   - References to source materials

2. **Implementation Files**
   - `enhanced_planner_implementation.py` - Drop-in replacement for planner prompts
   - `enhanced_execution_implementation.py` - Drop-in replacement for execution prompts

3. **This Guide** - Step-by-step implementation instructions

---

## Key Improvements Summary

| Enhancement | Impact | Complexity |
|-------------|--------|------------|
| **Conciseness Protocol** | 50-70% token reduction | Low |
| **Zero Redundancy Rule** | 80-90% fewer duplicate operations | Low |
| **Parallel Tool Execution** | 3-5x faster execution | Low |
| **Error Recovery Limits** | Prevents infinite loops | Low |
| **Code Citation Format** | Better navigation | Low |
| **Tool Selection Hierarchy** | More efficient tool usage | Low |
| **Security Protocol** | Better safety | Low |

---

## Phase 1: Basic Implementation (Week 1)

### Step 1: Backup Current Files

```bash
cd /Users/panda/Desktop/Projects/pythinker

# Backup current prompts
cp backend/app/domain/services/prompts/planner.py backend/app/domain/services/prompts/planner.py.backup
cp backend/app/domain/services/prompts/execution.py backend/app/domain/services/prompts/execution.py.backup
```

### Step 2: Apply Enhanced Planner Prompt

**File:** `backend/app/domain/services/prompts/planner.py`

**Changes Required:**

1. Replace `PLANNER_SYSTEM_PROMPT` with the enhanced version from `enhanced_planner_implementation.py`

2. Replace `CREATE_PLAN_PROMPT` with `ENHANCED_CREATE_PLAN_PROMPT`

**Quick apply:**
```bash
# Copy the enhanced implementation
cp sandbox/enhanced_planner_implementation.py backend/app/domain/services/prompts/planner.py
```

**Or manually edit:**
- Open both files side-by-side
- Copy the `ENHANCED_PLANNER_SYSTEM_PROMPT` constant
- Copy the `ENHANCED_CREATE_PLAN_PROMPT` constant
- Ensure `build_create_plan_prompt()` function is updated

### Step 3: Apply Enhanced Execution Prompt

**File:** `backend/app/domain/services/prompts/execution.py`

**Changes Required:**

1. Replace `EXECUTION_SYSTEM_PROMPT` with `ENHANCED_EXECUTION_SYSTEM_PROMPT`

2. Replace `EXECUTION_PROMPT` with `ENHANCED_EXECUTION_PROMPT`

3. Update signal templates (COT, SOURCE_ATTRIBUTION, DIAGNOSTIC)

4. Replace `SUMMARIZE_PROMPT` with `ENHANCED_SUMMARIZE_PROMPT`

**Quick apply:**
```bash
# Copy the enhanced implementation
cp sandbox/enhanced_execution_implementation.py backend/app/domain/services/prompts/execution.py
```

**Or manually edit:**
- Open both files side-by-side
- Replace all prompt constants with enhanced versions
- Ensure helper functions are updated

### Step 4: Validate Changes

```bash
# Activate conda environment
conda activate pythinker

# Navigate to backend
cd backend

# Run linter
ruff check .

# Check formatting
ruff format --check .

# Run tests
pytest tests/

# If any issues, fix them
ruff check --fix .
ruff format .
```

### Step 5: Test Enhanced Prompts

**Test Cases:**

1. **Simple Task** (should be <4 lines output):
   ```
   User: "What is 2 + 2?"
   Expected: Direct answer, no preamble
   ```

2. **Research Task** (should have acknowledgment):
   ```
   User: "Research best practices for FastAPI development"
   Expected: "I will research FastAPI best practices and provide a detailed report."
   Then execution.
   ```

3. **Web Browsing** (should consolidate into one step):
   ```
   User: "Search for Python tutorials and summarize the top 3"
   Expected Plan: ONE step: "Search Python tutorials, review top 3, summarize"
   NOT: Step 1: Search, Step 2: Click, Step 3: Extract
   ```

4. **Redundancy Prevention**:
   ```
   User: "Visit example.com" then "Visit example.com again"
   Expected: Second request reuses data from first visit
   ```

5. **Code Citation**:
   ```
   User: "Where is the auth logic?"
   Expected: "Auth logic is in `src/auth/login.py:45-67`"
   ```

### Step 6: Monitor Metrics

Track these metrics before/after:

1. **Response Length** (for simple tasks)
   - Before: Variable (often 5-10 lines)
   - After: 2-3 lines target

2. **Redundant Operations**
   - Before: Common (10-20% of operations)
   - After: Near-zero (<2%)

3. **Execution Time**
   - Before: Baseline
   - After: 2-4x faster (due to parallel execution)

4. **Error Recovery Loops**
   - Before: Can loop infinitely
   - After: Max 3 retries, then escalate

---

## Phase 2: Advanced Features (Weeks 2-3)

These require more extensive changes to the codebase.

### Enhancement 1: Think Tool (Scratchpad)

**File:** `backend/app/domain/services/tools/think_tool.py` (new)

**Purpose:** Explicit reasoning tool for critical decisions

**Implementation:**
1. Create new tool following the pattern in `agent_enhancement_plan.md` (lines 24-90)
2. Register in `backend/app/domain/services/tools/__init__.py`
3. Add `THINK_TOOL_RULES` to system prompt

**Testing:**
- Verify tool is called before git operations
- Verify tool is called before file deletions
- Check that reasoning is not visible to user

### Enhancement 2: Plan/Act Mode Switching

**Files:**
- `backend/app/domain/models/session.py` - Add ExecutionMode enum
- `backend/app/domain/services/tools/mode_tool.py` (new) - Mode switching tool
- `frontend/src/components/ChatMessage.vue` - Mode indicator UI

**Purpose:** Explicit planning vs execution phases

**Implementation:**
1. Add `ExecutionMode` enum to Session model (lines 104-112 in plan)
2. Create `ModeTool` for mode switching (lines 115-150 in plan)
3. Add mode indicator to frontend
4. Update prompts with `MODE_RULES` (lines 154-181 in plan)

**Testing:**
- Start in PLANNING mode for non-trivial tasks
- Cannot write code in PLANNING mode
- Must request mode switch before implementation

### Enhancement 3: Enhanced Task Management

**File:** `backend/app/domain/services/agents/task_state_manager.py`

**Purpose:** Better task tracking with activeForm for UI spinners

**Implementation:**
1. Add `activeForm` field to TaskStep (lines 218-223 in plan)
2. Add `active_task_id` to track one-in-progress task (line 215)
3. Update task status immediately after completion
4. Update frontend to show spinner with activeForm

**Testing:**
- Only ONE task can be `in_progress` at a time
- Tasks marked `completed` immediately after finishing
- Spinner shows activeForm text ("Running tests...")

### Enhancement 4: Proactive Memory System

**Files:**
- `backend/app/domain/services/tools/memory_tool.py` (new)
- `backend/app/domain/services/agents/memory_manager.py` (enhance)

**Purpose:** Save important discoveries without user permission

**Implementation:**
1. Create `MemoryTool` (lines 285-320 in plan)
2. Enhance `memory_manager.py` to support proactive saves
3. Add `MEMORY_RULES` to prompt (lines 324-340 in plan)

**Testing:**
- Agent saves project conventions discovered
- Agent saves user preferences
- Memories retrieved automatically in future tasks

### Enhancement 5: Git Safety Protocol

**File:** `backend/app/domain/services/agents/security_assessor.py`

**Purpose:** Prevent destructive git operations

**Implementation:**
1. Add `GIT_SAFETY_RULES` patterns (lines 409-431 in plan)
2. Block force push to main/master
3. Require confirmation for rebases, merges
4. Add `GIT_SAFETY_RULES_PROMPT` to system (lines 435-457 in plan)

**Testing:**
- Force push to main is blocked
- Regular push requires confirmation
- Commit --amend requires confirmation
- New commits preferred over amend

### Enhancement 6: Error Recovery with Limits

**File:** `backend/app/domain/services/agents/stuck_detector.py`

**Purpose:** Max 3 retries per error, then escalate

**Implementation:**
1. Enhance `StuckDetector` with retry tracking (lines 474-497 in plan)
2. Add `ERROR_RECOVERY_RULES` to prompt (lines 500-526 in plan)
3. Track errors by type + message
4. Return True to escalate after 3 attempts

**Testing:**
- Same error 3 times triggers user escalation
- Different errors have independent counters
- Escalation message is clear and actionable

---

## Phase 3: UI & Polish (Week 4)

### Enhancement 1: Code Citation Links

**File:** `frontend/src/components/ChatMessage.vue`

**Implementation:**
1. Parse `filepath:line` format in messages
2. Convert to clickable links
3. Emit event to open file at line

**Testing:**
- Clicking `src/auth.py:45` opens file at line 45
- Range syntax `src/auth.py:45-67` works

### Enhancement 2: Mode Indicator

**File:** `frontend/src/components/ChatMessage.vue`

**Implementation:**
1. Show badge for current mode (PLANNING | EXECUTION | VERIFICATION)
2. Different colors for each mode
3. Clear visual distinction

### Enhancement 3: Task Progress UI

**Files:**
- `frontend/src/components/ToolPanel*.vue`

**Implementation:**
1. Show spinner with activeForm text when task is `in_progress`
2. Checkmark when task is `completed`
3. Timeline view of all tasks

---

## Validation Checklist

Before marking implementation complete:

### Backend

- [ ] Ruff check passes: `ruff check .`
- [ ] Formatting correct: `ruff format --check .`
- [ ] All tests pass: `pytest tests/`
- [ ] No new type errors: `pyright`

### Frontend

- [ ] Lint passes: `bun run lint`
- [ ] Type check passes: `bun run type-check`
- [ ] Tests pass: `bun run test:run`

### Integration Tests

- [ ] Simple task outputs <4 lines
- [ ] Research task has acknowledgment first
- [ ] Web browsing consolidates into one step
- [ ] No redundant URL visits
- [ ] No redundant file creation
- [ ] Parallel tool execution works (3-5 concurrent)
- [ ] Code citations are clickable
- [ ] Error recovery stops after 3 retries
- [ ] Git force push is blocked
- [ ] Tasks show spinner with activeForm
- [ ] Only one task is in_progress at a time

### Performance Metrics

- [ ] Response length reduced 50-70% for simple tasks
- [ ] Redundant operations reduced 80-90%
- [ ] Execution time improved 2-4x (parallel execution)
- [ ] Token usage reduced 30-50% overall

---

## Rollback Plan

If issues arise:

### Quick Rollback (Phase 1 only)

```bash
cd /Users/panda/Desktop/Projects/pythinker/backend/app/domain/services/prompts

# Restore backups
cp planner.py.backup planner.py
cp execution.py.backup execution.py

# Restart services
docker compose -f docker-compose-development.yml restart backend
```

### Incremental Rollback (Phases 2-3)

1. Identify problematic feature
2. Comment out new code
3. Remove new tools from registration
4. Revert frontend changes if needed
5. Test incrementally

---

## Success Criteria

Implementation is successful when:

1. **All tests pass** (backend + frontend)
2. **Metrics improved** by target amounts
3. **No regressions** in existing functionality
4. **User feedback positive** (faster, clearer responses)
5. **Code quality maintained** (Ruff, type checks pass)

---

## Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **Phase 1** | Week 1 | Enhanced prompts deployed |
| **Phase 2** | Weeks 2-3 | Advanced features (Think, Mode, Memory, Git Safety) |
| **Phase 3** | Week 4 | UI enhancements, polish |
| **Total** | 4 weeks | Fully enhanced agent system |

---

## Support & References

**Documentation:**
- `enhanced_prompts.md` - Comprehensive analysis
- `agent_enhancement_plan.md` - Detailed feature specs
- `system-prompts-and-models-of-ai-tools-main/` - Source research

**Implementation Files:**
- `enhanced_planner_implementation.py` - Ready-to-use planner
- `enhanced_execution_implementation.py` - Ready-to-use executor

**Testing:**
- Use sandbox environment for initial testing
- Monitor logs for unexpected behavior
- Collect user feedback early

**Questions?**
- Review CLAUDE.md for project context
- Check agent_enhancement_plan.md for detailed specs
- Reference system-prompts research for best practices

---

## Next Actions

1. ✅ Review this implementation guide
2. ⬜ Execute Phase 1 (enhanced prompts)
3. ⬜ Validate Phase 1 results
4. ⬜ Plan Phase 2 implementation
5. ⬜ Execute Phases 2-3
6. ⬜ Collect metrics and user feedback
7. ⬜ Iterate based on results

---

**Good luck with the implementation! 🚀**
