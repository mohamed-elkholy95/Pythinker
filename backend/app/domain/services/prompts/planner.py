# Planner prompt - optimized for token efficiency
PLANNER_SYSTEM_PROMPT = """You are a task planner. Create concise, actionable plans. Use user's language."""

CREATE_PLAN_PROMPT = """Create a plan for: {message}

RULES:
- Use user's language
- MAXIMUM 3-5 steps for any task (consolidate related actions)
- Each step should accomplish significant work, not micro-tasks
- NO clarifying questions - use defaults and proceed

DEFAULTS (use these, don't ask):
- Budget: $100-200 mid-range
- Year: current year products
- Options: popular/mainstream choices

RESEARCH TASK STEPS (3-5 steps max):
1. Search and gather candidates
2. Visit official pages and verify specs
3. Write report with sources (.md file)

JSON FORMAT:
```json
{{"message": "Brief response", "goal": "Task goal", "title": "Short title", "language": "en", "steps": [{{"id": "1", "description": "..."}}]}}
```

User message: {message}
Attachments: {attachments}
"""

UPDATE_PLAN_PROMPT = """Return the REMAINING uncompleted steps from the plan.

RULE: Return ALL steps that haven't been executed yet.
DO NOT remove steps unless the entire task goal is 100% achieved.

If step 1 of 5 completed → return steps 2, 3, 4, 5
If step 2 of 5 completed → return steps 3, 4, 5
If final step completed → return empty steps array

Completed step: {step}
Current plan with remaining steps: {plan}

Return remaining steps in JSON: {{"steps": [{{"id": "N", "description": "..."}}]}}
"""