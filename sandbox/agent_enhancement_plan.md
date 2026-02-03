# Pythinker Agent Enhancement Plan

Based on comprehensive analysis of 30+ AI coding assistants' system prompts including Claude Code, Cursor, Windsurf, Devin, Cline, Lovable, v0, Bolt, and others.

---

## Executive Summary

This plan identifies **12 high-impact enhancements** extracted from industry-leading AI agents that can significantly improve Pythinker's reliability, efficiency, and user experience. Enhancements are prioritized by implementation complexity and expected impact.

---

## P0: Critical Enhancements (High Impact, Core Infrastructure)

### 1. Think Tool (Scratchpad) - From Devin AI

**What**: A dedicated tool for structured reasoning before critical decisions.

**Why**: Devin requires `<think>` before git operations, transitioning exploration→code, and before reporting completion. This prevents premature actions and improves decision quality.

**Current Gap**: Pythinker has CoT in prompts but no explicit reasoning tool the agent can invoke.

**Implementation**:
```python
# backend/app/domain/services/tools/think_tool.py
class ThinkTool(BaseTool):
    """Scratchpad for structured reasoning - not visible to user."""

    name = "think"

    def get_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "think",
                "description": "Use for complex reasoning before critical decisions. "
                              "REQUIRED before: git operations, file deletions, API calls, "
                              "transitioning from exploration to implementation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning": {
                            "type": "string",
                            "description": "Your step-by-step reasoning about the situation"
                        },
                        "conclusion": {
                            "type": "string",
                            "description": "What you've decided to do and why"
                        },
                        "risks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Potential risks or issues to watch for"
                        }
                    },
                    "required": ["reasoning", "conclusion"]
                }
            }
        }]

    async def invoke_function(self, name: str, **kwargs) -> ToolResult:
        # Simply acknowledge - this is for agent's internal reasoning
        return ToolResult(
            success=True,
            message="Reasoning recorded. Proceed with your planned action."
        )
```

**Prompt Enhancement** (add to `system.py`):
```python
THINK_TOOL_RULES = """
<think_tool_rules>
MANDATORY: Use the `think` tool BEFORE:
- Git operations (commit, push, merge, rebase)
- File deletions or destructive operations
- External API calls with side effects
- Transitioning from exploration to implementation
- Reporting task completion

The think tool is your scratchpad for reasoning through complex decisions.
It is NOT visible to the user - use it freely to organize your thoughts.
</think_tool_rules>
"""
```

**Files to Modify**:
- Create: `backend/app/domain/services/tools/think_tool.py`
- Modify: `backend/app/domain/services/prompts/system.py`
- Modify: `backend/app/domain/services/tools/__init__.py` (register tool)

---

### 2. Plan Mode vs Act Mode - From Cline, Google Antigravity

**What**: Explicit mode switching between planning/research and execution.

**Why**: Prevents premature implementation, ensures thorough analysis first, gives users control over when execution begins.

**Current Gap**: Pythinker has separate Planner/Executor agents but no explicit mode the user can see/control.

**Implementation**:

```python
# backend/app/domain/models/session.py - Add to Session model
class ExecutionMode(str, Enum):
    PLANNING = "planning"      # Research, design, create plan
    EXECUTION = "execution"    # Implement the plan
    VERIFICATION = "verification"  # Test and verify changes

# Add to Session model
execution_mode: ExecutionMode = ExecutionMode.PLANNING
```

**New Tool**:
```python
# backend/app/domain/services/tools/mode_tool.py
class ModeTool(BaseTool):
    """Switch between planning and execution modes."""

    name = "mode_switch"

    def get_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "request_execution_mode",
                "description": "Request to switch from PLANNING to EXECUTION mode. "
                              "Call this when you have a complete plan and are ready to implement.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "plan_summary": {
                            "type": "string",
                            "description": "Brief summary of the implementation plan"
                        },
                        "files_to_modify": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of files that will be created or modified"
                        },
                        "estimated_changes": {
                            "type": "string",
                            "description": "Scope of changes (small/medium/large)"
                        }
                    },
                    "required": ["plan_summary", "files_to_modify"]
                }
            }
        }]
```

**Prompt Enhancement**:
```python
MODE_RULES = """
<mode_rules>
EXECUTION MODES:

1. PLANNING MODE (default for new tasks):
   - Research and understand the problem
   - Explore the codebase structure
   - Design the implementation approach
   - Create detailed plan with file locations
   - Use `request_execution_mode` when ready

2. EXECUTION MODE (after plan approval):
   - Implement the approved plan step-by-step
   - Make focused, minimal changes
   - Test incrementally as you go

3. VERIFICATION MODE (after implementation):
   - Test all changes
   - Verify expected behavior
   - Clean up temporary files

RULES:
- Start in PLANNING mode for non-trivial tasks
- Do NOT write code in PLANNING mode (research only)
- Request mode switch before implementing
</mode_rules>
"""
```

**Files to Modify**:
- Modify: `backend/app/domain/models/session.py`
- Create: `backend/app/domain/services/tools/mode_tool.py`
- Modify: `backend/app/domain/services/prompts/system.py`
- Modify: `frontend/src/components/ChatMessage.vue` (show mode indicator)

---

### 3. Enhanced Task Management (TodoWrite Pattern) - From Claude Code, Cursor

**What**: Proactive task creation with real-time status, activeForm for spinners.

**Why**: Claude Code and Cursor both emphasize creating todos for 3+ step tasks with specific states and active form for UI feedback.

**Current Gap**: `TaskStateManager` exists but lacks:
- Proactive creation trigger
- activeForm for UI spinners
- One-task-in-progress rule
- Immediate completion marking

**Enhancement to TaskState**:
```python
# backend/app/domain/services/agents/task_state_manager.py

@dataclass
class EnhancedTaskState:
    """Enhanced task state with TodoWrite patterns."""
    objective: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)

    # NEW: TodoWrite enhancements
    active_task_id: str | None = None  # Only ONE task can be in_progress

@dataclass
class TaskStep:
    id: str
    subject: str              # Imperative: "Run tests"
    description: str          # Detailed description
    active_form: str          # Present continuous: "Running tests"
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELETED = "deleted"
```

**Prompt Enhancement**:
```python
TODO_RULES = """
<todo_rules>
TASK MANAGEMENT PROTOCOL:

When to create tasks:
- Multi-step work (3+ distinct steps)
- Complex tasks requiring tracking
- User provides a list of things to do

Task creation rules:
- ALWAYS provide both `subject` (imperative: "Fix bug") and `activeForm` (continuous: "Fixing bug")
- Create all tasks upfront, mark first as `in_progress`
- Maximum ONE task can be `in_progress` at any time
- Mark tasks `completed` IMMEDIATELY after finishing (don't batch)

Task states:
- `pending` → Not started
- `in_progress` → Currently working (shows spinner with activeForm)
- `completed` → Done
- `deleted` → Removed (no longer relevant)

CRITICAL: Only mark a task completed when FULLY accomplished:
- Tests passing
- Implementation complete
- No unresolved errors

If blocked, keep task as `in_progress` and create a new task for the blocker.
</todo_rules>
"""
```

**Files to Modify**:
- Modify: `backend/app/domain/services/agents/task_state_manager.py`
- Modify: `backend/app/domain/services/prompts/system.py`
- Modify: `frontend/src/components/ToolPanel*.vue` (show spinner with activeForm)

---

## P1: High-Impact Enhancements (Better Reliability)

### 4. Memory System with Proactive Persistence - From Windsurf

**What**: Proactive memory creation for important context that persists across sessions.

**Why**: Windsurf's `create_memory` allows saving important discoveries without user permission. Limited context window makes this critical.

**Current Gap**: Pythinker has `memory_manager.py` but it's reactive, not proactive.

**Implementation**:
```python
# backend/app/domain/services/tools/memory_tool.py
class MemoryTool(BaseTool):
    """Proactive memory creation for persistent context."""

    name = "memory"

    def get_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "create_memory",
                "description": "Save important context for future reference. "
                              "Use proactively when discovering: project conventions, "
                              "user preferences, critical file locations, API patterns.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Short identifier (e.g., 'auth_pattern', 'db_config')"
                        },
                        "content": {
                            "type": "string",
                            "description": "The information to remember"
                        },
                        "category": {
                            "type": "string",
                            "enum": ["convention", "preference", "architecture", "api", "other"],
                            "description": "Category for retrieval"
                        }
                    },
                    "required": ["key", "content"]
                }
            }
        }]
```

**Prompt Enhancement**:
```python
MEMORY_RULES = """
<memory_rules>
PROACTIVE MEMORY PROTOCOL:

Create memories for:
- Project conventions (naming, structure, patterns)
- User preferences discovered during tasks
- Critical file locations and their purposes
- API patterns and authentication methods
- Recurring error solutions

Memory is LIMITED - use for important, reusable context only.
Memories are auto-retrieved when relevant to future tasks.

NO user permission needed - save important discoveries freely.
</memory_rules>
"""
```

**Files to Modify**:
- Create: `backend/app/domain/services/tools/memory_tool.py`
- Modify: `backend/app/domain/services/agents/memory_manager.py`
- Modify: `backend/app/domain/services/prompts/system.py`

---

### 5. Conciseness Protocol - From Claude Code, Replit

**What**: Ultra-minimal responses with strict line limits.

**Why**: Claude Code enforces <4 lines, Replit <2 lines. Reduces noise, improves clarity.

**Current Gap**: Pythinker prompts encourage brevity but don't enforce it strictly.

**Prompt Enhancement**:
```python
CONCISENESS_RULES = """
<conciseness_protocol>
RESPONSE LENGTH RULES:

For SIMPLE tasks:
- Maximum 2-3 lines of explanation
- NO preamble ("Let me...", "I'll now...")
- NO postamble ("I hope this helps...", "Let me know...")
- Execute immediately, report results

For COMPLEX tasks:
- Brief acknowledgment (1-2 sentences)
- Then execute immediately

FORBIDDEN:
- "Here's what I found..."
- "I'll help you with..."
- "Let me explain..."
- Step-by-step previews before acting
- Excessive emoji usage

CORRECT EXAMPLES:
❌ "I'll now search for the authentication logic in the codebase."
✓ [Just execute the search]

❌ "Here's what I found: The auth is in src/auth.py"
✓ "Auth logic is in `src/auth.py:45-120`"
</conciseness_protocol>
"""
```

**Files to Modify**:
- Modify: `backend/app/domain/services/prompts/system.py`
- Modify: `backend/app/domain/services/prompts/execution.py`

---

### 6. Git Safety Protocol - From Claude Code

**What**: Strict rules preventing destructive git operations.

**Why**: Claude Code has comprehensive git safety that prevents common disasters.

**Current Gap**: Pythinker's `SecurityAssessor` handles some cases but lacks git-specific rules.

**Enhancement to SecurityAssessor**:
```python
# backend/app/domain/services/agents/security_assessor.py

GIT_SAFETY_RULES = {
    # ALWAYS BLOCKED
    "blocked": [
        r"git push.*--force.*main",
        r"git push.*--force.*master",
        r"git reset --hard",
        r"git checkout \.",
        r"git restore \.",
        r"git clean -f",
        r"git branch -D",
        r"--no-verify",
        r"--no-gpg-sign",
    ],
    # REQUIRE CONFIRMATION
    "confirm": [
        r"git push",
        r"git commit --amend",
        r"git rebase",
        r"git merge",
        r"git stash drop",
    ]
}
```

**Prompt Enhancement**:
```python
GIT_SAFETY_RULES_PROMPT = """
<git_safety>
GIT SAFETY PROTOCOL:

NEVER (blocked by system):
- Force push to main/master
- Reset --hard without explicit user request
- Skip hooks (--no-verify)
- Run destructive commands (checkout ., restore ., clean -f)

ALWAYS:
- Create NEW commits (don't amend unless explicitly asked)
- Use specific file adds (not `git add .` or `git add -A`)
- Include co-authorship: `Co-Authored-By: Pythinker <noreply@pythinker.ai>`
- Use HEREDOC for commit messages with special characters

AFTER PRE-COMMIT HOOK FAILURE:
- Fix the issue
- Re-stage files
- Create NEW commit (do NOT --amend, as previous commit didn't happen)
</git_safety>
"""
```

**Files to Modify**:
- Modify: `backend/app/domain/services/agents/security_assessor.py`
- Modify: `backend/app/domain/services/prompts/system.py`

---

### 7. Error Recovery with Retry Limits - From Cursor, Devin

**What**: Maximum 3 retry loops with explicit user escalation.

**Why**: Cursor stops at 3 linter fix attempts, Devin asks user after 3 test failures. Prevents infinite loops.

**Current Gap**: `StuckDetector` exists but doesn't enforce hard retry limits per error type.

**Enhancement**:
```python
# backend/app/domain/services/agents/stuck_detector.py

class EnhancedStuckDetector:
    """Enhanced stuck detection with per-error retry limits."""

    MAX_RETRIES_PER_ERROR = 3

    def __init__(self):
        self._error_retry_counts: dict[str, int] = {}

    def record_error(self, error_type: str, error_message: str) -> bool:
        """Record an error and check if retry limit exceeded.

        Returns:
            True if should escalate to user, False if can retry
        """
        key = f"{error_type}:{error_message[:100]}"
        self._error_retry_counts[key] = self._error_retry_counts.get(key, 0) + 1

        if self._error_retry_counts[key] >= self.MAX_RETRIES_PER_ERROR:
            return True  # Escalate to user
        return False
```

**Prompt Enhancement**:
```python
ERROR_RECOVERY_RULES = """
<error_recovery>
ERROR HANDLING PROTOCOL:

RETRY LIMITS:
- Maximum 3 attempts for the same error
- After 3 failures: STOP and ask user for help

BEFORE RETRYING:
1. Analyze the error message carefully
2. Try a fundamentally DIFFERENT approach
3. Do NOT repeat the same command with minor tweaks

WHEN TO ESCALATE:
- Same error 3 times
- Missing credentials or permissions
- Environment issues beyond your control
- Unclear requirements

ESCALATION FORMAT:
"I've attempted [X] 3 times with different approaches but continue to encounter [error].
Could you help by: [specific ask]?"
</error_recovery>
"""
```

**Files to Modify**:
- Modify: `backend/app/domain/services/agents/stuck_detector.py`
- Modify: `backend/app/domain/services/prompts/system.py`

---

## P2: Medium-Impact Enhancements (Better UX)

### 8. Code Citation Format - From Claude Code, Cursor, Augment

**What**: Consistent `file:line` format for code references.

**Why**: Allows users to click and navigate directly to code locations.

**Current Gap**: No standardized citation format in responses.

**Prompt Enhancement**:
```python
CODE_CITATION_RULES = """
<code_citations>
CODE REFERENCE FORMAT:

When referencing code, use: `filepath:line_number` or `filepath:start-end`

Examples:
- "The auth logic is in `src/auth/login.py:45`"
- "See the validation in `src/utils/validate.py:120-145`"
- "Modified `app/routes/api.py:78` to fix the bug"

For multiple related locations:
- `src/models/user.py:23` - User model definition
- `src/routes/auth.py:45-60` - Login endpoint
- `src/utils/jwt.py:12` - Token generation

This format enables direct navigation to source code.
</code_citations>
"""
```

**Frontend Enhancement**:
```typescript
// frontend/src/utils/codeLinks.ts
export function parseCodeReferences(text: string): string {
  // Convert `file:line` to clickable links
  const pattern = /`([^`]+):(\d+)(?:-(\d+))?`/g;
  return text.replace(pattern, (match, file, start, end) => {
    const lineRef = end ? `${start}-${end}` : start;
    return `<a href="#" onclick="openFile('${file}', ${start})">\`${file}:${lineRef}\`</a>`;
  });
}
```

**Files to Modify**:
- Modify: `backend/app/domain/services/prompts/system.py`
- Create: `frontend/src/utils/codeLinks.ts`
- Modify: `frontend/src/components/ChatMessage.vue`

---

### 9. Tool Selection Hierarchy - From Multiple Sources

**What**: Explicit hierarchy for choosing tools.

**Why**: All top agents prefer specialized tools over bash, semantic search over exact match.

**Current Gap**: Pythinker has dynamic toolsets but no explicit selection guidance.

**Prompt Enhancement**:
```python
TOOL_HIERARCHY_RULES = """
<tool_selection>
TOOL SELECTION HIERARCHY (prefer higher):

1. SPECIALIZED TOOLS (always prefer):
   - file_read over shell `cat`
   - file_write over shell `echo >`
   - file_search over shell `grep`
   - info_search_web over browser Google search

2. SEARCH STRATEGY:
   - Semantic search for understanding ("how does auth work?")
   - Pattern search (grep) for exact matches ("function login")
   - File list for structure exploration

3. BROWSER USAGE:
   - Use info_search_web FIRST, then browse specific URLs
   - NEVER navigate to google.com to type searches
   - browser_get_content for bulk extraction (5+ pages)
   - Autonomous browsing for interactive tasks

4. PARALLEL vs SEQUENTIAL:
   - Parallel: Independent read operations
   - Sequential: Operations with dependencies
   - NEVER guess parameters - wait for results

5. EFFICIENCY:
   - Batch file reads when possible
   - Don't repeat operations (check conversation history)
   - Don't navigate to URLs already visited
</tool_selection>
"""
```

**Files to Modify**:
- Modify: `backend/app/domain/services/prompts/system.py`

---

### 10. Update Plan Tool - From Windsurf

**What**: Explicit tool for updating the execution plan when scope changes.

**Why**: Windsurf requires `update_plan` when learning new information that changes scope.

**Current Gap**: Plans are static after creation.

**Implementation**:
```python
# backend/app/domain/services/tools/plan_tool.py
class PlanTool(BaseTool):
    """Tool for updating execution plans."""

    def get_tools(self) -> list[dict]:
        return [{
            "type": "function",
            "function": {
                "name": "update_plan",
                "description": "Update the execution plan when scope or approach changes. "
                              "REQUIRED when: discovering new requirements, completing major milestones, "
                              "or before committing to significant changes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why the plan needs updating"
                        },
                        "changes": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of changes to the plan"
                        },
                        "new_steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "description": {"type": "string"},
                                    "after_step": {"type": "string"}
                                }
                            },
                            "description": "New steps to add"
                        },
                        "removed_steps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Step IDs to remove"
                        }
                    },
                    "required": ["reason"]
                }
            }
        }]
```

**Files to Modify**:
- Create: `backend/app/domain/services/tools/plan_tool.py`
- Modify: `backend/app/domain/services/agents/task_state_manager.py`

---

## P3: Additional Enhancements (Nice to Have)

### 11. Browser Action Safety - From Cline

**What**: Strict browser action sequence rules.

**Why**: Cline enforces: launch → actions → close, one action per message.

**Prompt Enhancement**:
```python
BROWSER_SAFETY_RULES = """
<browser_safety>
BROWSER ACTION RULES:

SEQUENCE:
1. Start with browser_navigate to URL
2. Perform actions (click, type, scroll)
3. End session appropriately

SAFETY:
- Never enter passwords or payment info
- Suggest user takeover for sensitive forms
- Avoid suspicious downloads

ANTI-PATTERNS:
- Don't navigate to same URL repeatedly
- Don't scroll endlessly - extract content
- Don't retry failed clicks - refresh element indices
</browser_safety>
"""
```

---

### 12. Structured Reasoning Indicators - From Google Antigravity

**What**: Task boundary system with mode indicators.

**Why**: Antigravity uses TaskName, TaskSummary, TaskStatus for clear progress tracking.

**Implementation**:
```python
# Add to ToolEvent model
class ToolEvent(BaseEvent):
    # Existing fields...

    # NEW: Task boundary fields
    task_name: str | None = None       # Current task header
    task_summary: str | None = None    # Cumulative progress
    task_status: str | None = None     # What will be done next
    execution_mode: str | None = None  # PLANNING | EXECUTION | VERIFICATION
```

**Files to Modify**:
- Modify: `backend/app/domain/models/event.py`
- Modify: `frontend/src/components/ToolPanel*.vue`

---

## Implementation Priority Matrix

| Enhancement | Impact | Complexity | Priority |
|-------------|--------|------------|----------|
| 1. Think Tool | High | Low | P0 |
| 2. Plan/Act Mode | High | Medium | P0 |
| 3. Enhanced Tasks | High | Medium | P0 |
| 4. Proactive Memory | High | Medium | P1 |
| 5. Conciseness | Medium | Low | P1 |
| 6. Git Safety | High | Low | P1 |
| 7. Error Recovery | High | Low | P1 |
| 8. Code Citations | Medium | Low | P2 |
| 9. Tool Hierarchy | Medium | Low | P2 |
| 10. Update Plan | Medium | Medium | P2 |
| 11. Browser Safety | Low | Low | P3 |
| 12. Task Boundaries | Low | Medium | P3 |

---

## Implementation Phases

### Phase 1 (Week 1): Core Reliability
- [ ] P0-1: Think Tool
- [ ] P1-5: Conciseness Protocol (prompt only)
- [ ] P1-6: Git Safety Protocol
- [ ] P1-7: Error Recovery Limits

### Phase 2 (Week 2): Planning & Tasks
- [ ] P0-2: Plan Mode vs Act Mode
- [ ] P0-3: Enhanced Task Management
- [ ] P2-8: Code Citation Format

### Phase 3 (Week 3): Memory & Intelligence
- [ ] P1-4: Proactive Memory System
- [ ] P2-9: Tool Selection Hierarchy
- [ ] P2-10: Update Plan Tool

### Phase 4 (Week 4): Polish
- [ ] P3-11: Browser Safety Rules
- [ ] P3-12: Task Boundary UI
- [ ] Integration testing
- [ ] Documentation

---

## Validation Checklist

After implementation, verify:

**Backend**:
```bash
conda activate pythinker && cd backend && ruff check . && ruff format --check . && pytest tests/
```

**Frontend**:
```bash
cd frontend && bun run lint && bun run type-check
```

**Integration Tests**:
- [ ] Think tool triggers before git operations
- [ ] Mode switch requires plan summary
- [ ] Tasks show spinner with activeForm
- [ ] Git force push to main is blocked
- [ ] 3 retries triggers user escalation
- [ ] Code citations are clickable
- [ ] Memory persists across sessions

---

## References

Source prompts analyzed from:
- Claude Code 2.0 (Anthropic)
- Cursor Agent 2.0
- Windsurf Cascade Wave 11
- Devin AI
- Bolt (Open Source)
- v0 (Vercel)
- Cline (Open Source)
- Lovable
- Augment Code
- Poke
- Google Antigravity
- Replit Agent
