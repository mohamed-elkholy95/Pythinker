# Execution prompt
from typing import Optional, List
from datetime import datetime, timezone

# Current date signal template - injected to provide temporal awareness
CURRENT_DATE_SIGNAL = """
---
CURRENT DATE: {current_date}
Today is {day_of_week}, {full_date}. Use this for time-sensitive research and data verification.
---
"""

# Context pressure signal template - injected when pressure is high
CONTEXT_PRESSURE_SIGNAL = """
---
{pressure_signal}
---
"""

# Task state template - for todo recitation mechanism
TASK_STATE_SIGNAL = """
---
CURRENT TASK STATE:
{task_state}
---
"""

# Memory context template - for long-term memory retrieval (Phase 6: Qdrant integration)
MEMORY_CONTEXT_SIGNAL = """
---
RELEVANT CONTEXT FROM MEMORY:
{memory_context}
---
"""

# Chain-of-Thought reasoning template - injected for complex tasks
COT_REASONING_SIGNAL = """
---
STRUCTURED REASONING (use before taking action):

1. ANALYZE: What exactly needs to be accomplished?
   - Primary objective: {primary_objective}
   - Key constraints: {constraints}

2. PLAN: What's the optimal approach?
   - Break into sub-steps if complex
   - Identify required tools/resources
   - Consider potential failure points

3. VALIDATE: Before executing, verify:
   - [ ] Approach addresses the core requirement
   - [ ] No unnecessary complexity added
   - [ ] Error handling considered

Execute with this reasoning in mind, but output only the result.
---
"""

# Keywords that indicate a complex task requiring CoT
COMPLEX_TASK_INDICATORS = [
    "research", "analyze", "compare", "investigate", "design",
    "implement", "optimize", "debug", "refactor", "evaluate",
    "multiple", "comprehensive", "detailed", "thorough", "complete",
    "security", "performance", "architecture", "integration"
]


def is_complex_task(step_description: str) -> bool:
    """Determine if a task is complex enough to warrant CoT reasoning.

    Args:
        step_description: The step description to analyze

    Returns:
        True if the task appears complex
    """
    step_lower = step_description.lower()

    # Check for complexity indicators
    indicator_count = sum(
        1 for indicator in COMPLEX_TASK_INDICATORS
        if indicator in step_lower
    )

    # Complex if 2+ indicators or description is long (likely detailed task)
    return indicator_count >= 2 or len(step_description) > 300


def extract_task_constraints(step_description: str) -> List[str]:
    """Extract constraints from a task description.

    Args:
        step_description: The step description

    Returns:
        List of extracted constraints
    """
    constraints = []

    # Look for common constraint patterns
    constraint_patterns = [
        ("must", "Requirement"),
        ("should", "Recommendation"),
        ("without", "Exclusion"),
        ("only", "Limitation"),
        ("within", "Boundary"),
        ("before", "Deadline"),
        ("after", "Dependency"),
        ("not", "Prohibition"),
    ]

    step_lower = step_description.lower()
    for pattern, label in constraint_patterns:
        if pattern in step_lower:
            # Find the sentence containing the pattern
            sentences = step_description.split('.')
            for sentence in sentences:
                if pattern in sentence.lower():
                    constraints.append(f"{label}: {sentence.strip()}")
                    break

    return constraints[:5]  # Limit to 5 constraints

EXECUTION_SYSTEM_PROMPT = """
You are a task execution agent. Execute silently and efficiently:
- Take action immediately - no explanations or narration
- Never say "I'll do X" or "Let me X" - just do it
- Iterate until completion
- Deliver results, not progress commentary
"""

EXECUTION_PROMPT = """
Current task: {step}

Guidelines:
- Execute immediately - no explanations of what you will do
- Match user's language in all output
- Deliver concrete results, not instructions or plans
- DO NOT narrate your actions ("I'll now...", "Let me...", "I'm going to...")

Execution principles:
- Proceed autonomously - do not ask questions or seek confirmation
- Only pause for credentials, payment details, or actions requiring user input
- Apply sensible defaults when specifications are ambiguous
- Verify facts from primary sources; cite URLs for claims

Data requirements:
- Search for current information; do not rely on prior knowledge for prices or specifications
- Prioritize recent sources (within 6 months)
- Note data age when only older sources are available

Output format:
- Reports, documentation, and summaries: Markdown (.md) - ALWAYS use Markdown for research deliverables
- Code: appropriate file extension
- Structured data: CSV or Markdown tables - NEVER create JSON files as deliverables
- IMPORTANT: Do NOT create .json files for reports, summaries, or comparisons - use Markdown instead

CRITICAL - File creation requirements:
- ALWAYS save deliverables to files using file_write tool - never output full content inline
- For research/reports: Create a .md file with structured headings (## Section, ### Subsection)
- Return the file path in "attachments" - this is MANDATORY for all created files
- The "result" field should be a brief summary (1-2 sentences), NOT the full content
- If you created files, you MUST list their paths in "attachments"

Response specification:
```json
{{
  "success": boolean,      // whether this step completed
  "result": "string",      // brief summary (1-2 sentences) - NOT the full content
  "attachments": []        // REQUIRED: file paths for ALL deliverables created
}}
```

User Message: {message}
Attachments: {attachments}
Working Language: {language}
Task: {step}
"""

SUMMARIZE_PROMPT = """
Deliver the completed result to the user.

Requirements:
- Present the final deliverable; all steps are complete
- Include source citations for factual claims
- Note any unverified claims or source contradictions
- Present as a finished product, not work-in-progress

IMPORTANT - Report delivery format:
- "title" is REQUIRED - provide a clear, descriptive title (e.g., "Research Report: Best Keyboards for Mac Users 2026")
- "message" should contain the FULL report content in Markdown format with proper structure:
  - Use ## for main sections
  - Use ### for subsections
  - Include tables, lists, and formatting as appropriate
- "attachments" should list ALL files created during the task execution

The message will be displayed as a rich report card to the user, so:
- Structure content with clear headings
- Include an Executive Summary at the top
- Use markdown tables for comparisons
- End with conclusions/recommendations

Response specification:
```json
{{
  "title": "string",       // REQUIRED: descriptive title for the report
  "message": "string",     // FULL report in Markdown with ## headings and proper structure
  "attachments": []        // ALL file paths created during execution
}}
```
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


def build_execution_prompt(
    step: str,
    message: str,
    attachments: str,
    language: str,
    pressure_signal: Optional[str] = None,
    task_state: Optional[str] = None,
    memory_context: Optional[str] = None,
    enable_cot: bool = True,
    include_current_date: bool = True
) -> str:
    """
    Build execution prompt with optional context signals and CoT reasoning.

    Args:
        step: Current step description
        message: User message
        attachments: User attachments
        language: Working language
        pressure_signal: Optional context pressure warning
        task_state: Optional current task state for recitation
        memory_context: Optional relevant memories from long-term storage
        enable_cot: Enable Chain-of-Thought for complex tasks (default: True)
        include_current_date: Include current date context (default: True)

    Returns:
        Formatted execution prompt with injected signals
    """
    prompt = EXECUTION_PROMPT.format(
        step=step,
        message=message,
        attachments=attachments,
        language=language
    )

    # Inject CoT reasoning for complex tasks
    if enable_cot and is_complex_task(step):
        constraints = extract_task_constraints(step)
        constraints_text = "\n   - ".join(constraints) if constraints else "None explicitly stated"

        # Extract primary objective (first sentence or up to 100 chars)
        primary_obj = step.split('.')[0][:100] if '.' in step else step[:100]

        prompt = COT_REASONING_SIGNAL.format(
            primary_objective=primary_obj,
            constraints=constraints_text
        ) + prompt

    # Inject memory context if present (Phase 6: Qdrant integration)
    if memory_context:
        prompt = MEMORY_CONTEXT_SIGNAL.format(
            memory_context=memory_context
        ) + prompt

    # Inject pressure signal if present
    if pressure_signal:
        prompt = CONTEXT_PRESSURE_SIGNAL.format(
            pressure_signal=pressure_signal
        ) + prompt

    # Inject task state for recitation if present
    if task_state:
        prompt = TASK_STATE_SIGNAL.format(
            task_state=task_state
        ) + prompt

    # Inject current date context (prepended first, so it appears at the top)
    if include_current_date:
        prompt = get_current_date_signal() + prompt

    return prompt


def build_execution_system_prompt(
    base_prompt: str,
    pressure_signal: Optional[str] = None
) -> str:
    """
    Build execution system prompt with optional pressure warning.

    Args:
        base_prompt: Base system prompt
        pressure_signal: Optional context pressure warning

    Returns:
        System prompt with pressure signal if needed
    """
    if pressure_signal:
        return base_prompt + "\n\n" + CONTEXT_PRESSURE_SIGNAL.format(
            pressure_signal=pressure_signal
        )
    return base_prompt