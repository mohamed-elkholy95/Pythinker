# Planner prompt - optimized for token efficiency
from typing import Optional

PLANNER_SYSTEM_PROMPT = """You are a task planner. Create focused, actionable plans. No explanations - just plan."""

# Task memory template - for similar past tasks (Phase 6: Qdrant integration)
TASK_MEMORY_SIGNAL = """
---
RELEVANT PAST TASKS AND OUTCOMES:
{task_memory}
Consider these experiences when creating your plan.
---
"""

CREATE_PLAN_PROMPT = """Plan the following request: {message}

Planning principles:
- 3-5 substantive steps; consolidate related work
- Proceed with sensible defaults (mid-range budget, current year, mainstream options)
- Match the user's language throughout
- DO NOT explain or acknowledge - just create the plan

For research tasks:
- Search current sources and verify from official pages
- Compare similar products within the same category
- ALWAYS include a final step to save the report as a .md file using file_write
- The final step should compile all findings into a structured Markdown report with tables and citations

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
    task_memory: Optional[str] = None
) -> str:
    """Build create plan prompt with optional task memory context.

    Args:
        message: User message
        attachments: User attachments
        task_memory: Optional context from similar past tasks

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

    return base_prompt