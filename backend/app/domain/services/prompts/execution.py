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

# Source Attribution Signal - injected to prevent hallucination
SOURCE_ATTRIBUTION_SIGNAL = """
---
Source Attribution:

- Cite sources inline: "According to [source]..." or use numbered references [1]
- Do not fabricate statistics, metrics, or specific numbers
- Omit information that cannot be verified rather than adding disclaimers
- If data is unavailable, simply don't include it in the report

AVOID in final output:
- [Inferred], [Partial access], or similar inline tags
- Verbose explanations about source limitations
- "Not available" or "Could not verify" statements
- Meta-commentary about the research process

Write clean, professional prose with inline citations or numbered references.
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
Deliver the completed result as a professional research report.

REPORT STRUCTURE (follow this format exactly):

# [Clear, Descriptive Title]

## Introduction
Brief context and scope of the research (2-3 sentences).

## [Main Section 1]
### [Subsection if needed]
Content with **bold** for key terms. Use tables for comparisons:

| Category | Details | Notes |
|----------|---------|-------|
| Item 1   | Value   | Info  |

## [Main Section 2]
Continue with clear, factual content.

## Conclusion
Key takeaways and recommendations.

## References
[1] Source Name - URL

WRITING GUIDELINES:
- Be CONCISE - no filler text, disclaimers, or meta-commentary
- NO revision notes, change logs, or "this report has been updated" sections
- NO "Important Disclaimer" or similar notices
- Focus on FACTS and FINDINGS only
- Use **bold** for key terms, not for entire headings
- Use tables for structured comparisons
- Use bullet points for lists of items
- Include numbered references at the end
- Write in professional, direct tone

FORBIDDEN:
- "This report has been revised..."
- "Changes Made:" sections
- "IMPORTANT DISCLAIMER:"
- Meta-commentary about the report itself
- Work-in-progress language
- Excessive caveats or hedging

Response specification:
```json
{{
  "title": "string",       // Clear title (e.g., "Best Practices for Coding with Claude")
  "message": "string",     // FULL report in clean Markdown - NO meta-commentary
  "attachments": []        // File paths created during execution
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


def is_research_task(step_description: str) -> bool:
    """Determine if a task involves research or content extraction.

    Args:
        step_description: The step description to analyze

    Returns:
        True if the task involves research or web content
    """
    step_lower = step_description.lower()

    research_indicators = [
        "research", "search", "find", "browse", "web", "article",
        "content", "information", "look up", "investigate", "summarize",
        "extract", "analyze", "review", "read", "fetch", "scrape"
    ]

    return any(indicator in step_lower for indicator in research_indicators)


def build_execution_prompt(
    step: str,
    message: str,
    attachments: str,
    language: str,
    pressure_signal: Optional[str] = None,
    task_state: Optional[str] = None,
    memory_context: Optional[str] = None,
    enable_cot: bool = True,
    include_current_date: bool = True,
    enable_source_attribution: bool = True
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
        enable_source_attribution: Enable source attribution signal for research tasks (default: True)

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

    # Inject source attribution signal for research tasks
    if enable_source_attribution and is_research_task(step):
        prompt = SOURCE_ATTRIBUTION_SIGNAL + prompt

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