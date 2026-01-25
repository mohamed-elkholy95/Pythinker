# Planner prompt - optimized for token efficiency
from typing import Optional
from datetime import datetime, timezone

PLANNER_SYSTEM_PROMPT = """You are a task planner. Create focused, actionable plans. No explanations - just plan."""

# Current date signal template - for temporal awareness in planning
CURRENT_DATE_SIGNAL = """
---
CURRENT DATE: {current_date}
Today is {day_of_week}, {full_date}. Use this for time-sensitive planning and search queries.
---
"""


def get_current_date_signal() -> str:
    """Generate the current date signal with formatted date information.

    Returns:
        Formatted current date signal string
    """
    now = datetime.now(timezone.utc)
    return CURRENT_DATE_SIGNAL.format(
        current_date=now.strftime("%Y-%m-%d"),
        day_of_week=now.strftime("%A"),
        full_date=now.strftime("%B %d, %Y")
    )

THINKING_PROMPT = """Before creating a plan, think through the user's request step by step.

User request: {message}

Consider:
1. What is the user actually asking for?
2. What are the key challenges or constraints?
3. What approach would be most effective?

Think out loud briefly."""

# Task memory template - for similar past tasks (Phase 6: Qdrant integration)
TASK_MEMORY_SIGNAL = """
---
RELEVANT PAST TASKS AND OUTCOMES:
{task_memory}
Consider these experiences when creating your plan.
---
"""

CREATE_PLAN_PROMPT = """Plan the following request: {message}

Step writing rules:
- Start each step with an action verb (Analyze, Review, Design, Create, Develop, Search, Compare, Compile, Save, Deliver)
- Keep steps concise: one line, 5-15 words
- NEVER mention tool names (no "using file_write", "via browser", "with search tool")
- NEVER add explanatory phrases (no "in order to", "so that", "which will")
- 3-5 substantive steps; consolidate related work

Planning principles:
- Proceed with sensible defaults (mid-range budget, current year, mainstream options)
- Match the user's language throughout
- DO NOT explain or acknowledge - just create the plan

For research tasks, always end with:
- Compile findings into structured Markdown report with citations
- Save final report and deliver to user

Response format (JSON only, no other text):
```json
{{"goal": "objective", "title": "brief title", "language": "en", "steps": [{{"id": "1", "description": "..."}}]}}
```

User message: {message}
Attachments: {attachments}
"""

UPDATE_PLAN_PROMPT = """Return the remaining uncompleted steps.

Include all steps not yet executed. Return an empty steps array only when the task is fully complete.

Completed step: {step}
Current plan: {plan}

Response format: {{"steps": [{{"id": "N", "description": "..."}}]}}
"""


def build_create_plan_prompt(
    message: str,
    attachments: str,
    task_memory: Optional[str] = None,
    include_current_date: bool = True
) -> str:
    """Build create plan prompt with optional task memory context.

    Args:
        message: User message
        attachments: User attachments
        task_memory: Optional context from similar past tasks
        include_current_date: Include current date context (default: True)

    Returns:
        Formatted plan prompt with memory context if available
    """
    base_prompt = CREATE_PLAN_PROMPT.format(
        message=message,
        attachments=attachments
    )

    # Inject task memory if present (Phase 6: Qdrant integration)
    if task_memory:
        base_prompt = TASK_MEMORY_SIGNAL.format(
            task_memory=task_memory
        ) + base_prompt

    # Inject current date for temporal awareness
    if include_current_date:
        base_prompt = get_current_date_signal() + base_prompt

    return base_prompt