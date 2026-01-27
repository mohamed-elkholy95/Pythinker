# Agent Enhancement Plan: Integrating OpenHands Patterns

## Executive Summary

This plan outlines enhancements to Pythinker's agent system based on patterns from OpenHands. The key improvements focus on:

1. **Enhanced Stuck Detection** - Multi-scenario loop detection
2. **In-Context Learning Examples** - Trajectory-based instruction
3. **Improved System Prompt Structure** - Organized sections with clear guidelines
4. **Problem-Solving Workflow** - Structured approach to task execution
5. **Security Risk Assessment** - Action-level risk classification
6. **Enhanced Troubleshooting** - Reflective error recovery

---

## 1. Enhanced Stuck Detection System

### Current State (Pythinker)
- Basic stuck detection in `base.py` with tool usage tracking via `prompt_adapter.py`
- ReflectionAgent handles course corrections but lacks pattern-specific detection

### Enhancement: Multi-Scenario StuckDetector

**File**: `backend/app/domain/services/agents/stuck_detector.py`

```python
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

class LoopType(Enum):
    REPEATING_ACTION_OBSERVATION = "repeating_action_observation"
    REPEATING_ACTION_ERROR = "repeating_action_error"
    MONOLOGUE = "monologue"
    ACTION_OBSERVATION_PATTERN = "action_observation_pattern"
    CONTEXT_WINDOW_ERROR = "context_window_error"

@dataclass
class StuckAnalysis:
    loop_type: LoopType
    loop_repeat_times: int
    loop_start_idx: int
    recovery_suggestion: str

class StuckDetector:
    """
    Detects when the agent is stuck in a loop.

    Scenarios detected:
    1. Same action → same observation (4x repetition)
    2. Same action → error (3x repetition)
    3. Agent monologue (same message 3x without observations)
    4. Alternating pattern (action_1, action_2) repeated 3x
    5. Context window error loop (repeated memory compaction)
    """

    def __init__(self, history: List[dict]):
        self.history = history
        self.stuck_analysis: Optional[StuckAnalysis] = None

    def is_stuck(self) -> bool:
        """Check if agent is stuck in any known loop pattern."""
        if len(self.history) < 6:
            return False

        # Check each scenario
        if self._is_repeating_action_observation():
            return True
        if self._is_repeating_action_error():
            return True
        if self._is_stuck_monologue():
            return True
        if self._is_alternating_pattern():
            return True
        if self._is_context_window_loop():
            return True

        return False

    def get_recovery_action(self) -> str:
        """Get suggested recovery action based on loop type."""
        if not self.stuck_analysis:
            return "continue"

        recovery_map = {
            LoopType.REPEATING_ACTION_OBSERVATION: "try_alternative_approach",
            LoopType.REPEATING_ACTION_ERROR: "analyze_error_and_adjust",
            LoopType.MONOLOGUE: "take_concrete_action",
            LoopType.ACTION_OBSERVATION_PATTERN: "break_pattern_with_new_strategy",
            LoopType.CONTEXT_WINDOW_ERROR: "aggressive_memory_compaction",
        }
        return recovery_map.get(self.stuck_analysis.loop_type, "continue")
```

---

## 2. In-Context Learning Examples

### Current State
- Pythinker uses instruction-based prompts without example trajectories

### Enhancement: Add Example Trajectories

**File**: `backend/app/domain/services/prompts/examples.py`

```python
# In-context learning examples for different task types

CODING_EXAMPLE = """
--------------------- START OF EXAMPLE ---------------------

USER: Create a Python script that fetches weather data and displays it.

EXECUTION:
1. Explored codebase structure
2. Created weather.py with requests library
3. Encountered error: requests not installed
4. Installed requests via pip
5. Ran script successfully
6. Delivered working solution with documentation

KEY BEHAVIORS DEMONSTRATED:
- Immediate action without explanation
- Error recovery without user intervention
- Clean delivery of results

--------------------- END OF EXAMPLE ---------------------
"""

RESEARCH_EXAMPLE = """
--------------------- START OF EXAMPLE ---------------------

USER: Compare the top 3 project management tools for small teams.

EXECUTION:
1. Searched for "project management tools comparison 2026"
2. Visited official pages for Asana, Monday, Trello
3. Extracted pricing, features, limitations
4. Cross-validated with review sites
5. Created structured comparison table
6. Delivered report with citations

KEY BEHAVIORS DEMONSTRATED:
- Multiple search queries for coverage
- Official source verification
- Structured output with citations

--------------------- END OF EXAMPLE ---------------------
"""

def get_example_for_task_type(task_type: str) -> str:
    """Return appropriate example based on task classification."""
    examples = {
        "coding": CODING_EXAMPLE,
        "research": RESEARCH_EXAMPLE,
        "analysis": RESEARCH_EXAMPLE,
        "deployment": CODING_EXAMPLE,
    }
    return examples.get(task_type, "")
```

---

## 3. Enhanced System Prompt Structure

### Current State
- Well-organized but could benefit from OpenHands patterns

### Enhancement: Add New Sections

**Additions to `backend/app/domain/services/prompts/system.py`**

```python
# New sections to add

EFFICIENCY_RULES = """
<efficiency>
Cost Optimization:
- Combine multiple operations into single actions when possible
- Use efficient search patterns (grep, find with filters)
- Batch file operations instead of individual calls
- Prefer browser_get_content over full browser navigation for text extraction
</efficiency>
"""

PROBLEM_SOLVING_WORKFLOW = """
<problem_solving_workflow>
1. EXPLORATION: Understand the problem and codebase before proposing solutions
2. ANALYSIS: Consider multiple approaches, select the most promising
3. TESTING: Verify solutions work before delivery
   - For bug fixes: Reproduce issue first
   - For features: Test incrementally
4. IMPLEMENTATION: Make focused, minimal changes
5. VERIFICATION: Confirm solution addresses the original requirement
</problem_solving_workflow>
"""

TROUBLESHOOTING_RULES = """
<troubleshooting>
When encountering repeated failures:
1. Stop and reflect on 5-7 possible causes
2. Assess likelihood of each cause
3. Address most likely causes first
4. Document reasoning for future reference

Recovery strategies:
- If action fails 3x: Try fundamentally different approach
- If tool unavailable: Find alternative tool or method
- If information missing: Search for it, don't assume
</troubleshooting>
"""

PROCESS_MANAGEMENT_RULES = """
<process_management>
When managing processes:
- Never use generic kill patterns (pkill -f server, pkill -f python)
- Find specific PID first with ps aux
- Use application-specific shutdown commands when available
- Clean up temporary files and resources after completion
</process_management>
"""
```

---

## 4. Security Risk Assessment

### Enhancement: Action-Level Risk Classification

**File**: `backend/app/domain/services/agents/security_assessor.py`

```python
from enum import Enum
from typing import Optional
from dataclasses import dataclass

class ActionSecurityRisk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"

@dataclass
class SecurityAssessment:
    risk_level: ActionSecurityRisk
    reason: str
    requires_confirmation: bool

class SecurityAssessor:
    """Assess security risk of tool actions."""

    HIGH_RISK_PATTERNS = [
        "rm -rf",
        "sudo rm",
        "drop database",
        "delete from",
        "format",
        "chmod 777",
        "curl | bash",
        "wget | sh",
    ]

    MEDIUM_RISK_PATTERNS = [
        "sudo",
        "pip install",
        "npm install",
        "git push",
        "docker run",
    ]

    def assess_action(
        self,
        tool_name: str,
        tool_args: dict,
        autonomy_level: str = "autonomous"
    ) -> SecurityAssessment:
        """Assess the security risk of a proposed action."""

        # Shell commands need careful analysis
        if tool_name in ("shell_exec", "shell_execute"):
            command = tool_args.get("command", "")
            return self._assess_shell_command(command)

        # File deletion
        if tool_name == "file_delete":
            return SecurityAssessment(
                risk_level=ActionSecurityRisk.MEDIUM,
                reason="File deletion operation",
                requires_confirmation=autonomy_level == "supervised"
            )

        # Browser payment/login
        if tool_name == "browser_type":
            if any(kw in str(tool_args).lower() for kw in ["password", "credit", "card"]):
                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.HIGH,
                    reason="Potential credential or payment entry",
                    requires_confirmation=True
                )

        return SecurityAssessment(
            risk_level=ActionSecurityRisk.LOW,
            reason="Standard operation",
            requires_confirmation=False
        )

    def _assess_shell_command(self, command: str) -> SecurityAssessment:
        """Assess shell command risk."""
        command_lower = command.lower()

        for pattern in self.HIGH_RISK_PATTERNS:
            if pattern in command_lower:
                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.HIGH,
                    reason=f"High-risk pattern detected: {pattern}",
                    requires_confirmation=True
                )

        for pattern in self.MEDIUM_RISK_PATTERNS:
            if pattern in command_lower:
                return SecurityAssessment(
                    risk_level=ActionSecurityRisk.MEDIUM,
                    reason=f"Medium-risk pattern: {pattern}",
                    requires_confirmation=False
                )

        return SecurityAssessment(
            risk_level=ActionSecurityRisk.LOW,
            reason="Standard shell operation",
            requires_confirmation=False
        )
```

---

## 5. Enhanced Reflection with Troubleshooting

### Enhancement: Reflective Error Analysis

**Updates to `backend/app/domain/services/agents/reflection.py`**

```python
ENHANCED_REFLECTION_PROMPT = """
You are assessing task execution progress. Analyze the current state:

Current step: {step_description}
Error count: {error_count}
Last error: {last_error}
Iteration count: {iteration_count}

TROUBLESHOOTING PROTOCOL:
When errors occur repeatedly, reflect on possible causes:
1. Is the tool being used correctly?
2. Are prerequisites missing (dependencies, files, permissions)?
3. Is the approach fundamentally flawed?
4. Is there a simpler alternative?
5. Does the error message provide actionable guidance?

Based on this analysis, recommend one action:
- CONTINUE: Minor issue, proceed with current approach
- ADJUST: Same goal, modified approach
- REPLAN: Fundamentally rethink the strategy
- ESCALATE: Needs user input to proceed
- ABORT: Task is not achievable

Response format:
```json
{
  "decision": "continue|adjust|replan|escalate|abort",
  "reasoning": "Brief explanation of analysis",
  "suggested_adjustment": "If ADJUST, what specific change to make"
}
```
"""
```

---

## 6. Implementation Progress

### Phase 1: Core Enhancements (COMPLETED)
1. [x] Enhanced StuckDetector class with OpenHands patterns
   - File: `stuck_detector.py`
   - Added: LoopType, RecoveryStrategy, StuckAnalysis dataclasses
   - Added: Action-based pattern detection (action-error, action-observation, alternating)
   - Added: Tool failure cascade detection
   - Added: Detailed recovery guidance per loop type

2. [x] Add TROUBLESHOOTING_RULES to system prompt
   - File: `prompts/system.py`
   - Added diagnostic protocol for repeated failures
   - Added common causes checklist
   - Added recovery strategies

3. [x] Add PROBLEM_SOLVING_WORKFLOW to system prompt
   - File: `prompts/system.py`
   - Added 4-step workflow: Exploration → Analysis → Implementation → Verification

4. [ ] Integrate StuckDetector into execution loop (TODO: wire up track_tool_action)

### Phase 2: Quality Improvements (COMPLETED)
5. [x] Implement SecurityAssessor
   - File: `security_assessor.py`
   - Added risk classification (LOW, MEDIUM, HIGH, CRITICAL)
   - Added shell command pattern detection
   - Added sensitive data/path detection
   - Added browser credential/payment detection
   - Added autonomy-level-based confirmation requirements

6. [x] Add EFFICIENCY_RULES to system prompt
   - File: `prompts/system.py`
   - Added cost optimization guidelines

7. [x] Add PROCESS_MANAGEMENT_RULES to system prompt
   - File: `prompts/system.py`
   - Added safe process termination guidelines

8. [ ] Add in-context learning examples (TODO)
9. [ ] Enhance ReflectionAgent with troubleshooting protocol (TODO)

### Phase 3: Advanced Features (Future)
10. [ ] Multi-agent delegation support
11. [ ] Trajectory logging for future learning
12. [ ] Automatic example selection based on task type
13. [ ] Action confirmation flow for high-risk operations

---

## 7. Integration Points

### LangGraph Workflow
- StuckDetector checks in `execution_node` before each step
- SecurityAssessor checks before tool execution in `BaseAgent.execute_tool()`
- Enhanced reflection prompts in `reflection_node`

### BaseAgent
- Add `security_assessor` as optional dependency
- Track action history for stuck detection
- Integrate in-context examples based on task type

### Prompts
- Merge new sections into `build_system_prompt()`
- Add task-type detection for example selection

---

## 8. Metrics & Monitoring

Track enhancement effectiveness:
- Loop detection rate (stuck detections per 100 tasks)
- Recovery success rate (tasks completed after stuck detection)
- Security alerts (high/medium risk actions flagged)
- Error reduction (errors per task before/after)

---

## Next Steps

1. Review this plan
2. Approve implementation phases
3. Begin Phase 1 implementation
4. Test with sample tasks
5. Iterate based on results
