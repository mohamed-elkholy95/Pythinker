# Execution prompt
from typing import Optional

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


def build_execution_prompt(
    step: str,
    message: str,
    attachments: str,
    language: str,
    pressure_signal: Optional[str] = None,
    task_state: Optional[str] = None
) -> str:
    """
    Build execution prompt with optional context signals.

    Args:
        step: Current step description
        message: User message
        attachments: User attachments
        language: Working language
        pressure_signal: Optional context pressure warning
        task_state: Optional current task state for recitation

    Returns:
        Formatted execution prompt with injected signals
    """
    prompt = EXECUTION_PROMPT.format(
        step=step,
        message=message,
        attachments=attachments,
        language=language
    )

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