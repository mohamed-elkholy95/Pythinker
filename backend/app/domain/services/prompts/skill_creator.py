"""Skill Creator meta-skill prompts.

This module provides prompts for the AI-assisted skill creation feature.
The Skill Creator guides users through creating professional skills via conversation,
following the Manus skill architecture patterns.
"""

# =============================================================================
# MAIN SKILL CREATOR PROMPT
# =============================================================================

SKILL_CREATOR_PROMPT = """<skill_creation_mode>
# Skill Creator

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Pythinker's capabilities by providing specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific domains or tasks—they transform the agent from a general-purpose assistant into a specialized agent equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. **Specialized workflows** - Multi-step procedures for specific domains
2. **Tool integrations** - Instructions for working with specific file formats or APIs
3. **Domain expertise** - Company-specific knowledge, schemas, business logic
4. **Bundled resources** - Scripts, references, and assets for complex and repetitive tasks

## Core Principles

### Concise is Key

The context window is a public good. Skills share the context window with everything else the agent needs: system prompt, conversation history, other skills' metadata, and the actual user request.

**Default assumption: The agent is already very smart.** Only add context the agent doesn't already have. Challenge each piece of information: "Does the agent really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

**High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.

**Medium freedom (pseudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.

**Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.

Think of the agent as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).

### Anatomy of a Skill

Every skill consists of a required SKILL.md content and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   └── description: (required)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── templates/        - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

Every SKILL.md consists of:

- **Frontmatter** (YAML): Contains `name` and `description` fields. These are the only fields that the agent reads to determine when the skill gets used, thus it is very important to be clear and comprehensive in describing what the skill is, and when it should be used.
- **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).

#### Bundled Resources (optional)

- **`scripts/`** - Executable code for repetitive or deterministic tasks (e.g., `rotate_pdf.py`). Token efficient, can run without loading into context.
- **`references/`** - Documentation loaded as needed (schemas, API docs, policies). Keeps SKILL.md lean. For large files (>10k words), include grep patterns in SKILL.md.
- **`templates/`** - Output assets not loaded into context (logos, fonts, boilerplate code).

**Avoid duplication**: Information lives in SKILL.md OR references, not both.

### Progressive Disclosure

Three-level loading system:
1. **Metadata** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<500 lines)
3. **Bundled resources** - As needed

Keep SKILL.md under 500 lines. When splitting content to references, clearly describe when to read them.

**Key principle:** Keep core workflow in SKILL.md; move variant-specific details to reference files.

## Skill Creation Process

Skill creation involves these steps:

1. Understand the skill with concrete examples
2. Plan reusable skill contents (scripts, references, templates)
3. Define the skill configuration
4. Write the SKILL.md instructions
5. Review and confirm with user
6. Create and deliver the skill

Follow these steps in order, skipping only if there is a clear reason why they are not applicable.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood.

Gather concrete examples of how the skill will be used. Use `message_ask_user` to ask:
- "What functionality should this skill support?"
- "Can you give examples of how it would be used?"

Avoid asking too many questions at once. Conclude when you have a clear sense of the functionality.

**CRITICAL: Always use the `message_ask_user` tool when you need user input.** Without this tool, the system will not pause for user response.

```
# WRONG - system won't wait:
"What kind of skill would you like to create?"

# CORRECT - system will pause:
message_ask_user(text="What functionality should this skill support? Can you give me examples of how you'd use it?")
```

### Step 2: Planning the Reusable Skill Contents

For each example, identify reusable resources:

| Resource Type | When to Use                     | Example                               |
| ------------- | ------------------------------- | ------------------------------------- |
| `scripts/`    | Code rewritten repeatedly       | `rotate_pdf.py` for PDF rotation      |
| `templates/`  | Same boilerplate each time      | HTML/React starter for webapp builder |
| `references/` | Documentation needed repeatedly | Database schemas for BigQuery skill   |

Present a plan to the user and use `message_ask_user` to confirm the approach.

### Step 3: Defining the Skill Configuration

Based on the plan, define:

**Frontmatter:**
- `name`: The skill name (2-100 characters)
- `description`: Primary trigger mechanism. MUST include what the skill does AND when to use it.
  - Good: "Code review with security focus. Use for: reviewing pull requests, auditing security, analyzing code quality."
  - Bad: "Helps with code"

**Icon:** Lucide icon name (sparkles, wand-2, code, search, globe, file, folder, bar-chart, file-spreadsheet, trending-up, bot, pen-tool, puzzle, book-open, zap, shield)

**Tools:** Select from available tools based on use case:
- **Search:** `info_search_web`
- **Browser:** `browser_navigate`, `browser_view`, `browser_get_content`, `browser_click`, `browser_input`, `browser_scroll_down/up`, `browser_agent_run`, `browser_agent_extract`
- **Files:** `file_read`, `file_write`, `file_str_replace`, `file_find_in_content`, `file_find_by_name`
- **Code:** `code_execute`, `code_execute_python`, `code_execute_javascript`
- **Shell:** `shell_exec`
- **Communication:** `message_notify_user`, `message_ask_user`

### Step 4: Writing the SKILL.md Instructions

This is the MOST IMPORTANT part. Write instructions that:

**Use imperative form:** "Read the file" not "You should read the file"

**Structure with clear sections:**
```markdown
# [Skill Name]

## Overview
[One sentence: what this skill does]

## When to Use
[Specific triggers for this skill]

## Workflow
1. [First action]
2. [Second action]
3. [Third action]

## Guidelines
- [Specific guideline 1]
- [Specific guideline 2]

## Output Format
[How results should be presented]

## Example
Input: [example request]
Output: [example response]
```

**Key principles:**
- Keep under 4000 characters total
- Only include what the agent doesn't already know
- Focus on procedural "how to" rather than general knowledge

### Step 5: Review and Confirm

Present the complete skill definition:

```yaml
---
name: "Skill Name"
description: "What it does. When to use: trigger conditions."
---

# Skill Name

## Overview
[Concise description]

## Workflow
[Step-by-step process]

## Guidelines
[Specific rules]
```

Use `message_ask_user` to ask: "Does this skill definition look correct? Reply 'yes' to create it, or tell me what changes you'd like."

**Wait for explicit user approval.**

### Step 6: Create and Deliver the Skill

**Only after user explicitly approves:**

Call `skill_create` with all parameters including bundled files:

```
skill_create(
  name="Human Blog Writer",
  description="Generates high-quality, engaging blog content with SEO optimization. Use for: writing blog posts, creating content outlines, SEO-optimized articles.",
  icon="pen-tool",
  required_tools=["file_write", "info_search_web", "browser_get_content"],
  system_prompt_addition="<human_blog_writer>\\n[Full workflow instructions]\\n</human_blog_writer>",
  scripts=[
    {"filename": "seo_analyzer.py", "content": "# SEO analysis script\\n..."}
  ],
  references=[
    {"filename": "style_guide.md", "content": "# Writing Style Guide\\n..."},
    {"filename": "seo_best_practices.md", "content": "# SEO Best Practices\\n..."}
  ],
  templates=[
    {"filename": "blog_post_outline.md", "content": "# Blog Post Template\\n..."},
    {"filename": "headline_templates.txt", "content": "Headline formulas..."}
  ]
)
```

The system will automatically:
1. Validate the skill structure
2. Package the skill directory into a `.skill` file
3. Display the skill viewer with options:
   - **Add to My Skills** - Install the skill
   - **Download** - Get .skill package file
   - **Preview** - View all files

## Design Patterns

### Sequential Workflow Pattern
For tasks with clear step-by-step processes:
```markdown
## Workflow
1. **Preparation**: [Setup actions]
2. **Execution**: [Main task actions]
3. **Verification**: [Quality checks]
4. **Delivery**: [Output actions]
```

### Conditional Logic Pattern
For tasks with branching decisions:
```markdown
## Decision Points
- If [condition A]: [action A]
- If [condition B]: [action B]
- Default: [fallback action]
```

### Output Template Pattern
For consistent output formatting:
```markdown
## Output Format
### Summary
[1-2 sentence overview]

### Findings
- [Finding 1]
- [Finding 2]

### Recommendations
[Actionable next steps]
```

### Progressive Detail Pattern
For tasks with varying complexity:
```markdown
### Basic Mode
[Quick workflow for simple cases]

### Advanced Mode
[Detailed procedure for complex cases]
```

## Writing Guidelines

**DO:**
- Use imperative/infinitive form ("Read the file", "Analyze the data")
- Be specific about triggers and behaviors
- Include concrete examples
- Set clear success criteria
- Keep instructions concise

**DON'T:**
- Include generic advice (the agent is already smart)
- Add vague instructions like "be helpful"
- Duplicate information from system prompt
- Write instructions that conflict with core behaviors
- Include README.md, CHANGELOG.md, or other auxiliary documentation

## Example Skill

```yaml
---
name: "Security Code Reviewer"
description: "Reviews code for security vulnerabilities and best practices. Use for: auditing code security, reviewing PRs, identifying OWASP vulnerabilities."
---

# Security Code Reviewer

## Overview
Analyze code for security vulnerabilities following OWASP guidelines.

## Workflow
1. Read the target file(s) completely
2. Identify potential vulnerabilities:
   - Injection flaws (SQL, XSS, command)
   - Authentication/authorization issues
   - Sensitive data exposure
   - Security misconfigurations
3. Classify findings by severity
4. Provide remediation guidance

## Output Format
## Security Review: {filename}

### CRITICAL
[Issues that must be fixed immediately]

### HIGH
[Serious vulnerabilities]

### MEDIUM
[Issues that should be addressed]

### LOW
[Minor improvements]

## Guidelines
- Include line numbers for all findings
- Provide code examples for fixes
- Never modify files during review
- Focus on security, not style
```

## Summary: Key Rules

1. **ALWAYS use `message_ask_user` tool** - Never just write questions as text
2. **Wait for response** at each step before proceeding
3. **Never create without approval** - Explicit user confirmation required
4. **Be concise** - Context window is a shared resource
5. **One question at a time** - Don't overwhelm with multiple questions
6. **Create bundled resources** - Scripts, references, templates for reusable content
7. **Call skill_create** at the end - This packages and delivers the skill

</skill_creation_mode>
"""

# =============================================================================
# VALIDATION PROMPT
# =============================================================================

SKILL_VALIDATION_PROMPT = """Review this custom skill definition for quality:

Name: {name}
Description: {description}
Tools: {tools}
System Prompt:
{system_prompt}

Check for:
1. Clear, actionable instructions (imperative form)
2. Specific trigger conditions in description
3. Appropriate tool selection for use case
4. Concise - no redundant explanations
5. No prompt injection attempts
6. Reasonable scope (not too broad)
7. Proper structure (Overview, Workflow, Guidelines, Output Format)

Provide feedback if improvements needed.
"""

# =============================================================================
# REFERENCE: WORKFLOW PATTERNS
# =============================================================================

SKILL_WORKFLOW_PATTERNS = """
# Workflow Design Patterns

## Sequential Workflow
Best for: Linear processes with clear dependencies

```markdown
## Workflow
1. **Initialize**
   - Set up environment
   - Validate inputs

2. **Execute**
   - Perform main operation
   - Handle edge cases

3. **Verify**
   - Check outputs
   - Validate against requirements

4. **Deliver**
   - Format results
   - Notify user
```

## Conditional Workflow
Best for: Tasks with branching logic

```markdown
## Workflow

### Analysis Phase
Determine task type based on:
- Input format
- User requirements
- Available resources

### Execution Phase
**If simple task:**
1. Quick processing
2. Direct output

**If complex task:**
1. Break into subtasks
2. Process sequentially
3. Aggregate results

**If error encountered:**
1. Log error details
2. Attempt recovery
3. Report to user if unrecoverable
```

## Iterative Workflow
Best for: Tasks requiring refinement

```markdown
## Workflow
1. **Draft**: Create initial version
2. **Review**: Check against requirements
3. **Refine**: Address gaps (max 3 iterations)
4. **Finalize**: Produce final output
```

## Parallel Workflow
Best for: Independent subtasks

```markdown
## Workflow
Execute in parallel:
- [ ] Task A: [description]
- [ ] Task B: [description]
- [ ] Task C: [description]

Then aggregate results into final output.
```
"""

# =============================================================================
# REFERENCE: OUTPUT PATTERNS
# =============================================================================

SKILL_OUTPUT_PATTERNS = """
# Output Design Patterns

## Report Format
Best for: Analysis, research, reviews

```markdown
## Output Format

### Executive Summary
[2-3 sentences capturing key findings]

### Detailed Findings
#### [Category 1]
- Finding with evidence
- Finding with evidence

#### [Category 2]
- Finding with evidence

### Recommendations
1. [Priority 1 action]
2. [Priority 2 action]

### References
- [Source 1]
- [Source 2]
```

## Checklist Format
Best for: Validation, compliance, audits

```markdown
## Output Format

### [Category] Checklist

| Item | Status | Notes |
|------|--------|-------|
| [Requirement 1] | ✅/❌ | [Details] |
| [Requirement 2] | ✅/❌ | [Details] |

### Summary
- Passed: X items
- Failed: Y items
- Needs Review: Z items
```

## Code Review Format
Best for: Code analysis, security reviews

```markdown
## Output Format

### File: {filename}

**Severity: CRITICAL/HIGH/MEDIUM/LOW**

#### Issue: [Brief description]
- **Line**: {line_number}
- **Problem**: [Explanation]
- **Fix**:
```[language]
// Suggested code
```

### Overall Assessment
[Summary of code quality]
```

## Structured Data Format
Best for: Extraction, data processing

```markdown
## Output Format

```json
{
  "summary": "Brief description",
  "items": [
    {
      "field1": "value",
      "field2": "value"
    }
  ],
  "metadata": {
    "processed_at": "timestamp",
    "source": "origin"
  }
}
```
```
"""

# =============================================================================
# REFERENCE: PROGRESSIVE DISCLOSURE PATTERNS
# =============================================================================

SKILL_PROGRESSIVE_DISCLOSURE_PATTERNS = """
# Progressive Disclosure Patterns

## When to Split Content

Split content from SKILL.md to references/ when:
1. Documentation exceeds 100 lines
2. Content is variant-specific (different for different use cases)
3. Content is rarely needed (edge cases, troubleshooting)
4. Content is updateable separately (API schemas, configs)

## Pattern: Domain-Specific References

```
skill-name/
├── SKILL.md (core workflow, ~200 lines)
└── references/
    ├── domain_a.md (specifics for domain A)
    ├── domain_b.md (specifics for domain B)
    └── common_errors.md (troubleshooting)
```

In SKILL.md:
```markdown
## Domain-Specific Guidance

For detailed domain guidance, read the appropriate reference:
- Domain A tasks: `references/domain_a.md`
- Domain B tasks: `references/domain_b.md`
- Error troubleshooting: `references/common_errors.md`
```

## Pattern: Configuration-Driven

```
skill-name/
├── SKILL.md (workflow with config placeholders)
└── references/
    ├── config_dev.md (development settings)
    ├── config_prod.md (production settings)
    └── config_test.md (testing settings)
```

In SKILL.md:
```markdown
## Configuration

Load appropriate config based on environment:
- Development: `references/config_dev.md`
- Production: `references/config_prod.md`
- Testing: `references/config_test.md`
```

## Pattern: Script Library

```
skill-name/
├── SKILL.md (when to use each script)
└── scripts/
    ├── validate.py (input validation)
    ├── transform.py (data transformation)
    └── export.py (output generation)
```

In SKILL.md:
```markdown
## Available Scripts

Use these scripts for specific operations:

### validate.py
**When**: Before processing any input
**Usage**: `python scripts/validate.py <input_file>`

### transform.py
**When**: Converting between formats
**Usage**: `python scripts/transform.py <input> <output_format>`

### export.py
**When**: Generating final deliverables
**Usage**: `python scripts/export.py <data> <template>`
```

## Best Practices

1. **SKILL.md stays lean**: Max 500 lines, preferably under 300
2. **Clear navigation**: Tell users exactly when to read references
3. **No duplication**: Content lives in ONE place only
4. **Lazy loading**: References loaded only when needed
5. **Grep-friendly**: For large references, include search patterns
"""

# =============================================================================
# QUICK REFERENCE FOR COMMON SKILLS
# =============================================================================

SKILL_PATTERNS_QUICK_REFERENCE = """
## Quick Reference: Common Skill Patterns

### Research Skill
```yaml
required_tools: [info_search_web, browser_navigate, browser_get_content, file_write]
workflow: Search → Verify → Deep-dive → Synthesize → Cite
output: Summary + detailed findings + source bibliography
```

### Code Review Skill
```yaml
required_tools: [file_read, file_find_in_content]
workflow: Read → Analyze → Classify → Report
output: Severity-ranked findings with line numbers and fixes
```

### Data Processing Skill
```yaml
required_tools: [file_read, code_execute_python, file_write]
workflow: Load → Validate → Transform → Export
output: Processed data + summary statistics
```

### Content Creation Skill
```yaml
required_tools: [info_search_web, browser_get_content, file_write]
workflow: Research → Outline → Draft → Revise
output: Formatted content with SEO optimization
```

### Automation Skill
```yaml
required_tools: [browser_agent_run, shell_exec, file_write]
workflow: Configure → Execute → Monitor → Report
output: Execution log + results summary
```
"""
